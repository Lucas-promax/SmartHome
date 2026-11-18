/**
 * ============================================================
 * HTTP 请求封装 (基于 fetch)
 * 用于人员增删、历史数据查询、下发设备控制指令
 * ============================================================
 * 后期对接指引：
 *   修改 BASE_URL 为真实后端API地址
 *   当前识别接口不需要登录认证，直接对接 FastAPI 后端。
 * ============================================================
 */

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'

// 板端 USB 和 OV7670 共用会话、帧读取与关闭接口。
export const cameraApi = {
  usbDevices: () => request('/camera/usb/devices'),
  connectUsb: (device) => request('/camera/usb/connect', {
    method: 'POST', body: JSON.stringify({ device })
  }),
  ports: () => request('/camera/ports'),
  connect: (port, baudrate) => request('/camera/connect', {
    method: 'POST', body: JSON.stringify({ port, baudrate })
  }),
  disconnect: (session) => request(`/camera/connection?session=${encodeURIComponent(session)}`, { method: 'DELETE' }),
  frame: (session, after, previewAfter = 0) => request(`/camera/frame?session=${encodeURIComponent(session)}&after=${after}&preview_after=${previewAfter}`)
}

export function apiUrl(path = '') {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const apiPrefix = '/api'
  const relativePath = normalizedPath.startsWith(apiPrefix)
    ? normalizedPath.slice(apiPrefix.length) || '/'
    : normalizedPath
  return `${API_BASE_URL}${relativePath}`
}

// 请求超时(ms)
const TIMEOUT = 30000

/**
 * 通用请求函数
 * @param {string} url - 接口路径 (相对于 BASE_URL)
 * @param {object} options - fetch 选项
 * @returns {Promise<any>}
 */
async function request(url, options = {}) {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT)
  const isFormData = options.body instanceof FormData

  const config = {
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers
    },
    signal: controller.signal,
    ...options
  }

  // 对于 GET 请求，移除 Content-Type 头(无 body)
  if (!options.method || options.method === 'GET') {
    // 保留其他自定义头
  }

  try {
    const response = await fetch(`${API_BASE_URL}${url}`, config)
    clearTimeout(timeoutId)

    if (!response.ok) {
      const errorPayload = await response.json().catch(() => null)
      throw new Error(errorPayload?.message || `HTTP ${response.status}: ${response.statusText}`)
    }

    const data = await response.json()
    if (data && data.ok === false) {
      throw new Error(data.message || '请求失败')
    }
    return data && Object.prototype.hasOwnProperty.call(data, 'data') ? data.data : data
  } catch (error) {
    clearTimeout(timeoutId)
    if (error.name === 'AbortError') {
      throw new Error('请求超时')
    }
    throw error
  }
}

async function streamRequest(url, payload, onEvent) {
  const response = await fetch(`${API_BASE_URL}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!response.ok) {
    let message = `HTTP ${response.status}: ${response.statusText}`
    try {
      const data = await response.json()
      message = data.detail || data.message || message
    } catch (error) {
      // Keep the HTTP status message when the response is not JSON.
    }
    throw new Error(message)
  }
  if (!response.body) throw new Error('浏览器不支持流式响应')
  if (!response.headers.get('Content-Type')?.toLowerCase().startsWith('text/event-stream')) {
    throw new Error('助手接口未返回流式响应，请检查后端服务或网络连接')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let terminalEvent = false
  async function dispatch(chunk) {
    const data = chunk.split('\n').filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trimStart()).join('\n')
    if (!data) return
    const event = JSON.parse(data)
    await onEvent(event)
    if (event.type === 'error') throw new Error(event.message || 'Agent 请求失败')
    if (['done', 'confirm_required', 'client_tool_request'].includes(event.type)) terminalEvent = true
  }
  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n/g, '\n')
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() || ''
      for (const chunk of chunks) await dispatch(chunk)
      if (terminalEvent) return
      if (done) {
        if (buffer.trim()) await dispatch(buffer)
        if (!terminalEvent) throw new Error('助手连接提前结束，未收到完整回复，请重试')
        return
      }
    }
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}

// ============================================================
// API 接口封装
// ============================================================

// --- 首页看板 ---
export const homeApi = {
  /** 获取首页环境、设备、告警和事件流 */
  status: () => request('/home/status', { method: 'GET' })
}

export const hardwareApi = {
  send: (payload) => request('/hardware/command', { method: 'POST', body: JSON.stringify(payload) }),
  status: () => request('/hardware/status', { method: 'GET' }),
  ports: () => request('/hardware/ports', { method: 'GET' }),
  configure: (payload) => request('/hardware/serial', { method: 'PUT', body: JSON.stringify(payload) })
}

// --- 系统配置 ---
export const settingsApi = {
  /** 获取首页横幅告警配置 */
  getAlertSettings: () => request('/settings/alerts', { method: 'GET' }),

  /** 保存首页横幅告警配置 */
  updateAlertSettings: (payload) => request('/settings/alerts', {
    method: 'PUT',
    body: JSON.stringify(payload)
  })
}

// --- 人员管理 ---
export const personnelApi = {
  /** 获取人员列表 */
  list: () => request('/persons', { method: 'GET' }),

  /** 新增授权人员 (multipart/form-data) */
  add: (formData) => request('/persons', {
    method: 'POST',
    headers: {}, // 让浏览器自动设置 multipart boundary
    body: formData
  }),

  /** 修改授权人员 */
  update: (id, payload) => request(`/persons/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  }),

  /** 撤销授权，保留数据库和 face_info 信息 */
  delete: (id) => request(`/persons/${id}`, { method: 'DELETE' }),

  /** 删除人员，删除数据库记录和对应 face_info 照片目录 */
  hardDelete: (id) => request(`/persons/${id}/hard-delete`, { method: 'DELETE' }),

  /** 恢复授权，不需要重新上传照片 */
  restore: (id, role = 'resident') => request(`/persons/${id}/restore?role=${encodeURIComponent(role)}`, {
    method: 'POST'
  })
}

// --- 设备控制 ---
const DEVICE_ID_ALIASES = {
  door: 'door_main',
  fan: 'fan_main',
  light: 'light_main',
  window: 'window_main'
}

export const deviceApi = {
  /** 下发设备控制指令 */
  control: (device, action, value = null) => request(`/devices/${DEVICE_ID_ALIASES[device] || device}/control`, {
    method: 'POST',
    body: JSON.stringify({ action, value })
  }),

  /** 下发设备控制指令到真实后端设备接口 */
  controlDevice: (deviceId, action, value = null) => request(`/devices/${deviceId}/control`, {
    method: 'POST',
    body: JSON.stringify({ action, value })
  }),

  /** 获取设备当前状态 */
  status: () => request('/devices', { method: 'GET' })
}

// --- 历史数据 ---
export const historyApi = {
  /** 查询历史数据 */
  query: (type, range) => request(`/history/${type}?range=${range}`, { method: 'GET' }),

  /** 查询系统日志 */
  logs: (params = {}) => {
    const query = new URLSearchParams(params).toString()
    return request(`/logs${query ? `?${query}` : ''}`, { method: 'GET' })
  },

  /** 按条件清理系统日志 */
  cleanupLogs: (payload) => request('/logs', {
    method: 'DELETE',
    body: JSON.stringify(payload)
  })
}

export const logApi = {
  /** 查询系统日志 */
  list: (params = {}) => {
    const query = new URLSearchParams(params).toString()
    return request(`/logs${query ? `?${query}` : ''}`, { method: 'GET' })
  },

  /** 按条件清理系统日志 */
  cleanup: (payload) => request('/logs', {
    method: 'DELETE',
    body: JSON.stringify(payload)
  }
  )
}

// --- 数据分析 ---
export const analysisApi = {
  /** 查询统一数据分析结果 */
  overview: (params = {}) => {
    const query = new URLSearchParams(params).toString()
    return request(`/analysis/overview${query ? `?${query}` : ''}`, { method: 'GET' })
  }
}

// --- 智能助手 ---
export const agentApi = {
  settings: () => request('/agent/settings', { method: 'GET' }),
  updateSettings: (payload) => request('/agent/settings', {
    method: 'PUT',
    body: JSON.stringify(payload)
  }),
  conversations: () => request('/agent/conversations', { method: 'GET' }),
  conversation: (id) => request(`/agent/conversations/${encodeURIComponent(id)}`, { method: 'GET' }),
  updateConversation: (id, payload) => request(`/agent/conversations/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  }),
  deleteConversation: (id) => request(`/agent/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  streamChat: (payload, onEvent) => streamRequest('/agent/chat/stream', payload, onEvent)
}

// --- AI识别 ---
export const aiApi = {
  /** 获取人脸识别记录 */
  faceRecords: (params = {}) => {
    const query = new URLSearchParams(params).toString()
    return request(`/ai/face-records?${query}`, { method: 'GET' })
  },

  /** 获取YOLO识别记录 */
  yoloRecords: (params = {}) => {
    const query = new URLSearchParams(params).toString()
    return request(`/ai/yolo-records?${query}`, { method: 'GET' })
  }
}

// --- 视觉识别 ---
export const visionApi = {
  /** 物体识别：灭火器 / 无人机 */
  fireDroneDetect: (file) => {
    const formData = new FormData()
    formData.append('file', file, file.name || 'camera-frame.jpg')
    return request('/vision/fire-drone-detect', {
      method: 'POST',
      body: formData
    })
  },

  /** 人脸识别：匹配授权人脸并返回门禁动作 */
  faceRecognize: (file) => {
    const formData = new FormData()
    formData.append('file', file, file.name || 'face-frame.jpg')
    return request('/vision/face-recognize', {
      method: 'POST',
      body: formData
    })
  },

  /** 后端模型状态 */
  modelStatus: () => request('/vision/model-status', { method: 'GET' })
}

export default { homeApi, settingsApi, personnelApi, deviceApi, historyApi, logApi, analysisApi, agentApi, aiApi, visionApi }
