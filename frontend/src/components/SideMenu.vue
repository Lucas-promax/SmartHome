<!--
  SideMenu.vue - 侧边栏导航菜单
  桌面端固定在左侧，移动端在 Drawer 中显示
-->
<template>
  <div class="side-menu" :class="{ collapsed }">
    <div class="side-logo">
      <span class="logo-icon">🏠</span>
      <span v-if="!collapsed" class="logo-text">DnB26 智能家居</span>
      <el-button text class="collapse-btn" @click="$emit('toggleCollapse')">
        <el-icon><component :is="collapsed ? Expand : Fold" /></el-icon>
      </el-button>
    </div>

    <el-menu
      :default-active="activeRoute"
      :router="true"
      background-color="transparent"
      text-color="var(--sidebar-text)"
      active-text-color="var(--sidebar-active)"
      class="side-menu-list"
      :collapse="collapsed"
      :collapse-transition="false"
    >
      <el-menu-item index="/dashboard">
        <el-icon><Odometer /></el-icon>
        <span>首页看板</span>
      </el-menu-item>

      <el-menu-item index="/ai-recognition">
        <el-icon><View /></el-icon>
        <span>AI 识别</span>
      </el-menu-item>

      <el-menu-item index="/data-analysis">
        <el-icon><TrendCharts /></el-icon>
        <span>数据分析</span>
      </el-menu-item>

      <el-menu-item index="/personnel">
        <el-icon><User /></el-icon>
        <span>授权管理</span>
      </el-menu-item>

      <el-menu-item index="/logs">
        <el-icon><Document /></el-icon>
        <span>系统日志</span>
      </el-menu-item>

      <el-menu-item index="/assistant">
        <el-icon><ChatDotRound /></el-icon>
        <span>智能助手</span>
      </el-menu-item>

      <el-menu-item index="/settings">
        <el-icon><Setting /></el-icon>
        <span>系统配置</span>
      </el-menu-item>
    </el-menu>

    <div class="side-footer" v-if="!collapsed">
      <span class="version">v1.0.0 · BUPT</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Odometer, View, TrendCharts, User, Document, Setting, ChatDotRound, Fold, Expand } from '@element-plus/icons-vue'

const route = useRoute()
const activeRoute = computed(() => route.path)

defineProps({
  collapsed: {
    type: Boolean,
    default: false
  }
})

defineEmits(['navigate', 'toggleCollapse'])
</script>

<style scoped>
.side-menu {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.side-logo {
  padding: 20px 16px;
  display: flex;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}
.logo-icon { font-size: 28px; }
.logo-text {
  font-size: 16px;
  font-weight: 700;
  color: #e0e0e0;
}
.collapse-btn {
  margin-left: auto;
  color: #e0e0e0;
}
.collapsed .side-logo {
  padding: 18px 8px;
  justify-content: center;
  flex-direction: column;
}
.collapsed .logo-icon {
  font-size: 24px;
}
.collapsed .collapse-btn {
  margin-left: 0;
}
.side-menu-list {
  flex: 1;
  border-right: none !important;
  padding-top: 8px;
}
.side-menu-list:not(.el-menu--collapse) {
  width: 100%;
}
.side-menu-list.el-menu--collapse {
  width: 72px;
}
.side-menu-list .el-menu-item {
  margin: 2px 8px;
  border-radius: 8px;
  font-size: 14px;
}
.side-menu-list .el-menu-item:hover {
  background: rgba(255,255,255,0.08) !important;
}
.side-menu-list .el-menu-item.is-active {
  background: rgba(64,158,255,0.2) !important;
}
.side-footer {
  padding: 12px 16px;
  border-top: 1px solid rgba(255,255,255,0.1);
  text-align: center;
}
.version {
  font-size: 11px;
  color: var(--text-muted);
}
</style>
