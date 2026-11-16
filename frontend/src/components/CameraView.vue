<!--
  CameraView.vue - 摄像头实时视频窗口
  USB 使用浏览器采集；OV7670 使用后端独立串口解码，截图接口保持一致。
-->
<template>
  <div class="camera-container" :style="{ width: width, height: height }">
    <div class="camera-header">
      <span class="camera-title">
        <span class="status-dot" :class="cameraEnabled ? 'online' : 'offline'"></span>
        摄像头 · 实时画面
      </span>
      <el-tag size="small" :type="cameraEnabled ? 'success' : 'info'" effect="dark">
        {{ cameraEnabled ? 'LIVE' : serialRunning ? '接收中' : 'OFF' }}
      </el-tag>
    </div>

    <div class="camera-viewport" ref="viewportRef">
      <video v-show="!serialSource" ref="videoRef" class="camera-video" autoplay muted playsinline></video>
      <img v-if="serialSource && serialImage" :src="serialImage" class="camera-video" alt="OV7670 摄像头画面" />

      <canvas
        ref="canvasRef"
        :width="canvasWidth"
        :height="canvasHeight"
        class="camera-overlay"
      ></canvas>

      <div v-if="serialSource && serialImage" class="receive-progress">
        接收 {{ serialProgress }}% · {{ cameraEnabled ? '拍照取最近完整帧' : '等待完整帧后可拍照' }}
      </div>
      <div v-if="!cameraEnabled && !(serialSource && serialImage)" class="camera-placeholder">
        <el-icon :size="48"><VideoCamera /></el-icon>
        <p>{{ errorMessage || '摄像头未开启' }}</p>
      </div>
    </div>

    <div class="camera-actions">
      <el-select
        v-model="selectedCameraId"
        class="camera-select"
        aria-label="选择摄像头"
        placeholder="默认摄像头（首次开启后显示名称）"
        :disabled="starting"
        @change="changeCamera"
      >
        <el-option label="默认摄像头" value="" />
        <el-option
          v-for="(camera, index) in cameras"
          :key="camera.deviceId"
          :label="camera.label || `摄像头 ${index + 1}`"
          :value="camera.deviceId"
        />
        <el-option v-for="entry in serialPorts" :key="`ov7670:${entry.port}`"
          :label="`OV7670 · ${entry.port} · ${entry.description}`" :value="`ov7670:${entry.port}`" />
      </el-select>
      <el-select v-if="serialSource" v-model="baudrate" class="baud-select" aria-label="摄像头波特率"
        :disabled="starting || serialRunning">
        <el-option v-for="rate in [115200, 250000, 500000, 1000000, 2000000]" :key="rate" :label="`${rate} 波特率`" :value="rate" />
      </el-select>
      <el-button :disabled="starting" @click="refreshCameras">刷新设备</el-button>
      <el-button
        type="primary"
        :loading="starting"
        :disabled="cameraEnabled"
        @click="startCamera"
      >
        <el-icon><VideoCamera /></el-icon>
        开启摄像头
      </el-button>
      <el-button :disabled="starting || (!cameraEnabled && !serialRunning)" @click="stopCamera">
        <el-icon><SwitchButton /></el-icon>
        关闭摄像头
      </el-button>
    </div>

    <div class="camera-footer" v-if="cameraEnabled && detections.length > 0">
      <span class="detection-count">检测到 {{ detections.length }} 个目标</span>
      <div class="detection-tags">
        <el-tag
          v-for="(d, i) in detections"
          :key="i"
          size="small"
          :type="d.class === 'light bulb' ? 'warning' : 'info'"
          effect="plain"
        >
          {{ d.name }} {{ (d.confidence * 100).toFixed(0) }}%
        </el-tag>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { VideoCamera, SwitchButton } from '@element-plus/icons-vue'
import { cameraApi } from '../utils/http'

const props = defineProps({
  active: { type: Boolean, default: true },
  width: { type: String, default: '100%' },
  height: { type: String, default: 'auto' },
  detections: { type: Array, default: () => [] },
  hasLightBulb: { type: Boolean, default: false }
})

const emit = defineEmits(['lightBulbDetected', 'statusChange'])

const videoRef = ref(null)
const canvasRef = ref(null)
const viewportRef = ref(null)
const canvasWidth = ref(640)
const canvasHeight = ref(360)
const cameraEnabled = ref(false)
const starting = ref(false)
const errorMessage = ref('')
const cameras = ref([])
const selectedCameraId = ref('')
const serialPorts = ref([])
const baudrate = ref(500000)
const serialSource = computed(() => selectedCameraId.value.startsWith('ov7670:'))
const serialRunning = ref(false)
const serialImage = ref('')
const serialProgress = ref(0)

let stream = null
let animFrameId = null
let disposed = false
let serialSession = ''
let serialTimer = null
let serialFrameId = 0
let serialFrameAt = 0
let serialPreviewId = 0
let serialCapture = null
let operation = 0

onMounted(() => {
  updateCanvasSize()
  window.addEventListener('resize', updateCanvasSize)
  startRenderLoop()
  refreshCameras()
  navigator.mediaDevices?.addEventListener('devicechange', refreshCameras)
})

onUnmounted(() => {
  disposed = true
  navigator.mediaDevices?.removeEventListener('devicechange', refreshCameras)
  window.removeEventListener('resize', updateCanvasSize)
  cancelAnimationFrame(animFrameId)
  stopCamera()
})

watch(() => props.hasLightBulb, (val) => {
  if (val) emit('lightBulbDetected')
})

defineExpose({
  captureFrame,
  isCameraEnabled: () => cameraEnabled.value
})

function updateCanvasSize() {
  if (!viewportRef.value) return
  const w = viewportRef.value.clientWidth || 640
  const h = viewportRef.value.clientHeight || Math.round(w * 0.5625)
  canvasWidth.value = Math.round(w)
  canvasHeight.value = Math.round(h)
}

async function refreshCameras() {
  // USB 权限/枚举失败不应阻止后端串口设备选择。
  await Promise.all([refreshUsbCameras(), refreshSerialPorts()])
}

async function refreshSerialPorts() {
  try {
    const ports = await cameraApi.ports()
    if (!disposed) serialPorts.value = ports
  } catch {
    // 后端离线时仍可使用 USB 摄像头。
    if (!disposed) serialPorts.value = []
  }
}

async function refreshUsbCameras() {
  if (!navigator.mediaDevices?.enumerateDevices) return
  try {
    const devices = await navigator.mediaDevices.enumerateDevices()
    if (disposed) return
    cameras.value = devices.filter(device => device.kind === 'videoinput' && device.deviceId)
    if (selectedCameraId.value && !serialSource.value && !cameras.value.some(camera => camera.deviceId === selectedCameraId.value)) {
      selectedCameraId.value = ''
    }
  } catch {
    errorMessage.value = '无法获取摄像头列表，请检查浏览器权限后刷新设备'
  }
}

function changeCamera() {
  if (cameraEnabled.value || serialRunning.value) startCamera()
}

async function startCamera() {
  if (starting.value || disposed) return
  if (!serialSource.value && !navigator.mediaDevices?.getUserMedia) {
    errorMessage.value = '当前浏览器不支持摄像头调用'
    return
  }

  starting.value = true
  const stopping = stopCamera()
  const currentOperation = operation
  errorMessage.value = ''
  try {
    await stopping
    if (disposed || currentOperation !== operation) return
    if (serialSource.value) {
      const result = await cameraApi.connect(selectedCameraId.value.slice('ov7670:'.length), baudrate.value)
      if (disposed || currentOperation !== operation) {
        await cameraApi.disconnect(result.session)
        return
      }
      serialSession = result.session
      serialRunning.value = true
      errorMessage.value = '等待摄像头图像'
      pollSerialFrame(serialSession)
      return
    }
    const cameraStream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        // USB 摄像头与内置摄像头共用采集、截图和识别流程。
        ...(selectedCameraId.value
          ? { deviceId: { exact: selectedCameraId.value } }
          : { facingMode: 'environment' })
      },
      audio: false
    })
    if (disposed || currentOperation !== operation) {
      cameraStream.getTracks().forEach(track => track.stop())
      return
    }
    stream = cameraStream
    const track = stream.getVideoTracks()[0]
    track.addEventListener('ended', () => {
      if (stream !== cameraStream) return
      stopCamera()
      errorMessage.value = '摄像头已断开，请连接设备后重新选择并开启'
      refreshCameras()
    })
    await nextTick()
    if (videoRef.value) {
      videoRef.value.srcObject = stream
      await videoRef.value.play()
    }
    if (disposed || stream !== cameraStream) return
    cameraEnabled.value = true
    emit('statusChange', true)
    // 授权后浏览器才会提供完整设备名称，并标出实际使用的摄像头。
    await refreshUsbCameras()
    if (!disposed && stream === cameraStream) selectedCameraId.value = track.getSettings().deviceId || ''
  } catch (e) {
    stopCamera()
    errorMessage.value = e?.name === 'NotAllowedError'
      ? '摄像头权限被拒绝'
      : (serialSource.value ? `摄像头连接失败：${e.message}` : '摄像头开启失败，请检查设备或浏览器权限')
  } finally {
    starting.value = false
  }
}

function stopCamera() {
  operation += 1
  clearTimeout(serialTimer)
  const session = serialSession
  serialSession = ''
  serialRunning.value = false
  serialImage.value = ''
  serialCapture = null
  serialFrameId = 0
  serialFrameAt = 0
  serialPreviewId = 0
  serialProgress.value = 0
  if (stream) {
    stream.getTracks().forEach(track => track.stop())
    stream = null
  }
  if (videoRef.value) {
    videoRef.value.pause()
    videoRef.value.srcObject = null
  }
  cameraEnabled.value = false
  emit('statusChange', false)
  return session ? cameraApi.disconnect(session).catch(() => {}) : Promise.resolve()
}

async function pollSerialFrame(session) {
  if (disposed || session !== serialSession) return
  try {
    const requestedAt = Date.now()
    const result = await cameraApi.frame(session, serialFrameId, serialPreviewId)
    if (disposed || session !== serialSession) return
    if (result.error) throw new Error(result.error)
    const frameAt = requestedAt - (result.age_seconds ?? 0) * 1000
    const fresh = result.fresh && Date.now() - frameAt < 10000
    if (fresh && result.data_url) {
      const image = new Image()
      image.src = result.data_url
      await image.decode()
      if (disposed || session !== serialSession) return
      serialCapture = image
      serialFrameId = result.frame_id
      serialFrameAt = frameAt
      cameraEnabled.value = true
      errorMessage.value = ''
      emit('statusChange', true)
    } else if (!fresh || Date.now() - serialFrameAt >= 10000) {
      serialCapture = null
      cameraEnabled.value = false
      errorMessage.value = result.connected ? '等待摄像头新图像' : '正在连接摄像头'
      emit('statusChange', false)
    }
    // 预览和拍照各用独立缓存，半帧永远不会进入 captureFrame()。
    if (result.preview_fresh && result.preview) {
      const image = new Image()
      image.src = result.preview.data_url
      await image.decode()
      if (disposed || session !== serialSession) return
      serialImage.value = result.preview.data_url
      serialPreviewId = result.preview_id
      serialProgress.value = Math.round(result.preview.rows / result.preview.height * 100)
    } else if (!result.preview_fresh) {
      serialImage.value = ''
      serialProgress.value = 0
    }
  } catch (e) {
    if (disposed || session !== serialSession) return
    stopCamera()
    errorMessage.value = `摄像头连接中断：${e.message}`
    return
  }
  if (!disposed && session === serialSession) serialTimer = setTimeout(() => pollSerialFrame(session), 150)
}

function captureFrame() {
  const video = serialSource.value ? serialCapture : videoRef.value
  if (!cameraEnabled.value || !video) return null
  // 断线/停帧时不把旧图再次用于人脸开门。
  if (serialSource.value ? Date.now() - serialFrameAt >= 10000 : video.readyState < 2) return null

  const canvas = document.createElement('canvas')
  canvas.width = video.videoWidth || video.naturalWidth || 1280
  canvas.height = video.videoHeight || video.naturalHeight || 720
  const ctx = canvas.getContext('2d')
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', 0.9)
}

function startRenderLoop() {
  function render() {
    const canvas = canvasRef.value
    if (!canvas) {
      animFrameId = requestAnimationFrame(render)
      return
    }

    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    if (cameraEnabled.value) {
      if (!serialSource.value || serialProgress.value === 100) {
        props.detections.forEach(d => drawDetectionBox(ctx, d, canvas.width, canvas.height))
      }
      drawTimestamp(ctx, canvas.height)
    }

    animFrameId = requestAnimationFrame(render)
  }
  render()
}

function drawTimestamp(ctx, canvasH) {
  ctx.fillStyle = 'rgba(0,0,0,0.45)'
  ctx.fillRect(8, canvasH - 28, 168, 20)
  ctx.fillStyle = 'rgba(255,255,255,0.9)'
  ctx.font = '11px monospace'
  ctx.fillText(new Date().toLocaleString(), 14, canvasH - 14)
}

function drawDetectionBox(ctx, detection, canvasW, canvasH) {
  const sourceW = detection.image_width || detection.imageWidth || 640
  const sourceH = detection.image_height || detection.imageHeight || 480
  const scaleX = canvasW / sourceW
  const scaleY = canvasH / sourceH
  const [rawX, rawY, rawW, rawH] = detection.bbox
  const x = rawX * scaleX
  const y = rawY * scaleY
  const w = rawW * scaleX
  const h = rawH * scaleY
  const conf = detection.confidence
  const className = detection.class

  let color = '#4caf50'
  if (className === 'light bulb') color = '#ff9800'
  else if (className === 'person') color = '#2196f3'
  else if (className === 'drone') color = '#f56c6c'
  else if (className === 'fire_extinguisher') color = '#e6a23c'

  ctx.shadowColor = color
  ctx.shadowBlur = 8
  ctx.strokeStyle = color
  ctx.lineWidth = 2
  ctx.strokeRect(x, y, w, h)
  ctx.shadowBlur = 0

  const cornerLen = Math.min(w, h) * 0.2
  ctx.lineWidth = 3
  ctx.beginPath()
  ctx.moveTo(x, y + cornerLen)
  ctx.lineTo(x, y)
  ctx.lineTo(x + cornerLen, y)
  ctx.moveTo(x + w - cornerLen, y)
  ctx.lineTo(x + w, y)
  ctx.lineTo(x + w, y + cornerLen)
  ctx.moveTo(x, y + h - cornerLen)
  ctx.lineTo(x, y + h)
  ctx.lineTo(x + cornerLen, y + h)
  ctx.moveTo(x + w - cornerLen, y + h)
  ctx.lineTo(x + w, y + h)
  ctx.lineTo(x + w, y + h - cornerLen)
  ctx.stroke()

  const label = `${detection.name} ${(conf * 100).toFixed(0)}%`
  ctx.font = 'bold 12px "Microsoft YaHei", sans-serif'
  const textWidth = ctx.measureText(label).width + 8
  const labelY = Math.max(0, y - 22)

  ctx.fillStyle = color
  ctx.fillRect(x, labelY, textWidth, 22)
  ctx.fillStyle = '#ffffff'
  ctx.fillText(label, x + 4, labelY + 16)
}
</script>

<style scoped>
.camera-container {
  background: var(--bg-card);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: var(--shadow);
  border: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
}
.camera-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: rgba(0,0,0,0.03);
  border-bottom: 1px solid var(--border-color);
}
.camera-title {
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
}
.status-dot.online {
  background: var(--success);
  box-shadow: 0 0 0 3px rgba(103,194,58,0.18);
}
.status-dot.offline {
  background: var(--text-muted);
}
.camera-viewport {
  flex: 1;
  position: relative;
  background: #050608;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 240px;
  overflow: hidden;
}
.camera-video,
.camera-overlay {
  width: 100%;
  height: 100%;
  display: block;
}
.receive-progress {
  position: absolute;
  right: 8px;
  bottom: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.65);
  color: #fff;
  font-size: 12px;
}
.camera-video {
  object-fit: cover;
}
.camera-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.camera-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: rgba(255,255,255,0.72);
  gap: 12px;
  background: radial-gradient(circle at center, rgba(36,50,68,0.9), rgba(5,6,8,0.98));
}
.camera-placeholder p {
  margin: 0;
  font-size: 14px;
}
.camera-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--border-color);
  background: var(--bg-card);
}
.camera-select {
  flex: 1 1 240px;
  min-width: 0;
}
.baud-select {
  width: 180px;
}
.camera-actions .el-button {
  flex: 1;
}
.camera-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
  border-top: 1px solid var(--border-color);
}
.detection-count {
  color: var(--success);
  font-weight: 600;
}
.detection-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
</style>
