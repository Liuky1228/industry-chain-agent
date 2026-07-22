"""AKShare 数据增强模块

在 LLM 提取之后，用 AKShare + 东方财富 F10 API 对产业链数据中的公司
进行结构化数据回填：股票代码、主营业务、行业分类等。

数据源：
1. AKShare stock_info_a_code_name() — A股代码/名称映射表
2. 东方财富 F10 API — 公司详细信息（主营业务、行业、简介）
"""

import logging
import time
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

# ── 全局缓存 ──
_name_code_map: dict[str, str] = {}  # 公司简称 → 股票代码
_code_info_cache: dict[str, dict] = {}  # 股票代码 → 详细信息

# 东方财富 F10 接口
F10_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax"
F10_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0"}


def _ensure_name_code_map():
    """确保名称→代码映射表已加载"""
    global _name_code_map
    if _name_code_map:
        return

    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        # 构建映射：公司简称 → 股票代码
        for _, row in df.iterrows():
            name = str(row.get("name", "")).strip()
            code = str(row.get("code", "")).strip()
            if name and code:
                _name_code_map[name] = code
        logger.info(f"AKShare 名称映射表加载完成: {len(_name_code_map)} 只股票")
    except Exception as e:
        logger.warning(f"AKShare 名称映射表加载失败: {e}")


def _lookup_stock_code(company_name: str) -> Optional[str]:
    """
    根据公司名称查找 A 股股票代码

    支持精确匹配和包含匹配
    """
    if not company_name:
        return None

    _ensure_name_code_map()
    name = company_name.strip()

    # 精确匹配
    if name in _name_code_map:
        return _name_code_map[name]

    # 去掉常见后缀再匹配（如"科技"、"股份"、"集团"等）
    for suffix in ["股份有限公司", "有限公司", "股份公司", "有限责任公司",
                    "集团", "控股", "科技", "股份", "有限"]:
        short = name.replace(suffix, "").strip()
        if short and short in _name_code_map:
            return _name_code_map[short]

    # 包含匹配（名称是映射表中某个名字的一部分）
    for map_name, code in _name_code_map.items():
        if name in map_name or map_name in name:
            return code

    return None


def _fetch_f10_info(stock_code: str) -> Optional[dict]:
    """
    从东方财富 F10 API 获取公司详细信息

    Args:
        stock_code: A股股票代码，如 "300750" 或 "600519"

    Returns:
        {"main_business": "...", "industry": "...", "company_intro": "..."} 或 None
    """
    if not stock_code:
        return None

    if stock_code in _code_info_cache:
        return _code_info_cache[stock_code]

    # 判断市场前缀
    if stock_code.startswith(("6", "9")):
        market_code = f"SH{stock_code}"
    else:
        market_code = f"SZ{stock_code}"

    try:
        resp = httpx.get(
            F10_URL,
            params={"code": market_code},
            headers=F10_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        jbzl = data.get("jbzl", {})
        if not jbzl:
            return None

        info = {
            "main_business": (jbzl.get("jyfw") or "").strip(),
            "industry": (jbzl.get("sshy") or "").strip(),
            "company_intro": (jbzl.get("gsjj") or "").strip(),
            "full_name": (jbzl.get("gsmc") or "").strip(),
        }

        _code_info_cache[stock_code] = info
        return info

    except Exception as e:
        logger.warning(f"F10 查询失败 ({stock_code}): {e}")
        return None


def enrich_chain_data(chain_data: dict, delay: float = 0.5, timeout: float = 120.0) -> dict:
    """
    对产业链数据中的公司进行 AKShare + F10 数据增强

    增强内容：
    1. 股票代码：通过 AKShare 名称映射表查找
    2. 主营业务：通过东方财富 F10 API 获取
    3. 行业分类：通过 F10 API 获取
    4. 公司简介：通过 F10 API 获取（用于报告叙述）

    Args:
        chain_data: merge_and_analyze 返回的产业链数据
        delay: API 请求间隔（秒）
        timeout: 整体超时上限（秒），超时后返回已增强的部分数据

    Returns:
        增强后的 chain_data（原地修改并返回）
    """
    companies = chain_data.get("companies", [])
    if not companies:
        logger.info("无企业数据，跳过 AKShare 增强")
        return chain_data

    logger.info(f"开始 AKShare 数据增强: {len(companies)} 家企业 (超时={timeout}s)")

    enriched_count = 0
    code_filled = 0
    biz_filled = 0
    start_time = time.time()
    timed_out = False

    for i, comp in enumerate(companies):
        # 超时检查
        elapsed = time.time() - start_time
        if elapsed > timeout:
            logger.warning(
                f"AKShare 增强超时 ({timeout}s)，已处理 {i}/{len(companies)} 家企业，"
                f"提前返回已增强数据"
            )
            timed_out = True
            break
        name = comp.get("name", "").strip()
        if not name:
            continue

        original_code = comp.get("stock_code") or ""

        # 统一股票代码格式：去掉 .SZ/.SH 后缀，只保留6位数字
        if original_code:
            normalized = original_code.split(".")[0].strip()
            if normalized and len(normalized) == 6 and normalized.isdigit():
                comp["stock_code"] = normalized
                original_code = normalized

        original_biz = comp.get("main_business") or ""

        # ─ 1. 查找股票代码 ──
        if not original_code:
            code = _lookup_stock_code(name)
            if code:
                comp["stock_code"] = code
                code_filled += 1
                logger.debug(f"  {name} → 股票代码 {code}")

        # ── 2. 获取 F10 详细信息 ──
        current_code = comp.get("stock_code") or ""
        if current_code:
            f10 = _fetch_f10_info(current_code)
            if f10:
                # 填充主营业务（仅在空缺时）
                if not original_biz and f10.get("main_business"):
                    # 取经营范围的前 80 字作为主营业务描述
                    biz_text = f10["main_business"]
                    if len(biz_text) > 80:
                        biz_text = biz_text[:80] + "等"
                    comp["main_business"] = biz_text
                    biz_filled += 1

                # 填充行业分类（新字段）
                if f10.get("industry") and not comp.get("industry"):
                    comp["industry"] = f10["industry"]

                # 填充公司简介（新字段，供叙述生成使用）
                if f10.get("company_intro") and not comp.get("company_intro"):
                    comp["company_intro"] = f10["company_intro"]

                # ── P1: 数据源标签 ──
                # 标记每个字段的数据来源类型，用于报告生成时的数据源合规校验
                comp["_data_tags"] = {
                    "main_business": "industrial",      # 主营业务 → 产业研究类
                    "industry": "industrial",            # 行业分类 → 产业研究类
                    "company_intro": "industrial",       # 公司简介 → 产业研究类
                    "stock_code": "basic_info",          # 股票代码 → 基础信息类
                    "name": "basic_info",                # 公司名称 → 基础信息类
                }

                enriched_count += 1

        # 控制请求频率
        if current_code:
            time.sleep(delay)

    elapsed_total = time.time() - start_time
    timeout_note = " (已超时，部分增强)" if timed_out else ""
    logger.info(
        f"AKShare 增强完成{timeout_note}: {enriched_count}/{len(companies)} 家企业获得补充数据 | "
        f"股票代码填充 +{code_filled} | 主营业务填充 +{biz_filled} | "
        f"耗时 {elapsed_total:.1f}s"
    )

    # 同时增强环节中的公司信息（如果环节 companies 列表中有数据）
    _enrich_segment_companies(chain_data)

    return chain_data


def _enrich_segment_companies(chain_data: dict):
    """
    增强 chain_segments 中各环节的 companies 列表

    将全局 companies 列表中匹配的公司回填到对应环节
    """
    segments = chain_data.get("chain_segments", {})
    companies = chain_data.get("companies", [])

    # 构建公司名 → 公司完整信息的映射
    comp_map = {c.get("name", "").strip(): c for c in companies if c.get("name")}

    for level_key, segs in segments.items():
        for seg in segs:
            seg_company_names = seg.get("companies", [])
            if not seg_company_names:
                continue

            # 检查是否需要回填（如果 companies 列表为空但全局有匹配的公司）
            has_data = any(
                n.strip() in comp_map for n in seg_company_names if isinstance(n, str)
            )
            if not has_data:
                # 尝试从全局公司列表中找匹配的公司名
                matched = []
                for comp in companies:
                    comp_name = comp.get("name", "").strip()
                    comp_seg = comp.get("sub_segment", "").strip()
                    comp_pos_map = {
                        "上游": "upstream", "中游": "midstream",
                        "下游": "downstream", "配套服务": "supporting",
                    }
                    comp_level = comp_pos_map.get(comp.get("chain_position", ""), "")

                    if comp_level == level_key and (
                        comp_seg == seg.get("segment_name", "") or
                        comp_name in seg_company_names
                    ):
                        matched.append(comp_name)

                if matched:
                    seg["companies"] = matched
                    logger.debug(
                        f"  环节 '{seg.get('segment_name')}' 回填 {len(matched)} 家企业"
                    )


# ── 东方财富选股器 API（按行业分类查全部成分股）──
SCREENER_URL = "https://data.eastmoney.com/dataapi/xuangu/list"
SCREENER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0",
    "Referer": "https://data.eastmoney.com/",
}


def _query_stocks_by_industry(industry_name: str, max_pages: int = 2) -> list[dict]:
    """
    通过东方财富选股器 API 查询指定行业分类下的全部股票

    Args:
        industry_name: 行业分类名称（如"航空装备"、"半导体"）
        max_pages: 最大页数（每页100条）

    Returns:
        [{"name": "公司名", "code": "股票代码", "industry": "行业"}, ...]
    """
    all_stocks = []
    for page in range(1, max_pages + 1):
        params = {
            "st": "MARKET_CAP",
            "sr": -1,
            "ps": 100,
            "p": page,
            "sty": "SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,INDUSTRY",
            "filter": f'(INDUSTRY="{industry_name}")',
        }
        try:
            resp = httpx.get(
                SCREENER_URL, params=params, headers=SCREENER_HEADERS,
                timeout=15, follow_redirects=True,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("result", {}).get("data", [])
            if not items:
                break

            for item in items:
                name = item.get("SECURITY_NAME_ABBR", "")
                code = item.get("SECURITY_CODE", "")
                secucode = item.get("SECUCODE", "")
                if name and code:
                    # 从 SECUCODE 提取纯6位代码 (如 "600760.SH" → "600760")
                    pure_code = secucode.split(".")[0] if "." in secucode else code
                    all_stocks.append({
                        "name": name,
                        "code": pure_code,
                        "industry": industry_name,
                    })

            total = data.get("result", {}).get("count", 0)
            logger.info(f"行业 '{industry_name}' 第{page}页: {len(items)}条 (总计{total})")

            if len(all_stocks) >= total:
                break

            time.sleep(1)

        except Exception as e:
            logger.warning(f"选股器查询失败 (行业={industry_name}, 页={page}): {e}")
            break

    return all_stocks


def expand_companies_by_industry(
    chain_data: dict,
    seed_companies: list[str] | None = None,
    delay: float = 0.5,
    timeout: float = 180.0,
) -> dict:
    """
    通过行业分类扩展公司列表

    利用已有公司（或种子公司）的 F10 行业分类信息，
    查询同行业全部 A 股上市公司，将缺失的公司补充到 chain_data 中。

    Args:
        chain_data: 产业链数据
        seed_companies: 种子公司名列表（用于发现行业分类）
        delay: API 请求间隔
        timeout: 整体超时上限（秒）

    Returns:
        补充后的 chain_data
    """
    _ensure_name_code_map()
    start_time = time.time()

    # ── 1. 收集已有公司名 ──
    existing_names = set()
    for comp in chain_data.get("companies", []):
        name = comp.get("name", "").strip()
        if name:
            existing_names.add(name)

    # ── 2. 从已有公司 + 种子公司中发现行业分类 ──
    industries_to_query = set()

    # 从已有公司的 F10 缓存中获取行业分类
    for comp in chain_data.get("companies", []):
        code = comp.get("stock_code", "")
        if code and code in _code_info_cache:
            industry = _code_info_cache[code].get("industry", "")
            if industry:
                industries_to_query.add(industry)

    # 从种子公司中发现行业分类
    if seed_companies:
        for name in seed_companies:
            code = _lookup_stock_code(name)
            if code:
                f10 = _fetch_f10_info(code)
                if f10 and f10.get("industry"):
                    industries_to_query.add(f10["industry"])
                time.sleep(delay)

    # 如果已有公司中没有足够的行业信息，直接从种子公司查
    if not industries_to_query and seed_companies:
        for name in seed_companies[:5]:
            code = _lookup_stock_code(name)
            if code:
                f10 = _fetch_f10_info(code)
                if f10 and f10.get("industry"):
                    industries_to_query.add(f10["industry"])
                time.sleep(delay)

    if not industries_to_query:
        logger.warning("无法发现行业分类，跳过公司扩展")
        return chain_data

    logger.info(f"待查询行业分类: {industries_to_query}")

    # ── 3. 按行业查询全部成分股 ──
    all_new_stocks = []
    seen_codes = set()

    for industry in industries_to_query:
        # 超时检查
        if time.time() - start_time > timeout:
            logger.warning(f"行业扩展超时 ({timeout}s)，已查询行业: {industries_to_query}")
            break
        stocks = _query_stocks_by_industry(industry)
        for stock in stocks:
            if stock["code"] not in seen_codes:
                seen_codes.add(stock["code"])
                # 检查是否已存在于 chain_data
                if stock["name"] not in existing_names:
                    all_new_stocks.append(stock)
        time.sleep(delay)

    if not all_new_stocks:
        logger.info("未发现需要补充的新公司")
        return chain_data

    logger.info(f"发现 {len(all_new_stocks)} 家新公司待补充")

    # ── 4. 将新公司添加到 chain_data ──
    new_companies = []
    for stock in all_new_stocks:
        new_comp = {
            "name": stock["name"],
            "stock_code": stock["code"],
            "main_business": "",  # 后续由 F10 补充
            "products": [],
            "chain_position": "",  # 待 LLM 或规则分配
            "sub_segment": "",
            "market_position": "",
            "key_metrics": "",
            "industry": stock["industry"],
            "_source": "industry_expansion",  # 标记来源
            "_data_tags": {                    # P1: 数据源标签
                "stock_code": "basic_info",
                "industry": "industrial",
                "name": "basic_info",
            },
        }
        new_companies.append(new_comp)

    chain_data.setdefault("companies", []).extend(new_companies)

    # 尝试将新公司分配到产业链环节
    _assign_new_companies_to_segments(chain_data, new_companies)

    logger.info(f"行业扩展完成: 新增 {len(new_companies)} 家企业")
    return chain_data


def _assign_new_companies_to_segments(chain_data: dict, new_companies: list[dict]):
    """
    尝试将新扩展的公司分配到合适的产业链环节

    基于 F10 行业分类与现有环节的匹配关系进行分配
    """
    segments = chain_data.get("chain_segments", {})

    # 构建行业→环节的映射（从已有公司推断）
    industry_to_segment = {}
    for comp in chain_data.get("companies", []):
        if comp.get("_source") == "industry_expansion":
            continue
        industry = comp.get("industry", "")
        level = comp.get("chain_position", "")
        segment = comp.get("sub_segment", "")
        if industry and level and segment:
            level_key_map = {
                "上游": "upstream", "中游": "midstream",
                "下游": "downstream", "配套服务": "supporting",
            }
            level_key = level_key_map.get(level, "")
            if level_key:
                if industry not in industry_to_segment:
                    industry_to_segment[industry] = (level_key, segment)

    # 为新公司分配位置和环节
    for comp in new_companies:
        industry = comp.get("industry", "")
        if industry in industry_to_segment:
            level_key, segment_name = industry_to_segment[industry]
            # 从 chain_position 映射
            level_name_map = {
                "upstream": "上游", "midstream": "中游",
                "downstream": "下游", "supporting": "配套服务",
            }
            comp["chain_position"] = level_name_map.get(level_key, "")
            comp["sub_segment"] = segment_name

            # 添加到对应环节的 companies 列表
            segs = segments.get(level_key, [])
            for seg in segs:
                if seg.get("segment_name") == segment_name:
                    seg.setdefault("companies", [])
                    if comp["name"] not in seg["companies"]:
                        seg["companies"].append(comp["name"])
                    break


def get_data_source_summary(chain_data: dict) -> dict:
    """
    P1: 数据源合规性摘要

    统计 chain_data 中各字段的数据来源标签分布，
    用于报告生成时判断产业研究类数据占比是否达标（≥80%）。

    Returns:
        {
            "total_fields": int,
            "industrial_count": int,
            "basic_info_count": int,
            "financial_count": int,
            "industrial_ratio": float,  # 产业研究类占比
            "compliant": bool,          # 是否达标（≥80%）
        }
    """
    counts = {"industrial": 0, "basic_info": 0, "financial": 0}
    total = 0

    for comp in chain_data.get("companies", []):
        tags = comp.get("_data_tags", {})
        for field, tag in tags.items():
            if comp.get(field):  # 只统计有值的字段
                total += 1
                if tag in counts:
                    counts[tag] += 1

    industrial_ratio = counts["industrial"] / total if total > 0 else 0

    return {
        "total_fields": total,
        "industrial_count": counts["industrial"],
        "basic_info_count": counts["basic_info"],
        "financial_count": counts["financial"],
        "industrial_ratio": round(industrial_ratio, 3),
        "compliant": industrial_ratio >= 0.8,
    }
