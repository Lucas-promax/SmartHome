<!--
  App.vue - 主应用布局
  侧边栏导航 + 顶部标题栏 + 内容区
  支持电脑端侧边栏 / 手机端底部Tab导航
-->
<template>
  <el-container class="app-container">
    <!-- 桌面端侧边栏 -->
    <el-aside :width="isMobile ? '0px' : asideWidth" class="app-aside hide-on-mobile">
      <SideMenu :collapsed="asideCollapsed" @toggle-collapse="asideCollapsed = !asideCollapsed" />
    </el-aside>

    <!-- 移动端侧边栏 (drawer形式) -->
    <el-drawer
      v-model="mobileMenuVisible"
      direction="ltr"
      size="220px"
      :with-header="false"
    >
      <SideMenu @navigate="mobileMenuVisible = false" />
    </el-drawer>

    <el-container class="app-main">
      <!-- 顶部栏 -->
      <el-header class="app-header">
        <div class="header-left">
          <el-button
            v-if="isMobile"
            text
            class="menu-toggle"
            @click="mobileMenuVisible = true"
          >
            <el-icon :size="22"><Expand /></el-icon>
          </el-button>
          <h1 class="app-title">
            <span class="title-icon">🏠</span>
            <span class="title-text hide-on-mobile">DnB26 智能家居控制台</span>
            <span class="title-text-mobile" v-if="isMobile">DnB26</span>
          </h1>
        </div>
        <div class="header-right">
          <!-- 后端连接状态 -->
          <el-tag
            :type="wsConnected ? 'success' : 'danger'"
            size="small"
            effect="dark"
            class="ws-status hide-on-mobile"
          >
            {{ wsConnected ? '后端已连接' : '后端未连接' }}
          </el-tag>
          <ThemeToggle />
          <span class="header-time hide-on-mobile">{{ currentTime }}</span>
        </div>
      </el-header>

      <!-- 告警提示栏 -->
      <AlertBar :alerts="alerts" :staySeconds="alertStaySeconds" @dismiss="alerts = []" />

      <!-- 内容区 -->
      <el-main class="app-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>

      <!-- 移动端底部导航 -->
      <div class="mobile-nav" v-if="isMobile">
        <div
          v-for="route in navRoutes"
          :key="route.path"
          class="mobile-nav-item"
          :class="{ active: currentRoute === route.path }"
          @click="$router.push(route.path)"
        >
          <el-icon :size="20"><component :is="route.icon" /></el-icon>
          <span>{{ route.label }}</span>
        </div>
      </div>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, provide } from 'vue'
import { useRoute } from 'vue-router'
import {
  Expand, Odometer, View, TrendCharts, User, Document, Setting
} from '@element-plus/icons-vue'
import ThemeToggle from './components/ThemeToggle.vue'
import AlertBar from './components/AlertBar.vue'
import SideMenu from './components/SideMenu.vue'
import { homeApi } from './utils/http'

const route = useRoute()

// 响应式检测
const isMobile = ref(window.innerWidth < 768)
const mobileMenuVisible = ref(false)
const asideCollapsed = ref(false)
const asideWidth = computed(() => asideCollapsed.value ? '72px' : '220px')

// 时间显示
const currentTime = ref('')
let timeTimer = null

// Backend and Arduino are separate connections.
const wsConnected = ref(false)
const hardwareState = ref({ connected: false, ready: false, fresh_devices: {} })

// 告警列表
const alerts = ref([])
const alertStaySeconds = ref(5)

// 传感器数据(全局共享)
const sensorData = ref({
  temperature: null, humidity: null, environmentFresh: false,
  doorOpen: null, garageOpen: null, fanOn: null, lightOn: null,
  lightLevel: null, timestamp: null
})

const recentEvents = ref([])

// YOLO检测数据(全局共享)
const yoloData = ref({ detections: [], hasBulb: false })

// 提供全局数据给子组件
provide('sensorData', sensorData)
provide('hardwareState', hardwareState)
provide('yoloData', yoloData)
provide('recentEvents', recentEvents)
provide('refreshHomeStatus', loadHomeStatus)

// 导航路由
const navRoutes = [
  { path: '/dashboard', label: '看板', icon: Odometer },
  { path: '/ai-recognition', label: 'AI识别', icon: View },
  { path: '/data-analysis', label: '分析', icon: TrendCharts },
  { path: '/personnel', label: '授权', icon: User },
  { path: '/logs', label: '日志', icon: Document },
  { path: '/settings', label: '配置', icon: Setting }
]

const currentRoute = computed(() => route.path)

let statusTimer = null

onMounted(() => {
  updateTime()
  timeTimer = setInterval(updateTime, 1000)

  window.addEventListener('resize', handleResize)

  loadHomeStatus()
  statusTimer = setInterval(loadHomeStatus, 2000)
})

onUnmounted(() => {
  clearInterval(timeTimer)
  clearInterval(statusTimer)
  window.removeEventListener('resize', handleResize)
})

function handleResize() {
  isMobile.value = window.innerWidth < 768
}

function updateTime() {
  currentTime.value = new Date().toLocaleString('zh-CN')
}

let homeLoading = false
async function loadHomeStatus() {
  if (homeLoading) return
  homeLoading = true
  try {
    const data = await homeApi.status()
    hardwareState.value = data.hardware || { connected: false, ready: false, fresh_devices: {} }
    sensorData.value = mapHomeStatus(data)
    alerts.value = data.alerts || []
    alertStaySeconds.value = data.alert_settings?.banner_stay_seconds || 5
    recentEvents.value = data.events || []
    wsConnected.value = true
  } catch (e) {
    wsConnected.value = false
    hardwareState.value = { connected: false, ready: false, fresh_devices: {} }
    sensorData.value.environmentFresh = false
    alerts.value = [{ type: 'warning', message: `后端状态获取失败：${e.message}` }]
  } finally { homeLoading = false }
}

function mapHomeStatus(data) {
  const devices = Object.fromEntries((data.devices || []).map(device => [device.device_id, device]))
  const liveState = id => devices[id]?.fresh ? devices[id].state : {}
  const light = liveState('light_main')
  const fan = liveState('fan_main')
  const door = liveState('door_main')
  const garage = liveState('garage_main')
  const fresh = data.environment?.fresh === true
  return {
    temperature: fresh ? data.environment.temperature : null,
    humidity: fresh ? data.environment.humidity : null,
    environmentFresh: fresh, lightBright: fresh ? data.environment.light_bright : null,
    doorOpen: door.open ?? null, garageOpen: garage.open ?? null,
    fanOn: fan.power ?? null, lightOn: light.power ?? null,
    lightLevel: light.brightness ?? null,
    timestamp: data.environment?.created_at
  }
}
</script>

<style scoped>
.app-container {
  height: 100vh;
  overflow: hidden;
}

/* 侧边栏 */
.app-aside {
  background: var(--bg-sidebar) !important;
  overflow-y: auto;
  transition: width 0.3s;
}

/* 顶部栏 */
.app-header {
  background: var(--header-bg);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  height: 56px !important;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.header-left, .header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.app-title {
  font-size: 18px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
.title-icon { font-size: 24px; }
.header-time {
  font-size: 13px;
  color: var(--text-muted);
  min-width: 140px;
  text-align: right;
}

/* 内容区 */
.app-content {
  background: var(--bg-primary);
  overflow-y: auto;
  height: calc(100vh - 56px);
  padding: 0;
}

/* 移动端底部导航 */
.mobile-nav {
  display: flex;
  justify-content: space-around;
  background: var(--bg-card);
  border-top: 1px solid var(--border-color);
  padding: 6px 0;
  padding-bottom: max(6px, env(safe-area-inset-bottom));
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 99;
  height: 56px;
}
.mobile-nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px 12px;
  border-radius: 8px;
  transition: all 0.2s;
}
.mobile-nav-item.active {
  color: var(--accent);
}
.mobile-nav-item span {
  font-size: 10px;
}

@media (max-width: 768px) {
  .app-content {
    padding-bottom: 64px;
    height: calc(100vh - 56px - 56px);
  }
  .app-header {
    padding: 0 12px;
  }
  .app-title {
    font-size: 15px;
  }
}
</style>
