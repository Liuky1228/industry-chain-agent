"""巨潮资讯公告爬虫

接口文档：
- 公告搜索：http://www.cninfo.com.cn/new/hisAnnouncement/query (POST)
- PDF 下载：http://static.cninfo.com.cn/{adjunctUrl}
- 注意：巨潮主要提供上市公司公告（年报/季报），不是券商研报
"""

import httpx
import asyncio
import os
import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "http://www.cninfo.com.cn/",
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
}

SEARCH_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
PDF_BASE_URL = "http://static.cninfo.com.cn/"


@dataclass
class CninfoAnnouncement:
    """公告元数据"""
    announcement_id: str
    title: str
    stock_name: Optional[str]
    stock_code: Optional[str]
    publish_time: str
    pdf_url: str
    adjunct_url: str
    announcement_type: str = "announcement"


def to_report_meta(ann: CninfoAnnouncement):
    """将 CninfoAnnouncement 转换为 ReportMeta 兼容格式"""
    from app.crawler.eastmoney import ReportMeta
    return ReportMeta(
        info_code=f"cninfo_{ann.announcement_id}",
        title=ann.title,
        stock_name=ann.stock_name,
        stock_code=ann.stock_code,
        org_name=None,
        publish_date=ann.publish_time,
        researcher=None,
        rating=None,
        pdf_url=ann.pdf_url,
        source="cninfo",
        report_type="announcement",
    )


async def search_announcements(
    keyword: str,
    max_pages: int = 2,
    date_range_days: int = 365,
    delay: float = 5.0,
) -> list[CninfoAnnouncement]:
    """
    搜索巨潮资讯公告

    Args:
        keyword: 搜索关键词
        max_pages: 最大页数
        date_range_days: 时间范围
        delay: 请求间隔（巨潮反爬较严，建议5秒以上）
    """
    end_date = datetime.now().strftime("%Y-%m-%d")
    begin_date = (datetime.now() - timedelta(days=date_range_days)).strftime("%Y-%m-%d")
    date_range = f"{begin_date}~{end_date}"

    results: list[CninfoAnnouncement] = []

    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        for page in range(1, max_pages + 1):
            form_data = {
                "pageNum": page,
                "pageSize": 30,
                "column": "szse",  # szse=深交所, sse=上交所
                "tabName": "fulltext",
                "plate": "",
                "stock": "",
                "searchkey": keyword,
                "secid": "",
                "category": "",
                "trade": "",
                "seDate": date_range,
                "sortName": "",
                "sortType": "",
                "isHLtitle": "true",
            }

            try:
                resp = await client.post(SEARCH_URL, data=form_data)
                resp.raise_for_status()
                data = resp.json()

                announcements = data.get("announcements", [])
                if not announcements:
                    break

                for item in announcements:
                    adj_url = item.get("adjunctUrl", "")
                    if not adj_url:
                        continue

                    ann = CninfoAnnouncement(
                        announcement_id=str(item.get("announcementId", "")),
                        title=item.get("announcementTitle", "").replace("<em>", "").replace("</em>", ""),
                        stock_name=item.get("secName") or None,
                        stock_code=item.get("secCode") or None,
                        publish_time=datetime.fromtimestamp(
                            item.get("announcementTime", 0) / 1000
                        ).strftime("%Y-%m-%d") if item.get("announcementTime") else "",
                        pdf_url=PDF_BASE_URL + adj_url,
                        adjunct_url=adj_url,
                    )
                    results.append(ann)

                logger.info(f"巨潮: 关键词'{keyword}' 第{page}页获取 {len(announcements)} 条")

                if page < max_pages:
                    await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"巨潮搜索失败 (关键词={keyword}, 页={page}): {e}")
                break

    return results


async def download_announcement_pdf(
    ann: CninfoAnnouncement,
    save_dir: str = "data/pdfs",
    delay: float = 3.0,
) -> Optional[str]:
    """下载公告 PDF"""
    os.makedirs(save_dir, exist_ok=True)

    filename = f"cninfo_{ann.announcement_id}.pdf"
    filepath = os.path.join(save_dir, filename)

    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        return filepath

    async with httpx.AsyncClient(headers=HEADERS, timeout=60, follow_redirects=True) as client:
        try:
            resp = await client.get(ann.pdf_url)
            resp.raise_for_status()

            with open(filepath, "wb") as f:
                f.write(resp.content)

            logger.info(f"公告PDF已下载: {filepath}")
            await asyncio.sleep(delay)
            return filepath

        except Exception as e:
            logger.error(f"公告PDF下载失败 ({ann.announcement_id}): {e}")
            if os.path.exists(filepath):
                os.remove(filepath)
            return None


async def crawl_cninfo_for_companies(
    company_names: list[str],
    max_per_company: int = 2,
    date_range_days: int = 365,
    delay: float = 5.0,
    max_total: int = 20,
    progress_callback=None,
) -> list:
    """
    按公司名搜索巨潮资讯公告并下载 PDF

    主要获取年报、半年报等公司披露文件，
    这些文件包含详细的公司业务、财务和战略信息。

    Args:
        company_names: 公司名称列表
        max_per_company: 每家公司最多搜索页数
        date_range_days: 时间范围
        delay: 请求间隔（巨潮反爬较严）
        max_total: 最多下载的公告数
        progress_callback: 进度回调

    Returns:
        ReportMeta 对象列表（source="cninfo"）
    """

    all_announcements: list[CninfoAnnouncement] = []
    seen_ids = set()

    total = len(company_names)
    for i, name in enumerate(company_names):
        if progress_callback:
            pct = int((i / max(total, 1)) * 50)
            await progress_callback(f"巨潮搜索: {name}", pct)

        announcements = await search_announcements(
            keyword=name,
            max_pages=max_per_company,
            date_range_days=date_range_days,
            delay=delay,
        )

        for ann in announcements:
            if ann.announcement_id not in seen_ids:
                seen_ids.add(ann.announcement_id)
                all_announcements.append(ann)

        if len(all_announcements) >= max_total:
            break

    # 截取上限
    all_announcements = all_announcements[:max_total]

    if progress_callback:
        await progress_callback(f"巨潮搜索完成，找到 {len(all_announcements)} 份公告", 50)

    # 下载 PDF
    downloaded = []
    for i, ann in enumerate(all_announcements):
        if progress_callback:
            pct = 50 + int((i / max(len(all_announcements), 1)) * 50)
            await progress_callback(f"下载公告 ({i+1}/{len(all_announcements)}): {ann.title[:30]}...", pct)

        path = await download_announcement_pdf(ann, delay=delay)
        if path:
            meta = to_report_meta(ann)
            meta.local_path = path
            downloaded.append(meta)

    logger.info(f"巨潮爬取完成: {len(downloaded)}/{len(all_announcements)} 份公告下载成功")
    return downloaded
