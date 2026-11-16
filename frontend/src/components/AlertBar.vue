<!--
  AlertBar.vue - 顶部告警提示栏
  展示：高温预警、门窗异常开启提醒
  支持多条告警滚动显示
-->
<template>
  <div class="alert-bar" v-if="alerts.length > 0">
    <div class="alert-bar-inner">
      <el-icon class="alert-icon" :class="`alert-${alerts[0].type}`">
        <WarningFilled />
      </el-icon>
      <div class="alert-scroll">
        <span class="alert-item" :class="`alert-${currentAlert.type}`">
          {{ currentAlert.message }}
        </span>
      </div>
      <el-button text class="alert-close" @click="$emit('dismiss')">
        <el-icon><Close /></el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { WarningFilled, Close } from '@element-plus/icons-vue'

const props = defineProps({
  alerts: {
    type: Array,
    default: () => []
  },
  staySeconds: {
    type: Number,
    default: 5
  }
})

defineEmits(['dismiss'])

const activeIndex = ref(0)
let stayTimer = null

const currentAlert = computed(() => props.alerts[activeIndex.value] || props.alerts[0] || { type: 'info', message: '' })

onMounted(() => {
  startStayTimer()
})

onUnmounted(() => {
  clearInterval(stayTimer)
})

watch(() => [props.alerts.length, props.staySeconds], () => {
  activeIndex.value = 0
  clearInterval(stayTimer)
  startStayTimer()
})

function startStayTimer() {
  if (props.alerts.length <= 1) return
  stayTimer = setInterval(() => {
    activeIndex.value = (activeIndex.value + 1) % props.alerts.length
  }, Math.max(1, props.staySeconds) * 1000)
}
</script>

<style scoped>
.alert-bar {
  background: linear-gradient(135deg, #fff3e0, #ffecb3);
  border-bottom: 2px solid var(--warning);
  padding: 8px 0;
  position: sticky;
  top: 0;
  z-index: 100;
}
html.dark .alert-bar {
  background: linear-gradient(135deg, #3e2723, #4e342e);
}
.alert-bar-inner {
  display: flex;
  align-items: center;
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 16px;
  gap: 10px;
}
.alert-icon {
  font-size: 20px;
  flex-shrink: 0;
}
.alert-icon.alert-warning,
.alert-icon.alert-error { color: var(--danger); }
.alert-icon.alert-info { color: var(--accent); }

.alert-scroll {
  flex: 1;
  overflow: hidden;
  position: relative;
  height: 24px;
}
.alert-item {
  display: block;
  font-size: 14px;
  font-weight: 500;
  line-height: 24px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.alert-item.alert-warning { color: #e65100; }
.alert-item.alert-error { color: #c62828; }
.alert-item.alert-info { color: #1565c0; }
.alert-close {
  flex-shrink: 0;
}
</style>
