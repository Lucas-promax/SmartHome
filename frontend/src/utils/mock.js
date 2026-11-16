/**
 * ============================================================
 * Mock 模拟数据模块
 * 用于演示阶段生成所有假数据，后期替换为真实WebSocket + HTTP
 * ============================================================
 * 后期对接指引：
 *   1. WebSocket数据 → 替换 src/utils/websocket.js 中的连接地址
 *   2. HTTP接口   → 替换 src/utils/http.js 中的 baseURL
 *   3. 删除本文件中对应的 mock 数据生成逻辑
 * ============================================================
 */

// ---------- 工具函数 ----------
const rand = (min, max) => Math.floor(Math.random() * (max - min + 1) + min)
const randFloat = (min, max, decimals = 1) => parseFloat((Math.random() * (max - min) + min).toFixed(decimals))

// ---------- 传感器状态 ----------
let mockTemp = 24.5        // 当前温度
let mockHumidity = 52      // 当前湿度
let mockDoorLocked = true  // 入户门锁定
let mockWindowOpen = false // 窗户开关
let mockFanOn = false      // 风扇状态
const MAX_OPEN_DURATION = 30 // 窗户最大开启时长(秒), 超时触发告警

// ---------- 数据历史存储 ----------
export const tempHistory = []      // [{ time, value }]
export const doorHistory = []      // [{ time, action }]
export const windowHistory = []    // [{ time, action }]
export const lightHistory = []     // [{ time, value }]
export const lightBulbEvents = []  // 灯泡检测事件
export const faceRecords = []      // 人脸识别记录
export const yoloRecords = []      // YOLO物体识别记录
export const systemLogs = []       // 系统日志

// 初始化历史数据(最近7天)
const now = Date.now()
for (let i = 7 * 24; i >= 0; i -= 1) {
  const t = now - i * 3600000
  tempHistory.push({ time: new Date(t).toISOString(), value: randFloat(18, 32) })
  if (i % 4 === 0) doorHistory.push({ time: new Date(t).toISOString(), action: Math.random() > 0.7 ? 'close' : 'open' })
  if (i % 6 === 0) windowHistory.push({ time: new Date(t).toISOString(), action: Math.random() > 0.8 ? 'close' : 'open' })
  lightHistory.push({ time: new Date(t).toISOString(), value: rand(20, 100) })
}

// ---------- 模拟人脸库 ----------
const mockFaces = [
  { name: '张三', avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=zhang' },
  { name: '李四', avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=li' },
  { name: '王五', avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=wang' }
]

// ---------- 模拟人员列表 ----------
export const personnelList = [
  { id: 1, name: '张三', avatar: mockFaces[0].avatar, createdAt: '2026-06-15 10:30:00' },
  { id: 2, name: '李四', avatar: mockFaces[1].avatar, createdAt: '2026-06-20 14:22:00' },
  { id: 3, name: '王五', avatar: mockFaces[2].avatar, createdAt: '2026-07-01 09:15:00' }
]

// ---------- YOLO可检测物体列表 ----------
const yoloObjects = [
  { label: 'person', name: '人' },
  { label: 'chair', name: '椅子' },
  { label: 'laptop', name: '笔记本电脑' },
  { label: 'cell phone', name: '手机' },
  { label: 'book', name: '书' },
  { label: 'light bulb', name: '灯泡' },
  { label: 'cup', name: '杯子' },
  { label: 'backpack', name: '背包' }
]

// ============================================================
// 模拟WebSocket数据推送 (每个tick推送一次)
// ============================================================
let tickId = 0
export function generateMockSensorData() {
  tickId++

  // 温度自然波动 ±0.3°C
  mockTemp = parseFloat((mockTemp + (Math.random() - 0.5) * 0.6).toFixed(1))
  // 限制范围
  mockTemp = Math.max(16, Math.min(35, mockTemp))

  // 湿度自然波动 ±2%，限制在室内常见范围
  mockHumidity = Math.round(mockHumidity + rand(-2, 2))
  mockHumidity = Math.max(25, Math.min(85, mockHumidity))

  // 灯光亮度 (0~100)
  const lightLevel = Math.min(100, Math.max(0, 65 + rand(-10, 10)))

  // 偶尔模拟门窗状态变化(每30个tick约一次)
  if (tickId % 30 === 0) {
    mockWindowOpen = !mockWindowOpen
    windowHistory.push({ time: new Date().toISOString(), action: mockWindowOpen ? 'open' : 'close' })
    addSystemLog('window', mockWindowOpen ? '窗户已开启' : '窗户已关闭', 'info')
  }

  // 入户门偶尔开关
  if (tickId % 45 === 0 && Math.random() > 0.6) {
    mockDoorLocked = !mockDoorLocked
    doorHistory.push({ time: new Date().toISOString(), action: mockDoorLocked ? 'lock' : 'unlock' })
    addSystemLog('door', mockDoorLocked ? '入户门已锁定' : '入户门已解锁', mockDoorLocked ? 'info' : 'warning')
  }

  // 记录温度历史(每分钟一次)
  if (tickId % 4 === 0) {
    tempHistory.push({ time: new Date().toISOString(), value: mockTemp })
    if (tempHistory.length > 1000) tempHistory.shift()
  }

  // 记录灯光历史
  if (tickId % 4 === 0) {
    lightHistory.push({ time: new Date().toISOString(), value: lightLevel })
    if (lightHistory.length > 1000) lightHistory.shift()
  }

  return {
    temperature: mockTemp,
    humidity: mockHumidity,
    doorLocked: mockDoorLocked,
    windowOpen: mockWindowOpen,
    fanOn: mockFanOn,
    lightLevel: lightLevel,
    timestamp: new Date().toISOString()
  }
}

// ============================================================
// 模拟YOLO检测框生成 (用于摄像头视频叠加)
// ============================================================
export function generateMockYoloDetections(frameWidth = 640, frameHeight = 480) {
  const count = rand(0, 4)
  const detections = []
  for (let i = 0; i < count; i++) {
    const obj = yoloObjects[rand(0, yoloObjects.length - 1)]
    const x = rand(50, frameWidth - 150)
    const y = rand(50, frameHeight - 150)
    const w = rand(40, 120)
    const h = rand(60, 140)
    detections.push({
      class: obj.label,
      name: obj.name,
      confidence: randFloat(0.65, 0.99, 2),
      bbox: [x, y, w, h] // [x, y, width, height]
    })

    // 记录YOLO日志
    yoloRecords.push({
      id: yoloRecords.length + 1,
      objectClass: obj.label,
      objectName: obj.name,
      confidence: detections[i].confidence,
      // 模拟抓拍图 (使用占位图)
      snapshot: `https://picsum.photos/seed/yolo${yoloRecords.length}/320/240`,
      timestamp: new Date().toISOString()
    })
    if (yoloRecords.length > 500) yoloRecords.shift()
  }

  // 检查是否检测到灯泡
  const hasBulb = detections.some(d => d.class === 'light bulb')
  if (hasBulb) {
    lightBulbEvents.push({
      time: new Date().toISOString(),
      action: 'auto_turn_on',
      message: '检测到灯泡目标，自动下发开灯指令'
    })
    if (lightBulbEvents.length > 100) lightBulbEvents.shift()
  }

  return { detections, hasBulb }
}

// ============================================================
// 模拟人脸识别结果生成
// ============================================================
export function generateMockFaceRecognition() {
  // 70% 概率产生识别事件
  if (Math.random() > 0.7) {
    const isAuthorized = Math.random() > 0.25 // 75% 授权通过
    const face = mockFaces[rand(0, mockFaces.length - 1)]
    const record = {
      id: faceRecords.length + 1,
      snapshot: `https://picsum.photos/seed/face${faceRecords.length}/160/160`,
      name: isAuthorized ? face.name : (Math.random() > 0.5 ? '未知人员' : '伪造攻击'),
      result: isAuthorized ? 'authorized' : 'rejected',
      resultText: isAuthorized ? '授权通过' : '伪造人脸拒绝',
      timestamp: new Date().toISOString()
    }
    faceRecords.push(record)
    if (faceRecords.length > 500) faceRecords.shift()

    addSystemLog('face', `人脸识别: ${record.name} - ${record.resultText}`, isAuthorized ? 'info' : 'warning')
    return record
  }
  return null
}

// ============================================================
// 系统日志记录
// ============================================================
function addSystemLog(type, message, level = 'info') {
  systemLogs.unshift({
    id: systemLogs.length + 1,
    type,      // door | window | light | fan | face | yolo | system
    message,
    level,     // info | warning | error
    timestamp: new Date().toISOString()
  })
  if (systemLogs.length > 1000) systemLogs.length = 1000
}

// 手动触发日志(供控制操作使用)
export function addManualLog(type, message, level = 'info') {
  addSystemLog(type, message, level)
}

// ============================================================
// 模拟设备控制响应
// ============================================================
export function mockDeviceControl(device, action, value = null) {
  switch (device) {
    case 'door':
      mockDoorLocked = action === 'unlock'
      addSystemLog('door', action === 'unlock' ? '入户门已解锁' : '入户门已锁定', action === 'unlock' ? 'warning' : 'info')
      doorHistory.push({ time: new Date().toISOString(), action })
      break
    case 'window':
      mockWindowOpen = action === 'open'
      addSystemLog('window', action === 'open' ? '窗户已开启' : '窗户已关闭', 'info')
      windowHistory.push({ time: new Date().toISOString(), action })
      break
    case 'fan':
      mockFanOn = action === 'on'
      addSystemLog('fan', action === 'on' ? '风扇已开启' : '风扇已关闭', 'info')
      break
    case 'light':
      addSystemLog('light', `灯光亮度调节至 ${value}%`, 'info')
      break
    default:
      break
  }
  return { code: 200, message: '操作成功', data: { device, action, value } }
}

// ============================================================
// 告警条件检查
// ============================================================
export function checkAlerts(sensorData) {
  const alerts = []
  // 高温预警: 温度 > 30°C
  if (sensorData.temperature > 30) {
    alerts.push({
      type: 'warning',
      message: `⚠️ 高温预警：当前室内温度 ${sensorData.temperature}°C，超过30°C阈值`
    })
  }
  // 湿度预警: 湿度 < 30% 或 > 75%
  if (sensorData.humidity < 30 || sensorData.humidity > 75) {
    alerts.push({
      type: 'warning',
      message: `💧 湿度预警：当前室内湿度 ${sensorData.humidity}%，建议调节通风或加湿设备`
    })
  }
  // 窗户异常开启提醒
  if (sensorData.windowOpen) {
    alerts.push({
      type: 'info',
      message: '📢 提醒：窗户当前处于开启状态'
    })
  }
  // 门未锁定提醒
  if (!sensorData.doorLocked) {
    alerts.push({
      type: 'warning',
      message: '🔓 提醒：入户门当前未锁定'
    })
  }
  return alerts
}

// ============================================================
// 模拟HTTP查询历史数据 (后期替换为真实HTTP请求)
// ============================================================
export function mockQueryHistory(type, range) {
  const now = Date.now()
  let rangeMs = 24 * 3600000 // 默认今天
  if (range === '7days') rangeMs = 7 * 24 * 3600000
  else if (range === '30days') rangeMs = 30 * 24 * 3600000

  const cutoff = now - rangeMs
  switch (type) {
    case 'temperature':
      return tempHistory.filter(d => new Date(d.time).getTime() > cutoff)
    case 'door':
      return doorHistory.filter(d => new Date(d.time).getTime() > cutoff)
    case 'window':
      return windowHistory.filter(d => new Date(d.time).getTime() > cutoff)
    case 'light':
      return lightHistory.filter(d => new Date(d.time).getTime() > cutoff)
    default:
      return []
  }
}
