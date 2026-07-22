"""爬虫编排管道

整合关键词扩展 → 公司名扩展 → 东方财富研报搜索 → 巨潮资讯公告搜索 → PDF下载 的完整流程
"""

import logging
from app.crawler.eastmoney import crawl_industry, ReportMeta
from app.crawler.keyword_expander import expand_keywords, expand_companies
from app.config import get_settings

logger = logging.getLogger(__name__)


async def run_crawl_pipeline(
    industry_name: str,
    max_reports: int | None = None,
    date_range_days: int | None = None,
    progress_callback=None,
) -> tuple[list[ReportMeta], list[str]]:
    """
    执行完整的研报爬取管道（多数据源）

    数据源：
    1. 东方财富 — 行业研报 + 个股研报
    2. 巨潮资讯 — 上市公司公告（年报/半年报等）

    Args:
        industry_name: 产业名称
        max_reports: 最大研报数（默认从配置读取）
        date_range_days: 时间范围天数（默认从配置读取）
        progress_callback: async fn(message, progress_pct)

    Returns:
        (下载成功的研报列表, 种子公司名列表)
    """
    settings = get_settings()
    max_reports = max_reports or settings.max_reports_per_task
    date_range_days = date_range_days or settings.report_date_range_days
    delay = settings.crawl_delay_seconds

    # Step 1: 关键词扩展
    if progress_callback:
        await progress_callback("正在扩展产业关键词...", 5)

    keywords = expand_keywords(industry_name)
    logger.info(f"扩展关键词: {keywords}")

    if progress_callback:
        await progress_callback(
            f"关键词扩展完成: {', '.join(keywords[:8])}{'...' if len(keywords) > 8 else ''}", 8
        )

    # Step 2: 公司名扩展（用于搜索高相关性个股研报）
    if progress_callback:
        await progress_callback("正在获取代表性上市公司...", 9)

    companies = expand_companies(industry_name)
    logger.info(f"扩展公司: {companies}")

    if progress_callback:
        await progress_callback(
            f"公司扩展完成: {', '.join(companies[:6])}{'...' if len(companies) > 6 else ''}", 10
        )

    # Step 3: 东方财富研报爬取 (进度 10-75%)
    async def scaled_progress(msg, pct):
        if progress_callback:
            scaled_pct = 10 + int(pct * 0.65)
            await progress_callback(msg, scaled_pct)

    reports = await crawl_industry(
        industry_name=industry_name,
        keywords=keywords,
        company_names=companies,
        max_industry_pages=4,
        max_stock_pages=2,
        max_total=max_reports,
        date_range_days=date_range_days,
        delay=delay,
        progress_callback=scaled_progress,
    )

    logger.info(f"东方财富爬取完成: 共 {len(reports)} 份研报")

    # Step 4: 巨潮资讯公告爬取 (进度 75-100%)
    cninfo_reports = []
    try:
        from app.crawler.cninfo import crawl_cninfo_for_companies

        # 用种子公司名搜索巨潮资讯（取前8家，控制爬取量）
        cninfo_companies = companies[:8] if companies else [industry_name]
        cninfo_max = min(20, max(max_reports - len(reports), 5))

        async def cninfo_progress(msg, pct):
            if progress_callback:
                scaled_pct = 75 + int(pct * 0.25)
                await progress_callback(msg, scaled_pct)

        cninfo_reports = await crawl_cninfo_for_companies(
            company_names=cninfo_companies,
            max_per_company=1,
            date_range_days=date_range_days,
            delay=max(delay, 5.0),  # 巨潮反爬较严，至少5秒
            max_total=cninfo_max,
            progress_callback=cninfo_progress,
        )
        logger.info(f"巨潮资讯爬取完成: 共 {len(cninfo_reports)} 份公告")
    except Exception as e:
        logger.warning(f"巨潮资讯爬取失败（非致命错误）: {e}")

    # 合并两个数据源的结果
    all_reports = reports + cninfo_reports

    if progress_callback:
        await progress_callback(
            f"多源爬取完成: 东方财富 {len(reports)} 份 + 巨潮 {len(cninfo_reports)} 份 = {len(all_reports)} 份",
            100,
        )

    return all_reports, companies
