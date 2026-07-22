"""东方财富研报爬虫

接口文档：
- 研报列表：https://reportapi.eastmoney.com/report/list (GET, JSON)
- PDF 下载：https://pdf.dfcfw.com/pdf/H3_{infoCode}_1.pdf
- qType: 0=个股研报, 1=行业研报, 2=策略研报
"""

import httpx
import asyncio
import os
import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

from app.llm_common import LLMQuotaExceeded
from app.crawler.keyword_expander import pick_industry_code

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}

BASE_URL = "https://reportapi.eastmoney.com/report/list"
PDF_URL_TEMPLATE = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"


@dataclass
class ReportMeta:
    """研报元数据"""
    info_code: str
    title: str
    stock_name: Optional[str]
    stock_code: Optional[str]
    org_name: Optional[str]
    publish_date: str
    researcher: Optional[str]
    rating: Optional[str]
    pdf_url: str
    industry_code: Optional[str] = None
    industry_name: Optional[str] = None
    source: str = "eastmoney"
    report_type: str = "stock"  # industry / stock
    local_path: Optional[str] = None


def _build_params(
    q_type: int,
    page_no: int = 1,
    page_size: int = 50,
    begin_time: str = "",
    end_time: str = "",
    keyword: str = "",
    industry_code: str = "*",
) -> dict:
    """构建请求参数"""
    params = {
        "industryCode": industry_code,
        "pageSize": page_size,
        "industry": "*",
        "rating": "*",
        "ratingChange": "*",
        "beginTime": begin_time,
        "endTime": end_time,
        "pageNo": page_no,
        "fields": "",
        "qType": q_type,
        "orgCode": "",
        "rcode": "",
        "p": page_no,
        "pageCount": 1,
    }
    if keyword:
        params["keyword"] = keyword
    return params


def _parse_report_item(item: dict, report_type: str = "stock") -> Optional[ReportMeta]:
    """解析单条研报数据"""
    info_code = item.get("infoCode", "")
    if not info_code:
        return None

    return ReportMeta(
        info_code=info_code,
        title=item.get("title", "").strip(),
        stock_name=item.get("stockName") or None,
        stock_code=item.get("stockCode") or None,
        org_name=item.get("orgSName") or None,
        publish_date=item.get("publishDate", "")[:10],
        researcher=item.get("researcher") or None,
        rating=item.get("emRatingName") or None,
        industry_code=item.get("industryCode") or None,
        industry_name=item.get("industryName") or None,
        pdf_url=PDF_URL_TEMPLATE.format(info_code=info_code),
        report_type=report_type,
    )


async def search_reports(
    keyword: str,
    q_type: int = 1,
    max_pages: int = 2,
    date_range_days: int = 180,
    delay: float = 3.0,
    industry_code: str = "*",
) -> list[ReportMeta]:
    """
    搜索研报

    Args:
        keyword: 搜索关键词
        q_type: 研报类型 0=个股 1=行业 2=策略
        max_pages: 最大爬取页数
        date_range_days: 时间范围（天）
        delay: 请求间隔秒数

    Returns:
        研报元数据列表
    """
    end_time = datetime.now().strftime("%Y-%m-%d")
    begin_time = (datetime.now() - timedelta(days=date_range_days)).strftime("%Y-%m-%d")

    all_reports: list[ReportMeta] = []
    report_type = "industry" if q_type == 1 else "stock"

    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        for page in range(1, max_pages + 1):
            params = _build_params(
                q_type=q_type,
                page_no=page,
                begin_time=begin_time,
                end_time=end_time,
                keyword=keyword,
                industry_code=industry_code,
            )

            try:
                resp = await client.get(BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

                items = data.get("data", [])
                if not items:
                    logger.info(f"东方财富: 关键词'{keyword}'第{page}页无结果")
                    break

                for item in items:
                    report = _parse_report_item(item, report_type)
                    if report:
                        all_reports.append(report)

                logger.info(
                    f"东方财富: 关键词'{keyword}' 第{page}页获取 {len(items)} 条"
                )

                if page < max_pages:
                    await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"东方财富搜索失败 (关键词={keyword}, 页={page}): {e}")
                break

    # 去重
    seen = set()
    unique_reports = []
    for r in all_reports:
        if r.info_code not in seen:
            seen.add(r.info_code)
            unique_reports.append(r)

    return unique_reports


async def search_industry_reports(
    industry_name: str,
    max_pages: int = 2,
    date_range_days: int = 180,
    delay: float = 3.0,
    industry_code: str = "*",
) -> list[ReportMeta]:
    """搜索行业研报"""
    return await search_reports(
        keyword=industry_name,
        q_type=1,
        max_pages=max_pages,
        date_range_days=date_range_days,
        delay=delay,
        industry_code=industry_code,
    )


async def search_stock_reports(
    stock_name: str,
    max_pages: int = 1,
    date_range_days: int = 180,
    delay: float = 3.0,
    industry_code: str = "*",
) -> list[ReportMeta]:
    """搜索个股研报"""
    return await search_reports(
        keyword=stock_name,
        q_type=0,
        max_pages=max_pages,
        date_range_days=date_range_days,
        delay=delay,
        industry_code=industry_code,
    )


async def download_pdf(
    report: ReportMeta,
    save_dir: str = "data/pdfs",
    delay: float = 2.0,
) -> Optional[str]:
    """
    下载研报 PDF（自动破解东方财富 JS Cookie 反爬挑战）

    东方财富 PDF 服务器首次请求返回一段 JS 脚本，计算出 __tst_status 和
    EO_Bot_Ssid 两个 cookie 值，设置后才能拿到真正的 PDF。

    Returns:
        本地文件路径，下载失败返回 None
    """
    import re

    os.makedirs(save_dir, exist_ok=True)

    # 文件名：infoCode.pdf
    filename = f"{report.info_code}.pdf"
    filepath = os.path.join(save_dir, filename)

    # 已存在且大小合理则跳过（真实 PDF 一般 > 10KB）
    if os.path.exists(filepath) and os.path.getsize(filepath) > 10240:
        logger.info(f"PDF已存在: {filepath}")
        return filepath

    headers = {**HEADERS, "Referer": "https://data.eastmoney.com/"}

    async with httpx.AsyncClient(
        headers=headers, timeout=60, follow_redirects=True
    ) as client:
        try:
            # ── 第一次请求：获取 JS 挑战或直接拿到 PDF ──
            resp = await client.get(report.pdf_url)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")

            # 如果直接返回了 PDF，直接保存
            if "pdf" in content_type or "octet-stream" in content_type:
                if len(resp.content) > 10240:
                    with open(filepath, "wb") as f:
                        f.write(resp.content)
                    logger.info(f"PDF已下载: {filepath} ({len(resp.content)} bytes)")
                    await asyncio.sleep(delay)
                    return filepath

            # ── 收到 JS 挑战，解析 cookie ──
            script = resp.text
            if "<script>" in script or "document.cookie" in script:
                logger.info(f"遇到JS反爬挑战 ({report.info_code})，正在求解...")
                cookies = _solve_js_challenge(script)

                if cookies:
                    # 带 cookie 重新请求
                    await asyncio.sleep(1)
                    resp2 = await client.get(report.pdf_url, cookies=cookies)
                    resp2.raise_for_status()

                    ct2 = resp2.headers.get("content-type", "")
                    if ("pdf" in ct2 or "octet-stream" in ct2) and len(resp2.content) > 10240:
                        with open(filepath, "wb") as f:
                            f.write(resp2.content)
                        logger.info(f"PDF已下载(挑战破解): {filepath} ({len(resp2.content)} bytes)")
                        await asyncio.sleep(delay)
                        return filepath
                    else:
                        logger.warning(f"Cookie求解后仍非PDF ({report.info_code}): {ct2}, {len(resp2.content)} bytes")
                else:
                    logger.warning(f"JS挑战解析失败 ({report.info_code})")
            else:
                logger.warning(f"非PDF响应 ({report.info_code}): {content_type}")

            return None

        except Exception as e:
            logger.error(f"PDF下载失败 ({report.info_code}): {e}")
            if os.path.exists(filepath):
                os.remove(filepath)
            return None


def _solve_js_challenge(script: str) -> Optional[dict]:
    """
    从东方财富的 JS 反爬脚本中提取 cookie 值

    JS 结构：
    - __tst_status = WTKkN + bOYDu + wyeCN（三个大整数之和），后缀 "#"
    - EO_Bot_Ssid = iTyzs 函数中的参数值
    """
    import re

    try:
        # 提取 __tst_status 的三个分量
        wtk = re.search(r'WTKkN[:\s]*(\d+)', script)
        boy = re.search(r'bOYDu[:\s]*(\d+)', script)
        wye = re.search(r'wyeCN[:\s]*(\d+)', script)

        if not all([wtk, boy, wye]):
            logger.warning("JS挑战: 无法提取 __tst_status 分量")
            return None

        tst_status = int(wtk.group(1)) + int(boy.group(1)) + int(wye.group(1))

        # 提取 EO_Bot_Ssid 值（iTyzs function 的参数）
        prefix_matches = re.findall(r',(\d{5,})\)', script)
        ssid_value = prefix_matches[-1] if prefix_matches else None

        cookies = {"__tst_status": f"{tst_status}#"}
        if ssid_value:
            cookies["EO_Bot_Ssid"] = ssid_value

        logger.info(f"JS挑战求解成功: cookies={cookies}")
        return cookies

    except Exception as e:
        logger.error(f"JS挑战解析异常: {e}")
        return None


async def crawl_industry(
    industry_name: str,
    keywords: list[str] | None = None,
    company_names: list[str] | None = None,
    max_industry_pages: int = 2,
    max_stock_pages: int = 1,
    max_total: int = 30,
    date_range_days: int = 180,
    delay: float = 3.0,
    progress_callback=None,
) -> list[ReportMeta]:
    """
    完整的产业链研报爬取流程

    Args:
        industry_name: 产业名称
        keywords: 扩展关键词列表（None则只用产业名）
        company_names: 代表性公司名列表（用于搜索高相关性个股研报）
        max_industry_pages: 行业研报最大页数
        max_stock_pages: 个股研报最大页数
        max_total: 最大研报总数
        date_range_days: 时间范围
        delay: 请求间隔
        progress_callback: 进度回调 async fn(message, progress_pct)

    Returns:
        所有爬取到的研报元数据
    """
    search_keywords = [industry_name]
    if keywords:
        search_keywords.extend(keywords)

    # ── 办法C：两阶段探测 industryCode（精确过滤）──
    # 先用关键词探一轮，收集返回结果的(industryCode, industryName)，
    # 让 LLM 挑出对应目标产业的行业代码；任何失败均回退 "*"（原行为）。
    industry_code = "*"
    if progress_callback:
        await progress_callback(f"探测'{industry_name}'的行业代码...", 2)
    try:
        probe = await search_reports(
            keyword=industry_name, industry_code="*", q_type=1,
            max_pages=1, date_range_days=date_range_days, delay=0,
        )
        code_map: dict[str, str] = {}
        for r in probe:
            if r.industry_code:
                code_map[r.industry_code] = r.industry_name or ""
        if len(code_map) > 1:
            chosen = await asyncio.to_thread(pick_industry_code, industry_name, code_map)
            if chosen and chosen in code_map:
                industry_code = chosen
                logger.info(
                    f"办法C: industryCode 探测成功 '{industry_name}' "
                    f"-> {industry_code} ({code_map[industry_code]})"
                )
            else:
                logger.info(f"办法C: industryCode 无匹配，回退 '*'（产业='{industry_name}'）")
        else:
            logger.info(f"办法C: 探测结果行业单一或无结果，回退 '*'（产业='{industry_name}'）")
    except LLMQuotaExceeded as e:
        logger.warning(f"办法C: LLM 配额耗尽，跳过精确过滤回退 '*': {e}")
    except Exception as e:
        logger.warning(f"办法C: industryCode 探测异常，回退 '*': {e}")

    all_reports: list[ReportMeta] = []

    # ── Phase 1: 关键词搜索 (进度 0-25%) ──
    total_keywords = len(search_keywords)

    for i, kw in enumerate(search_keywords):
        if progress_callback:
            pct = int((i / max(total_keywords, 1)) * 25)
            await progress_callback(f"搜索关键词: {kw}", pct)

        # 搜索行业研报（办法C：传入探测到的精确 industryCode）
        industry_reports = await search_industry_reports(
            kw, industry_code=industry_code, max_pages=max_industry_pages,
            date_range_days=date_range_days, delay=delay,
        )
        all_reports.extend(industry_reports)

        # 搜索个股研报
        stock_reports = await search_stock_reports(
            kw, max_pages=max_stock_pages,
            date_range_days=date_range_days, delay=delay,
        )
        all_reports.extend(stock_reports)

        if len(all_reports) >= max_total:
            break

    # ── Phase 2: 公司名搜索个股研报 (进度 25-40%) ──
    if company_names:
        total_companies = len(company_names)
        for i, company in enumerate(company_names):
            if len(all_reports) >= max_total:
                break

            if progress_callback:
                pct = 25 + int(((i + 1) / total_companies) * 15)
                await progress_callback(f"搜索公司研报: {company}", pct)

            stock_reports = await search_stock_reports(
                company, max_pages=max_stock_pages,
                date_range_days=date_range_days, delay=delay,
            )
            all_reports.extend(stock_reports)

    # ── 办法C 安全过滤：精确查询后再确保行业研报属于目标行业 ──
    if industry_code != "*":
        safe = []
        for r in all_reports:
            if r.report_type == "stock" or r.industry_code == industry_code:
                safe.append(r)
            else:
                logger.info(f"办法C 安全过滤丢弃: '{r.title[:40]}' (行业={r.industry_name})")
        all_reports = safe

    # 去重
    seen = set()
    unique = []
    for r in all_reports:
        if r.info_code not in seen:
            seen.add(r.info_code)
            unique.append(r)

    # 截取上限
    unique = unique[:max_total]

    if progress_callback:
        await progress_callback(f"搜索完成，共找到 {len(unique)} 份研报", 40)

    # ── Phase 3: 下载 PDF (进度 40-100%) ──
    downloaded = []
    for i, report in enumerate(unique):
        if progress_callback:
            pct = 40 + int((i / max(len(unique), 1)) * 60)
            await progress_callback(
                f"下载研报 ({i+1}/{len(unique)}): {report.title[:30]}...", pct
            )

        path = await download_pdf(report, delay=delay)
        if path:
            report.local_path = path
            downloaded.append(report)

    if progress_callback:
        await progress_callback(f"下载完成，成功 {len(downloaded)}/{len(unique)} 份", 100)

    return downloaded
