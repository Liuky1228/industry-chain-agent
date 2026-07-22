import { useState, useMemo } from 'react'

/**
 * 产业链关系图谱（三栏卡片式）
 *
 * 基于已生成报告中的 chain_segments 和 companies 数据，
 * 按上中下游三栏布局展示产业链环节、描述和代表企业。
 * 配套服务栏目（如有）放在三栏下方。
 *
 * Props:
 *   - data: 后端 export_chain_visualization 的输出
 *       包含 categories/nodes/links/chain_flow/transmission_relations/chain_causal_logic
 *   - chainData: 完整的产业链分析数据（包含 chain_segments 与 companies 详情）
 */
export default function ChainGraph({ data, chainData }) {
  // 1. 构建 companies 索引，便于按名称查找详情
  const companiesIndex = useMemo(() => {
    const map = {}
    const list = chainData?.companies || []
    for (const c of list) {
      if (c.name) {
        map[c.name] = c
      }
    }
    // 兼容 data 中节点（如果 chainData 没传）
    if (Object.keys(map).length === 0 && data?.nodes) {
      for (const n of data.nodes) {
        if (n.name) {
          map[n.name] = {
            name: n.name,
            stock_code: n.stock_code,
            main_business: n.value,
            sub_segment: n.sub_segment,
          }
        }
      }
    }
    return map
  }, [data, chainData])

  // 2. 构建三栏数据：上游 / 中游 / 下游（配套服务单独放底部）
  const columns = useMemo(() => {
    const segments = chainData?.chain_segments || {}
    const buildCol = (label, colorKey, segs) => ({
      key: colorKey,
      label,
      colorKey,
      segments: (segs || []).filter((s) => s && (s.segment_name || s.name)),
    })
    return [
      buildCol('上游', 'upstream', segments.upstream),
      buildCol('中游', 'midstream', segments.midstream),
      buildCol('下游', 'downstream', segments.downstream),
    ]
  }, [chainData])

  const supportingSegments = useMemo(() => {
    return (chainData?.chain_segments?.supporting || []).filter(
      (s) => s && (s.segment_name || s.name)
    )
  }, [chainData])

  const totalSegments =
    columns.reduce((sum, c) => sum + c.segments.length, 0) + supportingSegments.length

  // 3. 没有任何数据
  if (totalSegments === 0) {
    return (
      <div className="chain-graph-empty">
        暂无产业链图谱数据
      </div>
    )
  }

  return (
    <div className="chain-graph">
      {/* 顶部信息条：仅保留产业链流转描述 */}
      {data?.chain_flow && (
        <div className="chain-graph-header">
          <div className="chain-graph-flow">
            <span className="chain-graph-flow-label">产业链流转：</span>
            <span className="chain-graph-flow-text">{data.chain_flow}</span>
          </div>
        </div>
      )}

      {/* 三栏布局 */}
      <div className="chain-graph-columns">
        {columns.map((col) => (
          <ChainColumn
            key={col.key}
            column={col}
            companiesIndex={companiesIndex}
          />
        ))}
      </div>

      {/* 配套服务（放在三栏下方） */}
      {supportingSegments.length > 0 && (
        <div className="chain-graph-supporting">
          <div className="chain-graph-supporting-header">
            <span className="chain-graph-supporting-dot" />
            配套服务
            <span className="chain-graph-supporting-count">{supportingSegments.length} 个环节</span>
          </div>
          <div className="chain-graph-supporting-list">
            {supportingSegments.map((seg, idx) => (
              <SegmentCard
                key={idx}
                segment={seg}
                colorKey="supporting"
                companiesIndex={companiesIndex}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* ── 子组件：单栏 ── */
function ChainColumn({ column, companiesIndex }) {
  return (
    <div className={`chain-column chain-column-${column.colorKey}`}>
      <div className="chain-column-header">
        <span className="chain-column-label">{column.label}</span>
        <span className="chain-column-count">{column.segments.length} 个环节</span>
      </div>
      <div className="chain-column-body">
        {column.segments.length === 0 ? (
          <div className="chain-column-empty">暂无该层级数据</div>
        ) : (
          column.segments.map((seg, idx) => (
            <SegmentCard
              key={idx}
              segment={seg}
              colorKey={column.colorKey}
              companiesIndex={companiesIndex}
            />
          ))
        )}
      </div>
    </div>
  )
}

/* ── 子组件：环节卡片 ── */
function SegmentCard({ segment, colorKey, companiesIndex }) {
  const [descExpanded, setDescExpanded] = useState(false)
  const [companiesExpanded, setCompaniesExpanded] = useState(false)
  const [hoveredCompany, setHoveredCompany] = useState(null)

  // 字段兼容
  const segName = segment.segment_name || segment.name || '未命名环节'
  const segDesc = segment.description || ''
  const segConcentration = segment.concentration || ''
  const segCompanies = (segment.companies || []).filter(Boolean)

  // 描述过长时折叠
  const DESC_LIMIT = 60
  const descNeedTruncate = segDesc.length > DESC_LIMIT
  const displayDesc =
    !descExpanded && descNeedTruncate ? segDesc.slice(0, DESC_LIMIT) + '…' : segDesc

  // 企业过多时折叠
  const COMPANIES_LIMIT = 10
  const companiesNeedTruncate = segCompanies.length > COMPANIES_LIMIT
  const displayCompanies = companiesExpanded
    ? segCompanies
    : segCompanies.slice(0, COMPANIES_LIMIT)

  return (
    <div className={`chain-segment-card chain-segment-${colorKey}`}>
      {/* 标题行 */}
      <div className="chain-segment-header">
        <h4 className="chain-segment-title">{segName}</h4>
        {segConcentration && (
          <span className={`concentration-tag concentration-${segConcentration}`}>
            {segConcentration}
          </span>
        )}
      </div>

      {/* 描述 */}
      {segDesc && (
        <div className="chain-segment-desc">
          <p>{displayDesc}</p>
          {descNeedTruncate && (
            <button
              type="button"
              className="chain-segment-toggle"
              onClick={() => setDescExpanded((v) => !v)}
            >
              {descExpanded ? '收起描述' : '展开描述'}
            </button>
          )}
        </div>
      )}

      {/* 代表企业 */}
      {segCompanies.length > 0 && (
        <div className="chain-segment-companies">
          <div className="chain-segment-companies-label">代表企业</div>
          <div className="chain-segment-chips">
            {displayCompanies.map((name, idx) => {
              const c = companiesIndex[name] || { name }
              const isHovered = hoveredCompany === name
              return (
                <span
                  key={idx}
                  className={`chain-company-chip ${isHovered ? 'highlighted' : ''}`}
                  onMouseEnter={() => setHoveredCompany(name)}
                  onMouseLeave={() => setHoveredCompany(null)}
                  title={
                    c.main_business
                      ? `${c.name}${c.stock_code ? ' (' + c.stock_code + ')' : ''}\n${c.main_business}`
                      : c.name
                  }
                >
                  <span className="chain-company-chip-name">{c.name || name}</span>
                  {c.stock_code && (
                    <span className="chain-company-chip-code">{c.stock_code}</span>
                  )}
                  {isHovered && c.main_business && (
                    <span className="chain-company-tooltip">
                      <span className="chain-company-tooltip-arrow" />
                      <div className="chain-company-tooltip-content">
                        {c.main_business}
                      </div>
                    </span>
                  )}
                </span>
              )
            })}
            {companiesNeedTruncate && !companiesExpanded && (
              <button
                type="button"
                className="chain-companies-toggle"
                onClick={() => setCompaniesExpanded(true)}
                title="展开查看更多企业"
              >
                +{segCompanies.length - COMPANIES_LIMIT} 更多
              </button>
            )}
          </div>
          <div className="chain-segment-companies-footer">
            <span className="chain-segment-companies-count">
              共 {segCompanies.length} 家
            </span>
            {companiesNeedTruncate && (
              <button
                type="button"
                className="chain-segment-toggle chain-segment-toggle-inline"
                onClick={() => setCompaniesExpanded((v) => !v)}
              >
                {companiesExpanded ? '收起企业' : `展开全部 ${segCompanies.length} 家`}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
