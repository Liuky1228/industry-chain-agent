import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  getTask, subscribeProgress, getReportDownloadUrl,
  getHtmlReportUrl, regenerateReports,
  cancelTask,
} from '../services/api'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import EventTimeline from './EventTimeline'
import EvidenceInspector, { findRelatedReports } from './EvidenceInspector'

const CHAIN_TABS = [
  { key: 'upstream', label: '上游' },
  { key: 'midstream', label: '中游' },
  { key: 'downstream', label: '下游' },
  { key: 'supporting', label: '配套服务' },
]

// P1: 新叙述字段映射（8章结构）
const NARRATIVE_KEYS = {
  upstream: 'node_analysis_upstream',
  midstream: 'node_analysis_midstream',
  downstream: 'node_analysis_downstream',
  supporting: 'derivative_segments',
}

// 关系/事件证据状态 → 中文标签与配色（与设计点①/⑨共用）
const EVIDENCE_META = {
  VERIFIED: { label: '已验证', bg: '#d1fae5', fg: '#065f46' },
  REPORTED: { label: '已报道', bg: '#dbeafe', fg: '#1e40af' },
  INFERRED: { label: '推断', bg: '#f3f4f6', fg: '#374151' },
  UNVERIFIED: { label: '未核实', bg: '#fee2e2', fg: '#991b1b' },
}

export default function ResultPage() {
  const { taskId } = useParams()
  const navigate = useNavigate()

  const [task, setTask] = useState(null)
  const [reports, setReports] = useState([])
  const [summary, setSummary] = useState(null)
  const [chainData, setChainData] = useState(null)
  const [narratives, setNarratives] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeChainTab, setActiveChainTab] = useState('upstream')
  const [cancelling, setCancelling] = useState(false)

  // Evidence Inspector：当前选中的关系（点击产业链关系表行时设置）
  const [selectedRelation, setSelectedRelation] = useState(null)

  // 重新生成报告（刷新为新章节结构）
  const [regenerating, setRegenerating] = useState(false)
  const [regenMsg, setRegenMsg] = useState('')

  const handleRegenerate = async () => {
    if (!window.confirm('确定要根据最新章节结构重新生成 HTML 与 Word 报告吗？此操作使用已分析的数据重新生成，不会重新调用大模型。')) return
    setRegenerating(true)
    setRegenMsg('')
    try {
      const res = await regenerateReports(taskId)
      setRegenMsg(`已重新生成：${res.html_report} / ${res.docx_report}`)
    } catch (e) {
      setRegenMsg('重新生成失败，请稍后重试')
    } finally {
      setRegenerating(false)
    }
  }

  const unsubscribeRef = useRef(null)

  useEffect(() => {
    loadInitialData()
    return () => {
      if (unsubscribeRef.current) unsubscribeRef.current()
    }
  }, [taskId])

  async function loadInitialData() {
    try {
      const data = await getTask(taskId)
      setTask(data.task)
      setReports(data.reports || [])
      setSummary(data.summary)
      setChainData(data.chain_data || null)

      // 检查是否已有缓存的叙述
      if (data.chain_data?._narratives) {
        setNarratives(data.chain_data._narratives)
      }

      if (!['completed', 'failed', 'cancelled'].includes(data.task.status)) {
        subscribeToProgress()
      }
    } catch (e) {
      console.error('加载任务详情失败:', e)
    } finally {
      setLoading(false)
    }
  }

  function subscribeToProgress() {
    unsubscribeRef.current = subscribeProgress(
      taskId,
      (progressData) => {
        setTask((prev) => ({
          ...prev,
          status: progressData.status,
          progress: progressData.progress,
          progress_message: progressData.message,
        }))
      },
      (finalData) => {
        getTask(taskId).then((data) => {
          setTask(data.task)
          setReports(data.reports || [])
          setSummary(data.summary)
          setChainData(data.chain_data || null)
          if (data.chain_data?._narratives) {
            setNarratives(data.chain_data._narratives)
          }
        })
      }
    )
  }

  async function handleCancel() {
    if (!window.confirm('确定要终止当前任务吗？已下载的数据将保留。')) return
    setCancelling(true)
    try {
      await cancelTask(taskId)
      const data = await getTask(taskId)
      setTask(data.task)
    } catch (e) {
      console.error('终止任务失败:', e)
      alert('终止失败: ' + (e.response?.data?.detail || e.message))
    } finally {
      setCancelling(false)
    }
  }

  if (loading) {
    return <div className="progress-section"><h3>加载中...</h3></div>
  }

  if (!task) {
    return (
      <div className="error-card">
        <h3>任务不存在</h3>
        <p>请返回首页重新创建任务</p>
      </div>
    )
  }

  const isRunning = !['completed', 'failed', 'cancelled'].includes(task.status)
  const isFailed = task.status === 'failed'
  const isCompleted = task.status === 'completed'

  const segments = chainData?.chain_segments || {}
  const companies = chainData?.companies || []
  const relations = chainData?.relations || []
  const referenceReports = chainData?._reference_reports || []
  // 仅保留「抽屉内相关研报不为空」的关系（相关研报为空的关系行不在前端展示）
  const visibleRelations = relations.filter(
    (r) => findRelatedReports(referenceReports, r.from_company, r.to_company).length > 0
  )
  const transmissions = chainData?.transmission_relations || []
  const causalLogic = chainData?.chain_causal_logic || ''

  return (
    <div className="result-page">
      <span className="back-link" onClick={() => navigate('/')}>
        &larr; 返回首页
      </span>

      {/* 运行中 */}
      {isRunning && (
        <div className="progress-section">
          <h3>{task.industry_name} - 产业链分析</h3>
          <div className="status-text">{task.progress_message || '准备中...'}</div>
          <div className="progress-bar-container">
            <div className="progress-bar" style={{ width: `${task.progress}%` }} />
          </div>
          <div className="progress-pct">{task.progress}%</div>
          <button
            className="btn-cancel"
            onClick={handleCancel}
            disabled={cancelling}
          >
            {cancelling ? '正在终止...' : '终止任务'}
          </button>
        </div>
      )}

      {/* 失败 */}
      {isFailed && (
        <div className="error-card">
          <h3>分析失败</h3>
          <p>{task.error_message || '未知错误'}</p>
        </div>
      )}

      {/* 已取消 */}
      {task.status === 'cancelled' && (
        <div className="cancelled-card">
          <h3>任务已终止</h3>
          <p>{task.industry_name} 的产业链分析已被终止。已下载的数据已保留。</p>
        </div>
      )}

      {/* 完成 */}
      {isCompleted && (
        <>
          {/* 标题 + 操作按钮 */}
          <div className="result-header">
            <h2>{task.industry_name} 产业链分析报告</h2>
            <div className="result-actions">
              <a href={getHtmlReportUrl(taskId)} target="_blank" rel="noreferrer">
                <button className="btn-download btn-html">下载 HTML 报告</button>
              </a>
              <a href={getReportDownloadUrl(taskId)} target="_blank" rel="noreferrer">
                <button className="btn-download">下载 Word 报告</button>
              </a>
              <button className="btn-download btn-regen" onClick={handleRegenerate} disabled={regenerating}>
                {regenerating ? '生成中…' : '重新生成报告'}
              </button>
            </div>
            {regenMsg && <p className="regen-msg">{regenMsg}</p>}
          </div>

          {/* ═══ 第一章：产业链全景概览（定义、流转、市场规模，原1+原5） ═══ */}
          <ReportSection title="第一章  产业链全景概览（定义、流转、市场规模）">
            {chainData?.industry_description && (
              <p className="section-text">{chainData.industry_description}</p>
            )}
            {narratives?.industry_boundary && (
              <div className="narrative-block">
                <p>{narratives.industry_boundary}</p>
              </div>
            )}
            {summary?.chain_flow && (
              <div className="chain-flow-path">
                <strong>产业链流转路径：</strong>{summary.chain_flow}
              </div>
            )}
            {narratives?.industry_profile && (
              <div className="narrative-block">
                <p>{narratives.industry_profile}</p>
              </div>
            )}
            {/* 市场数据 */}
            {chainData?.market_data && Object.values(chainData.market_data).some(v => v && (Array.isArray(v) ? v.length > 0 : true)) && (
              <>
                <div className="market-data-grid">
                  {chainData.market_data.market_size && (
                    <div className="market-data-item">
                      <div className="market-data-label">市场规模</div>
                      <div className="market-data-value">{chainData.market_data.market_size}</div>
                    </div>
                  )}
                  {chainData.market_data.forecast && (
                    <div className="market-data-item">
                      <div className="market-data-label">市场预测</div>
                      <div className="market-data-value">{chainData.market_data.forecast}</div>
                    </div>
                  )}
                  {chainData.market_data.competition_landscape && (
                    <div className="market-data-item">
                      <div className="market-data-label">竞争格局</div>
                      <div className="market-data-value">{chainData.market_data.competition_landscape}</div>
                    </div>
                  )}
                  {chainData.market_data.policy_environment && (
                    <div className="market-data-item">
                      <div className="market-data-label">政策环境</div>
                      <div className="market-data-value">{chainData.market_data.policy_environment}</div>
                    </div>
                  )}
                </div>
                {chainData.market_data.key_drivers?.length > 0 && (
                  <div className="market-data-tags-section">
                    <div className="market-data-label">核心驱动因素</div>
                    <div className="market-data-tags">
                      {chainData.market_data.key_drivers.map((d, i) => (
                        <span key={i} className="market-tag driver">{d}</span>
                      ))}
                    </div>
                  </div>
                )}
                {chainData.market_data.opportunities?.length > 0 && (
                  <div className="market-data-tags-section">
                    <div className="market-data-label">发展机遇</div>
                    <div className="market-data-tags">
                      {chainData.market_data.opportunities.map((o, i) => (
                        <span key={i} className="market-tag opportunity">{o}</span>
                      ))}
                    </div>
                  </div>
                )}
                {chainData.market_data.risks?.length > 0 && (
                  <div className="market-data-tags-section">
                    <div className="market-data-label">风险因素</div>
                    <div className="market-data-tags">
                      {chainData.market_data.risks.map((r, i) => (
                        <span key={i} className="market-tag risk">{r}</span>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </ReportSection>

          {/* ═══ 第二章：产业链深度拆解（原3） ═══ */}
          <ReportSection title="第二章  产业链深度拆解">
            {/* Tab 切换 */}
            <div className="chain-tabs">
              {CHAIN_TABS.map((tab) => {
                const segs = segments[tab.key] || []
                return (
                  <button
                    key={tab.key}
                    className={`chain-tab ${activeChainTab === tab.key ? 'active' : ''}`}
                    onClick={() => setActiveChainTab(tab.key)}
                  >
                    {tab.label}
                    <span className="tab-count">{segs.length}</span>
                  </button>
                )
              })}
            </div>

            {/* 当前 Tab 的叙述 */}
            {narratives && narratives[NARRATIVE_KEYS[activeChainTab]] && (
              <div className="narrative-block">
                <p>{narratives[NARRATIVE_KEYS[activeChainTab]]}</p>
              </div>
            )}

            {/* 当前 Tab 的环节列表 */}
            {(segments[activeChainTab] || []).length === 0 ? (
              <p className="empty-hint">暂无该层级的详细数据。</p>
            ) : (
              <div className="segments-list">
                {(segments[activeChainTab] || []).map((seg, idx) => (
                  <SegmentCard
                    key={idx}
                    segment={seg}
                    companiesMap={companiesMap(companies)}
                  />
                ))}
              </div>
            )}
          </ReportSection>

          {/* ═══ 第三章：产业逻辑分析（原2+原4） ═══ */}
          {((causalLogic || narratives?.causal_logic) || (transmissions.length > 0 || narratives?.transmission_path)) && (
            <ReportSection title="第三章  产业逻辑分析">
              {narratives?.causal_logic && (
                <div className="narrative-block">
                  <p>{narratives.causal_logic}</p>
                </div>
              )}
              {causalLogic && (
                <div className="causal-logic-block">
                  <strong>产业链成因逻辑：</strong>
                  <p>{causalLogic}</p>
                </div>
              )}
              {narratives?.transmission_path && (
                <div className="narrative-block">
                  <p>{narratives.transmission_path}</p>
                </div>
              )}
              {transmissions.length > 0 && (
                <TransmissionSection transmissions={transmissions} />
              )}
            </ReportSection>
          )}

          {/* ═══ 第四章：产业未来趋势与风险（原6+原8） ═══ */}
          {(narratives?.trend_deduction || narratives?.risk_analysis) && (
            <ReportSection title="第四章  产业未来趋势与风险">
              {narratives?.trend_deduction && (
                <>
                  <div className="subsection-title">未来趋势</div>
                  <div className="trend-deduction-content">
                    <MarkdownRenderer content={narratives.trend_deduction} />
                  </div>
                </>
              )}
              {narratives?.risk_analysis && (
                <>
                  <div className="subsection-title">风险分析</div>
                  <div className="narrative-block">
                    <MarkdownRenderer content={narratives.risk_analysis} />
                  </div>
                </>
              )}
            </ReportSection>
          )}

          {/* ═══ 第五章：近期产业链动态（原9） ═══ */}
          {chainData?.events && chainData.events.length > 0 && (
            <ReportSection title="第五章  近期产业链动态" id="recent-events">
              <EventTimeline
                events={chainData.events}
                eventWindow={chainData.event_window}
                eventPolicy={chainData.event_policy}
                referenceReports={referenceReports}
              />
            </ReportSection>
          )}

          {/* 参考研报板块已按要求从前端移除；后端 _reference_reports 字段保留，供 Evidence Inspector 交叉引用使用 */}

          {/* ═══ 附录 · 重点企业分析（原 重点企业介绍） ═══ */}
          {(() => {
            const filteredCompanies = companies.filter((c) => {
              if (!c.name || !String(c.name).trim()) return false
              if (!c.stock_code || !String(c.stock_code).trim()) return false
              if (!c.chain_position || !String(c.chain_position).trim()) return false
              if (!c.sub_segment || !String(c.sub_segment).trim()) return false
              if (!c.main_business || !String(c.main_business).trim()) return false
              const products = c.products || []
              if (!Array.isArray(products) || products.length === 0) return false
              if (products.every((p) => !p || !String(p).trim())) return false
              return true
            })
            if (filteredCompanies.length === 0) return null

            return (
            <ReportSection title="附录 · 重点企业分析" id="key-companies">
              <div className="companies-table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>企业名称</th>
                      <th>股票代码</th>
                      <th>产业链位置</th>
                      <th>细分环节</th>
                      <th>主营业务</th>
                      <th>核心产品</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredCompanies.slice(0, 30).map((c, i) => (
                      <tr key={i}>
                        <td className="company-name">{c.name}</td>
                        <td><span className="stock-code">{c.stock_code}</span></td>
                        <td>
                          <span className={`position-tag position-${c.chain_position}`}>
                            {c.chain_position}
                          </span>
                        </td>
                        <td>{c.sub_segment}</td>
                        <td className="text-ellipsis" title={c.main_business}>{c.main_business}</td>
                        <td className="text-ellipsis" title={(c.products || []).join('、')}>
                          {(c.products || []).slice(0, 3).join('、')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {filteredCompanies.length > 30 && (
                <p className="more-hint">共 {filteredCompanies.length} 家企业，仅展示前 30 家</p>
              )}
            </ReportSection>
            )
          })()}

          {/* ═══ 附录 · 企业关系（原 产业链关系） ═══ */}
          {visibleRelations.length > 0 && (
            <ReportSection title="附录 · 企业关系">
              <div className="relations-table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>供应方</th>
                      <th>需求方</th>
                      <th>关系类型</th>
                      <th>详情</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleRelations.slice(0, 50).map((r, i) => {
                      const isSelected = selectedRelation === r
                      return (
                        <tr
                          key={i}
                          className={`relation-row-clickable${isSelected ? ' relation-row-selected' : ''}`}
                          onClick={() => setSelectedRelation(r)}
                          title="点击查看证据详情"
                        >
                          <td className="company-name">{r.from_company || '-'}</td>
                          <td className="company-name">{r.to_company || '-'}</td>
                          <td>
                            <span className={`relation-tag relation-${r.type || ''}`}>
                              {r.type || '-'}
                            </span>
                          </td>
                          <td className="text-ellipsis" title={r.detail}>{r.detail || '-'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                {visibleRelations.length > 50 && (
                  <p className="more-hint">共 {visibleRelations.length} 条关系，仅展示前 50 条</p>
                )}
              </div>
            </ReportSection>
          )}
          {/* ═══ Evidence Inspector 抽屉（点击关系行触发，右侧滑入） ═══ */}
          {selectedRelation && (
            <EvidenceInspector
              relation={selectedRelation}
              referenceReports={chainData?._reference_reports || []}
              onClose={() => setSelectedRelation(null)}
            />
          )}
        </>
      )}
    </div>
  )
}

/* ── 辅助组件 ── */

function ReportSection({ title, children, id }) {
  return (
    <div className="report-section" id={id}>
      <h3 className="report-section-title">{title}</h3>
      <div className="report-section-body">
        {children}
      </div>
    </div>
  )
}

function MarkdownRenderer({ content }) {
  const rawHtml = marked.parse(content || '', { breaks: true, gfm: true })
  const html = DOMPurify.sanitize(rawHtml)
  return <div className="markdown-body" dangerouslySetInnerHTML={{ __html: html }} />
}

function SegmentCard({ segment, companiesMap }) {
  const [companiesExpanded, setCompaniesExpanded] = useState(false)
  const segCompanies = (segment.companies || []).map(name => companiesMap[name]).filter(Boolean)

  // 代表企业超过 10 家时折叠（与图谱视图一致）
  const COMPANIES_LIMIT = 10
  const companiesNeedTruncate = segCompanies.length > COMPANIES_LIMIT
  const displayCompanies = companiesExpanded ? segCompanies : segCompanies.slice(0, COMPANIES_LIMIT)

  // P0: 四维度属性
  const attrs = [
    { label: '功能定位', value: segment.functional_position },
    { label: '价值占比', value: segment.value_proportion },
    { label: '技术壁垒', value: segment.technical_barrier },
    { label: '竞争格局', value: segment.competitive_landscape },
  ].filter(a => a.value)

  return (
    <div className="segment-card">
      <div className="segment-header">
        <h4>{segment.segment_name || '未命名环节'}</h4>
        {segment.concentration && (
          <span className={`concentration-tag concentration-${segment.concentration}`}>
            集中度: {segment.concentration}
          </span>
        )}
      </div>
      {segment.description && (
        <p className="segment-desc">{segment.description}</p>
      )}

      {/* P0: 四维度属性表 */}
      {attrs.length > 0 && (
        <div className="segment-attrs">
          {attrs.map((attr, i) => (
            <div key={i} className="attr-row">
              <span className="attr-label">{attr.label}</span>
              <span className="attr-value">{attr.value}</span>
            </div>
          ))}
        </div>
      )}

      {segCompanies.length > 0 && (
        <div className="segment-companies">
          <span className="segment-label">代表企业：</span>
          <div className="company-chips">
            {displayCompanies.map((c, i) => (
              <span key={i} className="company-chip" title={c.main_business || ''}>
                {c.name}
                {c.stock_code && <span className="chip-code">{c.stock_code}</span>}
              </span>
            ))}
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
          {companiesNeedTruncate && (
            <div className="chain-segment-companies-footer">
              <span className="chain-segment-companies-count">共 {segCompanies.length} 家</span>
              <button
                type="button"
                className="chain-segment-toggle chain-segment-toggle-inline"
                onClick={() => setCompaniesExpanded((v) => !v)}
              >
                {companiesExpanded ? '收起企业' : `展开全部 ${segCompanies.length} 家`}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// P0: 传导关系展示组件
function TransmissionSection({ transmissions }) {
  // 按传导类型分组
  const groups = {}
  for (const tr of transmissions) {
    const type = tr.transmission_type || '其他'
    if (!groups[type]) groups[type] = []
    groups[type].push(tr)
  }

  const typeColors = {
    '成本传导': '#ef4444',
    '技术传导': '#3b82f6',
    '价值传导': '#10b981',
  }

  return (
    <div className="transmission-section">
      {Object.entries(groups).map(([type, items]) => (
        <div key={type} className="transmission-group">
          <h4 className="transmission-group-title">
            <span
              className="transmission-dot"
              style={{ background: typeColors[type] || '#6b7280' }}
            />
            {type}路径
          </h4>
          <div className="transmission-list">
            {items.map((tr, i) => (
              <div key={i} className="transmission-item">
                <div className="transmission-flow">
                  <span className="transmission-from">{tr.from_segment}</span>
                  <span className="transmission-arrow">&rarr;</span>
                  <span className="transmission-to">{tr.to_segment}</span>
                </div>
                {tr.description && (
                  <p className="transmission-desc">{tr.description}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/* ── 工具函数 ── */

function companiesMap(companies) {
  const map = {}
  for (const c of companies) {
    if (c.name) map[c.name] = c
  }
  return map
}
