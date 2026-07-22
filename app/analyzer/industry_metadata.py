"""产业元数据配置模块

为每个产业动态生成元数据（核心主干环节白名单、衍生赛道、占比上限等），
用于约束后续产业链生成过程中的边界识别和内容权重分配。

设计原则：
- 不依赖硬编码的产业字典，通过 LLM 动态生成，适配任意产业
- 生成结果带缓存，同一产业不重复调用 LLM
- 元数据作为 Prompt 约束注入 merge_and_analyze，而非硬阻断
"""

import json
import logging
import re
from openai import OpenAI, RateLimitError
from app.config import get_settings
from app.llm_common import LLMQuotaExceeded, raise_quota_error

logger = logging.getLogger(__name__)


def _strip_think_tags(text: str) -> str:
    """移除 MiniMax-M3 等模型输出的 <think>...</think> 推理块。"""
    if not text:
        return text
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

# ── 内存缓存 ──
_metadata_cache: dict[str, dict] = {}


# ─────────────────────────────────────────────
#  LLM Prompt
# ─────────────────────────────────────────────

METADATA_GENERATION_PROMPT = """你是一位资深产业研究员。请为「{industry_name}」产业链生成一份结构化的元数据配置。

【任务说明】
这份元数据将用于约束产业链分析报告的生成过程，确保报告聚焦于产业核心主干环节，
而非被衍生赛道或关联概念挤占核心内容。

【要求】
1. 核心主干环节：列出该产业链必须覆盖的一级/二级环节，按上中下游顺序排列。
   - 这些是产业界公认的、构成该产业链核心价值的关键环节
   - 数量通常在 6-15 个之间
   - 必须覆盖上游、中游、下游三个层级
2. 衍生/关联赛道：列出与该产业有关联但并非核心主干的延伸赛道。
   - 这些赛道的内容在报告中占比不应超过 15%
   - 例如：航空航天产业中的"太空旅游"、机器人产业中的"智能眼镜"
3. 产业定义：用 2-3 句话定义该产业的边界和核心范畴
4. 产业类型：判断属于"离散制造类"（线性分层结构）还是"流程制造类"（闭环迭代结构）

以JSON格式输出，严格遵守以下schema：
{{
  "industry_name": "{industry_name}",
  "industry_definition": "该产业的定义与边界说明（2-3句话）",
  "industry_type": "离散制造类/流程制造类",
  "core_segments": [
    {{"name": "环节名称", "level": "上游/中游/下游", "is_critical": true}}
  ],
  "derivative_segments": [
    {{"name": "衍生赛道名称", "reason": "为什么归为衍生赛道"}}
  ],
  "derivative_ratio_limit": 15,
  "data_priority": "产业研究类数据优先，金融行情类数据仅作补充"
}}

产业名称：{industry_name}"""


def generate_industry_metadata(industry_name: str) -> dict:
    """
    通过 LLM 为指定产业动态生成元数据

    Args:
        industry_name: 产业名称（如"航空航天"、"机器人"、"半导体"等）

    Returns:
        元数据字典，包含 core_segments、derivative_segments 等字段。
        如果 LLM 调用失败，返回最小可用的默认元数据。
    """
    # 检查缓存
    if industry_name in _metadata_cache:
        logger.info(f"产业元数据命中缓存: {industry_name}")
        return _metadata_cache[industry_name]

    settings = get_settings()
    client = OpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )

    prompt = METADATA_GENERATION_PROMPT.format(industry_name=industry_name)

    try:
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=3000,
        )

        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise ValueError("LLM 返回空内容")

        # 移除 MiniMax-M3 的 <think>...</think> 推理块
        content = _strip_think_tags(content)

        # 解析 JSON
        metadata = _parse_metadata_json(content)
        if not metadata or not metadata.get("core_segments"):
            raise ValueError("元数据解析失败或缺少 core_segments")

        # 基本校验
        metadata = _validate_metadata(metadata, industry_name)

        # 写入缓存
        _metadata_cache[industry_name] = metadata

        core_count = len(metadata.get("core_segments", []))
        deriv_count = len(metadata.get("derivative_segments", []))
        logger.info(
            f"产业元数据生成成功: '{industry_name}' | "
            f"核心主干 {core_count} 个 | 衍生赛道 {deriv_count} 个 | "
            f"类型: {metadata.get('industry_type', '未知')}"
        )

        return metadata

    except RateLimitError as e:
        raise_quota_error(e)
    except Exception as e:
        logger.warning(
            f"产业元数据 LLM 生成失败 ({industry_name}): {e}，"
            f"使用默认元数据"
        )
        default = _default_metadata(industry_name)
        _metadata_cache[industry_name] = default
        return default


def _parse_metadata_json(text: str) -> dict:
    """从 LLM 响应中解析 JSON"""
    import re

    # 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 提取 ```json ... ``` 代码块
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 提取 { ... } 块
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return {}


def _validate_metadata(metadata: dict, industry_name: str) -> dict:
    """
    校验元数据的基本完整性

    校验项：
    - core_segments 非空且数量 ≥ 4
    - 每个 core_segment 有 name 和 level
    - core_segments 覆盖至少 2 个层级（上游/中游/下游）
    - derivative_ratio_limit 在 5-30 之间
    """
    core = metadata.get("core_segments", [])

    # 确保每个环节有 name 和 level
    valid_core = []
    for seg in core:
        if isinstance(seg, dict) and seg.get("name"):
            if not seg.get("level"):
                seg["level"] = "中游"  # 默认
            valid_core.append(seg)
        elif isinstance(seg, str):
            valid_core.append({"name": seg, "level": "中游", "is_critical": True})

    metadata["core_segments"] = valid_core

    # 校验层级覆盖
    levels = {seg.get("level") for seg in valid_core}
    if len(levels) < 2 and valid_core:
        logger.warning(
            f"产业 '{industry_name}' 核心主干仅覆盖 {levels} 个层级，"
            f"建议补充其他层级环节"
        )

    # 校验衍生赛道比例
    ratio = metadata.get("derivative_ratio_limit", 15)
    if not isinstance(ratio, (int, float)):
        metadata["derivative_ratio_limit"] = 15
    elif ratio < 5 or ratio > 30:
        metadata["derivative_ratio_limit"] = 15

    # 确保衍生赛道列表存在
    if not isinstance(metadata.get("derivative_segments"), list):
        metadata["derivative_segments"] = []

    # 确保产业定义存在
    if not metadata.get("industry_definition"):
        metadata["industry_definition"] = (
            f"{industry_name}产业链的完整产业生态，"
            f"涵盖上游原材料/核心零部件、中游制造集成、下游应用与服务。"
        )

    return metadata


def _default_metadata(industry_name: str) -> dict:
    """
    生成默认元数据（LLM 调用失败时的兜底）

    不做具体的环节限定，但保留元数据结构，让后续流程正常运行。
    """
    return {
        "industry_name": industry_name,
        "industry_definition": (
            f"{industry_name}产业链的完整产业生态，"
            f"涵盖上游原材料/核心零部件、中游制造集成、下游应用与服务。"
        ),
        "industry_type": "离散制造类",
        "core_segments": [],
        "derivative_segments": [],
        "derivative_ratio_limit": 15,
        "data_priority": "产业研究类数据优先，金融行情类数据仅作补充",
        "_is_default": True,  # 标记为默认值，后续可据此判断是否需要重试
    }


def build_metadata_prompt_section(metadata: dict) -> str:
    """
    将元数据转换为 Prompt 约束文本，用于注入 MERGE_PROMPT

    Args:
        metadata: generate_industry_metadata 返回的元数据

    Returns:
        格式化的 Prompt 约束文本段落。如果元数据为默认值或无核心主干，
        返回空字符串（不注入约束）。
    """
    if metadata.get("_is_default"):
        return ""

    core_segments = metadata.get("core_segments", [])
    if not core_segments:
        return ""

    industry_name = metadata.get("industry_name", "未知产业")
    industry_def = metadata.get("industry_definition", "")
    industry_type = metadata.get("industry_type", "")
    derivative_segments = metadata.get("derivative_segments", [])
    ratio_limit = metadata.get("derivative_ratio_limit", 15)

    # 构建核心主干列表文本
    core_lines = []
    for seg in core_segments:
        name = seg.get("name", "")
        level = seg.get("level", "")
        critical = " ★" if seg.get("is_critical") else ""
        core_lines.append(f"   - [{level}] {name}{critical}")
    core_text = "\n".join(core_lines)

    # 构建衍生赛道列表文本
    deriv_text = ""
    if derivative_segments:
        deriv_names = [s.get("name", "") for s in derivative_segments if s.get("name")]
        if deriv_names:
            deriv_text = f"   衍生/关联赛道（内容占比必须≤{ratio_limit}%）：{'、'.join(deriv_names)}"

    section = f"""
【产业边界约束 — 必须遵守】
目标产业：{industry_name}
产业定义：{industry_def}
产业类型：{industry_type}

核心主干环节（内容占比必须≥{100 - ratio_limit}%）：
{core_text}

{deriv_text}

请严格按照上述边界组织内容：
1. 核心主干环节是报告的分析重点，每个环节必须深入分析其功能定位、价值占比、技术壁垒和竞争格局
2. 衍生赛道仅可在"衍生赛道补充分析"章节中简要提及，不得挤占核心主干的分析篇幅
3. 如果发现提取的数据中有内容属于衍生赛道，请降低其权重，不要将其作为核心环节展示"""

    return section


def get_cached_metadata(industry_name: str) -> dict | None:
    """获取已缓存的元数据（不触发 LLM 调用）"""
    return _metadata_cache.get(industry_name)
