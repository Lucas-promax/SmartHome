<template>
  <section class="hardware-settings dashboard-card">
    <div class="hardware-heading"><h3>Arduino 设备连接</h3><el-tag :type="status.ready ? 'success' : 'info'">{{ status.ready ? '状态已同步' : status.connected ? '等待状态' : '未连接' }}</el-tag></div>
    <p>选择家居主控的串口，固定 9600 波特率。连接后可能触发板子复位，请先确认现场设备可以复位。</p>
    <div class="hardware-actions">
      <el-select v-model="port" placeholder="选择设备控制串口" :disabled="busy" style="min-width: 240px">
        <el-option v-for="entry in ports" :key="entry.port" :value="entry.port" :label="`${entry.port} · ${entry.description}`" />
      </el-select>
      <el-button :disabled="busy" @click="loadPorts">刷新串口</el-button>
      <el-button type="primary" :loading="busy" :disabled="!port" @click="configure(true)">连接并保存</el-button>
      <el-button :disabled="busy" @click="configure(false)">断开并停用</el-button>
    </div>
    <p v-if="status.error" class="error-text">{{ status.error }}</p>
    <p>最近有效上报：{{ status.last_report_at ? new Date(status.last_report_at).toLocaleString('zh-CN') : '暂无' }}</p>
  </section>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { hardwareApi } from '../utils/http'

const status = ref({})
const ports = ref([])
const port = ref('')
const busy = ref(false)
let timer
let polling = false
let disposed = false
async function poll() {
  if (polling) return
  polling = true
  try { status.value = await hardwareApi.status() } catch { status.value = { error: '无法获取硬件连接状态' } }
  finally { polling = false }
}
async function loadPorts() {
  try { ports.value = await hardwareApi.ports() } catch (e) { ElMessage.error(e.message) }
}
async function configure(enabled) {
  busy.value = true
  try {
    status.value = await hardwareApi.configure({ port: port.value, enabled })
    ElMessage.info(enabled ? '已保存，正在连接并等待板端状态' : '已停用串口连接')
  } catch (e) { ElMessage.error(e.message) }
  finally { busy.value = false }
}
onMounted(async () => {
  await Promise.all([poll(), loadPorts()])
  port.value = status.value.port || ''
  if (!disposed) timer = setInterval(poll, 2000)
})
onUnmounted(() => { disposed = true; clearInterval(timer) })
</script>

<style scoped>
.hardware-settings { margin: 0 0 20px; padding: 20px; }
.hardware-heading, .hardware-actions { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
.hardware-heading { justify-content: space-between; }
p { color: var(--text-secondary); font-size: 13px; line-height: 1.7; margin: 12px 0; }
.error-text { color: var(--el-color-danger); }
</style>
