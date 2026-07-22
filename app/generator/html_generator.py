"""HTML 报告生成模块（与前端 ResultPage 展示 1:1 对齐）

生成一份「自包含」的 .html 报告：内联前端 App.css 全文，所有动态文本做 HTML
转义，markdown 章节（第六/八章）用 markdown2 在服务端渲染成静态 HTML。

章节顺序与前端 ResultPage 完全一致：
  第一章：产业链全景概览（定义、流转、市场规模）= 原1 + 原5
  第二章：产业链深度拆解 = 原3
  第三章：产业逻辑分析 = 原2 + 原4
  第四章：产业未来趋势与风险 = 原6 + 原8
  第五章：近期产业链动态 = 原9
  附录 · 重点企业分析
  附录 · 企业关系
  免责声明

注：与 docx_generator 不同，本模块完整复刻前端展示（含企业表/关系表/图谱），
且 markdown 章节是「渲染后」的 HTML，而非原文贴入。
"""

import os
import re
import html
import json
import logging
from datetime import datetime
import markdown2

logger = logging.getLogger(__name__)


# ── 证据状态 → (中文标签, 背景色, 前景色) ──
EVIDENCE_META = {
    "VERIFIED": ("已验证", "#d1fae5", "#065f46"),
    "REPORTED": ("已报道", "#dbeafe", "#1e40af"),
    "INFERRED": ("推断", "#f3f4f6", "#374151"),
    "UNVERIFIED": ("未核实", "#fee2e2", "#991b1b"),
}

# ── 事件标签 → (背景色, 前景色) ──
TAG_COLORS = {
    "产能扩张": ("#dbeafe", "#1e40af"),
    "政策法规": ("#ede9fe", "#5b21b6"),
    "并购重组": ("#fef3c7", "#92400e"),
    "技术突破": ("#d1fae5", "#065f46"),
    "价格变动": ("#ffedd5", "#9a3412"),
    "合规调查": ("#fee2e2", "#991b1b"),
    "合作生态": ("#ccfbf1", "#134e4a"),
}

CHAIN_TABS = [
    ("upstream", "上游"),
    ("midstream", "中游"),
    ("downstream", "下游"),
    ("supporting", "配套服务"),
]
NARRATIVE_KEYS = {
    "upstream": "node_analysis_upstream",
    "midstream": "node_analysis_midstream",
    "downstream": "node_analysis_downstream",
    "supporting": "derivative_segments",
}
TYPE_COLORS = {
    "成本传导": "#ef4444",
    "技术传导": "#3b82f6",
    "价值传导": "#10b981",
}


def esc(x):
    """HTML 转义，防止注入并避免破坏 HTML 结构。"""
    if x is None:
        return ""
    return html.escape(str(x))


def render_markdown(text):
    if not text:
        return ""
    return markdown2.markdown(
        text,
        extras=["tables", "fenced-code-blocks", "break-on-newline"],
    ) or ""


def _section(title, body, sid=None):
    id_attr = f' id="{esc(sid)}"' if sid else ""
    return (
        f'<div class="report-section"{id_attr}>'
        f'<h3 class="report-section-title">{esc(title)}</h3>'
        f'<div class="report-section-body">{body}</div>'
        f"</div>"
    )


def _unwrap(section_html):
    """从 _section(title, body) 的输出中提取内部 body（去掉外层章节包裹），用于把多章合并为一章。"""
    if not section_html:
        return ""
    m = re.search(r'<div class="report-section-body">(.*)</div>\s*</div>\s*$', section_html, re.S)
    return m.group(1) if m else section_html


def _append_section(sections, title, body, sid=None):
    """仅当 body 非空时才追加章节，避免合并后产生空标题章节。"""
    if body and body.strip():
        sections.append(_section(title, body, sid))


def _seg_card(seg, companies_index):
    name = seg.get("segment_name") or seg.get("name") or "未命名环节"
    parts = [f'<div class="segment-header"><h4>{esc(name)}</h4>']
    conc = seg.get("concentration")
    if conc:
        parts.append(
            f'<span class="concentration-tag concentration-{esc(conc)}">{esc(conc)}</span>'
        )
    parts.append("</div>")

    desc = seg.get("description")
    if desc:
        parts.append(f'<p class="segment-desc">{esc(desc)}</p>')

    attrs = [
        ("功能定位", seg.get("functional_position")),
        ("价值占比", seg.get("value_proportion")),
        ("技术壁垒", seg.get("technical_barrier")),
        ("竞争格局", seg.get("competitive_landscape")),
    ]
    attrs = [(l, v) for l, v in attrs if v]
    if attrs:
        rows = "".join(
            f'<div class="attr-row"><span class="attr-label">{esc(l)}</span>'
            f'<span class="attr-value">{esc(v)}</span></div>'
            for l, v in attrs
        )
        parts.append(f'<div class="segment-attrs">{rows}</div>')

    seg_comps = [c for c in (seg.get("companies") or []) if c]
    if seg_comps:
        COMPANIES_LIMIT = 10
        need_truncate = len(seg_comps) > COMPANIES_LIMIT

        def _chip(nm):
            c = companies_index.get(nm) or {"name": nm}
            code = c.get("stock_code")
            chip = (
                f'<span class="company-chip" title="{esc(c.get("main_business") or "")}">'
                f'{esc(c.get("name") or nm)}'
            )
            if code:
                chip += f'<span class="chip-code">{esc(code)}</span>'
            chip += "</span>"
            return chip

        first_chips = "".join(_chip(nm) for nm in seg_comps[:COMPANIES_LIMIT])
        if need_truncate:
            rest_chips = "".join(_chip(nm) for nm in seg_comps[COMPANIES_LIMIT:])
            n = len(seg_comps)
            toggle = (
                '<details class="company-chips-more">'
                '<summary class="seg-companies-toggle">'
                f'<span class="lbl-collapsed">展开全部 {n} 家</span>'
                '<span class="lbl-expanded">收起</span>'
                "</summary>"
                f'<div class="company-chips company-chips-more-inner">{rest_chips}</div>'
                "</details>"
            )
            chips_html = first_chips + toggle
            footer = (
                '<div class="chain-segment-companies-footer">'
                f'<span class="chain-segment-companies-count">共 {n} 家</span>'
                "</div>"
            )
        else:
            chips_html = first_chips
            footer = ""
        parts.append(
            '<div class="segment-companies"><span class="segment-label">代表企业：</span>'
            f'<div class="company-chips">{chips_html}</div>{footer}</div>'
        )
    return f'<div class="segment-card">{"".join(parts)}</div>'
def _ch1(chain_data, narratives, summary):
    parts = []
    desc = chain_data.get("industry_description")
    if desc:
        parts.append(f'<p class="section-text">{esc(desc)}</p>')
    nb = narratives.get("industry_boundary")
    if nb:
        parts.append(f'<div class="narrative-block"><p>{esc(nb)}</p></div>')
    cf = (summary or {}).get("chain_flow")
    if cf:
        parts.append(
            f'<div class="chain-flow-path">'
            f"<strong>产业链流转路径：</strong>{esc(cf)}</div>"
        )
    if not parts:
        return ""
    return _section("第一章  产业核心边界说明", "\n".join(parts))


def _ch2(chain_data, narratives):
    parts = []
    cl = narratives.get("causal_logic")
    if cl:
        parts.append(f'<div class="narrative-block"><p>{esc(cl)}</p></div>')
    ccl = chain_data.get("chain_causal_logic")
    if ccl:
        parts.append(
            f'<div class="causal-logic-block"><strong>产业链成因逻辑：</strong>'
            f"<p>{esc(ccl)}</p></div>"
        )
    if not parts:
        return ""
    return _section("第二章  产业链结构成因分析", "\n".join(parts))


def _ch3(chain_data, narratives, companies_index):
    segments = chain_data.get("chain_segments") or {}
    parts = []
    for key, label in CHAIN_TABS:
        segs = segments.get(key) or []
        if not segs:
            continue
        block = []
        narr = narratives.get(NARRATIVE_KEYS[key])
        if narr:
            block.append(f'<div class="narrative-block"><p>{esc(narr)}</p></div>')
        cards = "".join(_seg_card(s, companies_index) for s in segs)
        block.append(f'<div class="segments-list">{cards}</div>')
        parts.append(
            f'<div class="chain-tier"><h4 class="chain-tier-title">'
            f"{esc(label)}（{len(segs)} 个环节）</h4>"
            f'{"".join(block)}</div>'
        )
    if not parts:
        return ""
    return _section("第三章  产业链节点深度分析", "\n".join(parts))


def _ch4(chain_data, narratives):
    transmissions = chain_data.get("transmission_relations") or []
    parts = []
    narr = narratives.get("transmission_path")
    if narr:
        parts.append(f'<div class="narrative-block"><p>{esc(narr)}</p></div>')
    if transmissions:
        groups = {}
        for tr in transmissions:
            t = tr.get("transmission_type") or "其他"
            groups.setdefault(t, []).append(tr)
        gparts = []
        for t, items in groups.items():
            color = TYPE_COLORS.get(t, "#6b7280")
            items_html = ""
            for tr in items:
                flow = (
                    f'<span class="transmission-from">{esc(tr.get("from_segment"))}</span>'
                    '<span class="transmission-arrow">→</span>'
                    f'<span class="transmission-to">{esc(tr.get("to_segment"))}</span>'
                )
                desc = tr.get("description")
                desc_html = f'<p class="transmission-desc">{esc(desc)}</p>' if desc else ""
                items_html += (
                    f'<div class="transmission-item">'
                    f'<div class="transmission-flow">{flow}</div>{desc_html}</div>'
                )
            gparts.append(
                f'<div class="transmission-group">'
                f'<h4 class="transmission-group-title">'
                f'<span class="transmission-dot" style="background:{color}"></span>'
                f"{esc(t)}路径</h4>"
                f'<div class="transmission-list">{items_html}</div></div>'
            )
        parts.append(f'<div class="transmission-section">{"".join(gparts)}</div>')
    if not parts:
        return ""
    return _section("第四章  产业价值传导路径分析", "\n".join(parts))


def _ch5(chain_data, narratives):
    parts = []
    narr = narratives.get("industry_profile")
    if narr:
        parts.append(f'<div class="narrative-block"><p>{esc(narr)}</p></div>')
    md = chain_data.get("market_data") or {}
    if md and any(md.values()):
        grid = []
        for key, label in [
            ("market_size", "市场规模"),
            ("forecast", "市场预测"),
            ("competition_landscape", "竞争格局"),
            ("policy_environment", "政策环境"),
        ]:
            v = md.get(key)
            if v:
                grid.append(
                    f'<div class="market-data-item"><div class="market-data-label">{label}</div>'
                    f'<div class="market-data-value">{esc(v)}</div></div>'
                )
        if grid:
            parts.append(f'<div class="market-data-grid">{"".join(grid)}</div>')
        for key, label, cls in [
            ("key_drivers", "核心驱动因素", "driver"),
            ("opportunities", "发展机遇", "opportunity"),
            ("risks", "风险因素", "risk"),
        ]:
            arr = md.get(key) or []
            if arr:
                tags = "".join(
                    f'<span class="market-tag {cls}">{esc(d)}</span>' for d in arr
                )
                parts.append(
                    f'<div class="market-data-tags-section">'
                    f'<div class="market-data-label">{label}</div>'
                    f'<div class="market-data-tags">{tags}</div></div>'
                )
    if not parts:
        return ""
    return _section("第五章  产业总体画像", "\n".join(parts))


def _ch6(narratives):
    text = narratives.get("trend_deduction")
    if not text:
        return ""
    return _section(
        "第六章  产业未来趋势推演",
        f'<div class="trend-deduction-content"><div class="markdown-body">'
        f"{render_markdown(text)}</div></div>",
    )
def _ch8(narratives):
    text = narratives.get("risk_analysis")
    if not text:
        return ""
    return _section(
        "第八章  风险与不确定性",
        f'<div class="narrative-block"><div class="markdown-body">'
        f"{render_markdown(text)}</div></div>",
    )


def _ch9(chain_data):
    events = chain_data.get("events") or []
    reference_reports = chain_data.get("_reference_reports") or []
    window = chain_data.get("event_window") or {}
    policy = chain_data.get("event_policy") or {}
    disclaimer = policy.get("disclaimer") or (
        "本板块仅列已验证/已报道的事实事件，不构成任何投资建议；"
        "AI 不判断利好或利空，事件影响以原始披露为准。"
    )
    # 仅保留「能匹配到来源研报（且研报含可跳转链接）」的事件（与前端 EventTimeline 一致）
    matched = []
    for ev in events:
        rep = _find_event_report(ev.get("sourceTitle"), reference_reports)
        url = (rep.get("pdf_url") or rep.get("report_url")) if rep else None
        if url:
            matched.append((ev, url))
    sorted_ev = sorted(matched, key=lambda x: x[0].get("date") or "", reverse=True)
    parts = [f'<div class="event-disclaimer">{esc(disclaimer)}</div>']

    if not sorted_ev:
        wd = window.get("window_days") or "—"
        parts.append(
            f'<div class="event-empty">近 {esc(wd)} 天（基于公开研报）未抽取到带明确来源研报的重大产业链事件。'
            "<br>本板块仅呈现可回溯到具体研报来源的事实事件，不以空白填充。</div>"
        )
        return _section("第九章  近期产业链事件", "\n".join(parts), "recent-events")

    wd = window.get("window_days")
    gen = window.get("generated_at")
    win_items = (
        f'<span class="event-window-item">数据窗口：近 {esc(wd) if wd else "—"} 天</span>'
    )
    if gen:
        win_items += f'<span class="event-window-item">生成时间：{esc(gen)}</span>'
    win_items += f'<span class="event-window-item">事件数：{len(sorted_ev)}</span>'
    parts.append(f'<div class="event-window">{win_items}</div>')

    items_html = []
    for ev, url in sorted_ev:
        head = (
            f'<div class="event-card-head"><span class="event-title">'
            f'{esc(ev.get("title") or "（无标题）")}</span></div>'
        )
        tags = ev.get("tags") or []
        tags_html = ""
        if tags:
            tparts = []
            for t in tags:
                c = TAG_COLORS.get(t, ("#f3f4f6", "#374151"))
                tparts.append(
                    f'<span class="event-tag" style="background:{c[0]};color:{c[1]}">'
                    f"{esc(t)}</span>"
                )
            tags_html = f'<div class="event-tags">{"".join(tparts)}</div>'
        summary_html = (
            f'<p class="event-summary">{esc(ev.get("summaryZh") or "")}</p>'
            if ev.get("summaryZh")
            else ""
        )
        comps = ev.get("companies") or []
        comps_html = ""
        if comps:
            cparts = "".join(
                f'<span class="event-company">{esc(n)}</span>' for n in comps
            )
            comps_html = (
                f'<div class="event-companies"><span class="event-label">涉及企业：</span>'
                f"{cparts}</div>"
            )
        impact_html = (
            f'<div class="event-impact">{esc(ev.get("impactZh"))}</div>'
            if ev.get("impactZh")
            else ""
        )
        conf = ev.get("confidence")
        conf_html = (
            f'<span class="event-confidence">（置信度 {round((conf or 0) * 100)}%）</span>'
            if conf is not None
            else ""
        )
        src_html = (
            f'<div class="event-source">来源：'
            f'{esc(ev.get("sourceTitle") or ev.get("sourceType") or "研报")}{conf_html}</div>'
        )
        report_link = (
            f'<a class="event-report-link" href="{esc(url)}" '
            f'target="_blank" rel="noopener noreferrer">查看研报 →</a>'
        )
        items_html.append(
            f'<div class="event-item">'
            f'<div class="event-rail"><span class="event-dot"></span>'
            f'<span class="event-date">{esc(ev.get("date") or "日期未知")}</span></div>'
            f'<div class="event-card">{head}{tags_html}{summary_html}{comps_html}'
            f"{impact_html}{src_html}{report_link}</div></div>"
        )
    parts.append(f'<div class="event-list">{"".join(items_html)}</div>')
    return _section("第九章  近期产业链事件", "\n".join(parts), "recent-events")


def _key_companies(chain_data, companies_index):
    companies = chain_data.get("companies") or []

    def ok(c):
        if not (c.get("name") or "").strip():
            return False
        if not (c.get("stock_code") or "").strip():
            return False
        if not (c.get("chain_position") or "").strip():
            return False
        if not (c.get("sub_segment") or "").strip():
            return False
        if not (c.get("main_business") or "").strip():
            return False
        prods = c.get("products") or []
        if not isinstance(prods, list) or len(prods) == 0:
            return False
        if all((not (p or "").strip()) for p in prods):
            return False
        return True

    filtered = [c for c in companies if ok(c)]
    if not filtered:
        return ""

    rows = []
    for c in filtered[:30]:
        prods = c.get("products") or []
        prod_str = "、".join(prods[:3])
        rows.append(
            f"<tr>"
            f'<td class="company-name">{esc(c.get("name"))}</td>'
            f'<td><span class="stock-code">{esc(c.get("stock_code"))}</span></td>'
            f'<td><span class="position-tag position-{esc(c.get("chain_position"))}">'
            f'{esc(c.get("chain_position"))}</span></td>'
            f'<td>{esc(c.get("sub_segment"))}</td>'
            f'<td class="text-ellipsis" title="{esc(c.get("main_business"))}">'
            f'{esc(c.get("main_business"))}</td>'
            f'<td class="text-ellipsis" title="{esc(prod_str)}">{esc(prod_str)}</td>'
            f"</tr>"
        )
    more = (
        f'<p class="more-hint">共 {len(filtered)} 家企业，仅展示前 30 家</p>'
        if len(filtered) > 30
        else ""
    )
    body = (
        '<div class="companies-table-wrap"><table class="data-table">'
        "<thead><tr><th>企业名称</th><th>股票代码</th><th>产业链位置</th>"
        "<th>细分环节</th><th>主营业务</th><th>核心产品</th></tr></thead>"
        f'<tbody>{"".join(rows)}</tbody></table></div>{more}'
    )
    return _section("重点企业介绍", body, "key-companies")


def _find_related_reports(reports, company_a, company_b):
    """复刻前端 findRelatedReports：模糊匹配提及关系两端企业的参考研报。"""
    if not isinstance(reports, list) or not company_a:
        return []
    targets = [x for x in (company_a, company_b) if x]
    out = []
    for r in reports:
        haystack = f"{r.get('title') or ''} {r.get('stock_name') or ''}"
        if any(t and t in haystack for t in targets):
            out.append(r)
        if len(out) >= 5:
            break
    return out


def _find_event_report(source_title, reports):
    """根据事件 sourceTitle 匹配来源研报（与前端 EventTimeline.findEventReport 对齐）。

    后端保证事件的 sourceTitle 是「某份研报标题」，故用标题做包含匹配；
    返回带可跳转链接（pdf_url / report_url）的研报，找不到返回 None。
    """
    if not source_title or not isinstance(reports, list):
        return None
    for r in reports:
        rt = r.get("title") or ""
        if rt and (source_title == rt or source_title in rt or rt in source_title):
            return r
    return None


def _relations(chain_data):
    relations = chain_data.get("relations") or []
    reference_reports = chain_data.get("_reference_reports") or []
    # 仅保留「抽屉内相关研报不为空」的关系（与前端 ResultPage 一致）
    visible = [
        r for r in relations
        if _find_related_reports(reference_reports, r.get("from_company"), r.get("to_company"))
    ]
    if not visible:
        return ""
    rows = []
    for r in visible[:50]:
        type_cls = (r.get("type") or "").replace(" ", "-")
        related = _find_related_reports(reference_reports, r.get("from_company"), r.get("to_company"))
        payload = {
            "from": r.get("from_company") or "",
            "to": r.get("to_company") or "",
            "type": r.get("type") or "",
            "detail": r.get("detail") or "",
            "confidence": r.get("confidence") or 0,
            "evidenceStatus": r.get("evidenceStatus") or r.get("evidence_status") or "REPORTED",
            "related": [
                {"title": x.get("title") or "", "pdf_url": x.get("pdf_url") or x.get("report_url") or ""}
                for x in related
            ],
        }
        # 序列化为 data-rel 属性（单引号包裹；转义 &<>' 以免破坏属性/HTML 解析）
        safe = (
            json.dumps(payload, ensure_ascii=False)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("'", "&#39;")
        )
        rows.append(
            f'<tr class="relation-row-clickable" data-rel=\'{safe}\'>'
            f'<td class="company-name">{esc(r.get("from_company") or "-")}</td>'
            f'<td class="company-name">{esc(r.get("to_company") or "-")}</td>'
            f'<td><span class="relation-tag relation-{esc(type_cls)}">'
            f'{esc(r.get("type") or "-")}</span></td>'
            f'<td class="text-ellipsis" title="{esc(r.get("detail"))}">'
            f'{esc(r.get("detail") or "-")}</td>'
            f"</tr>"
        )
    more = (
        f'<p class="more-hint">共 {len(visible)} 条关系，仅展示前 50 条</p>'
        if len(visible) > 50
        else ""
    )
    body = (
        '<div class="relations-table-wrap"><table class="data-table">'
        "<thead><tr><th>供应方</th><th>需求方</th><th>关系类型</th>"
        "<th>详情</th></tr></thead>"
        f'<tbody>{"".join(rows)}</tbody></table></div>{more}'
    )
    return _section("产业链关系", body)


def _relation_drawer_html():
    """关系证据抽屉（HTML 报告内复刻前端 EvidenceInspector，纯静态 + 原生 JS）。"""
    return (
        '<div class="evidence-inspector-overlay" id="relDrawerOverlay" style="display:none">'
        '<aside class="evidence-inspector-drawer" id="relDrawer">'
        '<div class="evidence-inspector-header">'
        '<span class="evidence-inspector-kicker">证据详情</span>'
        '<button type="button" class="evidence-close-btn" id="relDrawerClose" aria-label="关闭">&times;</button>'
        "</div>"
        '<h2 class="evidence-relation-title" id="relDrawerTitle"></h2>'
        '<p class="evidence-relation-subtitle" id="relDrawerSubtitle"></p>'
        '<div class="evidence-info-cards" id="relDrawerCards"></div>'
        '<div class="evidence-block" id="relDrawerDetailBlock">'
        '<h4 class="evidence-block-title">关系详述</h4>'
        '<p class="evidence-block-text" id="relDrawerDetail"></p>'
        "</div>"
        '<div class="evidence-block" id="relDrawerReportsBlock">'
        '<h4 class="evidence-block-title">相关研报（提及此关系涉及企业）</h4>'
        '<div class="evidence-related-list" id="relDrawerReports"></div>'
        "</div>"
        "</aside>"
        "</div>"
    )


RELATION_DRAWER_JS = """
<script>
(function(){
  var META = {
    VERIFIED:{label:'已验证',bg:'#d1fae5',fg:'#065f46'},
    REPORTED:{label:'已报道',bg:'#dbeafe',fg:'#1e40af'},
    INFERRED:{label:'推断',bg:'#f3f4f6',fg:'#374151'},
    UNVERIFIED:{label:'未核实',bg:'#fee2e2',fg:'#991b1b'}
  };
  function esc(s){
    return (s==null?'':String(s)).replace(/[&<>"']/g,function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  var overlay=document.getElementById('relDrawerOverlay');
  function openDrawer(p){
    if(!p) return;
    document.getElementById('relDrawerTitle').innerHTML =
      esc(p.from)+' <span class="evidence-arrow">&rarr;</span> '+esc(p.to);
    var sub=document.getElementById('relDrawerSubtitle');
    if(p.detail){ sub.textContent=p.detail; sub.className='evidence-relation-subtitle'; }
    else { sub.textContent='（该关系未记录详细描述）'; sub.className='evidence-relation-subtitle evidence-muted'; }
    var meta=META[p.evidenceStatus]||META.REPORTED;
    var cards='';
    if(p.type){
      cards+='<div class="evidence-info-card"><span class="evidence-card-label">关系类型</span>'
        +'<span class="relation-tag relation-'+esc(p.type)+'">'+esc(p.type)+'</span></div>';
    }
    cards+='<div class="evidence-info-card"><span class="evidence-card-label">证据状态</span>'
      +'<span class="event-evidence" style="background:'+meta.bg+';color:'+meta.fg+'">'+meta.label+'</span></div>';
    cards+='<div class="evidence-info-card"><span class="evidence-card-label">置信度</span>'
      +'<span class="evidence-confidence">'+Math.round((Number(p.confidence)||0)*100)+'%</span></div>';
    document.getElementById('relDrawerCards').innerHTML=cards;
    var detailBlock=document.getElementById('relDrawerDetailBlock');
    if(p.detail){ detailBlock.style.display=''; document.getElementById('relDrawerDetail').textContent=p.detail; }
    else { detailBlock.style.display='none'; }
    var repBlock=document.getElementById('relDrawerReportsBlock');
    var repList=document.getElementById('relDrawerReports');
    if(p.related && p.related.length){
      repBlock.style.display='';
      repList.innerHTML=p.related.map(function(r){
        var link=r.pdf_url ? ' <a class="evidence-source-link ghost" href="'+esc(r.pdf_url)
          +'" target="_blank" rel="noopener noreferrer">查看研报 &rarr;</a>' : '';
        return '<div class="evidence-related-item"><span class="evidence-related-title">'+esc(r.title)+'</span>'+link+'</div>';
      }).join('');
    } else { repBlock.style.display='none'; repList.innerHTML=''; }
    overlay.style.display='flex';
  }
  function closeDrawer(){ overlay.style.display='none'; }
  overlay.addEventListener('click',function(e){ if(e.target===overlay) closeDrawer(); });
  document.getElementById('relDrawerClose').addEventListener('click',closeDrawer);
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape' && overlay.style.display!=='none') closeDrawer();
  });
  document.querySelectorAll('.relation-row-clickable').forEach(function(row){
    row.addEventListener('click',function(){
      try { openDrawer(JSON.parse(row.getAttribute('data-rel'))); }
      catch(err){ console.error('relation drawer parse error', err); }
    });
  });
})();
</script>
"""
def _load_app_css():
    """读取前端 App.css 全文（用于内联，保证与前端样式一致）。失败时返回空串。"""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        # app/generator -> 项目根 -> frontend/src/App.css
        css_path = os.path.join(here, "..", "..", "frontend", "src", "App.css")
        css_path = os.path.normpath(css_path)
        if os.path.exists(css_path):
            with open(css_path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception as e:
        logger.warning(f"读取 App.css 失败（HTML 报告将无前端样式）: {e}")
    return ""


EXTRA_CSS = r"""
body{margin:0;background:#eef1f5;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;color:#1f2937;line-height:1.65;}
.report-html-wrap{max-width:1080px;margin:0 auto;padding:32px 20px 64px;}
.result-page{background:#fff;border-radius:14px;padding:36px 40px;box-shadow:0 2px 12px rgba(0,0,0,.06);}
.result-header h2{margin:0 0 6px;font-size:26px;}
.report-meta{color:#6b7280;font-size:13px;margin-bottom:20px;}
.report-section{margin:30px 0;}
.report-section-title{border-left:4px solid #2563eb;padding-left:12px;font-size:20px;margin:0 0 14px;}
.markdown-body h1,.markdown-body h2,.markdown-body h3{margin:1em 0 .5em;line-height:1.3;}
.markdown-body p{margin:.6em 0;}
.markdown-body ul,.markdown-body ol{padding-left:1.5em;margin:.6em 0;}
.markdown-body strong{font-weight:700;}
.chain-tier{margin:18px 0;}
.chain-tier-title{font-size:16px;color:#374151;margin:14px 0 8px;}
.position-upstream{background:#dbeafe;color:#1e40af;}
.position-midstream{background:#d1fae5;color:#065f46;}
.position-downstream{background:#fef3c7;color:#92400e;}
.position-supporting{background:#ede9fe;color:#5b21b6;}
.relation-tag{display:inline-block;padding:2px 8px;border-radius:6px;font-size:12px;background:#eef2ff;color:#4338ca;}
.concentration-high{background:#fee2e2;color:#991b1b;}
.concentration-medium{background:#fef3c7;color:#92400e;}
.concentration-low{background:#d1fae5;color:#065f46;}
.chain-column{min-width:0;}
/* 代表企业超过 10 家时折叠（与前端 ReportPage / 图谱一致） */
.company-chips-more{margin:0;padding:0;border:0;}
.company-chips-more > summary{list-style:none;cursor:pointer;display:inline-flex;align-items:center;padding:3px 10px;font-size:12px;color:#2563eb;background:#fff;border:1px dashed #b6c5e0;border-radius:12px;white-space:nowrap;margin:0;}
.company-chips-more > summary::-webkit-details-marker{display:none;}
.company-chips-more > summary .lbl-expanded{display:none;}
.company-chips-more[open] > summary .lbl-collapsed{display:none;}
.company-chips-more[open] > summary .lbl-expanded{display:inline;}
.company-chips-more-inner{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;}
/* 第四章子标题（与前端 ResultPage 的 .subsection-title 一致） */
.subsection-title{font-size:15px;font-weight:700;color:#2563eb;margin:18px 0 12px;padding-left:10px;border-left:3px solid #2563eb;line-height:1.4;}
.subsection-title:first-child{margin-top:4px;}
"""


def generate_html_report(
    chain_data: dict,
    visualization: dict = None,
    summary: dict = None,
    output_dir: str = "data/reports",
    task_id: str = None,
) -> str:
    """
    生成「自包含」的 HTML 产业链分析报告（与前端 ResultPage 展示对齐）。

    Args:
        chain_data: 产业链分析完整结果（同 docx_generator）
        visualization: export_chain_visualization 的输出（图谱流转等），可空
        summary: get_chain_summary 的输出（产业链流转路径等），可空
        output_dir: 输出目录

    Returns:
        生成的 .html 文件路径
    """
    os.makedirs(output_dir, exist_ok=True)

    industry_name = chain_data.get("industry_name", "未知产业")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 文件名中的产业名做安全化，避免路径/文件名非法字符
    safe_name = "".join(ch for ch in industry_name if ch.isalnum() or ch in "一-鿿_ ")
    safe_name = safe_name.strip() or "产业"
    # task_id 存在时用固定文件名（覆盖旧文件，避免每次下载堆积）；否则用时间戳
    if task_id:
        filename = f"{safe_name}_产业链分析报告_{task_id}.html"
    else:
        filename = f"{safe_name}_产业链分析报告_{timestamp}.html"
    filepath = os.path.join(output_dir, filename)

    narratives = chain_data.get("_narratives", {}) or {}

    # 企业索引（供环节卡片 / 图谱卡片查询代表企业详情）
    companies = chain_data.get("companies") or []
    companies_index.clear()
    for c in companies:
        if c.get("name"):
            companies_index[c["name"]] = c

    sections = []
    # 第一章：产业链全景概览（定义、流转、市场规模）= 原1 + 原5
    _append_section(
        sections,
        "第一章  产业链全景概览（定义、流转、市场规模）",
        _unwrap(_ch1(chain_data, narratives, summary))
        + "\n"
        + _unwrap(_ch5(chain_data, narratives)),
    )
    # 第二章：产业链深度拆解 = 原3
    _append_section(sections, "第二章  产业链深度拆解", _unwrap(_ch3(chain_data, narratives, companies_index)))
    # 第三章：产业逻辑分析 = 原2 + 原4
    _append_section(
        sections,
        "第三章  产业逻辑分析",
        _unwrap(_ch2(chain_data, narratives))
        + "\n"
        + _unwrap(_ch4(chain_data, narratives)),
    )
    # 第四章：产业未来趋势与风险 = 原6 + 原8
    ch4_parts = []
    ch4_trend = _unwrap(_ch6(narratives))
    if ch4_trend:
        ch4_parts.append('<div class="subsection-title">未来趋势</div>')
        ch4_parts.append(ch4_trend)
    ch4_risk = _unwrap(_ch8(narratives))
    if ch4_risk:
        ch4_parts.append('<div class="subsection-title">风险分析</div>')
        ch4_parts.append(ch4_risk)
    _append_section(
        sections,
        "第四章  产业未来趋势与风险",
        "\n".join(ch4_parts),
    )
    # 第五章：近期产业链动态 = 原9
    _append_section(sections, "第五章  近期产业链动态", _unwrap(_ch9(chain_data)), "recent-events")
    # 附录：重点企业分析 / 企业关系（原 重点企业介绍 / 产业链关系）
    _append_section(
        sections,
        "附录 · 重点企业分析",
        _unwrap(_key_companies(chain_data, companies_index)),
        "key-companies",
    )
    _append_section(sections, "附录 · 企业关系", _unwrap(_relations(chain_data)))
    body = "\n".join(s for s in sections if s)

    disclaimer_html = (
        '<div class="report-section"><div class="report-section-body">'
        '<p style="color:#6b7280;font-size:13px;line-height:1.7;">'
        "免责声明：本报告由 AI 基于公开研报自动生成，仅供研究参考，不构成任何投资建议。"
        "报告中的产业链关系与事件均标注来源与证据状态；对于标注为「已报道/推断/未核实」的内容，"
        "请以原始披露为准。市场有风险，决策需谨慎。</p></div></div>"
    )

    app_css = _load_app_css()

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(industry_name)} 产业链分析报告</title>
<style>{app_css}</style>
<style>{EXTRA_CSS}</style>
</head>
<body>
<div class="report-html-wrap">
<div class="result-page">
  <div class="result-header">
    <h2>{esc(industry_name)} 产业链分析报告</h2>
  </div>
  <div class="report-meta">AI 智能分析 · 生成时间 {datetime.now().strftime('%Y年%m月%d日 %H:%M')} · HTML 格式</div>
{body}
{disclaimer_html}
{_relation_drawer_html()}
{RELATION_DRAWER_JS}
</div>
</div>
</body>
</html>
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_doc)

    logger.info(f"HTML 报告已生成: {filepath}")
    return filepath


# 模块级企业索引（单请求内使用，生成结束后即被下一次调用覆盖）
companies_index = {}
