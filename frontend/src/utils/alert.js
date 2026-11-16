/**
 * ============================================================
 * 告警弹窗 + 提示音效工具 (加分功能)
 * ============================================================
 * 设备异常时弹出红色告警弹窗 + 播放提示音效
 * 使用 Web Audio API 生成提示音 (无需外部音频文件)
 * ============================================================
 */
import { ElNotification } from 'element-plus'

// 音频上下文 (延迟初始化)
let audioCtx = null

function getAudioContext() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)()
  }
  return audioCtx
}

/**
 * 播放告警提示音
 * @param {string} type - 'warning' | 'error' | 'info'
 */
export function playAlertSound(type = 'warning') {
  try {
    const ctx = getAudioContext()
    const oscillator = ctx.createOscillator()
    const gainNode = ctx.createGain()

    oscillator.connect(gainNode)
    gainNode.connect(ctx.destination)

    if (type === 'error') {
      // 急促高频音 - 严重告警
      oscillator.type = 'square'
      oscillator.frequency.setValueAtTime(800, ctx.currentTime)
      oscillator.frequency.setValueAtTime(600, ctx.currentTime + 0.15)
      oscillator.frequency.setValueAtTime(800, ctx.currentTime + 0.3)
      gainNode.gain.setValueAtTime(0.3, ctx.currentTime)
      gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5)
      oscillator.start(ctx.currentTime)
      oscillator.stop(ctx.currentTime + 0.5)
    } else if (type === 'warning') {
      // 温和提示音
      oscillator.type = 'sine'
      oscillator.frequency.setValueAtTime(440, ctx.currentTime)
      oscillator.frequency.setValueAtTime(523, ctx.currentTime + 0.1)
      gainNode.gain.setValueAtTime(0.2, ctx.currentTime)
      gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3)
      oscillator.start(ctx.currentTime)
      oscillator.stop(ctx.currentTime + 0.3)
    } else {
      // 信息提示
      oscillator.type = 'sine'
      oscillator.frequency.setValueAtTime(523, ctx.currentTime)
      gainNode.gain.setValueAtTime(0.15, ctx.currentTime)
      gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.2)
      oscillator.start(ctx.currentTime)
      oscillator.stop(ctx.currentTime + 0.2)
    }
  } catch (e) {
    console.warn('播放提示音失败:', e)
  }
}

/**
 * 弹出告警通知
 * @param {string} title - 标题
 * @param {string} message - 消息内容
 * @param {string} type - 'warning' | 'error' | 'info' | 'success'
 * @param {boolean} playSound - 是否播放提示音
 */
export function showAlert(title, message, type = 'warning', playSound = true) {
  if (playSound) {
    playAlertSound(type)
  }

  ElNotification({
    title,
    message,
    type,
    duration: type === 'error' ? 0 : 5000, // 错误告警不自动关闭
    position: 'top-right',
    showClose: true,
    customClass: type === 'error' ? 'alert-notification-error' : ''
  })
}

/**
 * 设备异常告警弹窗 (加分功能4)
 * @param {string} device - 异常设备名
 * @param {string} detail - 异常详情
 */
export function showDeviceAlert(device, detail) {
  showAlert(
    `🚨 设备异常 - ${device}`,
    detail,
    'error',
    true
  )
}

/**
 * 灯泡检测弹窗提示 (加分功能1)
 * @param {function} onConfirm - 确认回调
 */
export function showLightBulbAlert(onConfirm) {
  playAlertSound('info')
  ElNotification({
    title: '💡 目标检测提示',
    message: '摄像头检测到灯泡目标，是否自动开启灯光？',
    type: 'info',
    duration: 8000,
    showClose: true,
    // 添加操作按钮
    customClass: 'light-bulb-notification'
  })
  // 自动下发开灯指令
  if (onConfirm) onConfirm()
}

export default { showAlert, showDeviceAlert, showLightBulbAlert, playAlertSound }
