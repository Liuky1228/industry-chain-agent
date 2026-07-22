"""LLM 信息提取模块

使用 DeepSeek API 从研报文本中提取结构化信息：
- 第一轮：单研报提取（公司、主营业务、上下游关系、环节属性、传导关系）
- 第二轮：跨研报整合（去重、冲突消解、关系补全、三要素强制生成）
"""

import json
import logging
from openai import OpenAI, RateLimitError
from app.config import get_settings
from app.llm_common import LLMQuotaExceeded, raise_quota_error
from app.analyzer.event_schema import (
    EVENT_TAGS,
    EVIDENCE_STATUS,
    EVENT_POLICY,
    IMPACT_GUARDRAIL,
    DEFAULT_EVIDENCE_STATUS,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  Prompt 模板
# ─────────────────────────────────────────────

SINGLE_REPORT_PROMPT = """你是一位资深的产业分析师。请从以下研报中提取结构化信息。

要求：
1. **尽可能多地提取研报中提及的所有公司**（含上市公司和未上市公司），不要只提取主角公司，正文中提及的供应商、客户、竞争对手、合作伙伴都要提取
2. 对每家公司，提取：主营业务描述、核心产品/服务、主要客户（下游方向）、主要供应商（上游方向）
3. 判断每家公司在产业链中的位置（上游/中游/下游/配套服务）及判断依据
4. 提取研报中明确提到的产业链上下游关系
5. 仅从文本中提取信息，不要推测或编造不存在的信息
6. 如果提供了研报对应的股票信息，请确保该公司的股票代码和主营业务准确填写
7. 提取研报中的**产业研究类量化数据**：市场规模、产能、产量、国产化率、成本占比、技术迭代节点、行业认证周期等。优先提取产业运营数据，其次提取增长率、预测值等。仅提取研报中明确提及的数据，不要编造
8. 提取研报中关于产业链各环节的以下属性信息（如有提及）：
   - 该环节的功能定位（在产业链中的核心作用）
   - 该环节的价值占比（成本/价值占下游整机或对应环节的比例）
   - 该环节的技术壁垒（核心技术门槛、认证周期等）
   - 该环节的竞争格局（头部企业、国产化率、垄断情况）
9. 提取研报中关于上下游环节间传导关系的描述（如有）：
   - 传导类型：成本传导 / 技术传导 / 价值传导
   - 具体描述：上游什么属性的变化如何影响下游什么属性

【股票代码提取规则 — 重要】
- 如果研报元数据中提供了股票代码，该公司必须直接使用该代码，不要覆盖或留空
- 仔细扫描正文，A股代码通常为6位数字（如600519、000858、300750、688981）
- 常见格式：股票代码"XXXXXX"、代码XXXXXX、(XXXXXX.XX)、XXXXXX.SH/XXXXXX.SZ
- 如果文本中出现了6位数字代码且上下文指向某公司，请将该代码赋给对应公司
- 不确定时填null，不要猜测

以JSON格式输出，严格遵守以下schema：
{{
  "companies": [
    {{
      "name": "公司名称",
      "stock_code": "股票代码（优先使用元数据提供的代码，其次从正文中提取的6位数字代码，无则null）",
      "main_business": "主营业务一句话描述",
      "products": ["产品1", "产品2"],
      "upstream_partners": [{{"name": "上游公司名", "supply": "供应什么"}}],
      "downstream_partners": [{{"name": "下游公司名", "purchase": "购买什么"}}],
      "chain_position": "上游/中游/下游/配套服务",
      "chain_position_reason": "判断依据",
      "sub_segment": "细分环节，如正极材料、电芯制造等"
    }}
  ],
  "explicit_relations": [
    {{"from_company": "公司A", "to_company": "公司B", "type": "供应/采购/合作/竞争", "detail": "具体描述"}}
  ],
  "segment_attributes": [
    {{
      "segment_name": "环节名称（如：特种材料、减速器、电芯制造等）",
      "level": "上游/中游/下游",
      "functional_position": "该环节在产业链中的核心作用（如有提及，无则null）",
      "value_proportion": "该环节成本/价值占比数据（如有提及，无则null）",
      "technical_barrier": "技术壁垒描述（如有提及，无则null）",
      "competitive_landscape": "竞争格局描述（如有提及，无则null）"
    }}
  ],
  "transmission_info": [
    {{
      "from_segment": "上游环节名称",
      "to_segment": "下游环节名称",
      "transmission_type": "成本传导/技术传导/价值传导",
      "description": "传导逻辑描述"
    }}
  ],
  "industry_summary": "研报中对行业整体情况的摘要",
  "key_data_points": ["关键数据点1", "关键数据点2"],
  "market_data": {{
    "market_size": "当前市场规模描述（如：2023年全球市场规模约500亿元），无则null",
    "growth_rate": "近年增长率（如：2023年同比增长25%），无则null",
    "forecast": "未来预测（如：预计2028年达到2000亿元，CAGR约30%），无则null",
    "key_drivers": ["市场驱动因素1", "驱动因素2"],
    "policy_environment": "相关政策法规或产业政策描述，无则null",
    "competition_landscape": "竞争格局概述（如：CR5约60%，头部集中度较高），无则null"
  }}
}}

研报标题：{report_title}
{report_meta}
研报内容：
{report_text}"""


MERGE_PROMPT = """你是一位资深产业研究员，正在为**产业研究机构**撰写产业链分析报告的核心数据整合。
以下是从多份关于"{industry_name}"产业链的研报中提取的信息。
请进行跨研报整合分析，遵循**产业生产逻辑**（而非资本流动逻辑）。

{metadata_section}

【整合要求】
1. 合并同一公司的重复信息，取最完整、最新的描述
2. 如果不同研报对同一公司的产业链定位有冲突，取多数意见并在reason中标注分歧
3. 根据已提取的上下游关系，推断可能的间接产业链关系（如A供应B、B供应C → A是C的间接上游）
4. 将每家公司归入产业链的四个层级之一：上游、中游、下游、配套服务
5. 为每个层级细分具体环节（如锂电池产业链上游可分为锂矿、正极材料、负极材料等），**每个层级至少细分2-3个环节**
6. 每家公司的"主营业务"必须填写，用一句话描述其核心业务
7. **确保产业链覆盖的全面性**：不要过度剔除公司，只要与产业链有一定关联的公司都应保留。目标：至少覆盖 20 家企业和 8 个细分环节。除了研报中提取的公司外，如果你知道该产业链中其他重要的A股上市公司（尤其是各环节的龙头或代表性企业），也请补充进来
8. 综合多份研报中的市场数据，整合出该产业的市场规模、增长率、预测、驱动因素等。如果不同研报的数据有差异，取最新或多数意见
{seed_company_section}

【产业链三要素 — 强制生成（P0级要求）】
以下三项是产业链分析的核心骨架，必须同时生成，缺一不可：

**要素一：环节节点四维度**
每个 chain_segments 中的环节，除了 segment_name/description/companies/concentration 外，还必须包含以下 4 个维度：
- functional_position：该环节在产业链中的核心功能定位（≥20字，用产业研究专业术语表述）
- value_proportion：该环节成本/价值占下游整机或对应环节的具体比例（无公开数据时标注"行业通用估值"）
- technical_barrier：核心技术门槛、行业认证周期等关键约束
- competitive_landscape：全球/国内市场的头部企业、垄断情况、国产化率水平

**要素二：环节间传导关系**
在 transmission_relations 中，为每两个相邻环节之间配置 1 种传导类型（成本传导/技术传导/价值传导），并撰写具体的传导逻辑描述。
格式示例："特种材料的技术突破，直接提升火箭壳体的强度/重量比，降低中游火箭制造的加工难度与单位成本"

**要素三：产业链成因逻辑**
在 chain_causal_logic 中，用 ≥300 字的完整文本解释"为什么产业链是这样构成的"。
要求：
- 说明各环节存在的必然性和先后逻辑关系
- 基于产业物理属性或商业逻辑，而非人为划分
- 不得使用"政策支持、技术迭代"等空泛套话，必须有具体的产业场景支撑

【数据来源约束 — 必须遵守】
- 分析依据必须**优先使用产业研究类数据**：产能、产量、国产化率、技术迭代节点、成本占比、行业认证周期、产能规模、政策规划落地数据等
- **金融行情类数据**（个股涨幅、市值、资金流向、PE/PB估值）**不得作为环节分析的核心支撑依据**
- 金融数据仅可在"企业基本信息"中作为补充，且全文占比不得超过10%
- **关系证据化（重要）**：relation 必须带 evidenceStatus（VERIFIED=一手官方披露 / REPORTED=研报等二手可信来源 / INFERRED=由文本推断 / UNVERIFIED=未核实）。本系统来源为研报，默认填 REPORTED，不要填 VERIFIED；sourceTitle 填该关系所依据的具体研报标题，便于前端回溯来源。

【股票代码填写规则 — 极其重要】
- 第一优先级：从下方"已提取的研报信息"中查找该公司的股票代码。如果任何一份研报中已提取到该公司的代码，必须直接继承使用
- 第二优先级：如果研报元数据中提供了某公司的股票代码，请使用该代码
- 第三优先级：如果你确实知道某家A股上市公司的代码（6位数字，如600519、000858、300750、688981），可以填写
- 如果以上都无法确定，填null — 不要猜测或编造代码
- 注意：非A股上市公司（如港股、美股）的代码格式不同，如有请标注（如02190.HK、NVDA等）

以JSON格式输出，严格遵守以下schema：
{{
  "industry_name": "{industry_name}",
  "industry_description": "产业链整体描述（包含产业定义、边界、战略定位）",
  "chain_segments": {{
    "upstream": [
      {{
        "segment_name": "环节名",
        "description": "环节描述",
        "companies": ["公司1", "公司2"],
        "concentration": "高/中/低",
        "functional_position": "该环节在产业链中的核心功能定位（≥20字）",
        "value_proportion": "成本/价值占比（无数据标注'行业通用估值'）",
        "technical_barrier": "核心技术门槛、认证周期等",
        "competitive_landscape": "头部企业、国产化率水平"
      }}
    ],
    "midstream": [
      {{
        "segment_name": "环节名",
        "description": "环节描述",
        "companies": ["公司1", "公司2"],
        "concentration": "高/中/低",
        "functional_position": "该环节在产业链中的核心功能定位（≥20字）",
        "value_proportion": "成本/价值占比",
        "technical_barrier": "核心技术门槛、认证周期等",
        "competitive_landscape": "头部企业、国产化率水平"
      }}
    ],
    "downstream": [
      {{
        "segment_name": "环节名",
        "description": "环节描述",
        "companies": ["公司1", "公司2"],
        "concentration": "高/中/低",
        "functional_position": "该环节在产业链中的核心功能定位（≥20字）",
        "value_proportion": "成本/价值占比",
        "technical_barrier": "核心技术门槛、认证周期等",
        "competitive_landscape": "头部企业、国产化率水平"
      }}
    ],
    "supporting": [
      {{
        "segment_name": "环节名",
        "description": "环节描述",
        "companies": ["公司1", "公司2"],
        "functional_position": "该环节在产业链中的核心功能定位（≥20字）",
        "value_proportion": "成本/价值占比",
        "technical_barrier": "核心技术门槛、认证周期等",
        "competitive_landscape": "头部企业、国产化率水平"
      }}
    ]
  }},
  "companies": [
    {{
      "name": "公司名称",
      "stock_code": "股票代码（优先从已提取数据中继承，A股6位数字如600519；港股如02190.HK；美股如NVDA；无则null）",
      "main_business": "主营业务（必须填写，一句话描述核心业务）",
      "products": ["产品1"],
      "chain_position": "上游/中游/下游/配套服务",
      "sub_segment": "细分环节",
      "market_position": "行业地位描述",
      "key_metrics": "关键产业/业务数据（优先使用产业研究类数据，非金融行情数据）"
    }}
  ],
  "relations": [
    {{"from_company": "A", "to_company": "B", "type": "供应/采购/合作/竞争", "detail": "描述", "confidence": 0.9, "sourceTitle": "该关系出自的研报标题", "sourceUrl": "", "evidenceStatus": "REPORTED"}}
  ],
  "transmission_relations": [
    {{
      "from_segment": "上游环节名称",
      "to_segment": "下游环节名称",
      "transmission_type": "成本传导/技术传导/价值传导",
      "description": "上游环节的什么属性变化，会影响下游环节的什么属性变化（具体描述）"
    }}
  ],
  "chain_flow": "产业链流转路径，如：锂矿→碳酸锂→正极材料→电芯→整车",
  "chain_causal_logic": "产业链成因逻辑（≥300字）：解释为什么产业链是这样构成的，各环节存在的必然性和先后逻辑关系",
  "market_data": {{
    "market_size": "综合多份研报后的市场规模描述（如：2023年中国市场规模约500亿元，同比增长25%）",
    "forecast": "未来市场预测（如：预计2028年达到2000亿元，CAGR约30%）",
    "key_drivers": ["核心驱动因素1", "驱动因素2", "驱动因素3"],
    "policy_environment": "产业政策和监管环境概述",
    "competition_landscape": "竞争格局概述（集中度、头部企业份额等）",
    "risks": ["行业风险因素1", "风险因素2"],
    "opportunities": ["行业发展机遇1", "机遇2"]
  }}
}}

已提取的研报信息：
{extracted_data}"""


def _get_client() -> OpenAI:
    """获取 DeepSeek 客户端（max_retries=0 避免 429 时无意义重试）"""
    settings = get_settings()
    return OpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        max_retries=0,
    )


def _strip_think_tags(text: str) -> str:
    """移除 LLM 响应中的 <think>...</think> 推理块（MiniMax-M3 等模型会输出思考过程）

    兼容以下格式：
    - <think>...</think>\n实际内容
    - <think>\n多行\n</think>\n实际内容
    - 不包含 think 标签时原样返回
    """
    import re
    if not text:
        return text
    # 移除所有 <think>...</think> 块（非贪婪、跨行）
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return cleaned.strip()


def _call_llm(prompt: str, temperature: float = 0.3, max_tokens: int = 8000) -> tuple[str, str]:
    """调用 DeepSeek API，返回 (content, finish_reason)

    Raises:
        LLMQuotaExceeded: 当 API 返回 429（配额/余额耗尽）时抛出，不应重试
    """
    settings = get_settings()
    client = _get_client()

    try:
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except RateLimitError as e:
        raise_quota_error(e)

    content = response.choices[0].message.content if response.choices else None
    finish_reason = response.choices[0].finish_reason if response.choices else "unknown"
    if not content:
        raise ValueError(f"LLM returned empty response (finish_reason={finish_reason})")
    # 移除 MiniMax-M3 等模型的 <think>...</think> 推理块
    content = _strip_think_tags(content)
    return content.strip(), finish_reason


def _try_repair_truncated_json(text: str) -> dict:
    """尝试修复被截断的 JSON（LLM 输出超出 max_tokens 时常见）"""
    import re

    # 策略1: 找到最后一个完整的对象，截断到那里
    # 尝试在 companies/relations 数组中找到可以截断的位置
    for key in ["companies", "relations", "chain_segments"]:
        pattern = rf'"{key}"\s*:\s*\['
        match = re.search(pattern, text)
        if match:
            array_start = match.end()
            # 从后往前找最后一个完整的 } 或 ]
            depth = 0
            last_valid_pos = array_start
            in_string = False
            escape_next = False

            for i in range(array_start, len(text)):
                ch = text[i]
                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\':
                    escape_next = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch in '{[':
                    depth += 1
                elif ch in '}]':
                    depth -= 1
                    if depth == 0:
                        last_valid_pos = i + 1

            # 尝试截断到最后一个完整元素
            truncated = text[:last_valid_pos]
            # 补全括号
            open_braces = truncated.count('{') - truncated.count('}')
            open_brackets = truncated.count('[') - truncated.count(']')
            truncated += ']' * max(0, open_brackets)
            truncated += '}' * max(0, open_braces)

            try:
                result = json.loads(truncated)
                logger.info(f"JSON 修复成功 (截断修复, key={key})")
                return result
            except json.JSONDecodeError:
                pass

    # 策略2: 简单补全所有开括号
    truncated = text.rstrip()
    open_braces = truncated.count('{') - truncated.count('}')
    open_brackets = truncated.count('[') - truncated.count(']')
    truncated += ']' * max(0, open_brackets)
    truncated += '}' * max(0, open_braces)

    try:
        result = json.loads(truncated)
        logger.info("JSON 修复成功 (简单括号补全)")
        return result
    except json.JSONDecodeError:
        pass

    return {}


def _parse_json_response(text: str, finish_reason: str = "") -> dict:
    """从 LLM 响应中提取 JSON，支持截断修复"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 代码块
    import re
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试提取 { ... } 块
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # 如果输出被截断（finish_reason == "length"），尝试修复
    if finish_reason == "length":
        logger.warning("LLM 输出被截断 (finish_reason=length)，尝试修复 JSON...")
        repaired = _try_repair_truncated_json(text)
        if repaired:
            return repaired

    logger.error(f"无法从 LLM 响应中解析 JSON (finish_reason={finish_reason}): {text[:500]}...")
    return {}


# ─────────────────────────────────────────────
#  研报相关性过滤
# ─────────────────────────────────────────────

RELEVANCE_FILTER_PROMPT = """你是一位严格的产业研究专家。请判断以下研报是否与"{industry_name}"产业链直接相关。

【判断依据】每份研报提供两个信息：
- 标题：研报/公告的标题
- 发布公司：发布该研报或公告的上市公司名称（若是该公司自身的公告、财报、分红、定增等，则该公司与内容高度相关）

【重要】判断必须严格。研报应与该产业本身直接相关，仅仅在标题或正文中附带提及该产业的不算相关。但请充分利用"发布公司"线索：
- 若发布公司本身就是该产业的核心企业（如该产业的设备商、材料商、制造商、设计公司、上游供应商等），即使标题是通用的"权益分派公告""年度报告""定增预案""股权激励"等，也应视为相关（给 3-4 分），因为该公司属于该产业、其公告天然反映产业动态。
- 若发布公司与该产业无关（如食品、煤炭、房地产、银行等行业的公司），则无论标题如何，都应给 1-2 分。

评分标准：
- 5分：研报核心主题完全围绕该产业（如标题直接包含产业名称或其核心子领域）
- 4分：研报核心主题是该产业的关键细分技术、核心零部件、直接上下游，或发布公司是该产业核心企业且其公告/研报直接涉及自身经营
- 3分：研报主题与该产业有一定关联但并非核心（如应用领域、边缘技术），或发布公司属于该产业但研报内容偏通用
- 2分：研报核心主题属于其他产业，仅间接或附带提及该产业
- 1分：研报与该产业完全无关

注意：以下情况应评为1-2分：
- 标题是关于其他行业的周报/日报/策略，只是正文中提到了目标产业，且发布公司也与目标产业无关
- 标题是关于宏观经济、大盘策略的
- 发布公司与目标产业完全不相关（即使标题里碰巧出现了产业相关字眼）

请逐行输出结果，每行格式：序号|评分
不要输出其他任何内容。

研报列表：
{reports_list}"""


def filter_relevant_reports(
    industry_name: str,
    parsed_reports: list[dict],
    threshold: int = 2,
    min_keep: int = 2,
) -> list[dict]:
    """
    过滤不相关的研报

    用 LLM 对每份研报的【标题 + 发布公司】进行相关性打分
    （方案 A：补充 stock_name 信号，避免"标题泛泛但公司确属该产业"的研报被误杀），
    只保留评分 >= threshold 的研报。

    Args:
        industry_name: 目标产业名称
        parsed_reports: 解析后的研报列表（每项含 title、stock_name 等）
        threshold: 最低相关性阈值（1-5，默认 2）
            - 阈值 2 = "边缘相关"也算保留（如其他产业周报附带提及目标产业、或产业公司发布的通用公告）
            - 阈值 3 = 仅保留"明确相关但不一定核心"
            - 阈值 4 = 仅保留"核心相关"（MiniMax-M3 评分偏严格时容易全过滤）
        min_keep: 过滤后最少保留的研报数。如果过滤结果 < min_keep，
                  不再回退到原列表（避免把不相关研报全放回去），
                  而是保留已过滤结果；若已过滤结果为空则向上层报错。

    Returns:
        过滤后的研报列表
    """
    if len(parsed_reports) <= 3:
        return parsed_reports

    reports_list = "\n".join(
        f"{i+1}. 标题：{r['title']}"
        + (f"；发布公司：{r['stock_name']}" if r.get('stock_name') else "")
        for i, r in enumerate(parsed_reports)
    )

    prompt = RELEVANCE_FILTER_PROMPT.format(
        industry_name=industry_name,
        reports_list=reports_list,
    )

    try:
        result_text, _ = _call_llm(prompt, temperature=0.1, max_tokens=1000)

        scores = {}
        for line in result_text.strip().split("\n"):
            line = line.strip()
            if "|" in line:
                parts = line.split("|")
                try:
                    idx = int(parts[0].strip()) - 1
                    score = int(parts[1].strip())
                    scores[idx] = score
                except (ValueError, IndexError):
                    continue

        filtered = []
        for i, report in enumerate(parsed_reports):
            score = scores.get(i, 3)
            if score >= threshold:
                filtered.append(report)
            else:
                logger.info(
                    f"过滤不相关研报: '{report['title'][:40]}' "
                    f"(相关度={score})"
                )

        # min_keep 保护（改法 C）：过滤后保留数过少时，
        # 【不再】回退到原列表（那会把不相关研报全放回去，
        # 污染后续 LLM 提取与参考研报附录），而是保留已过滤结果。
        # 若已过滤结果为空，由上层 if not parsed_reports 逻辑优雅报错，
        # 而不是带着垃圾跑完整个流程。
        if len(filtered) < min_keep:
            logger.warning(
                f"相关性过滤后仅剩 {len(filtered)} 份 < min_keep={min_keep}，"
                f"【不回退】保留已过滤的 {len(filtered)} 份研报 "
                f"(产业='{industry_name}', 阈值={threshold})"
            )
            return filtered

        logger.info(
            f"相关性过滤: {len(parsed_reports)} → {len(filtered)} 份"
            f" (产业='{industry_name}', 阈值={threshold})"
        )
        return filtered

    except Exception as e:
        logger.warning(f"相关性过滤失败，保留全部研报: {e}")
        return parsed_reports


def extract_single_report(report_title: str, report_text: str,
                          stock_name: str = None, stock_code: str = None) -> dict:
    """
    第一轮提取：从单份研报中提取结构化信息

    Args:
        report_title: 研报标题
        report_text: 研报全文

    Returns:
        结构化提取结果字典
    """
    # 文本过长时截断（保留前 50000 字符 ≈ 约 35000 token）
    max_text = 50000
    if len(report_text) > max_text:
        report_text = report_text[:max_text] + "\n\n[... 文本过长已截断 ...]"

    # 构建研报元数据上下文
    meta_parts = []
    if stock_name:
        meta_parts.append(f"研报对应股票：{stock_name}")
    if stock_code:
        meta_parts.append(f"股票代码：{stock_code}")
    report_meta = "\n".join(meta_parts) if meta_parts else ""

    prompt = SINGLE_REPORT_PROMPT.format(
        report_title=report_title,
        report_meta=report_meta,
        report_text=report_text,
    )

    try:
        result_text, finish_reason = _call_llm(prompt, temperature=0.2, max_tokens=16000)
        result = _parse_json_response(result_text, finish_reason)

        if not result:
            logger.warning(f"研报 '{report_title}' 提取结果为空 (finish_reason={finish_reason})")
            return {}

        logger.info(
            f"研报 '{report_title}' 提取完成: "
            f"{len(result.get('companies', []))} 家公司, "
            f"{len(result.get('explicit_relations', []))} 条关系, "
            f"{len(result.get('segment_attributes', []))} 个环节属性, "
            f"{len(result.get('transmission_info', []))} 条传导关系"
        )
        return result

    except LLMQuotaExceeded:
        # 配额耗尽错误必须向上抛出，不能返回空字典
        raise
    except Exception as e:
        logger.error(f"研报 '{report_title}' 提取失败: {e}")
        return {}


def _build_fallback_chain_data(industry_name: str, extracted_results: list[dict]) -> dict:
    """
    降级兜底：当 LLM 整合失败时，基于第一轮提取结果直接聚合产业链数据。
    保证 pipeline 不因为 LLM 整合失败而整体失败。
    """
    logger.warning("使用降级方案从提取结果聚合产业链数据")

    # 1. 聚合并去重公司
    companies_map: dict[str, dict] = {}
    for r in extracted_results:
        for c in r.get("companies", []):
            name = c.get("name")
            if not name:
                continue
            if name not in companies_map:
                companies_map[name] = {
                    "name": name,
                    "stock_code": c.get("stock_code"),
                    "main_business": c.get("main_business", "")
                    or f"{industry_name}产业链相关企业",
                    "products": c.get("products", []) or [],
                    "chain_position": c.get("chain_position", "中游"),
                    "sub_segment": c.get("sub_segment", ""),
                    "market_position": "",
                    "key_metrics": "",
                }
            else:
                existing = companies_map[name]
                # 补充更完整的信息
                if c.get("main_business") and len(c["main_business"]) > len(existing["main_business"]):
                    existing["main_business"] = c["main_business"]
                if c.get("stock_code"):
                    existing["stock_code"] = c["stock_code"]
                if c.get("sub_segment") and not existing["sub_segment"]:
                    existing["sub_segment"] = c["sub_segment"]

    companies = list(companies_map.values())

    # 2. 按层级分组
    level_map = {"上游": "upstream", "中游": "midstream", "下游": "downstream", "配套服务": "supporting"}
    level_order = ["上游", "中游", "下游", "配套服务"]

    # 3. 从 segment_attributes 聚合环节信息
    segments_map: dict[str, dict] = {}
    for r in extracted_results:
        for sa in r.get("segment_attributes", []):
            seg_name = sa.get("segment_name", "").strip()
            level = sa.get("level", "中游")
            if not seg_name or level not in level_map:
                continue
            key = f"{level_map[level]}::{seg_name}"
            if key not in segments_map:
                segments_map[key] = {
                    "level_key": level_map[level],
                    "segment_name": seg_name,
                    "description": f"{seg_name}是{industry_name}产业链{level}的重要环节",
                    "companies": set(),
                    "concentration": "中",
                    "functional_position": sa.get("functional_position", "")
                    or f"{seg_name}在{industry_name}产业链中承担核心功能",
                    "value_proportion": sa.get("value_proportion", "")
                    or "行业通用估值",
                    "technical_barrier": sa.get("technical_barrier", "")
                    or "技术门槛较高，需持续研发投入",
                    "competitive_landscape": sa.get("competitive_landscape", "")
                    or "竞争格局较为分散",
                }
            else:
                existing = segments_map[key]
                for field in ["functional_position", "value_proportion", "technical_barrier", "competitive_landscape"]:
                    if sa.get(field) and not existing.get(field):
                        existing[field] = sa[field]

    # 4. 将公司归入对应环节；无对应环节则按层级创建默认环节
    for c in companies:
        level = c.get("chain_position", "中游")
        if level not in level_map:
            level = "中游"
        level_key = level_map[level]
        sub_segment = c.get("sub_segment", "").strip()

        placed = False
        if sub_segment:
            for key, seg in segments_map.items():
                if seg["level_key"] == level_key and seg["segment_name"] == sub_segment:
                    seg["companies"].add(c["name"])
                    placed = True
                    break
        if not placed:
            # 创建默认环节
            default_seg_name = sub_segment or f"{level}核心环节"
            key = f"{level_key}::{default_seg_name}"
            if key not in segments_map:
                segments_map[key] = {
                    "level_key": level_key,
                    "segment_name": default_seg_name,
                    "description": f"{default_seg_name}是{industry_name}产业链{level}的核心环节",
                    "companies": set(),
                    "concentration": "中",
                    "functional_position": f"{default_seg_name}在{industry_name}产业链中承担核心功能",
                    "value_proportion": "行业通用估值",
                    "technical_barrier": "技术门槛较高，需持续研发投入",
                    "competitive_landscape": "竞争格局较为分散",
                }
            segments_map[key]["companies"].add(c["name"])

    # 5. 构建 chain_segments
    chain_segments = {"upstream": [], "midstream": [], "downstream": [], "supporting": []}
    for seg in segments_map.values():
        seg_copy = {
            "segment_name": seg["segment_name"],
            "description": seg["description"],
            "companies": sorted(seg["companies"]),
            "concentration": seg["concentration"],
            "functional_position": seg["functional_position"],
            "value_proportion": seg["value_proportion"],
            "technical_barrier": seg["technical_barrier"],
            "competitive_landscape": seg["competitive_landscape"],
        }
        chain_segments[seg["level_key"]].append(seg_copy)

    # 确保每个层级至少有一个环节
    for level_key, level_cn in [("upstream", "上游"), ("midstream", "中游"), ("downstream", "下游"), ("supporting", "配套服务")]:
        if not chain_segments[level_key]:
            chain_segments[level_key].append({
                "segment_name": f"{level_cn}核心环节",
                "description": f"{level_cn}核心环节是{industry_name}产业链的重要组成部分",
                "companies": [],
                "concentration": "中",
                "functional_position": f"{level_cn}核心环节在{industry_name}产业链中承担核心功能",
                "value_proportion": "行业通用估值",
                "technical_barrier": "技术门槛较高",
                "competitive_landscape": "竞争格局较为分散",
            })

    # 6. 聚合关系
    relations = []
    seen_relations = set()
    for r in extracted_results:
        for rel in r.get("explicit_relations", []):
            from_c = rel.get("from_company", "")
            to_c = rel.get("to_company", "")
            rtype = rel.get("type", "关联")
            detail = rel.get("detail", "")
            if not from_c or not to_c:
                continue
            key = (from_c, to_c, rtype, detail)
            if key not in seen_relations:
                seen_relations.add(key)
                relations.append({
                    "from_company": from_c,
                    "to_company": to_c,
                    "type": rtype,
                    "detail": detail,
                    "confidence": 0.7,
                    "sourceTitle": "",
                    "sourceUrl": "",
                    "evidenceStatus": "INFERRED",
                })

    # 7. 聚合传导关系
    transmission_relations = []
    seen_trans = set()
    for r in extracted_results:
        for t in r.get("transmission_info", []):
            from_seg = t.get("from_segment", "")
            to_seg = t.get("to_segment", "")
            ttype = t.get("transmission_type", "成本传导")
            desc = t.get("description", "")
            if not from_seg or not to_seg:
                continue
            key = (from_seg, to_seg, ttype)
            if key not in seen_trans:
                seen_trans.add(key)
                transmission_relations.append({
                    "from_segment": from_seg,
                    "to_segment": to_seg,
                    "transmission_type": ttype,
                    "description": desc or f"{from_seg}的变化会传导至{to_seg}",
                })

    # 8. 生成简化的成因逻辑
    segment_names = []
    for level_key in ["upstream", "midstream", "downstream", "supporting"]:
        names = [s["segment_name"] for s in chain_segments[level_key]]
        if names:
            segment_names.extend(names)
    chain_flow = "→".join(segment_names[:8]) if segment_names else f"{industry_name}产业链"
    chain_causal_logic = (
        f"{industry_name}产业链的形成源于产品从原材料到终端应用的自然分工。"
        f"上游环节提供核心原材料与关键零部件，中游环节负责整机制造与集成，"
        f"下游环节面向具体应用场景交付最终产品与服务，配套服务则为全流程提供支撑。"
        f"各环节之间通过供需关系、技术传递与成本传导形成紧密协作。"
        f"产业链主要流转路径为：{chain_flow}。"
    )

    # 9. 聚合市场数据
    market_data = {
        "market_size": "",
        "forecast": "",
        "key_drivers": [],
        "policy_environment": "",
        "competition_landscape": "",
        "risks": [],
        "opportunities": [],
    }
    drivers_set = set()
    for r in extracted_results:
        md = r.get("market_data", {})
        if md.get("market_size") and not market_data["market_size"]:
            market_data["market_size"] = md["market_size"]
        if md.get("forecast") and not market_data["forecast"]:
            market_data["forecast"] = md["forecast"]
        if md.get("policy_environment") and not market_data["policy_environment"]:
            market_data["policy_environment"] = md["policy_environment"]
        if md.get("competition_landscape") and not market_data["competition_landscape"]:
            market_data["competition_landscape"] = md["competition_landscape"]
        for d in md.get("key_drivers", []):
            if d:
                drivers_set.add(d)
    market_data["key_drivers"] = list(drivers_set)[:5] or ["市场需求增长", "技术迭代", "政策支持"]
    market_data["risks"] = ["市场竞争加剧", "原材料价格波动"]
    market_data["opportunities"] = ["国产替代加速", "应用场景拓展"]

    result = {
        "industry_name": industry_name,
        "industry_description": f"{industry_name}产业链涵盖从上游原材料与核心零部件，到中游整机制造与集成，再到下游应用及配套服务的完整产业生态。",
        "chain_segments": chain_segments,
        "companies": companies,
        "relations": relations,
        "transmission_relations": transmission_relations,
        "chain_flow": chain_flow,
        "chain_causal_logic": chain_causal_logic,
        "market_data": market_data,
    }

    logger.info(
        f"降级聚合完成: {len(companies)} 家公司, "
        f"{sum(len(v) for v in chain_segments.values())} 个环节, "
        f"{len(relations)} 条关系"
    )
    return result


def merge_and_analyze(
    industry_name: str,
    extracted_results: list[dict],
    seed_companies: list[str] | None = None,
    industry_metadata: dict | None = None,
) -> dict:
    """
    第二轮分析：跨研报整合，构建完整产业链

    Args:
        industry_name: 产业名称
        extracted_results: 所有研报的第一轮提取结果
        seed_companies: 种子公司名列表（来自 LLM 扩展 + AKShare），确保纳入最终结果
        industry_metadata: 产业元数据（来自 industry_metadata 模块），用于约束产业边界

    Returns:
        完整的产业链分析结果
    """
    # 过滤空结果
    valid_results = [r for r in extracted_results if r]
    if not valid_results:
        logger.error("没有有效的提取结果可供整合")
        return {}

    # 构建整合输入 —— 按报告级别截断，保证 JSON 结构完整
    max_chars = 300000  # DeepSeek 有 1M token 上下文，300K 字符绰绰有余
    while valid_results:
        extracted_json = json.dumps(valid_results, ensure_ascii=False, indent=2)
        if len(extracted_json) <= max_chars:
            break
        # 移除最后一条研报，直到 JSON 大小合理
        removed = valid_results.pop()
        removed_companies = len(removed.get("companies", []))
        logger.info(
            f"整合输入过长({len(extracted_json)}字符)，移除一份研报"
            f"({removed_companies}家公司)，剩余{len(valid_results)}份"
        )

    if not valid_results:
        logger.error("截断后无有效数据")
        return {}

    logger.info(f"整合输入: {len(valid_results)}份研报, {len(extracted_json)}字符")

    # 构建种子公司提示段
    seed_company_section = ""
    if seed_companies:
        seed_list = "、".join(seed_companies)
        seed_company_section = (
            f"\n【种子公司列表 — 必须纳入】\n"
            f"以下是已知的\"{industry_name}\"产业链代表性上市公司，请确保它们全部出现在最终的 companies 列表中，"
            f"并为每家公司填写正确的产业链位置、细分环节和主营业务：\n"
            f"{seed_list}\n"
            f"如果上述公司中有些公司不在上方已提取的研报信息中，请根据你的知识补充其信息。"
        )
        logger.info(f"种子公司列表({len(seed_companies)}家): {seed_list}")

    # 构建产业元数据约束段
    metadata_section = ""
    if industry_metadata:
        from app.analyzer.industry_metadata import build_metadata_prompt_section
        metadata_section = build_metadata_prompt_section(industry_metadata)
        if metadata_section:
            logger.info("产业元数据约束已注入 MERGE_PROMPT")

    prompt = MERGE_PROMPT.format(
        industry_name=industry_name,
        extracted_data=extracted_json,
        seed_company_section=seed_company_section,
        metadata_section=metadata_section,
    )

    # ── LLM 调用（带截断重试 + 输入缩减降级）──
    result = {}
    max_attempts = 4
    current_results = list(valid_results)  # 使用副本，后续可能缩减

    for attempt in range(1, max_attempts + 1):
        try:
            # 前两次用正常输入，第三次缩减到一半，第四次缩减到1/4
            if attempt == 1:
                working_results = current_results
                temp = 0.3
            elif attempt == 2:
                working_results = current_results
                temp = 0.2
            elif attempt == 3:
                half = max(1, len(current_results) // 2)
                working_results = current_results[:half]
                temp = 0.2
                logger.warning(
                    f"前2次尝试失败，缩减输入到 {half} 份研报重试 (attempt={attempt})"
                )
            else:
                quarter = max(1, len(current_results) // 4)
                working_results = current_results[:quarter]
                temp = 0.1
                logger.warning(
                    f"前3次尝试失败，缩减输入到 {quarter} 份研报重试 (attempt={attempt})"
                )

            extracted_json = json.dumps(working_results, ensure_ascii=False, indent=2)
            attempt_prompt = MERGE_PROMPT.format(
                industry_name=industry_name,
                extracted_data=extracted_json,
                seed_company_section=seed_company_section,
                metadata_section=metadata_section,
            )

            result_text, finish_reason = _call_llm(attempt_prompt, temperature=temp, max_tokens=64000)
            logger.info(
                f"LLM 整合分析完成 (尝试 {attempt}/{max_attempts}), "
                f"研报数={len(working_results)}, "
                f"finish_reason={finish_reason}, 响应长度={len(result_text)}"
            )

            result = _parse_json_response(result_text, finish_reason)

            # 如果截断且解析失败，记录日志并重试
            if not result and finish_reason == "length":
                logger.warning(
                    f"LLM 输出被截断且 JSON 修复失败，准备重试 "
                    f"(响应长度={len(result_text)}, attempt={attempt})"
                )
                continue

            if not result:
                logger.error(
                    f"产业链整合分析结果为空 (finish_reason={finish_reason}), "
                    f"LLM原始响应前1000字符:\n{result_text[:1000]}"
                )
                continue

            # 验证结果至少包含 companies 或 chain_segments
            has_companies = bool(result.get("companies"))
            has_segments = bool(result.get("chain_segments"))
            if not has_companies and not has_segments:
                logger.error(
                    f"产业链整合分析结果缺少关键数据 "
                    f"(companies={has_companies}, chain_segments={has_segments})"
                )
                result = {}
                continue

            # 规整关系证据字段（补齐 sourceTitle/sourceUrl/evidenceStatus）
            if "relations" in result:
                result["relations"] = _normalize_relations(result.get("relations", []))

            # 成功，跳出重试循环
            break

        except Exception as e:
            logger.error(f"LLM 整合分析异常 (尝试 {attempt}/{max_attempts}): {e}", exc_info=True)
            # 最后一次尝试的异常也继续走到下方的降级聚合

    if not result:
        logger.error(f"产业链整合分析在 {max_attempts} 次尝试后均失败，启用降级聚合")
        return _build_fallback_chain_data(industry_name, valid_results)

    # 日志输出三要素生成情况
    transmission_count = len(result.get("transmission_relations", []))
    causal_logic = result.get("chain_causal_logic", "")
    causal_len = len(causal_logic) if causal_logic else 0

    # 统计环节四维度覆盖率
    segments = result.get("chain_segments", {})
    total_segs = 0
    segs_with_4dims = 0
    for level_key in ["upstream", "midstream", "downstream", "supporting"]:
        for seg in segments.get(level_key, []):
            total_segs += 1
            has_all = all(
                seg.get(k)
                for k in ["functional_position", "value_proportion",
                          "technical_barrier", "competitive_landscape"]
            )
            if has_all:
                segs_with_4dims += 1

    dim_rate = f"{segs_with_4dims}/{total_segs}" if total_segs > 0 else "0/0"

    logger.info(
        f"产业链分析完成 '{industry_name}': "
        f"{len(result.get('companies', []))} 家公司, "
        f"{len(result.get('relations', []))} 条关系 | "
        f"传导关系 {transmission_count} 条 | "
        f"成因逻辑 {causal_len} 字 | "
        f"环节四维度覆盖 {dim_rate}"
    )
    return result


def _normalize_relations(relations: list) -> list:
    """
    规整关系字段：
    - 补齐 sourceTitle/sourceUrl/evidenceStatus
    - evidenceStatus 限缩到合法值；来源为研报（二手），VERIFIED 一律降级为 REPORTED
    """
    valid = set(EVIDENCE_STATUS)
    out = []
    for rel in relations:
        if not isinstance(rel, dict):
            continue
        ev = rel.get("evidenceStatus", DEFAULT_EVIDENCE_STATUS)
        if ev == "VERIFIED":
            ev = "REPORTED"
        elif ev not in valid:
            ev = DEFAULT_EVIDENCE_STATUS
        out.append({
            "from_company": rel.get("from_company", ""),
            "to_company": rel.get("to_company", ""),
            "type": rel.get("type", "关联"),
            "detail": rel.get("detail", ""),
            "confidence": rel.get("confidence", 0.7),
            "sourceTitle": rel.get("sourceTitle", "") or "",
            "sourceUrl": rel.get("sourceUrl", "") or "",
            "evidenceStatus": ev,
        })
    return out


# ─────────────────────────────────────────────
#  产业链事件（脉冲）抽取
#  参考 cwwindex.today 的「72小时产业链脉冲」：
#  事件 = 已验证/已报道的事实事件证据流，不做情感/利好利空判断
# ─────────────────────────────────────────────

EVENT_EXTRACTION_PROMPT = """你是一位严谨的产业事件分析师。请从以下关于"{industry_name}"产业链的研报中，抽取近期发生的重大产业链事件。

【事件定义】
事件是「已发生或已披露的具体事实」，例如：产能投产/扩产、政策发布、并购重组、技术节点突破、产品发布、价格调整、监管调查、战略合作等。
事件必须来自研报中明确提及的内容，不要推测或编造。

【抽取要求】
1. 仅抽取与"{industry_name}"产业链直接相关、且信号强度高（对产业格局有实质影响）的事件
2. 每条事件标注：
   - date：事件日期（尽量从文本提取精确日期 YYYY-MM-DD；若只提到季度/年份，用该季度/年份的代表日期；不要编造精确日期）
   - title：一句话短标题
   - summaryZh：2-3 句中文摘要，仅陈述事实，不评价
   - sourceType：固定为 "研报"
   - sourceTitle：发现该事件的研报标题（必须是下方提供的某份研报标题）
   - sourceUrl：留空字符串 ""
   - tags：从受控词表中选择 1-3 个（{tags}），不要自造新标签
   - companies：事件直接涉及的上市公司/企业名称列表（仅限研报中提及的，可空）
   - evidenceStatus：因来源为研报（二手），默认 "REPORTED"；仅当 LLM 推断超出原文明示时用 "INFERRED"；绝不可用 "VERIFIED"
   - confidence：0-1 置信度
   - impactZh：事件影响说明，【必须】包含以下护栏原句：「本事件仅为事实陈述，不等同于订单金额、价格涨幅、官方指数或股价变动依据；已报道不代表确定结论，具体以原始披露为准。」
3. 严禁收录未经证实的市场传闻（rumorsAllowed=false）
4. 严禁推断利好/利空或股价/指数涨跌（marketImpactInferred=false）
5. 若研报中缺乏明确的产业链事件，返回空数组（不要编造填充）

以 JSON 格式输出，严格遵守以下 schema：
{{
  "events": [
    {{
      "id": "event-1",
      "date": "2026-07-10",
      "title": "事件短标题",
      "summaryZh": "事实摘要（仅陈述，不评价）",
      "sourceType": "研报",
      "sourceTitle": "研报标题",
      "sourceUrl": "",
      "tags": ["产能扩张"],
      "companies": ["公司A"],
      "evidenceStatus": "REPORTED",
      "confidence": 0.85,
      "impactZh": "护栏原句..."
    }}
  ]
}}

研报列表（标题 + 正文摘要）：
{reports_block}"""


def extract_events(
    parsed_reports: list[dict],
    industry_name: str,
    window_days: int = 90,
    max_events: int = 15,
) -> dict:
    """
    从过滤后的研报中抽取近期产业链事件（脉冲式），参考 cwwindex 72H 脉冲设计。

    Args:
        parsed_reports: Phase 2.5 过滤后的研报列表（含 title/text/stock_name 等）
        industry_name: 目标产业名称
        window_days: 数据窗口天数（由 main.py 按爬取 date_range_days 传入）
        max_events: 单份报告最多保留的事件数

    Returns:
        {
          "events": [...],                       # 规整后的事件列表
          "event_window": {...},                 # 窗口元信息（天数/生成时间/说明）
          "event_policy": {...},                 # 抽取政策（前端免责声明来源）
        }
    """
    if not parsed_reports:
        return {
            "events": [],
            "event_window": _build_event_window(window_days),
            "event_policy": EVENT_POLICY,
        }

    # 构造研报块（截断过长文本，控制 token；最多取前 30 份避免超长）
    reports_block_parts = []
    for i, r in enumerate(parsed_reports[:30], 1):
        title = r.get("title", f"研报{i}")
        text = r.get("text", "") or ""
        if len(text) > 8000:
            text = text[:8000] + "\n[...文本过长已截断...]"
        reports_block_parts.append(f"【研报{i}】{title}\n{text}")
    reports_block = "\n\n".join(reports_block_parts)

    tags_str = "、".join(EVENT_TAGS)
    prompt = EVENT_EXTRACTION_PROMPT.format(
        industry_name=industry_name,
        tags=tags_str,
        reports_block=reports_block,
    )

    try:
        result_text, finish_reason = _call_llm(prompt, temperature=0.2, max_tokens=8000)
        result = _parse_json_response(result_text, finish_reason)
        events = result.get("events", []) if isinstance(result, dict) else []
        # 规整 + 截断 + 注入护栏
        events = _normalize_events(events, max_events)
        logger.info(f"产业链事件抽取完成: {len(events)} 条")
    except Exception as e:
        logger.warning(f"产业链事件抽取失败（非致命，返回空列表）: {e}")
        events = []

    return {
        "events": events,
        "event_window": _build_event_window(window_days),
        "event_policy": EVENT_POLICY,
    }


def _build_event_window(window_days: int) -> dict:
    """构造事件窗口元信息"""
    from datetime import datetime
    return {
        "window_days": window_days,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "note": f"数据窗口为近 {window_days} 天（基于公开研报），非实时 72 小时脉冲。",
    }


def _normalize_events(events: list, max_events: int) -> list:
    """
    规整事件字段：
    - 类型安全
    - tags 限缩到受控词表
    - evidenceStatus 限缩到合法值（默认 REPORTED）
    - 强制注入影响护栏（去情绪化）
    """
    valid_tags = set(EVENT_TAGS)
    out = []
    for idx, ev in enumerate(events, 1):
        if not isinstance(ev, dict):
            continue

        raw_tags = ev.get("tags", []) or []
        tags = [t for t in raw_tags if t in valid_tags][:3]
        if not tags:
            tags = ["合作生态"]

        evidence = ev.get("evidenceStatus", DEFAULT_EVIDENCE_STATUS)
        # 我们来源是研报（二手），无法获得一手官方/监管披露，
        # 故「已验证(VERIFIED)」一律降级为「已报道(REPORTED)」，保持诚实一致
        if evidence == "VERIFIED":
            evidence = "REPORTED"
        elif evidence not in EVIDENCE_STATUS:
            evidence = DEFAULT_EVIDENCE_STATUS

        impact = ev.get("impactZh", "") or ""
        # 强制包含护栏原句（避免 LLM 漏写导致情感暗示）
        if IMPACT_GUARDRAIL[:20] not in impact:
            impact = (impact + " " + IMPACT_GUARDRAIL).strip()

        try:
            confidence = float(ev.get("confidence", 0.7) or 0.7)
        except (ValueError, TypeError):
            confidence = 0.7

        out.append({
            "id": ev.get("id") or f"event-{idx}",
            "date": str(ev.get("date") or ""),
            "title": str(ev.get("title") or ""),
            "summaryZh": str(ev.get("summaryZh") or ""),
            "sourceType": "研报",
            "sourceTitle": str(ev.get("sourceTitle") or ""),
            "sourceUrl": str(ev.get("sourceUrl") or ""),
            "tags": tags,
            "companies": ev.get("companies", []) or [],
            "evidenceStatus": evidence,
            "confidence": confidence,
            "impactZh": impact,
        })

        if len(out) >= max_events:
            break

    return out
