/**
 * ============================================================
 * WebSocket 封装
 * 用于接收后端实时推送: 温度、门窗状态、灯光亮度、
 *   摄像头帧数据、YOLO识别坐标、人脸识别结果
 * ============================================================
 * 后期对接指引：
 *   修改 WS_URL 为真实WebSocket地址
 *   根据后端约定的消息格式调整 onMessage 中的解析逻辑
 *   当前版本使用 mock.js 模拟数据
 * ============================================================
 */

// 【后期对接】修改此处为真实WebSocket地址
const WS_URL = 'ws://localhost:8080/ws/device'

// 重连配置
const RECONNECT_DELAY = 3000   // 重连间隔(ms)
const MAX_RECONNECT = 10       // 最大重连次数

// 全局回调注册表 { eventName: [callback, ...] }
const listeners = {}

/**
 * 注册事件监听
 * @param {string} event - 事件名: 'sensor' | 'yolo' | 'face' | 'alert' | 'connected' | 'disconnected'
 * @param {function} callback
 */
export function on(event, callback) {
  if (!listeners[event]) listeners[event] = []
  listeners[event].push(callback)
}

/**
 * 移除事件监听
 */
export function off(event, callback) {
  if (!listeners[event]) return
  listeners[event] = listeners[event].filter(cb => cb !== callback)
}

/**
 * 触发事件
 */
function emit(event, data) {
  if (listeners[event]) {
    listeners[event].forEach(cb => {
      try { cb(data) } catch (e) { console.error(`[WS] ${event} 回调异常:`, e) }
    })
  }
}

// WebSocket 实例
let ws = null
let reconnectCount = 0
let reconnectTimer = null
let intentionalClose = false

/**
 * 建立WebSocket连接
 */
export function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    console.log('[WS] 已连接或正在连接中')
    return
  }

  intentionalClose = false
  console.log(`[WS] 正在连接 ${WS_URL} ...`)

  try {
    ws = new WebSocket(WS_URL)

    ws.onopen = () => {
      console.log('[WS] 连接成功')
      reconnectCount = 0
      emit('connected', { timestamp: new Date().toISOString() })
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        handleMessage(msg)
      } catch (e) {
        console.error('[WS] 消息解析失败:', e, '原始数据:', event.data)
      }
    }

    ws.onerror = (error) => {
      console.error('[WS] 连接错误:', error)
      emit('error', error)
    }

    ws.onclose = (event) => {
      console.log(`[WS] 连接关闭, code=${event.code}`)
      emit('disconnected', { code: event.code })
      if (!intentionalClose) {
        attemptReconnect()
      }
    }
  } catch (e) {
    console.error('[WS] 创建连接失败:', e)
    attemptReconnect()
  }
}

/**
 * 关闭WebSocket连接
 */
export function disconnect() {
  intentionalClose = true
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (ws) {
    ws.close(1000, '客户端主动关闭')
    ws = null
  }
}

/**
 * 重连机制
 */
function attemptReconnect() {
  if (reconnectCount >= MAX_RECONNECT) {
    console.warn(`[WS] 已达最大重连次数(${MAX_RECONNECT})，停止重连`)
    return
  }
  reconnectCount++
  console.log(`[WS] 第 ${reconnectCount} 次重连，等待 ${RECONNECT_DELAY}ms ...`)
  reconnectTimer = setTimeout(() => {
    connect()
  }, RECONNECT_DELAY)
}

/**
 * 根据消息类型分发到对应事件
 * 【后期对接】根据后端实际消息格式调整此函数
 */
function handleMessage(msg) {
  const { type, data } = msg

  switch (type) {
    case 'sensor':       // 传感器数据: 温度、门窗、灯光、风扇
      emit('sensor', data)
      break
    case 'yolo':         // YOLO物体检测结果
      emit('yolo', data)
      break
    case 'face':         // 人脸识别结果
      emit('face', data)
      break
    case 'alert':        // 告警消息
      emit('alert', data)
      break
    case 'camera_frame': // 摄像头帧 (base64图片)
      emit('camera_frame', data)
      break
    default:
      console.log('[WS] 未知消息类型:', type, data)
  }
}

/**
 * 发送消息到后端 (用于通过WebSocket下发设备控制指令)
 * @param {object} data - { device: 'door'|'fan'|'light', action: string, value?: any }
 */
export function sendCommand(data) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.warn('[WS] 未连接，无法发送指令')
    return false
  }
  ws.send(JSON.stringify({
    type: 'command',
    data: data,
    timestamp: new Date().toISOString()
  }))
  return true
}

/**
 * 获取连接状态
 * @returns {string} 'connecting' | 'open' | 'closing' | 'closed' | 'null'
 */
export function getStatus() {
  if (!ws) return 'null'
  const states = ['connecting', 'open', 'closing', 'closed']
  return states[ws.readyState] || 'unknown'
}
