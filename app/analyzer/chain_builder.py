"""产业链图谱构建

基于 LLM 提取的结构化数据，用 networkx 构建有向图，
支持关系推断和产业链可视化数据导出。
"""

import logging
import networkx as nx
from typing import Optional

logger = logging.getLogger(__name__)


def build_chain_graph(chain_data: dict) -> nx.DiGraph:
    """
    从产业链分析结果构建有向图

    Args:
        chain_data: LLM merge_and_analyze 的返回结果

    Returns:
        networkx DiGraph
    """
    G = nx.DiGraph()

    # 添加公司节点（过滤无效名称）
    valid_names = set()
    for company in chain_data.get("companies", []):
        name = company.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            logger.warning(f"跳过无效公司名: {company}")
            continue
        name = name.strip()
        valid_names.add(name)
        G.add_node(
            name,
            stock_code=company.get("stock_code"),
            main_business=company.get("main_business", ""),
            chain_position=company.get("chain_position", ""),
            sub_segment=company.get("sub_segment", ""),
            products=company.get("products", []),
        )

    # 添加关系边（过滤涉及无效公司名的关系）
    for rel in chain_data.get("relations", []):
        from_c = rel.get("from_company")
        to_c = rel.get("to_company")
        if not from_c or not to_c or not isinstance(from_c, str) or not isinstance(to_c, str):
            logger.warning(f"跳过无效关系: {rel}")
            continue
        if from_c.strip() not in valid_names or to_c.strip() not in valid_names:
            logger.warning(f"跳过涉及未知公司的关系: {rel}")
            continue
        G.add_edge(
            from_c.strip(),
            to_c.strip(),
            relation_type=rel.get("type", ""),
            detail=rel.get("detail", ""),
            confidence=rel.get("confidence", 0.5),
        )

    # 添加环节间传导关系边（新增 P0 功能）
    transmission_count = 0
    for trans in chain_data.get("transmission_relations", []):
        from_seg = trans.get("from_segment", "").strip()
        to_seg = trans.get("to_segment", "").strip()
        if not from_seg or not to_seg:
            continue
        # 使用环节名作为节点（加前缀避免与公司名冲突）
        from_node = f"segment:{from_seg}"
        to_node = f"segment:{to_seg}"
        if not G.has_node(from_node):
            G.add_node(from_node, node_type="segment", segment_name=from_seg)
        if not G.has_node(to_node):
            G.add_node(to_node, node_type="segment", segment_name=to_seg)
        G.add_edge(
            from_node, to_node,
            relation_type=trans.get("transmission_type", ""),
            detail=trans.get("description", ""),
            is_transmission=True,
        )
        transmission_count += 1

    if transmission_count:
        logger.info(f"  其中环节传导关系: {transmission_count} 条")

    logger.info(f"产业链图谱构建完成: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边")
    return G


def infer_indirect_relations(G: nx.DiGraph, max_depth: int = 2) -> list[dict]:
    """
    推断间接产业链关系

    例如：A→B→C 意味着 A 是 C 的间接上游

    Args:
        G: 产业链有向图
        max_depth: 最大推断深度

    Returns:
        推断出的间接关系列表
    """
    indirect = []

    for node in G.nodes():
        # 找到从该节点出发、深度 > 1 的可达节点
        try:
            paths = nx.single_source_shortest_path(G, node, cutoff=max_depth)
            for target, path in paths.items():
                if len(path) > 2 and target != node:  # 间接关系
                    indirect.append({
                        "from_company": node,
                        "to_company": target,
                        "type": "间接供应",
                        "path": path,
                        "detail": f"通过 {' → '.join(path)} 间接关联",
                    })
        except Exception:
            continue

    logger.info(f"推断出 {len(indirect)} 条间接关系")
    return indirect


def export_chain_visualization(chain_data: dict) -> dict:
    """
    导出产业链可视化数据（供前端 ECharts 使用）

    Returns:
        ECharts 兼容的数据格式
    """
    nodes = []
    links = []
    categories = [
        {"name": "上游"},
        {"name": "中游"},
        {"name": "下游"},
        {"name": "配套服务"},
    ]

    position_to_category = {
        "上游": 0,
        "中游": 1,
        "下游": 2,
        "配套服务": 3,
    }

    # 节点（过滤无效名称）
    for company in chain_data.get("companies", []):
        name = company.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            continue
        position = company.get("chain_position", "中游")
        cat_idx = position_to_category.get(position, 1)

        nodes.append({
            "name": name.strip(),
            "category": cat_idx,
            "symbolSize": 40 if company.get("stock_code") else 30,
            "value": company.get("main_business", ""),
            "stock_code": company.get("stock_code"),
            "sub_segment": company.get("sub_segment", ""),
        })

    # 边（过滤涉及空名称的关系）
    for rel in chain_data.get("relations", []):
        from_c = rel.get("from_company")
        to_c = rel.get("to_company")
        if not from_c or not to_c or not isinstance(from_c, str) or not isinstance(to_c, str):
            continue
        links.append({
            "source": from_c.strip(),
            "target": to_c.strip(),
            "value": rel.get("type", ""),
            "label": {"show": True, "formatter": rel.get("type", "")},
        })

    # 环节间传导关系（P0 新增）
    transmission_links = []
    for trans in chain_data.get("transmission_relations", []):
        from_seg = trans.get("from_segment", "").strip()
        to_seg = trans.get("to_segment", "").strip()
        if from_seg and to_seg:
            transmission_links.append({
                "from_segment": from_seg,
                "to_segment": to_seg,
                "transmission_type": trans.get("transmission_type", ""),
                "description": trans.get("description", ""),
            })

    return {
        "categories": categories,
        "nodes": nodes,
        "links": links,
        "chain_flow": chain_data.get("chain_flow", ""),
        "transmission_relations": transmission_links,
        "chain_causal_logic": chain_data.get("chain_causal_logic", ""),
    }


def get_chain_summary(chain_data: dict) -> dict:
    """
    生成产业链摘要统计

    Returns:
        摘要数据
    """
    companies = chain_data.get("companies", [])
    relations = chain_data.get("relations", [])
    segments = chain_data.get("chain_segments", {})

    position_counts = {}
    for c in companies:
        pos = c.get("chain_position", "未知")
        position_counts[pos] = position_counts.get(pos, 0) + 1

    transmission_relations = chain_data.get("transmission_relations", [])
    chain_causal_logic = chain_data.get("chain_causal_logic", "")

    return {
        "industry_name": chain_data.get("industry_name", ""),
        "total_companies": len(companies),
        "total_relations": len(relations),
        "position_counts": position_counts,
        "upstream_segments": len(segments.get("upstream", [])),
        "midstream_segments": len(segments.get("midstream", [])),
        "downstream_segments": len(segments.get("downstream", [])),
        "chain_flow": chain_data.get("chain_flow", ""),
        "transmission_count": len(transmission_relations),
        "causal_logic_length": len(chain_causal_logic) if chain_causal_logic else 0,
    }
