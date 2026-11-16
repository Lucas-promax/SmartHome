<!--
  AiRecognition.vue - AI识别页面
  物体识别使用 YOLO best.pt；人脸识别使用 ArcFace 授权人脸库并返回门禁动作。
-->
<template>
  <div class="page-container ai-page">
    <h2 class="page-title">
      <el-icon><View /></el-icon>
      AI 智能识别
      <el-tag size="small" type="success" effect="dark">真实后端推理</el-tag>
    </h2>

    <el-segmented v-model="recognitionType" :options="recognitionOptions" class="type-switch" @change="handleTypeChange" />

    <el-row :gutter="16" class="video-row">
      <el-col :xs="24" :lg="16">
        <CameraView
          ref="cameraRef"
          :active="true"
          :detections="[]"
          height="400px"
        />
      </el-col>

      <el-col :xs="24" :lg="8">
        <div class="dashboard-card control-panel">
          <template v-if="recognitionType === 'object'">
            <h4>物体识别（无人机、灭火器）</h4>

            <div class="field-block">
              <span class="field-label">识别模式</span>
              <el-radio-group v-model="objectMode" class="mode-group" @change="handleObjectModeChange">
                <el-radio-button label="video">视频实时识别</el-radio-button>
                <el-radio-button label="image">图片拍照识别</el-radio-button>
                <el-radio-button label="upload">上传照片识别</el-radio-button>
              </el-radio-group>
            </div>

            <div class="action-row" v-if="objectMode === 'video'">
              <el-button type="primary" :disabled="realtimeRunning" @click="startRealtimeDetect">
                <el-icon><VideoPlay /></el-icon>
                开始实时识别
              </el-button>
              <el-button :disabled="!realtimeRunning" @click="stopRealtimeDetect">
                <el-icon><VideoPause /></el-icon>
                停止识别
              </el-button>
            </div>
            <div class="field-block" v-if="objectMode === 'video'">
              <span class="field-label">识别间隔（秒）</span>
              <el-input-number
                v-model="realtimeIntervalSeconds"
                :min="1"
                :max="30"
                :step="1"
                :disabled="realtimeRunning"
                controls-position="right"
                style="width: 140px;"
              />
            </div>

            <div class="action-row" v-else-if="objectMode === 'image'">
              <el-button type="primary" :loading="detecting" @click="captureObjectDetect">
                <el-icon><Camera /></el-icon>
                拍照识别
              </el-button>
            </div>

            <div class="upload-block" v-else>
              <el-upload
                drag
                action="#"
                accept="image/*"
                :auto-upload="false"
                :show-file-list="false"
                :on-change="handleUploadDetect"
              >
                <el-icon class="upload-icon"><UploadFilled /></el-icon>
                <div class="el-upload__text">选择或拖入照片识别</div>
              </el-upload>
            </div>

            <div class="stat-grid">
              <div class="stat-item">
                <span class="stat-num">{{ objectDetections.length }}</span>
                <span class="stat-label">当前目标</span>
              </div>
              <div class="stat-item">
                <span class="stat-num">{{ objectRecords.length }}</span>
                <span class="stat-label">检测次数</span>
              </div>
              <div class="stat-item">
                <span class="stat-num">{{ droneCount }}</span>
                <span class="stat-label">无人机</span>
              </div>
              <div class="stat-item">
                <span class="stat-num">{{ extinguisherCount }}</span>
                <span class="stat-label">灭火器</span>
              </div>
            </div>

            <h4 class="section-title">当前检测结果</h4>
            <div class="current-detections">
              <div v-for="(d, i) in objectDetections" :key="`${d.class}-${i}`" class="detection-item">
                <el-tag :type="tagType(d.class)" size="small">{{ d.name }}</el-tag>
                <el-progress
                  :percentage="Math.round(d.confidence * 100)"
                  :stroke-width="6"
                  :color="progressColor(d.class)"
                  style="flex: 1; min-width: 60px;"
                />
                <span class="conf-text">{{ (d.confidence * 100).toFixed(1) }}%</span>
              </div>
              <el-empty v-if="objectDetections.length === 0" description="当前无检测目标" :image-size="44" />
            </div>
          </template>

          <template v-else>
            <h4>人脸识别</h4>
            <div class="face-state" :class="faceResult?.result || 'idle'">
              <span class="face-title">{{ faceResultTitle }}</span>
              <span class="face-subtitle">{{ faceResultSubtitle }}</span>
            </div>
            <div class="action-row">
              <el-button type="primary" :loading="detecting" @click="captureFaceRecognize">
                <el-icon><Camera /></el-icon>
                拍照识别
              </el-button>
            </div>
            <div class="face-detail" v-if="faceResult">
              <div><span>识别结果</span><strong>{{ faceResultText }}</strong></div>
              <div><span>匹配人员</span><strong>{{ faceResult.person?.name || faceResult.best_match?.name || '未知' }}</strong></div>
              <div><span>相似度</span><strong>{{ faceConfidenceText }}</strong></div>
              <div><span>门禁动作</span><strong>{{ faceResult.opened_door ? '板端报告开门' : '开门未确认' }}</strong></div>
            </div>
          </template>

          <el-alert
            v-if="statusMessage"
            :title="statusMessage"
            :type="statusType"
            :closable="false"
            show-icon
            class="status-alert"
          />
        </div>
      </el-col>
    </el-row>

    <el-row v-if="capturedImage" :gutter="16" class="snapshot-row">
      <el-col :xs="24" :lg="16">
        <div class="dashboard-card snapshot-card">
          <div class="snapshot-header">
            <h4>{{ recognitionType === 'object' ? objectSnapshotTitle : '人脸抓拍结果' }}</h4>
            <span>{{ lastDetectTime || '-' }}</span>
          </div>
          <div class="snapshot-preview" ref="snapshotRef">
            <img :src="capturedImage" alt="识别抓拍画面" @load="updateSnapshotSize" />
            <div
              v-for="(d, i) in snapshotDetections"
              :key="`snapshot-${i}`"
              class="snapshot-box"
              :style="boxStyle(d)"
            >
              <span>{{ d.name }} {{ (d.confidence * 100).toFixed(0) }}%</span>
            </div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :lg="8">
        <div class="dashboard-card result-list">
          <h4>{{ recognitionType === 'object' ? '抓拍目标' : '门禁结果' }}</h4>
          <template v-if="recognitionType === 'object'">
            <el-table :data="snapshotDetections" size="small" stripe max-height="260">
              <el-table-column prop="name" label="目标" min-width="90" />
              <el-table-column label="置信度" width="90">
                <template #default="{ row }">{{ (row.confidence * 100).toFixed(1) }}%</template>
              </el-table-column>
            </el-table>
            <el-empty v-if="snapshotDetections.length === 0" description="无目标" :image-size="44" />
          </template>
          <template v-else>
            <div class="face-summary" v-if="faceResult">
              <el-tag :type="faceResult.opened_door ? 'success' : 'danger'" effect="dark">
                {{ faceResultText }}
              </el-tag>
              <p>{{ faceResultSubtitle }}</p>
            </div>
            <el-empty v-else description="暂无人脸识别结果" :image-size="44" />
          </template>
        </div>
      </el-col>
    </el-row>

    <el-card class="records-card">
      <el-tabs v-model="activeRecordTab" type="border-card">
        <el-tab-pane label="物体识别记录" name="object">
          <div class="tab-header">
            <span class="tab-count">共 {{ objectRecords.length }} 条记录</span>
            <el-button size="small" text :disabled="objectRecords.length === 0" @click="objectRecords = []">
              <el-icon><Delete /></el-icon>
              清空
            </el-button>
          </div>
          <el-table :data="objectRecords" stripe size="small" style="width: 100%" max-height="360">
            <el-table-column prop="modeText" label="模式" width="110" />
            <el-table-column prop="targetSummary" label="检测目标" min-width="160" />
            <el-table-column prop="count" label="数量" width="80" />
            <el-table-column prop="time" label="时间" width="180" />
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="人脸识别记录" name="face">
          <div class="tab-header">
            <span class="tab-count">共 {{ faceRecords.length }} 条记录</span>
            <el-button size="small" text :disabled="faceRecords.length === 0" @click="faceRecords = []">
              <el-icon><Delete /></el-icon>
              清空
            </el-button>
          </div>
          <el-table :data="faceRecords" stripe size="small" style="width: 100%" max-height="360">
            <el-table-column prop="personName" label="人员" min-width="120" />
            <el-table-column prop="resultText" label="结果" width="110" />
            <el-table-column prop="confidenceText" label="相似度" width="100" />
            <el-table-column prop="doorText" label="门禁" width="100" />
            <el-table-column prop="time" label="时间" width="180" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { computed, nextTick, onUnmounted, ref } from 'vue'
import { Camera, Delete, UploadFilled, VideoPause, VideoPlay, View } from '@element-plus/icons-vue'
import CameraView from '../components/CameraView.vue'
import { visionApi } from '../utils/http'

const recognitionOptions = [
  { label: '物体识别', value: 'object' },
  { label: '人脸识别', value: 'face' }
]

const cameraRef = ref(null)
const snapshotRef = ref(null)
const recognitionType = ref('object')
const objectMode = ref('video')
const activeRecordTab = ref('object')
const objectDetections = ref([])
const snapshotDetections = ref([])
const capturedImage = ref('')
const detecting = ref(false)
const realtimeRunning = ref(false)
const realtimeIntervalSeconds = ref(5)
const statusMessage = ref('')
const statusType = ref('info')
const objectRecords = ref([])
const faceRecords = ref([])
const faceResult = ref(null)
const lastDetectTime = ref('')
const snapshotSize = ref({ width: 1, height: 1 })

let realtimeTimer = null

const droneCount = computed(() => objectDetections.value.filter(d => d.class === 'drone').length)
const extinguisherCount = computed(() => objectDetections.value.filter(d => normalizeClass(d.class) === 'fire_extinguisher').length)
const faceResultText = computed(() => {
  if (!faceResult.value) return '等待识别'
  if (faceResult.value.opened_door) return '授权通过'
  if (faceResult.value.result === 'control_failed') return '授权通过，开门未确认'
  if (faceResult.value.result === 'matched_no_permission') return '无门禁权限'
  return '未知人员'
})
const faceConfidenceText = computed(() => typeof faceResult.value?.confidence === 'number' ? `${(faceResult.value.confidence * 100).toFixed(1)}%` : '-')
const objectSnapshotTitle = computed(() => objectMode.value === 'upload' ? '上传照片识别结果' : '拍照识别结果')
const faceResultTitle = computed(() => faceResult.value ? faceResultText.value : '等待拍照识别')
const faceResultSubtitle = computed(() => {
  if (!faceResult.value) return '拍照后将与授权人员人脸库比对'
  if (faceResult.value.result === 'control_failed') return faceResult.value.message
  if (faceResult.value.opened_door) return `${faceResult.value.person?.name || '授权人员'} 已通过，板端报告开门`
  if (faceResult.value.result === 'matched_no_permission') return `${faceResult.value.person?.name || '已录入人员'} 已匹配，但没有门禁权限`
  return '未匹配到已录入人员，未发送开门指令'
})

onUnmounted(() => stopRealtimeDetect())

function handleTypeChange() {
  stopRealtimeDetect()
  activeRecordTab.value = recognitionType.value
  statusMessage.value = ''
  snapshotDetections.value = []
}

function handleObjectModeChange() {
  stopRealtimeDetect()
  statusMessage.value = ''
  if (objectMode.value === 'upload') {
    objectDetections.value = []
    snapshotDetections.value = []
  }
}

function startRealtimeDetect() {
  if (!ensureCameraReady()) return
  realtimeRunning.value = true
  setStatus(`实时识别运行中，每 ${realtimeIntervalSeconds.value} 秒识别一次`, 'success')
  runRealtimeOnce()
  realtimeTimer = window.setInterval(runRealtimeOnce, realtimeIntervalSeconds.value * 1000)
}

function stopRealtimeDetect() {
  realtimeRunning.value = false
  if (realtimeTimer) {
    window.clearInterval(realtimeTimer)
    realtimeTimer = null
  }
}

async function runRealtimeOnce() {
  if (detecting.value || !realtimeRunning.value) return
  await detectObjectFrame('video')
}

async function captureObjectDetect() {
  if (!ensureCameraReady()) return
  const frame = captureFrame()
  if (!frame) return
  capturedImage.value = frame
  await nextTick()
  updateSnapshotSize()
  await detectObjectFrame('image', frame)
}

async function handleUploadDetect(uploadFile) {
  const file = uploadFile.raw
  if (!file) return
  stopRealtimeDetect()
  objectMode.value = 'upload'
  capturedImage.value = URL.createObjectURL(file)
  snapshotDetections.value = []
  await nextTick()
  updateSnapshotSize()

  detecting.value = true
  try {
    const result = await visionApi.fireDroneDetect(file)
    const detections = Array.isArray(result?.detections) ? result.detections : []
    objectDetections.value = detections
    snapshotDetections.value = detections
    lastDetectTime.value = new Date().toLocaleString('zh-CN')
    addObjectRecord('upload', detections)
    setStatus(detections.length ? `上传识别完成：${detections.length} 个目标` : '上传识别完成：未发现目标', 'success')
  } catch (error) {
    setStatus(error.message || '上传识别失败', 'error')
  } finally {
    detecting.value = false
  }
}

async function captureFaceRecognize() {
  if (!ensureCameraReady()) return
  const frame = captureFrame()
  if (!frame) return
  capturedImage.value = frame
  snapshotDetections.value = []
  await nextTick()
  updateSnapshotSize()

  detecting.value = true
  try {
    const file = dataUrlToFile(frame, `face-frame-${Date.now()}.jpg`)
    const result = await visionApi.faceRecognize(file)
    faceResult.value = result
    lastDetectTime.value = new Date().toLocaleString('zh-CN')
    addFaceRecord(result)
    setStatus(result.message || faceResultSubtitle.value, result.opened_door ? 'success' : 'warning')
  } catch (error) {
    setStatus(error.message || '人脸识别失败', 'error')
  } finally {
    detecting.value = false
  }
}

async function detectObjectFrame(mode, existingFrame = '') {
  const frame = existingFrame || captureFrame()
  if (!frame) return

  detecting.value = true
  try {
    const file = dataUrlToFile(frame, `${mode}-frame-${Date.now()}.jpg`)
    const result = await visionApi.fireDroneDetect(file)
    const detections = Array.isArray(result?.detections) ? result.detections : []
    objectDetections.value = detections
    if (mode === 'image') snapshotDetections.value = detections
    lastDetectTime.value = new Date().toLocaleString('zh-CN')
    addObjectRecord(mode, detections)
    setStatus(detections.length ? `检测完成：${detections.length} 个目标` : '检测完成：未发现目标', 'success')
  } catch (error) {
    setStatus(error.message || '后端识别失败', 'error')
  } finally {
    detecting.value = false
  }
}

function ensureCameraReady() {
  if (!cameraRef.value?.isCameraEnabled?.()) {
    setStatus('请先开启摄像头并等待完整画面', 'warning')
    return false
  }
  return true
}

function captureFrame() {
  const frame = cameraRef.value?.captureFrame?.()
  if (!frame) setStatus('摄像头画面未就绪', 'warning')
  return frame
}

function dataUrlToFile(dataUrl, filename) {
  const [header, base64] = dataUrl.split(',')
  const mime = header.match(/:(.*?);/)?.[1] || 'image/jpeg'
  const bytes = atob(base64)
  const array = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i += 1) {
    array[i] = bytes.charCodeAt(i)
  }
  return new File([array], filename, { type: mime })
}

function addObjectRecord(mode, detections) {
  const modeTextMap = {
    video: '实时识别',
    image: '拍照识别',
    upload: '上传识别'
  }
  objectRecords.value.unshift({
    modeText: modeTextMap[mode] || '识别',
    targetSummary: detections.length ? detections.map(d => d.name).join('、') : '无目标',
    count: detections.length,
    time: new Date().toLocaleString('zh-CN')
  })
  objectRecords.value = objectRecords.value.slice(0, 100)
}

function addFaceRecord(result) {
  faceRecords.value.unshift({
    personName: result.person?.name || result.best_match?.name || '未知人员',
    resultText: result.opened_door ? '授权通过' : result.result === 'control_failed' ? '授权通过，控制未确认' : (result.result === 'matched_no_permission' ? '无权限' : '未知'),
    confidenceText: typeof result.confidence === 'number' ? `${(result.confidence * 100).toFixed(1)}%` : '-',
    doorText: result.opened_door ? '板端报告开门' : '开门未确认',
    time: new Date().toLocaleString('zh-CN')
  })
  faceRecords.value = faceRecords.value.slice(0, 100)
}

function setStatus(message, type = 'info') {
  statusMessage.value = message
  statusType.value = type
}

function updateSnapshotSize() {
  if (!snapshotRef.value) return
  const rect = snapshotRef.value.getBoundingClientRect()
  snapshotSize.value = { width: rect.width || 1, height: rect.height || 1 }
}

function boxStyle(detection) {
  const sourceW = detection.image_width || 640
  const sourceH = detection.image_height || 480
  const [x, y, w, h] = detection.bbox || [0, 0, 0, 0]
  const scaleX = snapshotSize.value.width / sourceW
  const scaleY = snapshotSize.value.height / sourceH
  return {
    left: `${x * scaleX}px`,
    top: `${y * scaleY}px`,
    width: `${w * scaleX}px`,
    height: `${h * scaleY}px`,
    borderColor: progressColor(detection.class)
  }
}

function normalizeClass(className) {
  if (className === 'fire extinguisher') return 'fire_extinguisher'
  return className
}

function tagType(className) {
  return normalizeClass(className) === 'fire_extinguisher' ? 'warning' : 'danger'
}

function progressColor(className) {
  return normalizeClass(className) === 'fire_extinguisher' ? '#e6a23c' : '#f56c6c'
}
</script>

<style scoped>
.ai-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.page-title {
  font-size: 18px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 0;
}
.type-switch {
  align-self: flex-start;
}
.video-row,
.snapshot-row {
  margin: 0 !important;
}
.control-panel {
  height: 400px;
  overflow-y: auto;
}
.control-panel h4,
.snapshot-card h4,
.result-list h4 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
}
.field-block {
  margin-bottom: 14px;
}
.field-label {
  display: block;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 6px;
}
.mode-group,
.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.action-row .el-button {
  flex: 1;
  min-width: 118px;
}
.status-alert {
  margin-top: 12px;
}
.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 14px;
}
.stat-item {
  text-align: center;
  padding: 10px 8px;
  border-radius: 8px;
  background: var(--bg-primary);
}
.stat-num {
  display: block;
  font-size: 22px;
  font-weight: 700;
  color: var(--accent);
}
.stat-label {
  font-size: 11px;
  color: var(--text-muted);
}
.section-title {
  margin-top: 16px;
}
.current-detections {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.detection-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.conf-text {
  font-size: 11px;
  color: var(--text-muted);
  min-width: 42px;
}
.face-state {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px;
  border-radius: 8px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  margin-bottom: 14px;
}
.face-state.granted {
  border-color: rgba(103,194,58,0.45);
}
.face-state.denied {
  border-color: rgba(245,108,108,0.45);
}
.face-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}
.face-subtitle {
  font-size: 12px;
  color: var(--text-muted);
}
.face-detail {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}
.face-detail div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-color);
  font-size: 13px;
}
.face-detail span {
  color: var(--text-muted);
}
.snapshot-card,
.result-list,
.records-card {
  border: 1px solid var(--border-color);
}
.snapshot-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--text-muted);
  font-size: 12px;
  margin-bottom: 8px;
}
.snapshot-preview {
  position: relative;
  width: 100%;
  max-height: 420px;
  overflow: hidden;
  background: #050608;
  border-radius: 8px;
}
.snapshot-preview img {
  display: block;
  width: 100%;
  height: auto;
}
.snapshot-box {
  position: absolute;
  border: 2px solid #f56c6c;
  box-shadow: 0 0 0 1px rgba(0,0,0,0.28);
  pointer-events: none;
}
.snapshot-box span {
  position: absolute;
  left: -2px;
  top: -24px;
  padding: 2px 6px;
  color: #fff;
  background: rgba(0,0,0,0.76);
  font-size: 12px;
  white-space: nowrap;
}
.face-summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.face-summary p {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}
.tab-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.tab-count {
  font-size: 13px;
  color: var(--text-muted);
}

@media (max-width: 768px) {
  .page-container { padding: 10px; }
  .control-panel { height: auto; }
}
</style>
