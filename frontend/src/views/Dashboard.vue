<template>
  <div class="dashboard">
    <div class="dashboard-card connection-strip">
      <div><el-tag :type="hardware.ready ? 'success' : 'warning'">{{ hardware.ready ? 'Arduino 状态已同步' : hardware.connected ? '等待板端状态' : 'Arduino 未连接' }}</el-tag>
        <span>{{ hardware.port || '未选择串口' }} · 9600 波特率</span></div>
      <el-button text type="primary" @click="$router.push('/settings')">连接设置</el-button>
      <el-tag v-if="hardware.mode === 'simulator'" type="warning">模拟硬件 · 不连接真实设备</el-tag>
      <p v-if="hardware.error">{{ hardware.error }}</p>
      <p>设备状态来自板端程序；门显示舵机控制状态，不代表门锁或机械位置检测。数据超过 12 秒未更新时停止控制。</p>
      <p v-if="hardware.last_rfid">最近刷卡：{{ hardware.last_rfid.uid || '未知卡' }} · {{ hardware.last_rfid.granted ? '板端授权通过' : '板端授权拒绝' }} · {{ formatTime(hardware.last_rfid.created_at) }}</p>
    </div>
    <el-row :gutter="16">
      <el-col v-for="card in cards" :key="card.title" :xs="12" :sm="8" :lg="4">
        <StatusCard v-bind="card" />
      </el-col>
    </el-row>
    <el-row :gutter="16">
      <el-col :xs="24" :lg="24" class="camera-col">
        <CameraView :active="true" :detections="yoloData.detections" :hasLightBulb="false" @statusChange="cameraEnabled = $event" height="460px" />
      </el-col>
      <el-col :xs="24" :lg="24">
        <div class="dashboard-card control-panel">
          <h3>远程控制</h3>
          <small>高亮表示各设备的待发送选择，默认关闭；不代表硬件实时状态。发送时将四组选择合并，一次写入串口。</small>
          <div class="device-controls">
          <div class="control-item">
            <strong>主门</strong>
            <div class="button-row"><el-button :type="selected('door_main', 'open') ? 'primary' : 'default'" :aria-pressed="selected('door_main', 'open')" :disabled="busy" @click="control('door_main', 'open')">开门</el-button><el-button :type="selected('door_main', 'close') ? 'primary' : 'default'" :aria-pressed="selected('door_main', 'close')" :disabled="busy" @click="control('door_main', 'close')">关门</el-button></div>
            <small>当前固件不会自动关门，请主动关闭。</small>
          </div>
          <div class="control-item">
            <strong>车库门</strong>
            <div class="button-row"><el-button :type="selected('garage_main', 'open') ? 'primary' : 'default'" :aria-pressed="selected('garage_main', 'open')" :disabled="busy" @click="control('garage_main', 'open')">打开</el-button><el-button :type="selected('garage_main', 'close') ? 'primary' : 'default'" :aria-pressed="selected('garage_main', 'close')" :disabled="busy" @click="control('garage_main', 'close')">关闭</el-button></div>
          </div>
          <div class="control-item">
            <strong>风扇 · {{ fanModeLabel }}</strong>
            <div class="button-row"><el-button :type="hardware.fan_mode === 'auto' ? 'primary' : 'default'" :disabled="busy || !fresh('fan_main')" @click="setFanAuto(true)">开启自动温控</el-button><el-button :type="hardware.fan_mode === 'manual' ? 'primary' : 'default'" :disabled="busy || !fresh('fan_main')" @click="setFanAuto(false)">关闭自动温控</el-button></div>
            <div class="button-row"><el-button :type="selected('fan_main', 'turn_on') ? 'primary' : 'default'" :aria-pressed="selected('fan_main', 'turn_on')" :disabled="busy" @click="control('fan_main', 'turn_on')">开启</el-button><el-button :type="selected('fan_main', 'turn_off') ? 'primary' : 'default'" :aria-pressed="selected('fan_main', 'turn_off')" :disabled="busy" @click="control('fan_main', 'turn_off')">关闭</el-button></div>
            <small>自动温控{{ hardware.fan_threshold == null ? '阈值未同步' : `：高于 ${hardware.fan_threshold}°C 开启，否则关闭` }}。关闭温控后保留当前开关状态，手动或语音控制不再被温控覆盖。温控按钮立即发送。</small>
          </div>
          <div class="control-item">
            <strong>主灯 · 五档亮度</strong>
            <div class="button-row">
              <el-button v-for="level in lightPresets" :key="level.value" :type="selected('light_main', 'set_level', level.value) ? 'primary' : 'default'" :aria-pressed="selected('light_main', 'set_level', level.value)" :disabled="busy" @click="control('light_main', 'set_level', level.value)">{{ level.label }}</el-button>
              <el-button :type="selected('light_main', 'turn_off') ? 'primary' : 'default'" :aria-pressed="selected('light_main', 'turn_off')" :disabled="busy" @click="control('light_main', 'turn_off')">关闭</el-button>
            </div>
            <div class="button-row"><el-button :type="selected('light_main', 'darker') ? 'primary' : 'default'" :aria-pressed="selected('light_main', 'darker')" :disabled="busy" @click="control('light_main', 'darker')">暗一档</el-button><el-button :type="selected('light_main', 'brighter') ? 'primary' : 'default'" :aria-pressed="selected('light_main', 'brighter')" :disabled="busy" @click="control('light_main', 'brighter')">亮一档</el-button></div>
            <small>实际亮度值：8 / 25 / 70 / 140 / 255；关闭后先选预设档位再逐档调节。</small>
          </div>
          </div>
          <div class="control-item send-controls">
            <details class="draft-details" ref="draftDetails">
            <summary>待发送指令（点击展开）</summary>
            <div class="draft-content">
            <p>四台设备一起发送，由 Arduino 逐字符读取执行。</p>
            <el-button @click="showJson = !showJson">{{ showJson ? '收起 JSON' : '查看 / 编辑 JSON' }}</el-button>
            <el-input v-if="showJson" :model-value="jsonText" @update:model-value="editJson" type="textarea" :rows="8" :disabled="busy" class="json-editor" />
            <strong>Arduino 串口指令预览</strong>
            <pre class="serial-preview">{{ serialPreview || '请求无效，无法生成指令' }}</pre>
            <small>按 JSON 数组顺序拼接动作字符，末尾仅附加一个 s 查询状态；不发送 JSON，也不附加换行。</small>
            <el-alert v-if="jsonError" :title="jsonError" type="error" :closable="false" />
            <el-alert v-if="extraFields.length" :title="`保留额外字段：${extraFields.join(', ')}。当前后端会拒绝这些字段，不会执行指令。`" type="warning" :closable="false" />
            </div>
            </details>
            <el-button type="primary" :disabled="!!jsonError || !draft.commands.every(item => fresh(item.device_id))" :loading="busy" @click="sendDraft">发送指令</el-button>
            <small>实时状态不覆盖草稿。一次发送不代表同时执行或全部成功；超时不会自动重发整组。</small>
            <template v-if="lastSend">
              <strong>最近一次发送</strong>
              <pre class="serial-preview">{{ lastSend.json }}</pre>
              <p>后端确认的串口指令：<code>{{ lastSend.command || '未确认串口写入' }}</code></p>
              <p>{{ lastSend.status }}</p>
              <p v-for="item in lastSend.results || []" :key="item.device_id">{{ deviceNames[item.device_id] }} · {{ item.command }} · {{ item.confirmed ? '板端状态已确认' : '未确认，请查看实时状态' }}</p>
            </template>
          </div>
          <el-tag v-if="busy" type="info">等待板端状态，请勿重复操作</el-tag>
        </div>
      </el-col>
    </el-row>
    <div class="dashboard-card event-log">
      <h3>最近事件</h3>
      <el-timeline>
        <el-timeline-item v-for="log in recentEvents" :key="log.id" :timestamp="formatTime(log.timestamp)" :type="log.level === 'warning' ? 'warning' : log.level === 'error' ? 'danger' : 'primary'">{{ log.message }}</el-timeline-item>
      </el-timeline>
      <el-empty v-if="!recentEvents.length" description="暂无事件" :image-size="60" />
    </div>
  </div>
</template>

<script setup>
import { ref, inject, computed } from 'vue'
import { ElMessage } from 'element-plus'
import CameraView from '../components/CameraView.vue'
import StatusCard from '../components/StatusCard.vue'
import { hardwareApi } from '../utils/http'

const sensorData = inject('sensorData')
const hardware = inject('hardwareState')
const yoloData = inject('yoloData')
const recentEvents = inject('recentEvents')
const refreshHomeStatus = inject('refreshHomeStatus')
const cameraEnabled = ref(false)
const busy = ref(false)
const fanModeLabel = computed(() => ({ auto: '自动温控已开启', manual: '自动温控已关闭' }[hardware.value.fan_mode] || '温控模式未同步'))
async function setFanAuto(enabled) {
  busy.value = true
  try {
    await hardwareApi.send({ device_id: 'fan_main', action: enabled ? 'auto_on' : 'auto_off' })
    ElMessage.success(enabled ? '自动温控已开启' : '自动温控已关闭')
  } catch (e) { ElMessage.error(e.message) }
  finally { await refreshHomeStatus(); busy.value = false }
}
const deviceOrder = ['door_main', 'garage_main', 'fan_main', 'light_main']
const deviceNames = { door_main: '主门', garage_main: '车库门', fan_main: '风扇', light_main: '主灯' }
const draft = ref({ commands: deviceOrder.map(device_id => ({ device_id, action: ['door_main', 'garage_main'].includes(device_id) ? 'close' : 'turn_off', value: null })) })
const choices = computed(() => Object.fromEntries(draft.value.commands.map(item => [item.device_id, item])))
const lastSend = ref(null)
function selected(device, action, value = null) { return choices.value[device]?.action === action && (choices.value[device]?.value ?? null) === value }
const jsonText = ref(JSON.stringify(draft.value, null, 2))
const jsonError = ref('')
const showJson = ref(false)
const draftDetails = ref(null)
function revealDraft() {
  showJson.value = true
  if (draftDetails.value) draftDetails.value.open = true
}
const extraFields = computed(() => [
  ...Object.keys(draft.value).filter(key => key !== 'commands'),
  ...draft.value.commands.flatMap((item, index) => Object.keys(item).filter(key => !['device_id', 'action', 'value'].includes(key)).map(key => `commands[${index}].${key}`))
])
const serialPreview = computed(() => {
  if (jsonError.value || extraFields.value.length) return ''
  const commands = draft.value.commands.map(({device_id: device, action, value}) => ({
    door_main: { open: 'd', close: 'D' }, garage_main: { open: 'g', close: 'G' },
    fan_main: { turn_on: 'f', turn_off: 'F' },
    light_main: { turn_on: 'l', turn_off: 'L', brighter: '+', darker: '-', set_level: { low: 'A', middle: 'B', high: 'C' }[value] }
  })[device]?.[action])
  return commands.every(Boolean) ? commands.join('') + 's' : ''
})
function validateCommand(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('JSON 必须是一个对象')
  if (!['light_main', 'fan_main', 'door_main', 'garage_main'].includes(value.device_id)) throw new Error('device_id 必须是已支持的设备 ID')
  const actions = value.device_id === 'light_main' ? ['turn_on', 'turn_off', 'set_level', 'brighter', 'darker'] : value.device_id === 'fan_main' ? ['turn_on', 'turn_off'] : ['open', 'close']
  if (!actions.includes(value.action)) throw new Error('此设备不支持该 action')
  if (value.action !== 'set_level' && value.value != null) throw new Error('此动作不接受 value，请设为 null 或省略')
  if (value.action === 'set_level' && !['low', 'middle', 'high'].includes(value.value)) throw new Error('set_level 的 value 必须为 low / middle / high')
}
function validateDraft(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || !Array.isArray(value.commands)) throw new Error('JSON 必须包含 commands 数组')
  if (value.commands.length !== 4) throw new Error('commands 必须包含四台设备的选择')
  value.commands.forEach(validateCommand)
  if (new Set(value.commands.map(item => item.device_id)).size !== 4) throw new Error('每台设备只能出现一次')
}
function editJson(text) {
  jsonText.value = text
  try {
    const value = JSON.parse(text)
    validateDraft(value)
    draft.value = value
    jsonError.value = ''
  } catch (e) { jsonError.value = e.message }
}
const lightPresets = [{ label: '低档 8', value: 'low' }, { label: '中档 70', value: 'middle' }, { label: '高档 255', value: 'high' }]
const fresh = id => hardware.value.connected && hardware.value.fresh_devices?.[id] === true
const cards = computed(() => {
  const d = sensorData.value
  const position = (id, value) => !fresh(id) || value == null ? '未知 / 未同步' : value ? '开启' : '关闭'
  return [
    { title: '温度 / 湿度', value: d.environmentFresh ? `${d.temperature}°C / ${d.humidity}%` : '--', subtitle: d.environmentFresh ? `环境光：${d.lightBright ? '亮' : '暗'} · DHT 有效性未上报` : '等待有效上报', status: d.environmentFresh ? 'normal' : 'offline', icon: 'Sunny' },
    { title: '主门', value: position('door_main', d.doorOpen), subtitle: '舵机控制状态', status: fresh('door_main') ? 'normal' : 'offline', icon: 'Lock' },
    { title: '车库门', value: position('garage_main', d.garageOpen), subtitle: '舵机控制状态', status: fresh('garage_main') ? 'normal' : 'offline', icon: 'Picture' },
    { title: '主灯亮度', value: fresh('light_main') ? `${d.lightLevel} / 255` : '--', subtitle: '板端输出值，非实测照度', status: fresh('light_main') ? 'normal' : 'offline', icon: 'Sunset' },
    { title: '风扇', value: position('fan_main', d.fanOn), subtitle: fanModeLabel.value, status: fresh('fan_main') ? 'normal' : 'offline', icon: 'Refresh' },
    { title: '摄像头', value: cameraEnabled.value ? '采集中' : '未开启', subtitle: '摄像头采集', status: cameraEnabled.value ? 'normal' : 'offline', icon: 'VideoCamera' }
  ]
})
function control(deviceId, action, value = null) {
  if (jsonError.value) { ElMessage.warning('JSON 有错误，请先修正；草稿未被覆盖'); revealDraft(); return }
  draft.value = { ...draft.value, commands: draft.value.commands.map(item => item.device_id === deviceId ? { ...item, action, value } : item) }
  jsonText.value = JSON.stringify(draft.value, null, 2)
}
async function sendDraft() {
  let payload
  try { payload = JSON.parse(jsonText.value); validateDraft(payload) }
  catch (e) { jsonError.value = e.message; revealDraft(); return }
  busy.value = true
  try {
    lastSend.value = { json: JSON.stringify(payload, null, 2), command: null, status: '发送中' }
    const result = await hardwareApi.send(payload)
    lastSend.value = { ...lastSend.value, command: result.command, status: result.message, results: result.results }
    if (result.complete) ElMessage.success(result.message)
    else ElMessage.warning(result.message)
  } catch (e) { lastSend.value = { ...lastSend.value, command: null, status: e.message }; ElMessage.error(e.message) }
  finally { await refreshHomeStatus(); busy.value = false }
}
function formatTime(value) { return value ? new Date(value).toLocaleString('zh-CN') : '--' }
</script>

<style scoped>
.dashboard { padding: 16px; display: flex; flex-direction: column; gap: 16px; }
.connection-strip, .control-panel, .event-log { padding: 18px; }
.connection-strip > div { display: inline-flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.connection-strip > .el-button { float: right; }
p, small { color: var(--text-secondary); font-size: 12px; line-height: 1.7; }
p { margin: 10px 0 0; }
.control-panel { display: flex; flex-direction: column; gap: 10px; }
.control-panel h3 { margin-bottom: 0; }
.device-controls { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 20px; }
.control-item { display: flex; flex-direction: column; gap: 6px; padding-top: 10px; border-top: 1px solid var(--border-color); }
.button-row { display: flex; flex-wrap: wrap; gap: 6px; }
.button-row .el-button { padding: 8px 12px; }
.send-controls { align-items: flex-start; }
.draft-details { width: 100%; }
.draft-details summary { cursor: pointer; font-size: 13px; font-weight: 600; line-height: 1.7; }
.draft-content { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; padding-top: 8px; }
.draft-content .json-editor, .draft-content .serial-preview { width: 100%; box-sizing: border-box; }
.button-row .el-button { margin-left: 0; }
.json-editor :deep(textarea) { font-family: Consolas, monospace; }
.serial-preview { margin: 0; padding: 14px; background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 6px; white-space: pre-wrap; overflow-wrap: anywhere; font-family: Consolas, monospace; }
.camera-col { margin-bottom: 16px; }
h3 { margin: 0 0 12px; font-size: 15px; }
.event-log { max-height: 340px; overflow-y: auto; }
@media (max-width: 768px) { .dashboard { padding: 10px; } }
</style>
