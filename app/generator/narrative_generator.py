"""LLM 叙述生成模块（P1 重构 — 机构视角）

基于已有的结构化产业链数据，用 LLM 生成分析性叙述文字。
遵循"产业生产逻辑"而非"资本流动逻辑"，为产业研究机构撰写报告。

输出结构匹配8章标准报告：
  1. industry_boundary   — 产业核心边界说明
  2. causal_logic         — 产业链结构成因分析
  3. node_analysis        — 产业链节点深度分析（上/中/下游合并为一段）
  4. transmission_path    — 产业价值传导路径分析
  5. industry_profile     — 产业总体画像
  6. trend_deduction      — 产业未来趋势推演
  7. derivative_segments  — 衍生赛道补充分析
"""

import json
import logging
import re
from typing import Optional
from openai import OpenAI, RateLimitError
from app.config import get_settings
from app.llm_common import LLMQuotaExceeded, raise_quota_error

logger = logging.getLogger(__name__)


def _strip_think_tags(text: str) -> str:
    """移除 MiniMax-M3 等模型输出的 <think>...</think> 推理块。

    这些推理块会污染 JSON 解析和后续处理，必须在所有 LLM 响应入口处剥离。
    """
    if not text:
        return text
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return cleaned.strip()


def _extract_year(value) -> "Optional[str]":
    """从 publish_date 等字段中提取 4 位年份；提取不到返回 None。"""
    if not value:
        return None
    m = re.search(r"(?:19|20)\d{2}", str(value))
    return m.group(0) if m else None


def _compact_reference_reports(refs: list) -> list:
    """提取参考研报的标题与年份，供叙述 LLM 在正文标注数据来源。"""
    out = []
    for r in refs or []:
        if not isinstance(r, dict):
            continue
        title = r.get("title") or r.get("report_title") or ""
        if not title:
            continue
        out.append({"title": title, "year": _extract_year(r.get("publish_date", ""))})
    return out


def _format_reference_reports_for_prompt(refs: list) -> str:
    """把参考研报格式化为 prompt 可用的引用清单（带序号/标题/年份）。"""
    if not refs:
        return "（本次无可引用的参考研报，所有量化数据请统一注明「（行业估算）」）"
    lines = []
    for i, r in enumerate(refs, 1):
        year = r.get("year") or "年份未知"
        lines.append(f"{i}. 《{r.get('title', '')}》（{year}）")
    return "\n".join(lines)


# ── P1: 机构视角叙述 Prompt ──
NARRATIVE_PROMPT = """你是一位资深产业研究员，正在为产业研究机构撰写一份关于「{industry_name}」产业链的研究报告。
请基于以下已整理的产业链结构化数据，为报告的每个章节撰写分析性叙述文字。

【核心要求】
1. 遵循"产业生产逻辑"，从价值生成、流转与传导的角度分析
2. 不得使用"投资建议""资金流向""个股涨幅""PE/PB估值"等金融分析术语
3. 使用"价值传导""配套缺口""国产化率""技术壁垒""成本占比""产能规模"等产业研究专业表述
4. 每个章节必须有实质性分析，引用具体企业、数据和产业逻辑
5. 趋势推演必须基于产业链传导逻辑，不得使用"政策支持、技术迭代"等通用套话
6. 每个章节 300-500 字，内容要有深度
7. 引用任何量化数据（产能、产量、国产化率、技术节点、市场份额、金额、年份等）时，须在句末标注来源：能对应到下方参考研报的写「据《研报标题》(年份)」；若数据源于行业通用估算、无法精确溯源到具体研报，须注明「（行业估算）」。禁止编造不存在的研报来源。

【数据使用约束】
- 优先使用产业研究类数据：产能、产量、国产化率、技术节点、成本占比、认证周期、产能规模
- 金融行情数据（股价、市值、资金流向）不得作为分析核心依据
- 企业基本信息中可简要提及股票代码和市值，但不作为分析支撑

{data_section}

【可引用的参考研报（标注数据来源时使用，格式：据《标题》(年份)）】
{reference_reports_section}

请以JSON格式输出，严格遵守以下格式：
{{
  "industry_boundary": "产业核心边界说明（产业定义、覆盖范围、核心主干环节、主要应用场景与功能价值、产业链对国民经济的意义）",
  "causal_logic": "产业链结构成因分析（为什么产业链是这样构成的，各环节存在的必然性和先后逻辑关系）",
  "node_analysis_upstream": "上游节点深度分析（核心部件/原材料供应、功能定位、技术壁垒、竞争格局、价值占比）",
  "node_analysis_midstream": "中游节点深度分析（制造/集成环节、功能定位、技术壁垒、竞争格局、价值占比）",
  "node_analysis_downstream": "下游节点深度分析（应用领域/终端需求、功能定位、技术壁垒、竞争格局、价值占比）",
  "transmission_path": "产业价值传导路径分析（成本传导/技术传导/需求反向传导的具体路径和逻辑）",
  "industry_profile": "产业总体画像（产业规模、发展阶段、价值与利润分布、核心矛盾）",
  "trend_deduction": "产业未来趋势推演（基于传导逻辑推导3-5年趋势，非通用套话）",
  "derivative_segments": "衍生赛道补充分析（关联/衍生赛道的基本面，篇幅精简）"
}}

以下是「{industry_name}」产业链的结构化数据：
{chain_data_json}"""


def generate_narratives(chain_data: dict) -> dict:
    """
    基于结构化产业链数据，生成机构视角分析性叙述文字

    Args:
        chain_data: merge_and_analyze 返回的完整产业链数据

    Returns:
        各章节叙述文字字典（9个字段）
    """
    industry_name = chain_data.get("industry_name", "未知产业")

    # 构建输入数据 —— 包含 P0 新增的三要素字段
    compact_data = _build_compact_data(chain_data)

    chain_data_json = json.dumps(compact_data, ensure_ascii=False, indent=1)

    # 根据数据量决定分段生成还是一次性生成
    data_len = len(chain_data_json)
    if data_len > 50000:
        return _generate_narratives_segmented(industry_name, compact_data)

    # 构建数据描述
    data_section = _build_data_description(compact_data)
    reference_reports_section = _format_reference_reports_for_prompt(compact_data.get("reference_reports", []))

    prompt = NARRATIVE_PROMPT.format(
        industry_name=industry_name,
        data_section=data_section,
        reference_reports_section=reference_reports_section,
        chain_data_json=chain_data_json,
    )

    try:
        settings = get_settings()
        client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.35,
            max_tokens=12000,
        )
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise ValueError("LLM 返回空内容")

        # 移除 MiniMax-M3 等模型的 <think> 推理块，避免污染 JSON 解析
        content = _strip_think_tags(content)

        result = _parse_narrative_json(content)
        if result:
            # 补齐缺失字段
            for key in _expected_keys():
                if key not in result:
                    result[key] = ""
            logger.info(f"叙述生成成功: {industry_name} (机构视角)")
            return result

        logger.warning(f"叙述 JSON 解析失败: {industry_name}")
        return _empty_narratives()

    except RateLimitError as e:
        logger.error(f"叙述生成配额限制: {e}")
        raise_quota_error(e)
    except Exception as e:
        logger.error(f"叙述生成异常: {e}", exc_info=True)
        return _empty_narratives()


def _build_compact_data(chain_data: dict) -> dict:
    """
    构建精简的输入数据，包含 P0 新增的三要素字段。
    P1: 过滤掉金融行情相关字段，仅保留产业研究类数据。
    """
    compact_data = {
        "industry_description": chain_data.get("industry_description", ""),
        "chain_flow": chain_data.get("chain_flow", ""),
        "chain_causal_logic": chain_data.get("chain_causal_logic", ""),
        "market_data": _filter_market_data(chain_data.get("market_data", {})),
        "chain_segments": {},
        "transmission_relations": chain_data.get("transmission_relations", []),
        "companies_summary": [],
        "relations_count": len(chain_data.get("relations", [])),
        "reference_reports": _compact_reference_reports(chain_data.get("_reference_reports", [])),
    }

    # 环节信息 — 包含 P0 四维度
    segments = chain_data.get("chain_segments", {})
    for level in ["upstream", "midstream", "downstream", "supporting"]:
        segs = segments.get(level, [])
        compact_data["chain_segments"][level] = [
            {
                "segment_name": s.get("segment_name", ""),
                "description": s.get("description", ""),
                "concentration": s.get("concentration", ""),
                "functional_position": s.get("functional_position", ""),
                "value_proportion": s.get("value_proportion", ""),
                "technical_barrier": s.get("technical_barrier", ""),
                "competitive_landscape": s.get("competitive_landscape", ""),
                "companies": s.get("companies", [])[:8],
            }
            for s in segs
        ]

    # 企业摘要（取前 30 家）— 过滤金融字段
    for c in chain_data.get("companies", [])[:30]:
        compact_data["companies_summary"].append({
            "name": c.get("name", ""),
            "stock_code": c.get("stock_code"),
            "main_business": c.get("main_business", ""),
            "chain_position": c.get("chain_position", ""),
            "sub_segment": c.get("sub_segment", ""),
            "market_position": c.get("market_position", ""),
            "products": c.get("products", [])[:3],
            # P1: 不包含 stock_price, market_cap, fund_flow 等金融字段
        })

    return compact_data


def _filter_market_data(market_data: dict) -> dict:
    """
    P1: 过滤市场数据，保留产业研究类字段，弱化金融行情类。
    保留: market_size, forecast, competition_landscape, policy_environment,
          key_drivers, opportunities, risks
    移除: 任何包含 stock/index/pe/pb/fund_flow 的字段
    """
    if not market_data:
        return {}

    financial_keywords = {"stock", "index", "pe", "pb", "fund_flow", "valuation", "市值", "涨幅"}
    filtered = {}
    for key, value in market_data.items():
        if any(fw in key.lower() for fw in financial_keywords):
            continue  # 跳过金融行情类字段
        filtered[key] = value
    return filtered


def _expected_keys() -> list:
    """返回期望的所有叙述字段"""
    return [
        "industry_boundary",
        "causal_logic",
        "node_analysis_upstream",
        "node_analysis_midstream",
        "node_analysis_downstream",
        "transmission_path",
        "industry_profile",
        "trend_deduction",
        "derivative_segments",
    ]


def _generate_narratives_segmented(industry_name: str, compact_data: dict) -> dict:
    """数据量大时，分段生成叙述（匹配8章结构）"""
    settings = get_settings()
    client = OpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url
    )
    results = {}

    reference_reports_section = _format_reference_reports_for_prompt(compact_data.get("reference_reports", []))
    citation_rule = ("引用任何量化数据时须在句末标注来源：能对应参考研报的写"
                     "「据《研报标题》(年份)」，无法溯源注明「（行业估算）」；禁止编造来源。")

    # 分段1: 产业边界 + 成因逻辑 + 上游节点
    seg1_data = {
        "industry_description": compact_data.get("industry_description", ""),
        "chain_flow": compact_data.get("chain_flow", ""),
        "chain_causal_logic": compact_data.get("chain_causal_logic", ""),
        "upstream_segments": compact_data.get("chain_segments", {}).get("upstream", []),
        "companies": [c for c in compact_data.get("companies_summary", [])
                      if c.get("chain_position") == "上游"][:15],
    }
    seg1_prompt = f"""请基于以下数据，为「{industry_name}」撰写三段分析性叙述文字。
要求每段 300-500 字，引用具体企业和数据，遵循产业生产逻辑，不使用金融分析术语。
{citation_rule}

【可引用的参考研报】
{reference_reports_section}

以JSON格式输出：
{{
  "industry_boundary": "产业核心边界说明",
  "causal_logic": "产业链结构成因分析",
  "node_analysis_upstream": "上游节点深度分析"
}}

数据：
{json.dumps(seg1_data, ensure_ascii=False, indent=1)}"""

    try:
        resp = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[{"role": "user", "content": seg1_prompt}],
            temperature=0.35,
            max_tokens=6000,
        )
        content = resp.choices[0].message.content if resp.choices else ""
        # 移除 MiniMax-M3 等模型的 <think> 推理块
        content = _strip_think_tags(content)
        parsed = _parse_narrative_json(content)
        if parsed:
            results.update(parsed)
    except RateLimitError as e:
        logger.error(f"叙述生成(段1)配额限制: {e}")
        raise_quota_error(e)
    except Exception as e:
        logger.warning(f"叙述生成(段1)失败: {e}")

    # 分段2: 中游 + 下游节点
    seg2_data = {
        "midstream_segments": compact_data.get("chain_segments", {}).get("midstream", []),
        "downstream_segments": compact_data.get("chain_segments", {}).get("downstream", []),
        "companies": [c for c in compact_data.get("companies_summary", [])
                      if c.get("chain_position") in ("中游", "下游")][:20],
    }
    seg2_prompt = f"""请基于以下数据，为「{industry_name}」撰写两段分析性叙述文字。
要求每段 300-500 字，引用具体企业和数据，遵循产业生产逻辑。
{citation_rule}

【可引用的参考研报】
{reference_reports_section}

以JSON格式输出：
{{
  "node_analysis_midstream": "中游节点深度分析",
  "node_analysis_downstream": "下游节点深度分析"
}}

数据：
{json.dumps(seg2_data, ensure_ascii=False, indent=1)}"""

    try:
        resp = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[{"role": "user", "content": seg2_prompt}],
            temperature=0.35,
            max_tokens=6000,
        )
        content = resp.choices[0].message.content if resp.choices else ""
        # 移除 MiniMax-M3 等模型的 <think> 推理块
        content = _strip_think_tags(content)
        parsed = _parse_narrative_json(content)
        if parsed:
            results.update(parsed)
    except RateLimitError as e:
        logger.error(f"叙述生成(段2)配额限制: {e}")
        raise_quota_error(e)
    except Exception as e:
        logger.warning(f"叙述生成(段2)失败: {e}")

    # 分段3: 传导路径 + 产业画像 + 趋势推演 + 衍生赛道
    seg3_data = {
        "transmission_relations": compact_data.get("transmission_relations", []),
        "market_data": compact_data.get("market_data", {}),
        "supporting_segments": compact_data.get("chain_segments", {}).get("supporting", []),
        "relations_count": compact_data.get("relations_count", 0),
    }
    seg3_prompt = f"""请基于以下数据，为「{industry_name}」撰写四段分析性叙述文字。
要求每段 300-500 字。传导路径必须基于实际的环节间传导逻辑，趋势推演不得空泛。
{citation_rule}

【可引用的参考研报】
{reference_reports_section}

以JSON格式输出：
{{
  "transmission_path": "产业价值传导路径分析",
  "industry_profile": "产业总体画像",
  "trend_deduction": "产业未来趋势推演",
  "derivative_segments": "衍生赛道补充分析"
}}

数据：
{json.dumps(seg3_data, ensure_ascii=False, indent=1)}"""

    try:
        resp = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[{"role": "user", "content": seg3_prompt}],
            temperature=0.35,
            max_tokens=8000,
        )
        content = resp.choices[0].message.content if resp.choices else ""
        # 移除 MiniMax-M3 等模型的 <think> 推理块
        content = _strip_think_tags(content)
        parsed = _parse_narrative_json(content)
        if parsed:
            results.update(parsed)
    except RateLimitError as e:
        logger.error(f"叙述生成(段3)配额限制: {e}")
        raise_quota_error(e)
    except Exception as e:
        logger.warning(f"叙述生成(段3)失败: {e}")

    # 补齐缺失字段
    for key in _expected_keys():
        if key not in results:
            results[key] = ""

    filled = sum(1 for v in results.values() if v)
    logger.info(f"分段叙述生成完成: {industry_name}, 成功 {filled}/{len(_expected_keys())} 段")
    return results


def _build_data_description(data: dict) -> str:
    """构建数据概要描述，帮助 LLM 理解数据结构"""
    parts = []
    segments = data.get("chain_segments", {})
    for level, label in [("upstream", "上游"), ("midstream", "中游"),
                          ("downstream", "下游"), ("supporting", "配套")]:
        segs = segments.get(level, [])
        if segs:
            names = [s.get("segment_name", "") for s in segs]
            parts.append(f"{label}环节: {', '.join(names)}")
            # P0: 展示四维度覆盖情况
            has_attrs = any(s.get("functional_position") for s in segs)
            if has_attrs:
                parts.append(f"  (已含四维度属性: 功能定位/价值占比/技术壁垒/竞争格局)")

    # P0: 传导关系
    transmissions = data.get("transmission_relations", [])
    if transmissions:
        parts.append(f"环节间传导关系: {len(transmissions)} 条")

    # P0: 因果逻辑
    causal = data.get("chain_causal_logic", "")
    if causal:
        parts.append(f"产业链成因逻辑: 已提供 ({len(causal)}字)")

    # 市场数据概要
    market_data = data.get("market_data", {})
    if market_data:
        if market_data.get("market_size"):
            parts.append(f"市场规模: {market_data['market_size']}")
        if market_data.get("forecast"):
            parts.append(f"市场预测: {market_data['forecast']}")
        if market_data.get("key_drivers"):
            parts.append(f"驱动因素: {', '.join(market_data['key_drivers'][:5])}")

    return "\n".join(parts)


def _parse_narrative_json(text: str) -> dict:
    """从 LLM 响应中解析叙述 JSON"""
    import re

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 代码块
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试提取 { ... } 块
    brace_match = re.search(r'\{.*\}', text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return {}


def _empty_narratives() -> dict:
    """返回空叙述（匹配8章结构）"""
    return {key: "" for key in _expected_keys()}


# ══════════════════════════════════════════════════════════════
# P2: 独立趋势推演函数
# ══════════════════════════════════════════════════════════════

TREND_DEDUCTION_PROMPT = """你是一位资深产业研究员，正在为「{industry_name}」产业链撰写未来3-5年的趋势推演报告。

【核心原则】
你的趋势推演必须严格基于产业链的实际传导逻辑，而非空泛的宏观套话。
每一条趋势判断都必须有明确的传导路径支撑：从某个核心环节的技术/成本/需求变化出发 → 沿传导路径分析对上下游的影响 → 总结对产业全局的长期影响。

【禁止事项】
- 禁止使用"政策支持、技术迭代、市场需求增长"等万能套话作为趋势判断
- 禁止脱离产业链结构空谈未来
- 禁止使用金融行情数据（股价、市值、PE等）作为趋势依据

【必须覆盖的维度】
1. **产业链结构演变趋势**：未来哪些环节可能合并/分裂/新增？哪些环节的重要性会上升/下降？
2. **价值重心转移方向**：产业链的利润池会向哪个环节迁移？为什么？
3. **核心环节迭代方向**：关键环节的技术路线/产能布局/竞争格局会发生什么具体变化？
4. **潜在风险点**：基于传导逻辑，哪个环节的断裂/瓶颈会对全产业链造成最大冲击？

【输出要求】
- 总字数 600-1000 字
- 分为 3-4 个趋势判断，每个判断包含：趋势描述 + 传导路径 + 具体依据
- 引用具体的企业名称、技术路线、产能数据
- 每条趋势判断须显式回扣下方「前文节点分析」中的具体事实（如某环节价值占比、技术壁垒、代表企业角色、具体传导关系），不得仅做泛化推断；并尽量标注数据来源「据《研报标题》(年份)」，无法溯源注明「（行业估算）」

以下是「{industry_name}」的产业链数据：

【前文节点分析（趋势推演须显式回扣其中的具体事实）】
{prior_analysis_section}

产业链结构：
{segments_info}

环节间传导关系：
{transmission_info}

产业链成因逻辑：
{causal_logic}

市场数据：
{market_info}

【可引用的参考研报】
{reference_reports_section}

请直接输出趋势推演文本（不需要JSON格式）："""


def generate_trend_deduction(chain_data: dict) -> str:
    """
    P2: 独立的趋势推演函数

    基于产业链传导逻辑，生成专业的趋势推演文本。
    与 generate_narratives 中的趋势推演不同，本函数：
    1. 使用专门的深度推演Prompt
    2. 输出更长、更有深度的趋势分析
    3. 可独立调用，不影响其他叙述字段

    Args:
        chain_data: merge_and_analyze 返回的完整产业链数据

    Returns:
        趋势推演文本字符串
    """
    industry_name = chain_data.get("industry_name", "未知产业")

    # 构建输入数据
    segments = chain_data.get("chain_segments", {})
    segments_parts = []
    for level, label in [("upstream", "上游"), ("midstream", "中游"),
                          ("downstream", "下游"), ("supporting", "配套")]:
        segs = segments.get(level, [])
        if segs:
            seg_names = []
            for s in segs:
                name = s.get("segment_name", "")
                fp = s.get("functional_position", "")
                tb = s.get("technical_barrier", "")
                seg_names.append(f"  - {name}: {fp} | 壁垒: {tb}")
            segments_parts.append(f"【{label}】\n" + "\n".join(seg_names))

    segments_info = "\n".join(segments_parts) if segments_parts else "（无环节数据）"

    # 传导关系
    transmissions = chain_data.get("transmission_relations", [])
    if transmissions:
        trans_parts = []
        for tr in transmissions:
            trans_parts.append(
                f"  {tr.get('from_segment', '')} → {tr.get('to_segment', '')}: "
                f"[{tr.get('transmission_type', '')}] {tr.get('description', '')}"
            )
        transmission_info = "\n".join(trans_parts)
    else:
        transmission_info = "（无传导关系数据）"

    causal_logic = chain_data.get("chain_causal_logic", "") or "（无成因逻辑数据）"

    # 市场数据
    market_data = chain_data.get("market_data", {})
    market_parts = []
    if market_data.get("market_size"):
        market_parts.append(f"市场规模: {market_data['market_size']}")
    if market_data.get("forecast"):
        market_parts.append(f"市场预测: {market_data['forecast']}")
    if market_data.get("competition_landscape"):
        market_parts.append(f"竞争格局: {market_data['competition_landscape']}")
    if market_data.get("key_drivers"):
        market_parts.append(f"驱动因素: {', '.join(market_data['key_drivers'][:5])}")
    market_info = "\n".join(market_parts) if market_parts else "（无市场数据）"

    # 前文节点分析（供趋势推演显式回扣）
    narratives = chain_data.get("_narratives", {}) or {}
    prior_parts = []
    for key in ("node_analysis_upstream", "node_analysis_midstream",
                "node_analysis_downstream", "transmission_path", "industry_profile"):
        val = narratives.get(key)
        if val:
            prior_parts.append(f"【{key}】\n{val}")
    prior_analysis_section = "\n\n".join(prior_parts) if prior_parts else "（前文节点分析尚未生成）"

    # 参考研报（供标注数据来源）
    reference_reports_section = _format_reference_reports_for_prompt(
        _compact_reference_reports(chain_data.get("_reference_reports", []))
    )

    prompt = TREND_DEDUCTION_PROMPT.format(
        industry_name=industry_name,
        prior_analysis_section=prior_analysis_section,
        segments_info=segments_info,
        transmission_info=transmission_info,
        causal_logic=causal_logic,
        market_info=market_info,
        reference_reports_section=reference_reports_section,
    )

    try:
        settings = get_settings()
        client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4000,
        )
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise ValueError("LLM 返回空内容")

        # 移除 MiniMax-M3 等模型的 <think> 推理块
        content = _strip_think_tags(content)

        logger.info(f"趋势推演生成成功: {industry_name} ({len(content)}字)")
        return content.strip()

    except RateLimitError as e:
        logger.error(f"趋势推演生成配额限制: {e}")
        raise_quota_error(e)
    except Exception as e:
        logger.error(f"趋势推演生成异常: {e}", exc_info=True)
        return ""


# ══════════════════════════════════════════════════════════════
# Pipeline 集成：带重试保障的叙述生成
# ══════════════════════════════════════════════════════════════

def generate_narratives_with_retry(chain_data: dict, max_attempts: int = 3) -> dict:
    """
    Pipeline 集成版叙述生成：带重试 + 输入降级策略，确保必须生成成功。

    策略：
    1. 前2次用正常输入，temperature 递减（0.35 → 0.25 → 0.15）
    2. 第3次缩减输入（只保留核心环节+传导关系）
    3. 3次均失败才返回空

    Args:
        chain_data: merge_and_analyze 返回的完整产业链数据
        max_attempts: 最大重试次数（默认3）

    Returns:
        各章节叙述文字字典
    """
    last_result = _empty_narratives()

    for attempt in range(1, max_attempts + 1):
        try:
            if attempt <= 2:
                # 正常输入，temperature 递减
                temp = 0.35 - (attempt - 1) * 0.1
                work_data = chain_data
            else:
                # 降级：只保留核心数据
                logger.warning(f"叙述生成前2次失败，缩减输入重试 (attempt={attempt})")
                work_data = _degrade_chain_data(chain_data)
                temp = 0.15

            # 构造精简数据 JSON
            compact_data = _build_compact_data(work_data)
            chain_data_json = json.dumps(compact_data, ensure_ascii=False, indent=1)

            # 判断数据量是否过大，分段生成
            if len(chain_data_json) > 50000:
                data_section = _build_data_description(compact_data)
                result = _generate_narratives_segmented(
                    chain_data.get("industry_name", "未知产业"), compact_data
                )
            else:
                data_section = _build_data_description(compact_data)
                prompt = NARRATIVE_PROMPT.format(
                    industry_name=chain_data.get("industry_name", "未知产业"),
                    data_section=data_section,
                    chain_data_json=chain_data_json,
                )

                settings = get_settings()
                client = OpenAI(
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_base_url,
                )
                response = client.chat.completions.create(
                    model=settings.deepseek_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temp,
                    max_tokens=12000,
                )
                content = response.choices[0].message.content if response.choices else None
                if not content:
                    raise ValueError("LLM 返回空内容")
                # 移除 MiniMax-M3 等模型的 <think> 推理块
                content = _strip_think_tags(content)
                result = _parse_narrative_json(content)

            if result:
                # 补齐缺失字段
                for key in _expected_keys():
                    if key not in result:
                        result[key] = ""
                # 验证至少有一个章节有内容
                has_content = any(result.get(k, "").strip() for k in _expected_keys())
                if has_content:
                    logger.info(f"叙述生成成功 (attempt={attempt}, temp={temp})")
                    return result
                else:
                    logger.warning(f"叙述结果为空 (attempt={attempt})")

            last_result = result if result else _empty_narratives()

        except RateLimitError as e:
            logger.error(f"叙述生成配额限制 (attempt={attempt}): {e}")
            raise_quota_error(e)
        except Exception as e:
            logger.error(f"叙述生成异常 (attempt={attempt}): {e}", exc_info=True)

    logger.error(f"叙述生成在 {max_attempts} 次尝试后均失败")
    return last_result


def generate_trend_deduction_with_retry(chain_data: dict, max_attempts: int = 2) -> str:
    """
    Pipeline 集成版趋势推演：带重试保障。

    Args:
        chain_data: merge_and_analyze 返回的完整产业链数据
        max_attempts: 最大重试次数（默认2）

    Returns:
        趋势推演文本字符串
    """
    for attempt in range(1, max_attempts + 1):
        try:
            result = generate_trend_deduction(chain_data)
            if result and len(result) >= 100:
                logger.info(f"趋势推演生成成功 (attempt={attempt}, {len(result)}字)")
                return result
            logger.warning(f"趋势推演内容不足 (attempt={attempt}, {len(result) if result else 0}字)")
        except Exception as e:
            logger.error(f"趋势推演生成异常 (attempt={attempt}): {e}", exc_info=True)

    logger.error(f"趋势推演生成在 {max_attempts} 次尝试后均失败")
    return ""


def _degrade_chain_data(chain_data: dict) -> dict:
    """降级版产业链数据：只保留核心环节和传导关系，减少输入体积"""
    degraded = dict(chain_data)

    # 环节只保留名称和四维度，去掉 companies 列表和 description
    segments = chain_data.get("chain_segments", {})
    degraded["chain_segments"] = {}
    for level in ["upstream", "midstream", "downstream", "supporting"]:
        segs = segments.get(level, [])
        degraded["chain_segments"][level] = [
            {
                "segment_name": s.get("segment_name", ""),
                "functional_position": s.get("functional_position", ""),
                "value_proportion": s.get("value_proportion", ""),
                "technical_barrier": s.get("technical_barrier", ""),
                "competitive_landscape": s.get("competitive_landscape", ""),
            }
            for s in segs
        ]

    # 企业只保留前15家核心企业
    degraded["companies"] = chain_data.get("companies", [])[:15]

    return degraded


# ── 风险与不确定性专题 prompt ──

RISK_ANALYSIS_PROMPT = """你是一位资深产业研究员，正在为「{industry_name}」产业链撰写「风险与不确定性」专题分析。

【核心原则】
风险必须基于本产业链的实际结构（环节、传导关系、技术壁垒、竞争格局）推导，而非空泛的宏观套话。每条风险须说明：风险点 + 作用环节 + 沿传导路径的潜在冲击 + 不确定性来源。

【禁止事项】
- 禁止只罗列"政策风险、市场风险、竞争风险"等万能标签而不结合本产业具体环节
- 禁止脱离产业链结构空谈

【输出要求】
- 列出 3-5 条该产业特有的风险与不确定性
- 每条包含：风险描述 + 关联环节 + 传导冲击 + 不确定性说明
- 引用具体企业、技术节点或产能数据
- 尽量标注数据来源「据《研报标题》(年份)」，无法溯源注明「（行业估算）」
- 总字数 400-700 字

以下是「{industry_name}」的产业链数据：

【前文节点分析（风险须结合其中具体事实）】
{prior_analysis_section}

产业链结构：
{segments_info}

环节间传导关系：
{transmission_info}

产业链成因逻辑：
{causal_logic}

【可引用的参考研报】
{reference_reports_section}

请直接输出风险与不确定性分析文本（不需要JSON格式）："""


def generate_risk_analysis(chain_data: dict) -> str:
    """
    生成「风险与不确定性」专题分析文本。
    基于产业链实际结构与前文节点分析，列出 3-5 条产业特有风险。
    """
    industry_name = chain_data.get("industry_name", "未知产业")

    segments = chain_data.get("chain_segments", {})
    segments_parts = []
    for level, label in [("upstream", "上游"), ("midstream", "中游"),
                          ("downstream", "下游"), ("supporting", "配套")]:
        segs = segments.get(level, [])
        if segs:
            seg_names = []
            for s in segs:
                name = s.get("segment_name", "")
                fp = s.get("functional_position", "")
                tb = s.get("technical_barrier", "")
                seg_names.append(f"  - {name}: {fp} | 壁垒: {tb}")
            segments_parts.append(f"【{label}】\n" + "\n".join(seg_names))
    segments_info = "\n".join(segments_parts) if segments_parts else "（无环节数据）"

    transmissions = chain_data.get("transmission_relations", [])
    if transmissions:
        trans_parts = [
            f"  {tr.get('from_segment', '')} → {tr.get('to_segment', '')}: "
            f"[{tr.get('transmission_type', '')}] {tr.get('description', '')}"
            for tr in transmissions
        ]
        transmission_info = "\n".join(trans_parts)
    else:
        transmission_info = "（无传导关系数据）"

    causal_logic = chain_data.get("chain_causal_logic", "") or "（无成因逻辑数据）"

    narratives = chain_data.get("_narratives", {}) or {}
    prior_parts = []
    for key in ("node_analysis_upstream", "node_analysis_midstream",
                "node_analysis_downstream", "transmission_path", "industry_profile"):
        val = narratives.get(key)
        if val:
            prior_parts.append(f"【{key}】\n{val}")
    prior_analysis_section = "\n\n".join(prior_parts) if prior_parts else "（前文节点分析尚未生成）"

    reference_reports_section = _format_reference_reports_for_prompt(
        _compact_reference_reports(chain_data.get("_reference_reports", []))
    )

    prompt = RISK_ANALYSIS_PROMPT.format(
        industry_name=industry_name,
        prior_analysis_section=prior_analysis_section,
        segments_info=segments_info,
        transmission_info=transmission_info,
        causal_logic=causal_logic,
        reference_reports_section=reference_reports_section,
    )

    try:
        settings = get_settings()
        client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=3000,
        )
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise ValueError("LLM 返回空内容")
        content = _strip_think_tags(content)
        logger.info(f"风险与不确定性分析生成成功: {industry_name} ({len(content)}字)")
        return content.strip()
    except RateLimitError as e:
        logger.error(f"风险分析生成配额限制: {e}")
        raise_quota_error(e)
    except Exception as e:
        logger.error(f"风险分析生成异常: {e}", exc_info=True)
        return ""


def generate_risk_analysis_with_retry(chain_data: dict, max_attempts: int = 2) -> str:
    """Pipeline 集成版风险分析：带重试保障。"""
    for attempt in range(1, max_attempts + 1):
        try:
            result = generate_risk_analysis(chain_data)
            if result and len(result) >= 100:
                logger.info(f"风险分析生成成功 (attempt={attempt}, {len(result)}字)")
                return result
            logger.warning(f"风险分析内容不足 (attempt={attempt}, {len(result) if result else 0}字)")
        except Exception as e:
            logger.error(f"风险分析生成异常 (attempt={attempt}): {e}", exc_info=True)
    logger.error(f"风险分析生成在 {max_attempts} 次尝试后均失败")
    return ""
