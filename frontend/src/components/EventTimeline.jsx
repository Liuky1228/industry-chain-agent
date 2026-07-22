/**
 * 产业链事件时间轴（脉冲式，参考 cwwindex 72H 脉冲设计）
 *
 * 设计原则（与后端 event_schema 一致）：
 *  - 事件为「已验证/已报道的事实事件证据流」，不做利好/利空判断
 *  - 每条事件带来源（sourceTitle）、证据状态（evidenceStatus）、去情绪化护栏（impactZh）
 *  - 无事件时显示诚实空状态，绝不编造
 *
 * Props:
 *  - events: 事件数组（chainData.events）
 *  - eventWindow: 窗口元信息（chainData.event_window）
 *  - eventPolicy: 抽取政策（chainData.event_policy，含 disclaimer）
 *  - referenceReports: 参考研报列表（chainData._reference_reports），用于把事件回溯到来源研报
 */
import { useMemo } from 'react'

// 事件标签 → 配色（受控词表，与后端 EVENT_TAGS 顺序对应）
const TAG_COLORS = {
  产能扩张: { bg: '#dbeafe', fg: '#1e40af' },
  政策法规: { bg: '#ede9fe', fg: '#5b21b6' },
  并购重组: { bg: '#fef3c7', fg: '#92400e' },
  技术突破: { bg: '#d1fae5', fg: '#065f46' },
  价格变动: { bg: '#ffedd5', fg: '#9a3412' },
  合规调查: { bg: '#fee2e2', fg: '#991b1b' },
  合作生态: { bg: '#ccfbf1', fg: '#134e4a' },
}

// 证据状态 → 配色与中文标签
const EVIDENCE_META = {
  VERIFIED: { label: '已验证', bg: '#d1fae5', fg: '#065f46' },
  REPORTED: { label: '已报道', bg: '#dbeafe', fg: '#1e40af' },
  INFERRED: { label: '推断', bg: '#f3f4f6', fg: '#374151' },
  UNVERIFIED: { label: '未核实', bg: '#fee2e2', fg: '#991b1b' },
}

// 根据事件 sourceTitle 匹配来源研报（与 _reference_reports 对齐）。
// 事件的 sourceTitle 由后端保证是「某份研报标题」，故用标题做包含匹配；
// 返回带可跳转链接（pdf_url / report_url）的研报，找不到返回 null。
function findEventReport(sourceTitle, reports) {
  if (!sourceTitle || !Array.isArray(reports)) return null
  for (const r of reports) {
    const rt = r.title || ''
    if (rt && (sourceTitle === rt || sourceTitle.includes(rt) || rt.includes(sourceTitle))) {
      return r
    }
  }
  return null
}

export default function EventTimeline({
  events = [],
  eventWindow = {},
  eventPolicy = {},
  referenceReports = [],
}) {
  const disclaimer = eventPolicy?.disclaimer ||
    '本板块仅列已验证/已报道的事实事件，不构成任何投资建议；AI 不判断利好或利空，事件影响以原始披露为准。'

  // 仅保留「能匹配到来源研报（且研报含可跳转链接）」的事件；无来源则不展示该条
  const sorted = useMemo(() => {
    const list = (events || []).filter((ev) => {
      const rep = findEventReport(ev.sourceTitle, referenceReports)
      const url = rep && (rep.pdf_url || rep.report_url)
      return !!url
    })
    list.sort((a, b) => {
      const da = a.date || ''
      const db = b.date || ''
      if (!da) return 1
      if (!db) return -1
      return db.localeCompare(da)
    })
    return list
  }, [events, referenceReports])

  // 空状态
  if (!sorted || sorted.length === 0) {
    return (
      <div className="event-timeline">
        <div className="event-disclaimer">{disclaimer}</div>
        <div className="event-empty">
          近 {eventWindow?.window_days ?? '—'} 天（基于公开研报）未抽取到带明确来源研报的重大产业链事件。
          <br />
          本板块仅呈现可回溯到具体研报来源的事实事件，不以空白填充。
        </div>
      </div>
    )
  }

  return (
    <div className="event-timeline">
      {/* 顶部免责声明条 */}
      <div className="event-disclaimer">{disclaimer}</div>

      {/* 窗口元信息 */}
      <div className="event-window">
        <span className="event-window-item">
          数据窗口：近 {eventWindow?.window_days ?? '—'} 天
        </span>
        {eventWindow?.generated_at && (
          <span className="event-window-item">生成时间：{eventWindow.generated_at}</span>
        )}
        <span className="event-window-item">事件数：{sorted.length}</span>
      </div>

      {/* 时间轴 */}
      <div className="event-list">
        {sorted.map((ev, idx) => {
          const rep = findEventReport(ev.sourceTitle, referenceReports)
          const reportUrl = (rep && (rep.pdf_url || rep.report_url)) || ''
          return (
            <div className="event-item" key={ev.id || idx}>
              {/* 时间轴左侧圆点 + 日期 */}
              <div className="event-rail">
                <span className="event-dot" />
                <span className="event-date">{ev.date || '日期未知'}</span>
              </div>

              {/* 事件主体 */}
              <div className="event-card">
                <div className="event-card-head">
                  <span className="event-title">{ev.title || '（无标题）'}</span>
                </div>

                {/* 标签 */}
                {ev.tags?.length > 0 && (
                  <div className="event-tags">
                    {ev.tags.map((t, i) => {
                      const c = TAG_COLORS[t] || { bg: '#f3f4f6', fg: '#374151' }
                      return (
                        <span
                          key={i}
                          className="event-tag"
                          style={{ background: c.bg, color: c.fg }}
                        >
                          {t}
                        </span>
                      )
                    })}
                  </div>
                )}

                {/* 摘要（完整展示，去掉原「展开全文」折叠） */}
                <p className="event-summary">{ev.summaryZh}</p>

                {/* 涉及企业 */}
                {ev.companies?.length > 0 && (
                  <div className="event-companies">
                    <span className="event-label">涉及企业：</span>
                    {ev.companies.map((name, i) => (
                      <span key={i} className="event-company">
                        {name}
                      </span>
                    ))}
                  </div>
                )}

                {/* 影响护栏 */}
                {ev.impactZh && (
                  <div className="event-impact">{ev.impactZh}</div>
                )}

                {/* 来源 + 查看研报 */}
                <div className="event-source-row">
                  <div className="event-source">
                    来源：{ev.sourceTitle || ev.sourceType || '研报'}
                    {ev.confidence != null && (
                      <span className="event-confidence">
                        （置信度 {Math.round((ev.confidence || 0) * 100)}%）
                      </span>
                    )}
                  </div>
                  {reportUrl && (
                    <a
                      className="event-report-link"
                      href={reportUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      查看研报 →
                    </a>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
