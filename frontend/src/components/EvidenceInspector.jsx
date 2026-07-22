// Evidence Inspector（证据检查器）
// 对标 cwwindex「CHAIN VIEW → EVIDENCE INSPECTOR」：点击产业链关系表中的某一行，
// 从右侧滑入抽屉，展示该关系的证据详情。
// 纯前端组件，不依赖后端改动；对旧格式报告（仅 5 字段）自动降级显示。

// 证据状态 → 中文标签与配色（与 ResultPage 的 EVIDENCE_META 保持一致）
const EVIDENCE_META = {
  VERIFIED: { label: '已验证', bg: '#d1fae5', fg: '#065f46' },
  REPORTED: { label: '已报道', bg: '#dbeafe', fg: '#1e40af' },
  INFERRED: { label: '推断', bg: '#f3f4f6', fg: '#374151' },
  UNVERIFIED: { label: '未核实', bg: '#fee2e2', fg: '#991b1b' },
}

// 从参考研报列表中，模糊匹配「涉及关系两端企业」的研报
export function findRelatedReports(reports, companyA, companyB) {
  if (!Array.isArray(reports) || !companyA) return []
  const targets = [companyA, companyB].filter(Boolean)
  return reports
    .filter((r) => {
      const haystack = `${r.title || ''} ${r.stock_name || ''}`
      return targets.some((name) => name && haystack.includes(name))
    })
    .slice(0, 5)
}

export default function EvidenceInspector({ relation, referenceReports, onClose }) {
  // 解构 relation 字段（带默认值，兼容旧报告 5 字段格式）
  const {
    from_company = '',
    to_company = '',
    type = '',
    detail = '',
    confidence = 0,
    evidenceStatus = 'REPORTED',
  } = relation || {}

  const evMeta = EVIDENCE_META[evidenceStatus] || EVIDENCE_META.REPORTED
  const relatedReports = findRelatedReports(referenceReports, from_company, to_company)

  // ESC 关闭
  const handleKeyDown = (e) => {
    if (e.key === 'Escape') onClose()
  }

  return (
    <div
      className="evidence-inspector-overlay"
      onClick={onClose}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={-1}
      aria-label="关闭证据详情"
    >
      <aside
        className="evidence-inspector-drawer"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 顶部栏 */}
        <div className="evidence-inspector-header">
          <span className="evidence-inspector-kicker">证据详情</span>
          <button
            type="button"
            className="evidence-close-btn"
            onClick={onClose}
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        {/* 主标题：A → B */}
        <h2 className="evidence-relation-title">
          {from_company || '未知'} <span className="evidence-arrow">→</span>{' '}
          {to_company || '未知'}
        </h2>

        {/* 副标题：detail 全文（替代"供应/合作"等简单类型词） */}
        {detail ? (
          <p className="evidence-relation-subtitle">{detail}</p>
        ) : (
          <p className="evidence-relation-subtitle evidence-muted">
            （该关系未记录详细描述）
          </p>
        )}

        {/* 信息卡片区：关系类型(小标签) / 证据状态 / 置信度 */}
        <div className="evidence-info-cards">
          {type && (
            <div className="evidence-info-card">
              <span className="evidence-card-label">关系类型</span>
              <span className={`relation-tag relation-${type}`}>{type}</span>
            </div>
          )}
          <div className="evidence-info-card">
            <span className="evidence-card-label">证据状态</span>
            <span
              className="event-evidence"
              style={{ background: evMeta.bg, color: evMeta.fg }}
            >
              {evMeta.label}
            </span>
          </div>
          <div className="evidence-info-card">
            <span className="evidence-card-label">置信度</span>
            <span className="evidence-confidence">
              {Math.round((Number(confidence) || 0) * 100)}%
            </span>
          </div>
        </div>

        {/* 关系详述 */}
        {detail && (
          <div className="evidence-block">
            <h4 className="evidence-block-title">关系详述</h4>
            <p className="evidence-block-text">{detail}</p>
          </div>
        )}

        {/* 交叉引用：提及此关系涉及企业的参考研报 */}
        {relatedReports.length > 0 && (
          <div className="evidence-block">
            <h4 className="evidence-block-title">
              相关研报（提及此关系涉及企业）
            </h4>
            <div className="evidence-related-list">
              {relatedReports.map((r, i) => (
                <div className="evidence-related-item" key={i}>
                  <span className="evidence-related-title">{r.title}</span>
                  {r.pdf_url && (
                    <a
                      className="evidence-source-link ghost"
                      href={r.pdf_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      查看研报 →
                    </a>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </aside>
    </div>
  )
}
