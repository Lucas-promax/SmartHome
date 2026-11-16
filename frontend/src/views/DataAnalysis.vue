<!--
  DataAnalysis.vue - 数据统计分析页
  数据来自后端 SQLite 聚合接口，按实际采样频率自动使用秒/分钟/小时粒度。
-->
<template>
  <div class="page-container analysis-page">
    <h2 class="page-title">
      <el-icon><TrendCharts /></el-icon>
      数据统计分析
    </h2>

    <div class="dashboard-card filter-bar">
      <div class="filter-left">
        <el-radio-group v-model="timeRange" @change="onRangeChange" size="default">
          <el-radio-button value="30m">近30分钟</el-radio-button>
          <el-radio-button value="6h">近6小时</el-radio-button>
          <el-radio-button value="24h">近24小时</el-radio-button>
          <el-radio-button value="7d">近7天</el-radio-button>
        </el-radio-group>
        <span class="bucket-label">当前粒度：{{ bucketLabel }}</span>
      </div>
      <div class="filter-right">
        <el-date-picker
          v-model="customRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          format="MM-DD HH:mm:ss"
          value-format="YYYY-MM-DDTHH:mm:ssZ"
          size="default"
          @change="onCustomRange"
        />
        <el-button size="default" type="primary" :loading="loading" @click="refreshCharts">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <el-row :gutter="16" class="summary-row">
      <el-col v-for="item in summaryCards" :key="item.label" :xs="12" :sm="8" :lg="4">
        <div class="metric-card dashboard-card">
          <span class="metric-label">{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <small>{{ item.extra }}</small>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="charts-row" v-loading="loading">
      <el-col :xs="24" :lg="12">
        <ChartCard title="室内温度/湿度趋势" :option="environmentChartOption" download-name="温湿度趋势" height="340px" />
      </el-col>

      <el-col :xs="24" :lg="12">
        <ChartCard title="灯光亮度变化" :option="lightChartOption" download-name="灯光亮度" height="340px" />
      </el-col>

      <el-col :xs="24" :lg="12">
        <ChartCard title="入户门操作统计" :option="doorChartOption" download-name="入户门统计" height="340px" />
      </el-col>

      <el-col :xs="24" :lg="12">
        <ChartCard title="车库门操作统计" :option="windowChartOption" download-name="车库门统计" height="340px" />
      </el-col>

      <el-col :xs="24" :lg="12">
        <ChartCard title="门禁识别结果" :option="accessChartOption" download-name="门禁识别" height="340px" />
      </el-col>

      <el-col :xs="24" :lg="12">
        <ChartCard title="AI识别调用趋势" :option="visionTimelineOption" download-name="AI识别趋势" height="340px" />
      </el-col>

      <el-col :xs="24" :lg="12">
        <ChartCard title="设备操作来源" :option="deviceSourceOption" download-name="设备操作来源" height="320px" />
      </el-col>

      <el-col :xs="24" :lg="12">
        <ChartCard title="AI识别目标分布" :option="visionObjectOption" download-name="识别目标分布" height="320px" />
      </el-col>
    </el-row>

    <el-row :gutter="16" class="tables-row">
      <el-col :xs="24" :lg="12">
        <div class="dashboard-card table-card">
          <div class="table-title">环境统计</div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="记录数">{{ sensors.raw_count || 0 }}</el-descriptions-item>
            <el-descriptions-item label="高温次数">{{ sensors.high_temperature_count || 0 }}</el-descriptions-item>
            <el-descriptions-item label="平均温度">{{ formatValue(sensors.temperature_avg, '°C') }}</el-descriptions-item>
            <el-descriptions-item label="温度范围">{{ formatRange(sensors.temperature_min, sensors.temperature_max, '°C') }}</el-descriptions-item>
            <el-descriptions-item label="平均湿度">{{ formatValue(sensors.humidity_avg, '%') }}</el-descriptions-item>
            <el-descriptions-item label="湿度范围">{{ formatRange(sensors.humidity_min, sensors.humidity_max, '%') }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </el-col>

      <el-col :xs="24" :lg="12">
        <div class="dashboard-card table-card">
          <div class="table-title">近期设备日志</div>
          <el-table :data="devices.recent_logs || []" size="small" stripe max-height="250">
            <el-table-column prop="created_at" label="时间" min-width="160" :formatter="formatTableTime" />
            <el-table-column prop="device_id" label="设备" min-width="110" :formatter="formatDevice" />
            <el-table-column prop="action" label="动作" min-width="90" />
            <el-table-column prop="source" label="来源" min-width="90" :formatter="formatSource" />
          </el-table>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { TrendCharts, Refresh } from '@element-plus/icons-vue'
import ChartCard from '../components/ChartCard.vue'
import { analysisApi } from '../utils/http'

const timeRange = ref('6h')
const customRange = ref(null)
const loading = ref(false)
const analysis = ref({})

const sensors = computed(() => analysis.value.sensors || {})
const devices = computed(() => analysis.value.devices || {})
const access = computed(() => analysis.value.access || {})
const vision = computed(() => analysis.value.vision || {})
const summary = computed(() => analysis.value.summary || {})

onMounted(() => {
  loadData()
})

function rangeParams() {
  if (customRange.value && customRange.value.length === 2) {
    return { after: customRange.value[0], before: customRange.value[1] }
  }
  const now = new Date()
  const start = new Date(now)
  if (timeRange.value === '30m') start.setMinutes(now.getMinutes() - 30)
  else if (timeRange.value === '6h') start.setHours(now.getHours() - 6)
  else if (timeRange.value === '24h') start.setHours(now.getHours() - 24)
  else start.setDate(now.getDate() - 7)
  return { after: start.toISOString(), before: now.toISOString() }
}

async function loadData() {
  loading.value = true
  try {
    analysis.value = await analysisApi.overview(rangeParams())
  } catch (error) {
    ElMessage.error(error.message || '加载数据分析失败')
  } finally {
    loading.value = false
  }
}

function onRangeChange() {
  customRange.value = null
  loadData()
}

function onCustomRange(val) {
  if (val) {
    timeRange.value = ''
    loadData()
  }
}

function refreshCharts() {
  loadData()
}

const bucketLabel = computed(() => {
  const seconds = analysis.value.bucket_seconds || sensors.value.bucket_seconds
  if (!seconds) return '自动'
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`
  return `${Math.round(seconds / 3600)}小时`
})

const summaryCards = computed(() => [
  { label: '传感器记录', value: sensors.value.raw_count || 0, extra: bucketLabel.value },
  { label: '设备操作', value: sumObject(devices.value.operation_counts), extra: `远程 ${devices.value.source_counts?.remote || 0}` },
  { label: '门禁通过', value: access.value.granted || 0, extra: `拒绝/未知 ${access.value.denied || 0}` },
  { label: 'AI识别', value: sumObject(vision.value.mode_counts), extra: `目标 ${sumObject(vision.value.object_counts)}` },
  { label: '人员数量', value: summary.value.persons || 0, extra: '数据库' },
  { label: '日志总量', value: (summary.value.device_logs || 0) + (summary.value.vision_logs || 0) + (summary.value.access_logs || 0), extra: '设备/视觉/门禁' }
])

function sumObject(obj = {}) {
  return Object.values(obj || {}).reduce((sum, value) => sum + Number(value || 0), 0)
}

function timeLabel(value) {
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

function baseTimeAxis() {
  return {
    type: 'time',
    axisLabel: { formatter: (v) => timeLabel(v), rotate: 30, fontSize: 10 }
  }
}

function emptyOption(text = '暂无数据') {
  return {
    title: { text, left: 'center', top: 'middle', textStyle: { fontSize: 14, color: '#909399' } },
    xAxis: { show: false },
    yAxis: { show: false },
    series: []
  }
}

const environmentChartOption = computed(() => {
  const series = sensors.value.series || []
  if (!series.length) return emptyOption()
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['温度', '湿度'], top: 0 },
    grid: { top: 42, right: 42, bottom: 58, left: 52 },
    xAxis: baseTimeAxis(),
    yAxis: [
      { type: 'value', name: '°C', min: 0, max: 40, axisLabel: { formatter: '{value}°C' } },
      { type: 'value', name: '%', min: 0, max: 100, axisLabel: { formatter: '{value}%' } }
    ],
    series: [
      {
        name: '温度', type: 'line', smooth: true, symbol: 'none', sampling: 'lttb',
        data: series.map(d => [d.time, d.temperature]),
        lineStyle: { color: '#f56c6c', width: 2 }
      },
      {
        name: '湿度', type: 'line', smooth: true, symbol: 'none', yAxisIndex: 1, sampling: 'lttb',
        data: series.map(d => [d.time, d.humidity]),
        lineStyle: { color: '#409eff', width: 2 }
      }
    ]
  }
})

const lightChartOption = computed(() => {
  const series = devices.value.brightness_series || []
  if (!series.length) return emptyOption('当前时间范围内无灯光亮度调整')
  return {
    tooltip: { trigger: 'axis' },
    grid: { top: 24, right: 24, bottom: 58, left: 50 },
    xAxis: baseTimeAxis(),
    yAxis: { type: 'value', name: '输出值', min: 0, max: 255 },
    series: [{
      name: '亮度', type: 'line', smooth: true, step: 'end', symbolSize: 6,
      data: series.map(d => [d.time, d.value]),
      lineStyle: { color: '#e6a23c', width: 2 },
      itemStyle: { color: '#e6a23c' }
    }]
  }
})

function operationChartOption(keys, names, colors) {
  const rows = devices.value.timeline || []
  if (!rows.length) return emptyOption('当前时间范围内无设备操作')
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: names, top: 0 },
    grid: { top: 42, right: 24, bottom: 58, left: 46 },
    xAxis: { type: 'category', data: rows.map(d => timeLabel(d.time)), axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: { type: 'value', name: '次', minInterval: 1 },
    series: keys.map((key, index) => ({
      name: names[index], type: 'bar', stack: 'ops', data: rows.map(d => d[key] || 0),
      itemStyle: { color: colors[index], borderRadius: [4, 4, 0, 0] }
    }))
  }
}

const doorChartOption = computed(() => operationChartOption(['door_lock', 'door_unlock'], ['关闭', '开启'], ['#67c23a', '#f56c6c']))
const windowChartOption = computed(() => operationChartOption(['window_open', 'window_close'], ['开启', '关闭'], ['#e6a23c', '#409eff']))

const accessChartOption = computed(() => {
  const rows = access.value.timeline || []
  if (!rows.length) return emptyOption('当前时间范围内无门禁记录')
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['通过', '拒绝', '未知'], top: 0 },
    grid: { top: 42, right: 24, bottom: 58, left: 46 },
    xAxis: { type: 'category', data: rows.map(d => timeLabel(d.time)), axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: { type: 'value', name: '次', minInterval: 1 },
    series: [
      { name: '通过', type: 'bar', stack: 'access', data: rows.map(d => d.granted || 0), itemStyle: { color: '#67c23a' } },
      { name: '拒绝', type: 'bar', stack: 'access', data: rows.map(d => d.denied || 0), itemStyle: { color: '#f56c6c' } },
      { name: '未知', type: 'bar', stack: 'access', data: rows.map(d => d.unknown || 0), itemStyle: { color: '#909399' } }
    ]
  }
})

const visionTimelineOption = computed(() => {
  const rows = vision.value.timeline || []
  if (!rows.length) return emptyOption('当前时间范围内无AI识别记录')
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['人脸识别', '物体识别'], top: 0 },
    grid: { top: 42, right: 24, bottom: 58, left: 46 },
    xAxis: { type: 'category', data: rows.map(d => timeLabel(d.time)), axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: { type: 'value', name: '次', minInterval: 1 },
    series: [
      { name: '人脸识别', type: 'line', smooth: true, data: rows.map(d => d.face || 0), lineStyle: { color: '#8e6be8' } },
      { name: '物体识别', type: 'line', smooth: true, data: rows.map(d => d.object || 0), lineStyle: { color: '#00a870' } }
    ]
  }
})

function pieOption(dataMap, fallbackText) {
  const data = Object.entries(dataMap || {}).map(([name, value]) => ({ name: translateLabel(name), value }))
  if (!data.length) return emptyOption(fallbackText)
  return {
    tooltip: { trigger: 'item' },
    legend: { orient: 'vertical', right: 8, top: 20 },
    series: [{
      type: 'pie', radius: ['42%', '68%'], center: ['38%', '52%'], data,
      label: { formatter: '{b}: {c}' }
    }]
  }
}

const deviceSourceOption = computed(() => pieOption(devices.value.source_counts, '当前时间范围内无设备来源数据'))
const visionObjectOption = computed(() => pieOption(vision.value.object_counts || vision.value.mode_counts, '当前时间范围内无识别目标数据'))

function translateLabel(value) {
  const map = {
    remote: '远程控制', user: '网页或助手控制', hardware: '板端上报', face: '人脸识别', general: '通用识别', fire_drone: '无人机/灭火器', realtime: '实时识别', image: '图片识别'
  }
  return map[value] || value
}

function formatValue(value, unit) {
  if (value === null || value === undefined) return '-'
  return `${value}${unit}`
}

function formatRange(min, max, unit) {
  if (min === null || min === undefined || max === null || max === undefined) return '-'
  return `${min}${unit} - ${max}${unit}`
}

function formatTableTime(row, column, value) {
  return value ? timeLabel(value) : '-'
}

function formatDevice(row, column, value) {
  const map = { door_main: '主门', window_main: '窗户（历史）', garage_main: '车库门', light_main: '主灯', fan_main: '风扇' }
  return map[value] || value
}

function formatSource(row, column, value) {
  return translateLabel(value)
}
</script>

<style scoped>
.analysis-page {
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
.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.filter-left,
.filter-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.bucket-label {
  color: var(--text-secondary);
  font-size: 13px;
}
.summary-row,
.charts-row,
.tables-row {
  margin: 0 !important;
}
.summary-row .el-col,
.charts-row .el-col,
.tables-row .el-col {
  margin-bottom: 16px;
}
.metric-card {
  min-height: 92px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
}
.metric-label {
  color: var(--text-secondary);
  font-size: 13px;
}
.metric-card strong {
  font-size: 24px;
  color: var(--text-primary);
  line-height: 1;
}
.metric-card small {
  color: var(--text-secondary);
}
.table-card {
  min-height: 330px;
}
.table-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 12px;
}

@media (max-width: 768px) {
  .filter-bar,
  .filter-left,
  .filter-right {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
