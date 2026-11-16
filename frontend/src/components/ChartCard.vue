<!--
  ChartCard.vue - ECharts 图表封装组件
  特性：自适应容器、主题跟随、截图下载(加分功能3)
-->
<template>
  <div class="chart-card dashboard-card">
    <div class="chart-card-header">
      <span class="chart-title">{{ title }}</span>
      <el-button-group class="chart-actions">
        <el-button size="small" text @click="downloadChart">
          <el-icon><Download /></el-icon>
          <span class="hide-on-mobile">下载</span>
        </el-button>
        <slot name="actions"></slot>
      </el-button-group>
    </div>
    <div class="chart-body" ref="chartContainer"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { Download } from '@element-plus/icons-vue'

const props = defineProps({
  title: { type: String, default: '图表' },
  option: { type: Object, default: () => ({}) },
  height: { type: String, default: '320px' },
  // 截图下载文件名
  downloadName: { type: String, default: 'chart' }
})

const chartContainer = ref(null)
let chartInstance = null
let resizeObserver = null

onMounted(() => {
  nextTick(() => initChart())
})

onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect()
  if (chartInstance) chartInstance.dispose()
  window.removeEventListener('resize', handleResize)
})

// 监听option变化更新图表
watch(() => props.option, (newOpt) => {
  if (chartInstance && newOpt) {
    chartInstance.setOption(newOpt, true)
  }
}, { deep: true })

// 监听深色主题切换
watch(() => document.documentElement.classList.contains('dark'), () => {
  if (chartInstance) {
    chartInstance.dispose()
    initChart()
  }
})

function initChart() {
  if (!chartContainer.value) return
  const isDark = document.documentElement.classList.contains('dark')

  chartInstance = echarts.init(chartContainer.value, isDark ? 'dark' : undefined)

  if (props.option && Object.keys(props.option).length > 0) {
    chartInstance.setOption(props.option)
  }

  // ResizeObserver 自动适应容器大小
  resizeObserver = new ResizeObserver(() => {
    chartInstance && chartInstance.resize()
  })
  resizeObserver.observe(chartContainer.value)
  window.addEventListener('resize', handleResize)
}

function handleResize() {
  chartInstance && chartInstance.resize()
}

/**
 * 截图下载功能 (加分功能3)
 * 使用 ECharts getDataURL 导出PNG
 */
function downloadChart() {
  if (!chartInstance) return
  const url = chartInstance.getDataURL({
    type: 'png',
    pixelRatio: 2,
    backgroundColor: document.documentElement.classList.contains('dark') ? '#16213e' : '#ffffff'
  })
  const link = document.createElement('a')
  link.href = url
  link.download = `${props.downloadName}_${new Date().toLocaleDateString()}.png`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

// 暴露图表实例供外部调用
defineExpose({ chartInstance, downloadChart })
</script>

<style scoped>
.chart-card {
  display: flex;
  flex-direction: column;
}
.chart-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.chart-title {
  font-size: 15px;
  font-weight: 600;
}
.chart-body {
  flex: 1;
  width: 100%;
  min-height: v-bind(height);
}
.chart-actions {
  flex-shrink: 0;
}
</style>
