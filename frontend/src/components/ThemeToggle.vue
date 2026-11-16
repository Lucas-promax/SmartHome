<!--
  ThemeToggle.vue - 浅色/深色主题切换按钮 (加分功能2)
  通过切换 html.dark class 实现主题切换
  状态持久化到 localStorage
-->
<template>
  <el-tooltip :content="isDark ? '切换到浅色模式' : '切换到深色模式'" placement="bottom">
    <el-button
      circle
      class="theme-toggle-btn"
      @click="toggleTheme"
    >
      <el-icon :size="18">
        <Sunny v-if="isDark" />
        <Moon v-else />
      </el-icon>
    </el-button>
  </el-tooltip>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { Sunny, Moon } from '@element-plus/icons-vue'

const isDark = ref(false)

function applyTheme(theme) {
  isDark.value = theme === 'dark'
  document.documentElement.classList.toggle('dark', isDark.value)
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
}

function onThemeChange(event) {
  applyTheme(event.detail?.theme === 'dark' ? 'dark' : 'light')
}

onMounted(() => {
  applyTheme(localStorage.getItem('theme') === 'dark' ? 'dark' : 'light')
  window.addEventListener('theme-change', onThemeChange)
})

onUnmounted(() => {
  window.removeEventListener('theme-change', onThemeChange)
})

function toggleTheme() {
  applyTheme(isDark.value ? 'light' : 'dark')
}
</script>

<style scoped>
.theme-toggle-btn {
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 18px;
  transition: transform 0.3s;
}
.theme-toggle-btn:hover {
  transform: rotate(30deg);
  color: var(--accent);
}
</style>
