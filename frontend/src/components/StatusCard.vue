<!--
  StatusCard.vue - 状态展示卡片
  用于 Dashboard 顶部的传感器状态卡片
-->
<template>
  <div class="dashboard-card status-card" :class="`status-${status}`">
    <div class="card-icon">
      <el-icon :size="22">
        <component :is="icon" />
      </el-icon>
    </div>
    <div class="card-info">
      <span class="card-title">{{ title }}</span>
      <span class="card-value">{{ value }}</span>
      <span v-if="subtitle" class="card-subtitle">{{ subtitle }}</span>
    </div>
    <div class="card-indicator" :class="`indicator-${status}`"></div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  value: { type: String, default: '--' },
  subtitle: { type: String, default: '' },
  status: { type: String, default: 'normal' }, // normal | warning | danger | offline
  icon: { type: String, default: 'Odometer' }
})
</script>

<style scoped>
.status-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  position: relative;
  overflow: hidden;
  cursor: default;
  transition: transform 0.2s, box-shadow 0.2s;
  margin-bottom: 16px;
}
.status-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
}
.card-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.card-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.card-title {
  font-size: 12px;
  color: var(--text-muted);
}
.card-value {
  font-size: 18px;
  font-weight: 700;
}
.card-subtitle {
  font-size: 11px;
  color: var(--text-muted);
}
.card-indicator {
  position: absolute;
  top: 0;
  right: 0;
  width: 4px;
  height: 100%;
  border-radius: 0 2px 2px 0;
}

/* 状态配色 */
.status-normal .card-icon { background: rgba(103,194,58,0.12); color: var(--success); }
.status-normal .card-indicator { background: var(--success); }

.status-warning .card-icon { background: rgba(230,162,60,0.12); color: var(--warning); }
.status-warning .card-indicator { background: var(--warning); }

.status-danger .card-icon { background: rgba(245,108,108,0.12); color: var(--danger); }
.status-danger .card-indicator { background: var(--danger); }

.status-offline .card-icon { background: rgba(144,147,153,0.12); color: var(--text-muted); }
.status-offline .card-indicator { background: var(--text-muted); }
</style>
