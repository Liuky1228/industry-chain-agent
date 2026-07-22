import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

/**
 * 创建产业链分析任务
 */
export async function createTask(industryName, maxReports = 30, dateRangeDays = 180) {
  const resp = await api.post('/tasks', {
    industry_name: industryName,
    max_reports: maxReports,
    date_range_days: dateRangeDays,
  })
  return resp.data
}

/**
 * 获取任务列表
 */
export async function listTasks() {
  const resp = await api.get('/tasks')
  return resp.data
}

/**
 * 获取任务详情
 */
export async function getTask(taskId) {
  const resp = await api.get(`/tasks/${taskId}`)
  return resp.data
}

/**
 * 订阅任务进度 (SSE)
 * @param {string} taskId
 * @param {function} onProgress - 回调 (data: {status, progress, message}) => void
 * @param {function} onDone - 完成回调
 * @returns {function} 取消订阅函数
 */
export function subscribeProgress(taskId, onProgress, onDone) {
  const url = `/api/tasks/${taskId}/stream`
  const eventSource = new EventSource(url)

  // 防重复触发 onDone 的 flag（正常 progress 事件和 error fallback 都可能触发）
  let settled = false
  const settle = (payload) => {
    if (settled) return
    settled = true
    eventSource.close()
    if (onProgress) onProgress(payload)
    if (onDone) onDone(payload)
  }

  eventSource.addEventListener('progress', (event) => {
    try {
      const data = JSON.parse(event.data)
      onProgress(data)
      if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
        settle(data)
      }
    } catch (e) {
      console.error('SSE parse error:', e)
    }
  })

  // Bug #3: 原实现仅 close 不调 onDone，会导致 UI 永远卡在"运行中"
  // 改为：网络出错时拉一次 task 状态，如果已终态则走 onDone 流程
  eventSource.onerror = () => {
    eventSource.close()
    // 异步拉一次最新状态判断是否终态
    api.get(`/tasks/${taskId}`)
      .then((resp) => {
        const t = resp && resp.task
        if (!t) {
          // 任务可能已被删除
          settle({ status: 'failed', progress: 0, message: '任务不存在' })
          return
        }
        if (t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled') {
          settle({
            status: t.status,
            progress: t.progress,
            message: t.progress_message || '',
          })
        }
        // 否则 task 仍在运行，UI 维持现状（用户可手动刷新页面）
      })
      .catch((e) => {
        console.error('SSE error fallback failed:', e)
        // 网络都不通时不做任何操作，让 UI 维持；用户可手动刷新
      })
  }

  return () => eventSource.close()
}

/**
 * 下载报告文件
 */
export function getReportDownloadUrl(taskId) {
  return `/api/tasks/${taskId}/report`
}

/**
 * 获取 HTML 报告下载地址（与前端展示 1:1 对齐，自包含可离线打开）
 */
export function getHtmlReportUrl(taskId) {
  return `/api/tasks/${taskId}/html-report`
}

/**
 * 根据已存储的分析数据重新生成 HTML + Word 报告（不重新调用大模型）
 */
export async function regenerateReports(taskId) {
  const resp = await api.post(`/tasks/${taskId}/regenerate`, null, {
    timeout: 120000,
  })
  return resp.data
}

/**
 * 生成 LLM 分析叙述（异步，耗时较长）
 */
export async function generateNarratives(taskId) {
  const resp = await api.post(`/tasks/${taskId}/narratives`, null, {
    timeout: 300000, // 5 分钟超时
  })
  return resp.data
}

/**
 * 获取已生成的叙述
 */
export async function getNarratives(taskId) {
  const resp = await api.get(`/tasks/${taskId}/narratives`)
  return resp.data
}

/**
 * P2: 生成独立趋势推演（基于传导逻辑的深度推演）
 */
export async function generateTrend(taskId) {
  const resp = await api.post(`/tasks/${taskId}/trend`, null, {
    timeout: 180000, // 3 分钟超时
  })
  return resp.data
}

/**
 * P2: 获取报告校验结果
 */
export async function getValidation(taskId) {
  const resp = await api.get(`/tasks/${taskId}/validation`)
  return resp.data
}

/**
 * 终止任务
 */
export async function cancelTask(taskId) {
  const resp = await api.post(`/tasks/${taskId}/cancel`)
  return resp.data
}
