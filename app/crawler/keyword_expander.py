"""基于 LLM 的关键词扩展

用户输入一个产业名称，通过 DeepSeek 扩展出相关的子领域关键词，
用于更广泛地搜索研报。

例如：输入"新能源汽车" → 扩展出"动力电池, 电机, 电控, 充电桩, 锂矿"等
"""

import logging
import re
from typing import Optional
from openai import OpenAI, RateLimitError
from app.config import get_settings
from app.llm_common import LLMQuotaExceeded, raise_quota_error

logger = logging.getLogger(__name__)


def _strip_think_tags(text: str) -> str:
    """移除 MiniMax-M3 等模型输出的 <think>...</think> 推理块。"""
    if not text:
        return text
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def expand_keywords(industry_name: str) -> list[str]:
    """
    用 LLM 扩展产业关键词

    Args:
        industry_name: 产业名称，如"锂电池"、"光伏"、"半导体"

    Returns:
        扩展后的关键词列表（不含原始输入）
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)

    prompt = f"""你是一位资深的产业分析师。请根据产业名称"{industry_name}"，扩展出与该产业链**直接相关**的核心子领域关键词。

要求：
1. 关键词必须紧扣"{industry_name}"产业链的核心上下游环节，不要扩展到大类不相关的领域
2. 每个关键词应足够具体，适合用于在财经网站搜索研报
3. 优先选择该产业链中最核心、最有代表性的环节
4. 返回 8-12 个关键词，尽量覆盖产业链的主要环节
5. 仅返回关键词列表，用英文逗号分隔，不要有其他文字

示例：
输入：新能源汽车
输出：动力电池,锂矿,正极材料,电机电控,充电桩,电池回收

输入：{industry_name}
输出："""

    try:
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=1500,  # MiniMax-M3 的 <think> 块常 800-1200 token，500 不够
        )

        result = response.choices[0].message.content.strip()
        result = _strip_think_tags(result)
        keywords = [kw.strip() for kw in re.split(r'[,，]', result) if kw.strip()]

        logger.info(f"关键词扩展 '{industry_name}' → {keywords}")
        return keywords

    except RateLimitError as e:
        raise_quota_error(e)
    except Exception as e:
        logger.error(f"关键词扩展失败: {e}")
        return []


def expand_companies(industry_name: str) -> list[str]:
    """
    用 LLM 扩展产业链代表性上市公司

    返回的公司名用于搜索个股研报(qType=0)，
    个股研报天然与目标产业相关，避免行业关键词搜索返回不相关结果。

    Args:
        industry_name: 产业名称

    Returns:
        公司名称列表
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)

    prompt = f"""你是一位A股市场专家。请列出"{industry_name}"产业链中最具代表性的A股上市公司。

要求：
1. 必须是A股上市公司（沪深两市）
2. 覆盖产业链上中下游各环节
3. 优先选择各环节的龙头企业
4. 返回 10-15 个公司名称
5. 仅返回公司名称列表，用英文逗号分隔，不要有其他文字

示例：
输入：新能源汽车
输出：宁德时代,比亚迪,天齐锂业,赣锋锂业,璞泰来,恩捷股份,汇川技术,特锐德,华友钴业,亿纬锂能,当升科技,先导智能

输入：{industry_name}
输出："""

    try:
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,  # 同样为 MiniMax-M3 长 think 预留空间
        )

        result = response.choices[0].message.content.strip()
        result = _strip_think_tags(result)
        companies = [c.strip() for c in re.split(r'[,，]', result) if c.strip()]

        logger.info(f"公司扩展 '{industry_name}' → {companies}")
        return companies

    except RateLimitError as e:
        raise_quota_error(e)
    except Exception as e:
        logger.error(f"公司扩展失败: {e}")
        return []


def pick_industry_code(industry_name: str, pairs: dict[str, str]) -> Optional[str]:
    """
    从东方财富行业分类清单中挑出对应目标产业的行业代码（办法C 用）。

    东方财富研报 API 支持按 industryCode 精确过滤（替代写死的 "*"），
    但产业名 → industryCode 没有稳定公开映射。本函数先用关键词探一轮、
    收集返回结果的 (industryCode, industryName)，再用 LLM 判断哪个分类
    真正属于目标产业，返回其代码。

    Args:
        industry_name: 目标产业名称
        pairs: {industryCode: industryName} 映射（来自探测搜索的返回结果）

    Returns:
        选中的 industryCode 字符串；无匹配或失败返回 None
    """
    if not pairs:
        return None

    settings = get_settings()
    client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)

    listing = "\n".join(f"- 代码 {code}: {name}" for code, name in pairs.items())
    prompt = f"""你是A股行业分类专家。以下是东方财富研报接口对关键词"{industry_name}"搜索后返回的行业分类清单：

{listing}

目标产业是"{industry_name}"。请判断上述哪个（或哪些）东方财富行业分类真正属于"{industry_name}"产业链（包括其直接上游、下游与核心环节，如设备/材料/制造/设计等）。
只输出对应的行业代码（若多个相关则用逗号分隔），不要输出其他任何内容。如果没有任何一个匹配，输出 NONE。"""

    try:
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )
        result = response.choices[0].message.content.strip()
        result = _strip_think_tags(result)
        if not result or result.upper() == "NONE":
            return None
        # 取第一个出现在 pairs 中的代码（规避 LLM 幻觉出的无效代码）
        for tok in re.split(r"[,，\s]+", result):
            tok = tok.strip()
            if tok in pairs:
                return tok
        return None
    except RateLimitError as e:
        raise_quota_error(e)
    except Exception as e:
        logger.error(f"行业代码判定失败: {e}")
        return None
