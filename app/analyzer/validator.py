"""输出校验模块（P2）

在报告生成后、返回结果前，自动执行内容合规性校验。
校验项覆盖 P0/P1 的核心要求：
  1. 核心主干占比 ≥70%
  2. 衍生赛道占比 ≤15%
  3. 节点维度完整性（四维度）
  4. 传导逻辑存在性
  5. 成因逻辑存在性 ≥200字
  6. 章节结构合规
  7. 数据来源合规（产业研究类 ≥80%）
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def validate_report(chain_data: dict, industry_metadata: Optional[dict] = None) -> dict:
    """
    校验报告内容的合规性

    Args:
        chain_data: merge_and_analyze 返回的产业链数据
        industry_metadata: 产业元数据（含核心主干白名单）

    Returns:
        {
            "passed": bool,           # 是否全部通过（无 ERROR）
            "score": int,             # 综合得分 0-100
            "errors": [...],          # ERROR 级别问题
            "warnings": [...],        # WARNING 级别问题
            "details": {...},         # 各项校验的详细数据
        }
    """
    errors = []
    warnings = []
    details = {}
    score = 100

    # ── 校验1: 核心主干占比 ──
    check1 = _check_core_segment_ratio(chain_data, industry_metadata)
    details["core_ratio"] = check1
    if not check1["passed"]:
        errors.append(check1["message"])
        score -= 20
    elif check1.get("ratio") is not None and check1.get("ratio", 1) < 0.8:
        warnings.append(check1["message"])
        score -= 5

    # ── 校验2: 衍生赛道占比 ──
    check2 = _check_derivative_ratio(chain_data, industry_metadata)
    details["derivative_ratio"] = check2
    if not check2["passed"]:
        errors.append(check2["message"])
        score -= 20
    elif check2.get("ratio") is not None and check2.get("ratio", 0) > 0.1:
        warnings.append(check2["message"])
        score -= 5

    # ── 校验3: 节点维度完整性 ──
    check3 = _check_node_dimensions(chain_data)
    details["node_dimensions"] = check3
    if not check3["passed"]:
        errors.append(check3["message"])
        score -= 20
    elif check3.get("coverage") is not None and check3.get("coverage", 1) < 0.9:
        warnings.append(f"节点四维度覆盖率 {check3.get('coverage', 0):.0%}（建议 ≥90%）")
        score -= 5

    # ── 校验4: 传导逻辑存在性 ──
    check4 = _check_transmission_relations(chain_data)
    details["transmission"] = check4
    if not check4["passed"]:
        errors.append(check4["message"])
        score -= 15

    # ── 校验5: 成因逻辑存在性 ──
    check5 = _check_causal_logic(chain_data)
    details["causal_logic"] = check5
    if not check5["passed"]:
        warnings.append(check5["message"])
        score -= 10

    # ── 校验6: 章节结构合规 ──
    check6 = _check_chapter_structure(chain_data)
    details["chapter_structure"] = check6
    if not check6["passed"]:
        errors.append(check6["message"])
        score -= 10

    # ── 校验7: 数据来源合规 ──
    check7 = _check_data_source_compliance(chain_data)
    details["data_source"] = check7
    if not check7["passed"]:
        warnings.append(check7["message"])
        score -= 10

    # ── 校验8: 情感中性软规则（不阻断，仅告警）──
    # 参考 cwwindex 的 marketImpactInferred:false 原则：事件/风险叙述不得暗示利好利空或涨跌
    check8 = _check_sentiment_neutrality(chain_data)
    details["sentiment_neutrality"] = check8
    if not check8["passed"]:
        warnings.append(check8["message"])
        score -= 5

    score = max(0, score)
    passed = len(errors) == 0

    result = {
        "passed": passed,
        "score": score,
        "errors": errors,
        "warnings": warnings,
        "details": details,
    }

    if passed:
        logger.info(f"报告校验通过: 得分={score}, warnings={len(warnings)}")
    else:
        logger.warning(f"报告校验未通过: 得分={score}, errors={len(errors)}, warnings={len(warnings)}")

    return result


def _check_core_segment_ratio(chain_data: dict, metadata: Optional[dict]) -> dict:
    """校验1: 核心主干环节内容占比 ≥70%"""
    if not metadata or metadata.get("_is_default"):
        return {
            "passed": True,
            "message": "无产业元数据，跳过核心主干占比校验",
            "ratio": None,
        }

    core_segments_raw = metadata.get("core_segments", [])
    # Handle both list of strings and list of dicts (LLM may return either format)
    core_segments = {s["name"] if isinstance(s, dict) else s for s in core_segments_raw if s}
    if not core_segments:
        return {"passed": True, "message": "元数据无核心主干定义，跳过校验", "ratio": None}

    # 统计所有环节
    segments = chain_data.get("chain_segments", {})
    all_segments = []
    for level in ["upstream", "midstream", "downstream", "supporting"]:
        for seg in segments.get(level, []):
            all_segments.append(seg.get("segment_name", ""))

    if not all_segments:
        return {"passed": False, "message": "无任何产业链环节数据", "ratio": 0}

    # 计算核心主干占比
    core_count = sum(1 for s in all_segments if s in core_segments)
    ratio = core_count / len(all_segments) if all_segments else 0

    passed = ratio >= 0.7
    return {
        "passed": passed,
        "message": f"核心主干环节占比 {ratio:.0%}（{core_count}/{len(all_segments)}），{'达标' if passed else '未达70%'}",
        "ratio": ratio,
        "core_count": core_count,
        "total_count": len(all_segments),
    }


def _check_derivative_ratio(chain_data: dict, metadata: Optional[dict]) -> dict:
    """校验2: 衍生赛道内容占比 ≤15%"""
    if not metadata or metadata.get("_is_default"):
        return {"passed": True, "message": "无产业元数据，跳过衍生赛道占比校验", "ratio": None}

    derivative_segments_raw = metadata.get("derivative_segments", [])
    # Handle both list of strings and list of dicts (LLM may return either format)
    derivative_segments = {s["name"] if isinstance(s, dict) else s for s in derivative_segments_raw if s}
    if not derivative_segments:
        return {"passed": True, "message": "元数据无衍生赛道定义，跳过校验", "ratio": 0}

    segments = chain_data.get("chain_segments", {})
    all_segments = []
    for level in ["upstream", "midstream", "downstream", "supporting"]:
        for seg in segments.get(level, []):
            all_segments.append(seg.get("segment_name", ""))

    if not all_segments:
        return {"passed": True, "message": "无环节数据", "ratio": 0}

    derivative_count = sum(1 for s in all_segments if s in derivative_segments)
    ratio = derivative_count / len(all_segments) if all_segments else 0

    passed = ratio <= 0.15
    return {
        "passed": passed,
        "message": f"衍生赛道占比 {ratio:.0%}（{derivative_count}/{len(all_segments)}），{'达标' if passed else '超过15%'}",
        "ratio": ratio,
    }


def _check_node_dimensions(chain_data: dict) -> dict:
    """校验3: 所有环节是否包含4个必填维度"""
    segments = chain_data.get("chain_segments", {})
    total = 0
    complete = 0
    dimension_names = ["functional_position", "value_proportion", "technical_barrier", "competitive_landscape"]

    for level in ["upstream", "midstream", "downstream", "supporting"]:
        for seg in segments.get(level, []):
            total += 1
            has_all = all(seg.get(dim) for dim in dimension_names)
            if has_all:
                complete += 1

    if total == 0:
        return {"passed": False, "message": "无任何产业链环节数据", "coverage": 0}

    coverage = complete / total if total else 0
    passed = coverage >= 0.8  # 至少80%的环节四维度完整

    return {
        "passed": passed,
        "message": f"节点四维度完整性: {complete}/{total} ({coverage:.0%}) 环节四维度完整",
        "coverage": coverage,
        "complete": complete,
        "total": total,
    }


def _check_transmission_relations(chain_data: dict) -> dict:
    """校验4: 是否存在 transmission_relations 且每条有传导类型"""
    transmissions = chain_data.get("transmission_relations", [])

    if not transmissions:
        return {
            "passed": False,
            "message": "缺少环节间传导关系数据（transmission_relations 为空）",
            "count": 0,
        }

    # 检查每条传导关系是否有传导类型
    valid_count = sum(1 for tr in transmissions if tr.get("transmission_type"))
    ratio = valid_count / len(transmissions) if transmissions else 0

    passed = ratio >= 0.8
    return {
        "passed": passed,
        "message": f"传导关系: {len(transmissions)} 条，其中 {valid_count} 条含传导类型 ({ratio:.0%})",
        "count": len(transmissions),
        "valid_count": valid_count,
    }


def _check_causal_logic(chain_data: dict) -> dict:
    """校验5: 是否存在 chain_causal_logic 且长度 ≥200字"""
    causal_logic = chain_data.get("chain_causal_logic", "")

    if not causal_logic:
        return {
            "passed": False,
            "message": "缺少产业链成因逻辑（chain_causal_logic 为空）",
            "length": 0,
        }

    length = len(causal_logic)
    passed = length >= 200

    return {
        "passed": passed,
        "message": f"产业链成因逻辑: {length}字，{'达标' if passed else '不足200字'}",
        "length": length,
    }


def _check_chapter_structure(chain_data: dict) -> dict:
    """校验6: 数据结构是否支持8章标准报告"""
    required_fields = [
        ("industry_description", "产业描述"),
        ("chain_segments", "产业链环节"),
        ("companies", "企业列表"),
    ]
    optional_but_expected = [
        ("chain_causal_logic", "产业链成因逻辑"),
        ("transmission_relations", "传导关系"),
        ("market_data", "市场数据"),
    ]

    missing_required = []
    for field, label in required_fields:
        if not chain_data.get(field):
            missing_required.append(label)

    missing_optional = []
    for field, label in optional_but_expected:
        if not chain_data.get(field):
            missing_optional.append(label)

    passed = len(missing_required) == 0

    messages = []
    if missing_required:
        messages.append(f"缺少必要数据: {', '.join(missing_required)}")
    if missing_optional:
        messages.append(f"缺少可选数据: {', '.join(missing_optional)}")

    message = "; ".join(messages) if messages else "章节数据结构完整"

    return {
        "passed": passed,
        "message": message,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
    }


def _check_data_source_compliance(chain_data: dict) -> dict:
    """校验7: 产业研究类数据占比 ≥80%"""
    try:
        from app.crawler.akshare_enricher import get_data_source_summary
        summary = get_data_source_summary(chain_data)
    except Exception:
        # 如果导入失败，手动统计
        total = 0
        industrial = 0
        for comp in chain_data.get("companies", []):
            tags = comp.get("_data_tags", {})
            for field, tag in tags.items():
                if comp.get(field):
                    total += 1
                    if tag == "industrial":
                        industrial += 1
        ratio = industrial / total if total > 0 else 1.0
        summary = {
            "industrial_ratio": ratio,
            "compliant": ratio >= 0.8,
            "total_fields": total,
            "industrial_count": industrial,
        }

    ratio = summary.get("industrial_ratio", 1.0)
    compliant = summary.get("compliant", True)

    if summary.get("total_fields", 0) == 0:
        return {
            "passed": True,
            "message": "无数据标签，跳过数据源合规校验",
            "ratio": None,
        }

    return {
        "passed": compliant,
        "message": f"产业研究类数据占比 {ratio:.0%}，{'达标' if compliant else '未达80%'}",
        "ratio": ratio,
        "total_fields": summary.get("total_fields", 0),
        "industrial_count": summary.get("industrial_count", 0),
    }


# 明确的「利好/利空/涨跌/买卖建议」类词汇（命中即视为违背情感中性原则）
_SENTIMENT_WORDS = [
    "利好", "利空", "看涨", "看跌", "看多", "看空",
    "强烈推荐", "买入评级", "卖出评级", "买入建议", "卖出建议",
    "暴涨", "暴跌", "大涨", "大跌",
]


def _check_sentiment_neutrality(chain_data: dict) -> dict:
    """
    校验8（软规则）：事件与风险叙述是否保持情感中性。

    参考 cwwindex 的 marketImpactInferred:false 原则——
    不暗示利好/利空、不推断股价/指数涨跌、不给出买卖建议。

    仅作告警（不影响 passed），便于人工复核。
    """
    hits = []

    # 1) 扫描事件（脉冲板块）
    for ev in chain_data.get("events", []) or []:
        if not isinstance(ev, dict):
            continue
        blob = " ".join([
            str(ev.get("title", "")),
            str(ev.get("summaryZh", "")),
            str(ev.get("impactZh", "")),
        ])
        found = [w for w in _SENTIMENT_WORDS if w in blob]
        if found:
            hits.append(f"事件「{ev.get('title', '')}」含情感词：{', '.join(found)}")

    # 2) 扫描风险与不确定性叙述
    narratives = chain_data.get("_narratives", {}) or {}
    risk_text = narratives.get("risk_analysis", "") or ""
    if risk_text:
        found = [w for w in _SENTIMENT_WORDS if w in risk_text]
        if found:
            hits.append(f"风险与不确定性分析含情感词：{', '.join(found)}")

    if hits:
        return {
            "passed": False,
            "message": "检测到可能违背情感中性的表述（仅告警，不影响报告生成）："
                       + "；".join(hits[:5])
                       + ("…" if len(hits) > 5 else ""),
            "hit_count": len(hits),
        }

    return {
        "passed": True,
        "message": "事件与风险叙述保持情感中性（未检测到利好/利空/涨跌暗示）",
        "hit_count": 0,
    }
