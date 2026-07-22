"""FastAPI 主入口

产业链分析 Agent 的后端服务。
"""

import json
import logging
import asyncio
import os
import threading
import glob
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.database import init_db, get_db
from app.database_models import Task, Report
from app.config import get_settings
from app.api_models import (
    TaskCreateRequest,
    TaskResponse,
    ReportMetaResponse,
    TaskDetailResponse,
)

# ── 日志配置 ──
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "backend.log")

formatter = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

# 控制台 handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# 文件 handler（追加写入，便于排查历史问题）
file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
file_handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

# 报告输出目录：锚定到项目根目录，避免换目录启动 uvicorn 时相对路径失效（Issue 1）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPORT_DIR = os.path.join(_PROJECT_ROOT, "data", "reports")


# ════════════════════════════════════════════
#  任务取消信号管理
# ════════════════════════════════════════════

# 每个运行中的任务对应一个 threading.Event，set() 表示取消
_cancel_events: dict[str, threading.Event] = {}


class TaskCancelledError(Exception):
    """任务被用户取消时抛出"""
    pass


def _check_cancel(task_id: str):
    """检查任务是否被取消，若取消则抛出 TaskCancelledError"""
    event = _cancel_events.get(task_id)
    if event and event.is_set():
        raise TaskCancelledError(f"任务 {task_id} 已被用户取消")


def _build_report_web_url(info_code: str, report_type: str) -> str:
    """构建东方财富研报网页版链接（pdf_url 不可用时的回退）。

    实测可用：
      - 行业研报：https://data.eastmoney.com/report/zw_industry.jshtml?infocode=<code>
      - 个股研报：https://data.eastmoney.com/report/zw_stock.jshtml?infocode=<code>
    info_code 为空时返回空串（前端据此置灰按钮）。
    """
    if not info_code:
        return ""
    sub = "zw_stock" if report_type == "stock" else "zw_industry"
    return f"https://data.eastmoney.com/report/{sub}.jshtml?infocode={info_code}"


def _register_cancel_event(task_id: str):
    """注册取消信号"""
    _cancel_events[task_id] = threading.Event()


def _unregister_cancel_event(task_id: str):
    """注销取消信号"""
    _cancel_events.pop(task_id, None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    logger.info("正在初始化数据库...")
    init_db()
    settings = get_settings()
    os.makedirs(settings.pdf_dir, exist_ok=True)
    os.makedirs(settings.report_dir, exist_ok=True)
    logger.info("产业链分析 Agent 启动完成")
    yield


app = FastAPI(
    title="产业链分析 Agent",
    description="输入产业名称，自动爬取研报、提取信息、生成产业链报告",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ════════════════════════════════════════════
#  API 路由
# ════════════════════════════════════════════

@app.post("/api/tasks", response_model=TaskResponse)
def create_task(
    req: TaskCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """创建产业链分析任务"""
    task = Task(industry_name=req.industry_name, status="pending", progress=0, progress_message="")
    db.add(task)
    db.commit()
    db.refresh(task)

    # 启动后台任务
    background_tasks.add_task(run_pipeline, task.id, req.industry_name, req.max_reports, req.date_range_days)

    return TaskResponse.model_validate(task)


@app.get("/api/tasks", response_model=list[TaskResponse])
def list_tasks(db: Session = Depends(get_db)):
    """获取所有任务列表"""
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    return [TaskResponse.model_validate(t) for t in tasks]


@app.get("/api/tasks/{task_id}", response_model=TaskDetailResponse)
def get_task(task_id: str, db: Session = Depends(get_db)):
    """获取任务详情"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    reports = db.query(Report).filter(Report.task_id == task_id).all()
    report_list = [
        ReportMetaResponse(
            id=r.id, title=r.title, stock_name=r.stock_name,
            stock_code=r.stock_code, publish_date=r.publish_date,
            source=r.source, report_type=r.report_type, parse_status=r.parse_status,
        )
        for r in reports
    ]

    # 解析结果数据
    viz_data = None
    summary_data = None
    chain_data_raw = None
    if task.result_json:
        try:
            result = json.loads(task.result_json)
            chain_data_raw = result
            from app.analyzer.chain_builder import export_chain_visualization, get_chain_summary
            viz_data = export_chain_visualization(result)
            summary_data = get_chain_summary(result)
        except Exception as e:
            # Bug #4: 之前直接 pass 会让 result_json 损坏的任务返回空数据且无任何留痕
            # 改为记 error log，chain_data_raw 保留为 None 让前端正常渲染"无数据"状态
            logger.error(
                f"任务 {task_id} result_json 解析失败（task status={task.status}）: {e}",
                exc_info=True,
            )

    return TaskDetailResponse(
        task=TaskResponse.model_validate(task),
        reports=report_list,
        visualization=viz_data,
        summary=summary_data,
        chain_data=chain_data_raw,
    )


@app.get("/api/tasks/{task_id}/stream")
async def stream_progress(task_id: str, db: Session = Depends(get_db)):
    """SSE 实时进度推送"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_generator():
        from app.database import SessionLocal
        while True:
            db2 = SessionLocal()
            try:
                t = db2.query(Task).filter(Task.id == task_id).first()
                if not t:
                    break

                yield {
                    "event": "progress",
                    "data": json.dumps({
                        "status": t.status,
                        "progress": t.progress,
                        "message": t.progress_message or "",
                    }, ensure_ascii=False),
                }

                if t.status in ("completed", "failed", "cancelled"):
                    break
            finally:
                db2.close()

            await asyncio.sleep(2)

    return EventSourceResponse(event_generator())


@app.get("/api/tasks/{task_id}/report")
def download_report(task_id: str, db: Session = Depends(get_db)):
    """下载生成的报告文件"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.report_path or not os.path.exists(task.report_path):
        raise HTTPException(status_code=404, detail="报告文件不存在")

    return FileResponse(
        path=task.report_path,
        filename=os.path.basename(task.report_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.get("/api/tasks/{task_id}/html-report")
def download_html_report(task_id: str, db: Session = Depends(get_db)):
    """下载生成的 HTML 报告（与前端 ResultPage 展示 1:1 对齐，自包含可离线打开）"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.result_json:
        raise HTTPException(status_code=404, detail="报告数据不存在")

    try:
        chain_data = json.loads(task.result_json)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"报告数据解析失败: {e}")

    from app.analyzer.chain_builder import export_chain_visualization, get_chain_summary
    from app.generator.html_generator import generate_html_report

    visualization = export_chain_visualization(chain_data)
    summary = get_chain_summary(chain_data)
    filepath = generate_html_report(
        chain_data,
        visualization,
        summary,
        output_dir=_REPORT_DIR,
        task_id=task_id,
    )
    return FileResponse(
        path=filepath,
        filename=os.path.basename(filepath),
        media_type="text/html",
    )


@app.post("/api/tasks/{task_id}/regenerate")
def regenerate_reports(task_id: str, db: Session = Depends(get_db)):
    """从已存储的 result_json 重新生成 HTML + DOCX 报告（不重新分析），并更新 report_path。

    用于章节结构等调整后，把历史任务的报告刷新为新结构。
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.result_json:
        raise HTTPException(status_code=404, detail="报告数据不存在")

    try:
        chain_data = json.loads(task.result_json)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"报告数据解析失败: {e}")

    from app.analyzer.chain_builder import export_chain_visualization, get_chain_summary
    from app.generator.html_generator import generate_html_report
    from app.generator.docx_generator import generate_report

    # 重新生成前清理旧 docx，避免 data/reports 目录文件堆积（Issue 3）
    if task.report_path and os.path.exists(task.report_path):
        try:
            os.remove(task.report_path)
            logger.info(f"已清理旧 docx: {task.report_path}")
        except OSError as e:
            logger.warning(f"清理旧 docx 失败 {task.report_path}: {e}")

    visualization = export_chain_visualization(chain_data)
    summary = get_chain_summary(chain_data)
    html_path = generate_html_report(
        chain_data, visualization, summary, output_dir=_REPORT_DIR, task_id=task_id
    )
    docx_path = generate_report(chain_data, output_dir=_REPORT_DIR)
    task.report_path = docx_path
    db.commit()
    return {
        "html_report": os.path.basename(html_path),
        "docx_report": os.path.basename(docx_path),
        "report_path": task.report_path,
    }


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)):
    """删除任务（同时清理磁盘文件）"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # ── 收集待删文件路径（先记下，再删 DB，最后删文件）──
    pdf_paths: list[str] = []
    report_records = db.query(Report).filter(Report.task_id == task_id).all()
    for r in report_records:
        if r.local_path:
            pdf_paths.append(r.local_path)

    report_path = task.report_path
    # docx 生成时的临时图表目录（_charts_<时间戳>/）
    chart_dirs: list[str] = []
    if report_path:
        report_dir = os.path.dirname(report_path)
        if report_dir:
            # 找该目录下与本次报告时间戳相关的 _charts_ 目录
            ts_marker = ""
            base = os.path.basename(report_path)
            # 报告文件名形如 "产业名_产业链分析报告_YYYYMMDD_HHMMSS.docx"
            if "_" in base:
                tail = base.rsplit("_", 1)[-1]  # "YYYYMMDD_HHMMSS.docx"
                ts_marker = tail.replace(".docx", "").strip()
            if ts_marker:
                for entry in os.listdir(report_dir):
                    if entry.startswith("_charts_") and ts_marker in entry:
                        chart_dirs.append(os.path.join(report_dir, entry))

    # ── 删 DB ──
    db.delete(task)  # 级联删除 reports（cascade="all, delete-orphan"）
    db.commit()

    # ── 删磁盘文件（失败不影响 DB 一致性）──
    for pdf in pdf_paths:
        try:
            if os.path.exists(pdf):
                os.remove(pdf)
                logger.info(f"已删除 PDF: {pdf}")
        except Exception as e:
            logger.warning(f"删除 PDF 失败 {pdf}: {e}")

    if report_path:
        try:
            if os.path.exists(report_path):
                os.remove(report_path)
                logger.info(f"已删除报告: {report_path}")
        except Exception as e:
            logger.warning(f"删除报告失败 {report_path}: {e}")

    # HTML 报告（与 docx 同目录，文件名含 task_id），避免删除任务后残留孤儿文件（Issue 5）
    if report_path:
        html_dir = os.path.dirname(report_path)
        if html_dir and os.path.isdir(html_dir):
            for html_file in glob.glob(os.path.join(html_dir, f"*_{task_id}.html")):
                try:
                    os.remove(html_file)
                    logger.info(f"已删除 HTML 报告: {html_file}")
                except Exception as e:
                    logger.warning(f"删除 HTML 报告失败 {html_file}: {e}")

    for d in chart_dirs:
        try:
            if os.path.isdir(d):
                import shutil
                shutil.rmtree(d)
                logger.info(f"已删除图表目录: {d}")
        except Exception as e:
            logger.warning(f"删除图表目录失败 {d}: {e}")

    return {"message": "已删除"}


@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str, db: Session = Depends(get_db)):
    """终止正在运行的任务"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"任务已处于终态: {task.status}")

    # 发送取消信号
    event = _cancel_events.get(task_id)
    if event:
        event.set()
        logger.info(f"已发送取消信号: 任务 {task_id}")

    # 立即更新状态（pipeline 检测到信号后也会更新，但这里先给前端即时反馈）
    task.status = "cancelled"
    task.error_message = "用户已终止任务"
    db.commit()

    return {"message": "已发送终止信号", "task_id": task_id}


# ════════════════════════════════════════════
#  后台任务管道
# ════════════════════════════════════════════

def run_pipeline(task_id: str, industry_name: str, max_reports: int, date_range_days: int):
    """
    完整的产业链分析后台任务

    流程：爬取研报 → 解析PDF → LLM提取 → 产业链分析 → 生成报告
    """
    from app.database import SessionLocal
    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        db.close()
        return
    db.close()

    # 注册取消信号
    _register_cancel_event(task_id)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except Exception:
        loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(
            _async_pipeline(task_id, industry_name, max_reports, date_range_days)
        )
    except TaskCancelledError:
        # 用户取消 — 状态已在 cancel API 中设为 cancelled，这里做日志
        logger.info(f"任务 {task_id} 已被用户取消")
    except Exception as e:
        logger.error(f"任务 {task_id} 执行失败: {e}", exc_info=True)
        from app.database import SessionLocal
        err_db = SessionLocal()
        try:
            err_task = err_db.query(Task).filter(Task.id == task_id).first()
            if err_task:
                err_task.status = "failed"
                err_task.error_message = str(e)
                err_db.commit()
        finally:
            err_db.close()
    finally:
        _unregister_cancel_event(task_id)


async def _async_pipeline(task_id: str, industry_name: str, max_reports: int, date_range_days: int):
    """异步执行管道"""
    from app.crawler.pipeline import run_crawl_pipeline
    from app.parser.pdf_parser import parse_pdf
    from app.analyzer.extractor import (
        extract_single_report,
        merge_and_analyze,
        filter_relevant_reports,
        extract_events,
    )
    from app.analyzer.chain_builder import build_chain_graph, infer_indirect_relations, export_chain_visualization
    from app.generator.docx_generator import generate_report
    from app.database import SessionLocal
    from app.database_models import Task, Report

    async def update_progress(message: str, progress: int, status: str = ""):
        """异步更新进度，数据库操作在后台线程执行避免阻塞事件循环"""
        def _db_update():
            db2 = SessionLocal()
            try:
                t = db2.query(Task).filter(Task.id == task_id).first()
                if t:
                    t.progress_message = message
                    t.progress = progress
                    if status:
                        t.status = status
                    db2.commit()
            finally:
                db2.close()
        await asyncio.to_thread(_db_update)

    # ── Phase 1: 爬取研报 ──
    await update_progress("开始爬取研报...", 0, "crawling")

    async def crawl_callback(msg, pct):
        _check_cancel(task_id)
        await update_progress(msg, pct)

    crawl_results = await run_crawl_pipeline(
        industry_name=industry_name,
        max_reports=max_reports,
        date_range_days=date_range_days,
        progress_callback=crawl_callback,
    )

    # run_crawl_pipeline 返回 (reports, seed_companies)
    if isinstance(crawl_results, tuple):
        crawl_results, seed_companies = crawl_results
    else:
        seed_companies = []

    if not crawl_results:
        raise RuntimeError("未爬取到任何研报，请检查产业名称或网络连接")

    # 检查取消
    _check_cancel(task_id)

    # 保存研报元数据到数据库
    db = SessionLocal()
    try:
        for r in crawl_results:
            report_record = Report(
                task_id=task_id,
                title=r.title,
                stock_name=r.stock_name,
                stock_code=r.stock_code,
                publish_date=r.publish_date,
                source=r.source,
                report_type=r.report_type,
                pdf_url=r.pdf_url,
                info_code=r.info_code,
                local_path=r.local_path,
            )
            db.add(report_record)
        db.commit()
    finally:
        db.close()

    await update_progress(f"爬取完成，共 {len(crawl_results)} 份研报", 70, "parsing")

    # ── Phase 2: PDF 解析（异步包装避免阻塞事件循环）──
    parsed_reports = []
    for i, report in enumerate(crawl_results):
        _check_cancel(task_id)  # 每份 PDF 解析前检查
        if not report.local_path:
            continue

        pct = 70 + int((i / len(crawl_results)) * 10)
        await update_progress(f"解析研报 ({i+1}/{len(crawl_results)})", pct)

        parsed = await asyncio.to_thread(parse_pdf, report.local_path)
        if parsed.is_valid:
            parsed_reports.append({
                "title": report.title,
                "text": parsed.full_text,
                "tables_count": len(parsed.tables),
                "stock_name": report.stock_name,
                "stock_code": report.stock_code,
            })

    if not parsed_reports:
        raise RuntimeError("所有研报解析失败，无法继续分析")

    await update_progress(f"解析完成，{len(parsed_reports)} 份有效", 78, "analyzing")

    # ── Phase 2.5: 相关性过滤 ──
    _check_cancel(task_id)  # 相关性过滤前检查
    await update_progress("正在过滤不相关研报...", 79)
    parsed_reports = await asyncio.to_thread(
        filter_relevant_reports, industry_name, parsed_reports
    )

    if not parsed_reports:
        raise RuntimeError("所有研报均被过滤（与目标产业不相关），请尝试更具体的产业名称")

    await update_progress(f"相关性过滤完成，保留 {len(parsed_reports)} 份", 80, "analyzing")

    # ── Phase 3: LLM 提取 ──
    from app.analyzer.extractor import extract_single_report, LLMQuotaExceeded

    extracted_results = []
    try:
        for i, report_data in enumerate(parsed_reports):
            _check_cancel(task_id)
            pct = 80 + int((i / len(parsed_reports)) * 10)
            await update_progress(f"LLM提取信息 ({i+1}/{len(parsed_reports)}): {report_data['title'][:25]}...", pct)

            result = await asyncio.to_thread(
                extract_single_report,
                report_data["title"],
                report_data["text"],
                report_data.get("stock_name"),
                report_data.get("stock_code"),
            )
            if result:
                extracted_results.append(result)
    except LLMQuotaExceeded as e:
        # 配额耗尽时，如果还没提取到任何结果，直接失败；否则用已有结果继续
        if not extracted_results:
            logger.error(f"LLM API 配额耗尽，无法继续提取: {e}")
            raise RuntimeError(
                f"LLM API 配额耗尽: {e}。请检查 API 账户余额或配额设置。"
            ) from e
        else:
            logger.warning(f"LLM API 配额耗尽，但已提取 {len(extracted_results)} 份，继续后续流程")

    if not extracted_results:
        raise RuntimeError("LLM 提取失败，未获得任何有效信息")

    await update_progress("正在生成产业元数据...", 89)

    # ── Phase 3.8: 生成产业元数据（P0 新增）──
    _check_cancel(task_id)
    from app.analyzer.industry_metadata import generate_industry_metadata
    industry_metadata = await asyncio.to_thread(generate_industry_metadata, industry_name)

    # ── Phase 3.9: 产业链事件抽取（脉冲式，参考 cwwindex 72H 脉冲）──
    # 从【经过 Phase 2.5 相关性过滤】的研报中抽取近期事实事件；
    # 与 cwwindex 一致：事件为事实证据流，不做利好/利空判断。
    _check_cancel(task_id)
    await update_progress("正在抽取近期产业链事件...", 89)
    event_result = {"events": [], "event_window": {}, "event_policy": {}}
    try:
        event_result = await asyncio.to_thread(
            extract_events, parsed_reports, industry_name, date_range_days
        )
        logger.info(f"产业链事件抽取完成: {len(event_result.get('events', []))} 条")
    except Exception as e:
        logger.warning(f"产业链事件抽取失败（非致命，跳过）: {e}")

    await update_progress("正在进行产业链整合分析...", 90)

    # ── Phase 4: 产业链整合分析（注入元数据约束）──
    _check_cancel(task_id)
    chain_data = await asyncio.to_thread(
        merge_and_analyze, industry_name, extracted_results, seed_companies, industry_metadata
    )
    if not chain_data:
        raise RuntimeError(
            "产业链整合分析失败：LLM 未返回有效的产业链数据。"
            "可能原因：输入研报信息不足、LLM 输出被截断或返回格式异常。"
            "请查看后端日志获取详细信息。"
        )

    # ── 合并 Phase 3.9 抽取的事件数据（脉冲式）──
    if event_result and event_result.get("events") is not None:
        chain_data["events"] = event_result.get("events", [])
        chain_data["event_window"] = event_result.get("event_window", {})
        chain_data["event_policy"] = event_result.get("event_policy", {})
        logger.info(
            f"已将 {len(chain_data.get('events', []))} 条产业链事件写入结果"
        )

    # ── Phase 4.5: AKShare 数据增强（带超时保护）──
    _check_cancel(task_id)
    await update_progress("正在补充企业结构化数据（AKShare）...", 92)
    try:
        from app.crawler.akshare_enricher import enrich_chain_data, expand_companies_by_industry
        chain_data = await asyncio.wait_for(
            asyncio.to_thread(enrich_chain_data, chain_data),
            timeout=150,
        )

        # ── Phase 4.6: 行业分类扩展（补充同行业其他上市公司，带超时保护）──
        await update_progress("正在通过行业分类扩展企业列表...", 93)
        chain_data = await asyncio.wait_for(
            asyncio.to_thread(expand_companies_by_industry, chain_data, seed_companies),
            timeout=200,
        )
    except asyncio.TimeoutError:
        logger.warning("AKShare 数据增强超时（150s/200s），跳过剩余增强步骤，继续后续流程")
    except Exception as e:
        logger.warning(f"AKShare 数据增强失败（非致命错误）: {e}")

    # 构建图谱（容错处理）
    try:
        graph = build_chain_graph(chain_data)
        indirect = infer_indirect_relations(graph)
    except Exception as e:
        logger.warning(f"图谱构建失败（非致命错误）: {e}")
        graph = None
        indirect = []

    # 保存结果 JSON
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.result_json = json.dumps(chain_data, ensure_ascii=False)
            db.commit()
        else:
            logger.warning(f"保存结果时任务 {task_id} 不存在（可能已被删除）")
    finally:
        db.close()

    await update_progress("正在生成报告文档...", 95, "generating")

    # 将参考研报信息附加到 chain_data，供 Word 报告附录使用
    # 注意：必须只保留【经过 Phase 2.5 相关性过滤】的研报，
    # 否则附录会混入大量与目标产业无关的爬取结果（问题 2 根因之一）。
    # parsed_reports 是经过 filter_relevant_reports 过滤后的子集（dict 列表），
    # 其 title 与 crawl_results（ReportMeta 对象）的 title 完全一致。
    _filtered_titles = {r["title"] for r in parsed_reports}
    chain_data["_reference_reports"] = [
        {
            "title": r.title,
            "stock_name": r.stock_name,
            "stock_code": r.stock_code,
            "org_name": r.org_name,
            "publish_date": r.publish_date,
            "source": r.source,
            "report_type": r.report_type,
            "info_code": r.info_code,
            # 原始研报 PDF（首选跳转，浏览器可直接打开）
            "pdf_url": r.pdf_url,
            # 研报网页版（pdf_url 不可用时回退，确保用户总能看到研报）
            "report_url": _build_report_web_url(r.info_code, r.report_type),
        }
        for r in crawl_results
        if r.title in _filtered_titles
    ]
    logger.info(
        f"参考研报附录：原始爬取 {len(crawl_results)} 份，相关性过滤后保留 {len(chain_data['_reference_reports'])} 份"
    )

    # ── Phase 4.8: 输出校验（P2 新增）──
    _check_cancel(task_id)
    try:
        from app.analyzer.validator import validate_report
        validation_result = validate_report(chain_data, industry_metadata)
        chain_data["_validation"] = validation_result
        if not validation_result["passed"]:
            logger.warning(f"报告校验未通过: {validation_result['errors']}")
        # 保存校验结果到数据库（使用新 session）
        val_db = SessionLocal()
        try:
            task_obj = val_db.query(Task).filter(Task.id == task_id).first()
            if task_obj:
                task_obj.result_json = json.dumps(chain_data, ensure_ascii=False)
                val_db.commit()
        finally:
            val_db.close()
    except Exception as e:
        logger.warning(f"输出校验失败（不影响报告生成）: {e}")

    # ── Phase 4.9: LLM 叙述生成（一步到位生成完整7章，含深度趋势推演）──
    _check_cancel(task_id)
    await update_progress("正在生成AI分析叙述...", 96)
    try:
        from app.generator.narrative_generator import (
            generate_narratives_with_retry,
            generate_trend_deduction_with_retry,
            generate_risk_analysis_with_retry,
        )

        # Step 1: 生成7章叙述（retry × 3，必须成功）
        narratives = await asyncio.wait_for(
            asyncio.to_thread(generate_narratives_with_retry, chain_data),
            timeout=300,  # 5 分钟超时
        )

        # 先把已生成的叙述写入 chain_data，供后续趋势推演回扣前文（节点分析章节）
        chain_data["_narratives"] = narratives

        # Step 2: 立即生成独立深度版趋势推演，覆盖合并版中的简易版
        trend_text = await asyncio.wait_for(
            asyncio.to_thread(generate_trend_deduction_with_retry, chain_data),
            timeout=180,  # 3 分钟超时
        )
        if trend_text and len(trend_text) >= 200:
            narratives["trend_deduction"] = trend_text
            logger.info("深度趋势推演已覆盖合并版中的简易版")

        # Step 3: 生成风险与不确定性专题分析，写入 narratives
        try:
            risk_text = await asyncio.wait_for(
                asyncio.to_thread(generate_risk_analysis_with_retry, chain_data),
                timeout=180,
            )
            if risk_text and len(risk_text) >= 100:
                narratives["risk_analysis"] = risk_text
                logger.info("风险与不确定性分析已生成")
        except Exception as e:
            logger.warning(f"风险分析生成失败（不影响报告）: {e}")

        narr_db = SessionLocal()
        try:
            task_obj = narr_db.query(Task).filter(Task.id == task_id).first()
            if task_obj:
                task_obj.result_json = json.dumps(chain_data, ensure_ascii=False)
                narr_db.commit()
        finally:
            narr_db.close()

        await update_progress(f"AI分析叙述已生成 (共{sum(len(v) for v in narratives.values())}字)", 97)
    except asyncio.TimeoutError:
        logger.error("叙述生成超时（5分钟），跳过叙述生成，继续后续流程")
    except Exception as e:
        logger.error(f"叙述生成失败（不影响报告生成）: {e}", exc_info=True)

    # ── Phase 5: 生成 Word 报告 ──
    _check_cancel(task_id)
    report_path = await asyncio.to_thread(generate_report, chain_data)

    # 完成
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = "completed"
            task.progress = 100
            task.progress_message = "分析完成"
            task.report_path = report_path
            db.commit()
        else:
            logger.warning(f"任务 {task_id} 在完成收尾时不存在（可能已被删除）")
    finally:
        db.close()

    logger.info(f"任务 {task_id} 完成: 报告路径={report_path}")


# ════════════════════════════════════════════
#  叙述生成
# ════════════════════════════════════════════

@app.post("/api/tasks/{task_id}/narratives")
async def generate_narratives_endpoint(task_id: str, db: Session = Depends(get_db)):
    """基于产业链数据生成 LLM 分析性叙述"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.result_json:
        raise HTTPException(status_code=400, detail="任务尚未完成分析")

    try:
        chain_data = json.loads(task.result_json)
    except Exception:
        raise HTTPException(status_code=500, detail="结果数据解析失败")

    from app.generator.narrative_generator import generate_narratives
    narratives = await asyncio.to_thread(generate_narratives, chain_data)

    # 将叙述保存到任务（供后续复用，避免重复调用 LLM）
    existing_narratives = {}
    if task.result_json:
        try:
            rd = json.loads(task.result_json)
            existing_narratives = rd.get("_narratives", {})
        except Exception:
            pass
    existing_narratives.update(narratives)

    # 保存叙述到 result_json 的 _narratives 字段
    chain_data["_narratives"] = existing_narratives
    task.result_json = json.dumps(chain_data, ensure_ascii=False)
    db.commit()

    return {"narratives": narratives}


@app.get("/api/tasks/{task_id}/narratives")
async def get_narratives(task_id: str, db: Session = Depends(get_db)):
    """获取已生成的叙述（如果有缓存则直接返回）"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task or not task.result_json:
        return {"narratives": None}

    try:
        chain_data = json.loads(task.result_json)
        narratives = chain_data.get("_narratives")
        return {"narratives": narratives}
    except Exception:
        return {"narratives": None}


# ════════════════════════════════════════════
#  P2: 趋势推演 & 输出校验
# ════════════════════════════════════════════

@app.post("/api/tasks/{task_id}/trend")
async def generate_trend_endpoint(task_id: str, db: Session = Depends(get_db)):
    """P2: 独立的趋势推演生成（基于传导逻辑的深度推演）"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.result_json:
        raise HTTPException(status_code=400, detail="任务尚未完成分析")

    try:
        chain_data = json.loads(task.result_json)
    except Exception:
        raise HTTPException(status_code=500, detail="结果数据解析失败")

    from app.generator.narrative_generator import generate_trend_deduction
    trend_text = await asyncio.to_thread(generate_trend_deduction, chain_data)

    # 保存到 _narratives 中的 trend_deduction 字段
    if trend_text:
        existing_narratives = {}
        try:
            existing_narratives = chain_data.get("_narratives", {})
        except Exception:
            pass
        existing_narratives["trend_deduction"] = trend_text
        chain_data["_narratives"] = existing_narratives
        task.result_json = json.dumps(chain_data, ensure_ascii=False)
        db.commit()

    return {"trend_deduction": trend_text}


@app.get("/api/tasks/{task_id}/validation")
async def get_validation(task_id: str, db: Session = Depends(get_db)):
    """P2: 获取报告校验结果"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task or not task.result_json:
        return {"validation": None}

    try:
        chain_data = json.loads(task.result_json)
        validation = chain_data.get("_validation")
        return {"validation": validation}
    except Exception:
        return {"validation": None}


# ════════════════════════════════════════════
#  健康检查
# ════════════════════════════════════════════

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "产业链分析 Agent"}
