"""图表生成模块

基于产业链结构化数据，使用 matplotlib 生成分析图表，
供 Word 报告嵌入使用。
"""

import os
import logging
import tempfile
import matplotlib
matplotlib.use("Agg")  # 无头模式
import matplotlib.pyplot as plt
from matplotlib import font_manager

logger = logging.getLogger(__name__)

# ── 全局字体配置 ──
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

# 配色方案
COLORS = {
    "上游": "#3b82f6",
    "中游": "#f59e0b",
    "下游": "#10b981",
    "配套服务": "#8b5cf6",
}
RELATION_COLORS = {
    "供应": "#3b82f6",
    "采购": "#f59e0b",
    "合作": "#10b981",
    "竞争": "#ef4444",
}
CONCENTRATION_COLORS = {"高": "#ef4444", "中": "#f59e0b", "低": "#10b981"}

# chain_segments 的 key 可能是英文或中文，统一映射
LEVEL_KEY_MAP = {
    "upstream": "上游",
    "midstream": "中游",
    "downstream": "下游",
    "supporting": "配套服务",
    "上游": "上游",
    "中游": "中游",
    "下游": "下游",
    "配套服务": "配套服务",
}


def generate_all_charts(chain_data: dict, output_dir: str = None) -> dict:
    """
    生成所有产业链分析图表

    Args:
        chain_data: 完整的产业链分析数据
        output_dir: 图表输出目录，默认使用临时目录

    Returns:
        图表路径字典 {"chart_name": filepath, ...}
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="chain_charts_")
    os.makedirs(output_dir, exist_ok=True)

    charts = {}

    # 图1: 企业分布柱状图
    try:
        path = _chart_position_distribution(chain_data, output_dir)
        if path:
            charts["position_distribution"] = path
    except Exception as e:
        logger.warning(f"企业分布图生成失败: {e}")

    # 图2: 关系类型饼图
    try:
        path = _chart_relation_types(chain_data, output_dir)
        if path:
            charts["relation_types"] = path
    except Exception as e:
        logger.warning(f"关系类型图生成失败: {e}")

    # 图3: 环节结构图
    try:
        path = _chart_segment_structure(chain_data, output_dir)
        if path:
            charts["segment_structure"] = path
    except Exception as e:
        logger.warning(f"环节结构图生成失败: {e}")

    # 图4: 集中度分析图
    try:
        path = _chart_concentration(chain_data, output_dir)
        if path:
            charts["concentration"] = path
    except Exception as e:
        logger.warning(f"集中度图生成失败: {e}")

    logger.info(f"图表生成完成: 共 {len(charts)} 张")
    return charts


def _chart_position_distribution(chain_data: dict, output_dir: str) -> str:
    """图1: 产业链各环节企业数量分布"""
    companies = chain_data.get("companies", [])
    if not companies:
        return None

    # 统计各环节企业数
    position_counts = {}
    for c in companies:
        pos = c.get("chain_position", "未知")
        position_counts[pos] = position_counts.get(pos, 0) + 1

    # 过滤掉未知位置
    position_counts = {k: v for k, v in position_counts.items() if k in COLORS}
    if not position_counts:
        return None

    # 按固定顺序排列
    order = ["上游", "中游", "下游", "配套服务"]
    labels = [p for p in order if p in position_counts]
    values = [position_counts[p] for p in labels]
    colors = [COLORS[p] for p in labels]

    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(labels, values, color=colors, width=0.55, edgecolor="white", linewidth=0.8)

    # 在柱子上方标注数值
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                str(val), ha="center", va="bottom", fontsize=13, fontweight="bold",
                color="#374151")

    ax.set_title("产业链各环节企业分布", fontsize=15, fontweight="bold",
                 color="#1a478a", pad=15)
    ax.set_ylabel("企业数量（家）", fontsize=11, color="#6b7280")
    ax.set_ylim(0, max(values) * 1.25 + 1)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#e5e7eb")
    ax.spines["bottom"].set_color("#e5e7eb")
    ax.tick_params(colors="#6b7280")

    plt.tight_layout()
    path = os.path.join(output_dir, "position_distribution.png")
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _chart_relation_types(chain_data: dict, output_dir: str) -> str:
    """图2: 产业链关系类型分布饼图"""
    relations = chain_data.get("relations", [])
    if not relations:
        return None

    # 统计关系类型
    type_counts = {}
    for r in relations:
        rtype = r.get("type", "其他")
        type_counts[rtype] = type_counts.get(rtype, 0) + 1

    if not type_counts:
        return None

    labels = list(type_counts.keys())
    values = list(type_counts.values())
    colors = [RELATION_COLORS.get(l, "#9ca3af") for l in labels]

    fig, ax = plt.subplots(figsize=(6, 5))

    # 饼图
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, colors=colors, autopct="%1.0f%%",
        startangle=90, pctdistance=0.75,
        wedgeprops=dict(width=0.5, edgecolor="white", linewidth=2),
    )
    for t in autotexts:
        t.set_fontsize(11)
        t.set_fontweight("bold")
        t.set_color("white")
    for t in texts:
        t.set_fontsize(11)
        t.set_color("#374151")

    # 中心标注总数
    ax.text(0, 0, f"共{sum(values)}条\n关系", ha="center", va="center",
            fontsize=12, fontweight="bold", color="#374151")

    ax.set_title("产业链关系类型分布", fontsize=15, fontweight="bold",
                 color="#1a478a", pad=15)

    plt.tight_layout()
    path = os.path.join(output_dir, "relation_types.png")
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _chart_segment_structure(chain_data: dict, output_dir: str) -> str:
    """图3: 产业链环节结构图（各环节企业数量对比）"""
    segments = chain_data.get("chain_segments", {})
    companies = chain_data.get("companies", [])

    # 构建企业名称集合，用于匹配
    company_names = {c.get("name", "").strip() for c in companies if c.get("name")}

    # 收集所有环节数据（兼容英文/中文 key）
    all_segments = []
    level_order = ["上游", "中游", "下游", "配套服务"]
    for raw_key, segs in segments.items():
        level = LEVEL_KEY_MAP.get(raw_key, raw_key)
        for seg in segs:
            seg_name = seg.get("segment_name", "")
            seg_companies = seg.get("companies", [])
            count = len(seg_companies)
            if seg_name:
                all_segments.append({
                    "name": seg_name,
                    "level": level,
                    "count": count,
                })

    if not all_segments:
        return None

    # 按环节企业数排序
    all_segments.sort(key=lambda x: x["count"], reverse=True)

    # 取前 15 个环节
    display_segs = all_segments[:15]
    display_segs.reverse()  # 从下到上绘制

    labels = [f"{s['name']}" for s in display_segs]
    values = [s["count"] for s in display_segs]
    colors = [COLORS.get(s["level"], "#9ca3af") for s in display_segs]

    fig, ax = plt.subplots(figsize=(8, max(4, len(display_segs) * 0.35)))
    bars = ax.barh(labels, values, color=colors, height=0.6, edgecolor="white", linewidth=0.5)

    # 标注数值
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + 0.2, bar.get_y() + bar.get_height() / 2,
                str(val), ha="left", va="center", fontsize=10, color="#374151")

    ax.set_title("产业链各环节企业数量分布", fontsize=15, fontweight="bold",
                 color="#1a478a", pad=15)
    ax.set_xlabel("企业数量（家）", fontsize=11, color="#6b7280")
    ax.set_xlim(0, max(values) * 1.3 + 1)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#e5e7eb")
    ax.spines["bottom"].set_color("#e5e7eb")
    ax.tick_params(colors="#6b7280")

    # 添加图例
    from matplotlib.patches import Patch
    legend_items = [Patch(facecolor=COLORS[l], label=l) for l in level_order
                    if any(s["level"] == l for s in display_segs)]
    if legend_items:
        ax.legend(handles=legend_items, loc="lower right", fontsize=9,
                  frameon=False)

    plt.tight_layout()
    path = os.path.join(output_dir, "segment_structure.png")
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _chart_concentration(chain_data: dict, output_dir: str) -> str:
    """图4: 各环节市场集中度分析"""
    segments = chain_data.get("chain_segments", {})

    # 收集有集中度数据的环节（兼容英文/中文 key）
    data = []
    level_order = ["上游", "中游", "下游", "配套服务"]
    conc_map = {"高": 3, "中": 2, "低": 1}

    for raw_key, segs in segments.items():
        level = LEVEL_KEY_MAP.get(raw_key, raw_key)
        for seg in segs:
            conc = seg.get("concentration", "")
            if conc in conc_map:
                data.append({
                    "name": seg.get("segment_name", ""),
                    "level": level,
                    "concentration": conc,
                    "score": conc_map[conc],
                })

    if not data:
        return None

    # 按层级和集中度排序
    data.sort(key=lambda x: (level_order.index(x["level"]) if x["level"] in level_order else 99,
                              -x["score"]))

    labels = [f"[{d['level']}] {d['name']}" for d in data]
    scores = [d["score"] for d in data]
    colors = [CONCENTRATION_COLORS.get(d["concentration"], "#9ca3af") for d in data]

    fig, ax = plt.subplots(figsize=(8, max(3.5, len(data) * 0.4)))
    bars = ax.barh(labels, scores, color=colors, height=0.55, edgecolor="white", linewidth=0.5)

    # 标注集中度等级文字
    for bar, d in zip(bars, data):
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                d["concentration"], ha="left", va="center", fontsize=10,
                fontweight="bold", color=CONCENTRATION_COLORS.get(d["concentration"], "#666"))

    ax.set_title("产业链各环节市场集中度", fontsize=15, fontweight="bold",
                 color="#1a478a", pad=15)
    ax.set_xlim(0, 4)
    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels(["低", "中", "高"], fontsize=10, color="#6b7280")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#e5e7eb")
    ax.spines["bottom"].set_color("#e5e7eb")
    ax.tick_params(colors="#6b7280")

    # 图例
    from matplotlib.patches import Patch
    legend_items = [
        Patch(facecolor=CONCENTRATION_COLORS["高"], label="高集中度"),
        Patch(facecolor=CONCENTRATION_COLORS["中"], label="中集中度"),
        Patch(facecolor=CONCENTRATION_COLORS["低"], label="低集中度"),
    ]
    ax.legend(handles=legend_items, loc="lower right", fontsize=9, frameon=False)

    plt.tight_layout()
    path = os.path.join(output_dir, "concentration.png")
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path
