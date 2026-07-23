import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { createTask, listTasks } from '../services/api'

const QUICK_TAGS = ['锂电池', '光伏', '半导体', '新能源汽车', '人工智能', '生物医药', '航空航天']

// 后端 created_at 为 UTC（无时区标记），统一按中国时区(UTC+8)显示 年/月/日 时:分（24小时制）
function formatTaskCreatedAt(iso) {
  if (!iso) return ''
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z')
  if (isNaN(d.getTime())) return ''
  const cn = new Date(d.getTime() + 8 * 3600 * 1000)
  const date = `${cn.getUTCFullYear()}/${cn.getUTCMonth() + 1}/${cn.getUTCDate()}`
  const hh = String(cn.getUTCHours()).padStart(2, '0')
  const mm = String(cn.getUTCMinutes()).padStart(2, '0')
  return `${date}  ${hh}:${mm}`
}

export default function HomePage() {
  const [industryName, setIndustryName] = useState('')
  const [maxReports, setMaxReports] = useState(30)
  const [dateRange, setDateRange] = useState(180)
  const [loading, setLoading] = useState(false)
  const [tasks, setTasks] = useState([])
  const navigate = useNavigate()

  useEffect(() => {
    loadTasks()
  }, [])

  async function loadTasks() {
    try {
      const data = await listTasks()
      setTasks(data)
    } catch (e) {
      console.error('加载任务列表失败:', e)
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!industryName.trim() || loading) return

    setLoading(true)
    try {
      const task = await createTask(industryName.trim(), maxReports, dateRange)
      navigate(`/task/${task.id}`)
    } catch (e) {
      console.error('创建任务失败:', e)
      alert('创建任务失败: ' + (e.response?.data?.detail || e.message))
    } finally {
      setLoading(false)
    }
  }

  function getStatusLabel(status) {
    const map = {
      pending: '等待中',
      crawling: '爬取中',
      parsing: '解析中',
      analyzing: '分析中',
      generating: '生成中',
      completed: '已完成',
      failed: '失败',
      cancelled: '已取消',
    }
    return map[status] || status
  }

  function getStatusClass(status) {
    if (status === 'completed') return 'completed'
    if (status === 'failed') return 'failed'
    if (status === 'cancelled') return 'cancelled'
    if (status === 'pending') return 'pending'
    return 'running'
  }

  return (
    <div>
      {/* 主输入区域 */}
      <div className="home-hero">
        <h2>产业链智能分析</h2>
        <p>输入产业名称，AI 自动爬取研报、提取信息、构建产业链图谱并生成专业报告</p>
      </div>

      <div className="input-card">
        <form onSubmit={handleSubmit}>
          <div className="input-group">
            <input
              type="text"
              value={industryName}
              onChange={(e) => setIndustryName(e.target.value)}
              placeholder="请输入产业名称，如：锂电池、光伏、半导体"
              disabled={loading}
              autoFocus
            />
            <button type="submit" className="btn-primary" disabled={loading || !industryName.trim()}>
              {loading ? '创建中...' : '开始分析'}
            </button>
          </div>

          <div className="input-options">
            <label>
              研报上限
              <input
                type="number"
                value={maxReports}
                onChange={(e) => setMaxReports(Number(e.target.value))}
                min={5}
                max={100}
              />
              份
            </label>
            <label>
              时间范围
              <input
                type="number"
                value={dateRange}
                onChange={(e) => setDateRange(Number(e.target.value))}
                min={30}
                max={730}
              />
              天
            </label>
          </div>
        </form>

        <div className="quick-tags">
          <span>热门产业：</span>
          {QUICK_TAGS.map((tag) => (
            <span
              key={tag}
              className="tag"
              onClick={() => setIndustryName(tag)}
            >
              {tag}
            </span>
          ))}
        </div>
      </div>

      {/* 历史任务列表 */}
      {tasks.length > 0 && (
        <div className="history-section">
          <h3>历史任务</h3>
          <div className="task-list">
            {tasks.map((task) => (
              <div
                key={task.id}
                className="task-item"
                onClick={() => navigate(`/task/${task.id}`)}
              >
                <div className="task-info">
                  <h4>{task.industry_name}</h4>
                  <span>
                    {formatTaskCreatedAt(task.created_at)} | 进度 {task.progress}%
                  </span>
                </div>
                <span className={`status-badge ${getStatusClass(task.status)}`}>
                  {getStatusLabel(task.status)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
