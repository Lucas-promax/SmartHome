<!--
  SystemLogs.vue - 系统日志页面
  展示数据库中的操作、设备、门禁和视觉识别日志，支持筛选、搜索、导出和条件清理。
-->
<template>
  <div class="page-container logs-page">
    <h2 class="page-title">
      <el-icon><Document /></el-icon>
      系统日志
      <el-tag size="small" type="info" effect="plain" style="margin-left:8px;">
        {{ total }} 条
      </el-tag>
    </h2>

    <div class="dashboard-card filter-bar">
      <div class="filter-left">
        <el-select v-model="filters.source" placeholder="日志来源" clearable style="width: 132px;" @change="reloadFirstPage">
          <el-option label="全部来源" value="" />
          <el-option label="操作日志" value="operation" />
          <el-option label="设备日志" value="device" />
          <el-option label="门禁日志" value="access" />
          <el-option label="视觉日志" value="vision" />
        </el-select>

        <el-select v-model="filters.log_type" placeholder="日志类型" clearable style="width: 132px;" @change="reloadFirstPage">
          <el-option label="全部类型" value="" />
          <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>

        <el-select v-model="filters.level" placeholder="日志级别" clearable style="width: 116px;" @change="reloadFirstPage">
          <el-option label="全部级别" value="" />
          <el-option label="信息" value="info" />
          <el-option label="警告" value="warning" />
          <el-option label="错误" value="error" />
        </el-select>

        <el-date-picker
          v-model="timeRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          value-format="YYYY-MM-DDTHH:mm:ssZ"
          style="width: 340px;"
          @change="reloadFirstPage"
        />

        <el-input v-model="filters.keyword" placeholder="搜索日志内容、详情..." clearable style="width: 220px;" @keyup.enter="reloadFirstPage" @clear="reloadFirstPage">
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>

      <div class="filter-right">
        <el-button size="small" text @click="reloadFirstPage" :loading="loading">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
        <el-button size="small" text @click="openCleanupDialog" :disabled="total === 0">
          <el-icon><Delete /></el-icon> 清理日志
        </el-button>
        <el-button size="small" text @click="exportLogs" :disabled="logs.length === 0">
          <el-icon><Download /></el-icon> 导出
        </el-button>
      </div>
    </div>

    <div class="dashboard-card log-card" v-loading="loading">
      <el-timeline v-if="logs.length > 0">
        <el-timeline-item
          v-for="log in logs"
          :key="log.id"
          :timestamp="formatTime(log.timestamp)"
          :type="timelineType(log.level)"
          :icon="getLogIcon(log.type)"
          placement="left"
          size="large"
        >
          <div class="log-entry" :class="`log-${log.level}`">
            <el-tag :type="sourceTag(log.source)" size="small" effect="plain" class="log-type-tag">
              {{ sourceLabel(log.source) }}
            </el-tag>
            <el-tag :type="getTypeTagColor(log.type)" size="small" effect="plain" class="log-type-tag">
              {{ getTypeLabel(log.type) }}
            </el-tag>
            <el-tag :type="levelTag(log.level)" size="small" effect="dark" class="log-level-tag">
              {{ levelLabel(log.level) }}
            </el-tag>
            <span class="log-message">{{ log.message }}</span>
          </div>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无日志记录" :image-size="80" />

      <el-pagination
        v-if="total > pageSize"
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next, total"
        small
        style="margin-top: 16px; justify-content: center;"
        @current-change="loadLogs"
      />
    </div>

    <el-dialog v-model="cleanupVisible" title="清理日志" width="520px">
      <el-alert type="warning" :closable="false" show-icon title="清理会直接删除数据库中的日志记录，请先确认筛选条件。" />
      <el-form label-width="96px" class="cleanup-form">
        <el-form-item label="日志来源">
          <el-select v-model="cleanup.source" clearable placeholder="全部来源">
            <el-option label="全部来源" value="" />
            <el-option label="操作日志" value="operation" />
            <el-option label="设备日志" value="device" />
            <el-option label="门禁日志" value="access" />
            <el-option label="视觉日志" value="vision" />
          </el-select>
        </el-form-item>
        <el-form-item label="日志类型">
          <el-select v-model="cleanup.log_type" clearable placeholder="全部类型">
            <el-option label="全部类型" value="" />
            <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="日志级别">
          <el-select v-model="cleanup.level" clearable placeholder="全部级别">
            <el-option label="全部级别" value="" />
            <el-option label="信息" value="info" />
            <el-option label="警告" value="warning" />
            <el-option label="错误" value="error" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="cleanupTimeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DDTHH:mm:ssZ"
          />
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="cleanup.keyword" clearable placeholder="按日志内容或详情匹配" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cleanupVisible = false">取消</el-button>
        <el-button type="danger" :loading="cleanupLoading" @click="confirmCleanup">确认清理</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Search, Delete, Download, Document, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { logApi } from '../utils/http'

const filters = reactive({ source: '', log_type: '', level: '', keyword: '' })
const cleanup = reactive({ source: '', log_type: '', level: '', keyword: '' })
const logs = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const cleanupLoading = ref(false)
const cleanupVisible = ref(false)
const timeRange = ref([])
const cleanupTimeRange = ref([])

const typeMap = {
  door: { label: '入户门', color: '' },
  window: { label: '窗户', color: 'success' },
  garage: { label: '车库门', color: 'success' },
  rfid: { label: 'RFID 刷卡', color: 'info' },
  light: { label: '灯光', color: 'warning' },
  fan: { label: '风扇', color: 'info' },
  face: { label: '人脸识别', color: 'danger' },
  yolo: { label: '物体识别', color: 'success' },
  auth: { label: '认证', color: 'info' },
  settings: { label: '系统配置', color: 'warning' },
  device: { label: '设备操作', color: 'success' },
  person: { label: '人员管理', color: 'danger' },
  logs: { label: '日志管理', color: 'info' },
  system: { label: '系统', color: 'info' }
}

const typeOptions = computed(() => Object.entries(typeMap).map(([value, item]) => ({ value, label: item.label })))

function buildParams(base, range) {
  const params = {
    source: base.source || '',
    log_type: base.log_type || '',
    level: base.level || '',
    keyword: (base.keyword || '').trim(),
  }
  if (range?.length === 2) {
    params.after = range[0]
    params.before = range[1]
  }
  return Object.fromEntries(Object.entries(params).filter(([, value]) => value !== ''))
}

async function loadLogs() {
  loading.value = true
  try {
    const data = await logApi.list({
      ...buildParams(filters, timeRange.value),
      limit: pageSize,
      offset: (page.value - 1) * pageSize
    })
    logs.value = data.items || []
    total.value = data.total || 0
  } catch (error) {
    ElMessage.error(error.message || '日志加载失败')
  } finally {
    loading.value = false
  }
}

function reloadFirstPage() {
  page.value = 1
  loadLogs()
}

function openCleanupDialog() {
  cleanup.source = filters.source
  cleanup.log_type = filters.log_type
  cleanup.level = filters.level
  cleanup.keyword = filters.keyword
  cleanupTimeRange.value = [...(timeRange.value || [])]
  cleanupVisible.value = true
}

async function confirmCleanup() {
  const payload = buildParams(cleanup, cleanupTimeRange.value)
  await ElMessageBox.confirm('确认按照当前条件清理日志？该操作不可撤销。', '确认清理', {
    type: 'warning',
    confirmButtonText: '清理',
    cancelButtonText: '取消'
  })
  cleanupLoading.value = true
  try {
    const data = await logApi.cleanup(payload)
    ElMessage.success(`已清理 ${data.total || 0} 条日志`)
    cleanupVisible.value = false
    reloadFirstPage()
  } catch (error) {
    ElMessage.error(error.message || '日志清理失败')
  } finally {
    cleanupLoading.value = false
  }
}

function exportLogs() {
  const data = JSON.stringify(logs.value, null, 2)
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `system_logs_${new Date().toLocaleDateString()}.json`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
  ElMessage.success('日志已导出')
}

function sourceLabel(source) {
  return { operation: '操作', device: '设备', access: '门禁', vision: '视觉' }[source] || source
}

function sourceTag(source) {
  return { operation: 'info', device: 'success', access: 'warning', vision: 'danger' }[source] || 'info'
}

function getTypeLabel(type) {
  return typeMap[type]?.label || type
}

function getTypeTagColor(type) {
  return typeMap[type]?.color || 'info'
}

function levelLabel(level) {
  return { info: '信息', warning: '警告', error: '错误' }[level] || level
}

function levelTag(level) {
  return { info: 'info', warning: 'warning', error: 'danger' }[level] || 'info'
}

function timelineType(level) {
  return level === 'error' ? 'danger' : level === 'warning' ? 'warning' : 'primary'
}

function getLogIcon(type) {
  return {
    door: 'Lock',
    window: 'Picture',
    light: 'Sunset',
    fan: 'Refresh',
    face: 'User',
    yolo: 'View',
    settings: 'Setting',
    person: 'User',
    device: 'Operation',
    auth: 'Key',
    logs: 'Document'
  }[type] || 'InfoFilled'
}

function formatTime(ts) {
  return new Date(ts).toLocaleString('zh-CN')
}

onMounted(loadLogs)
</script>

<style scoped>
.logs-page {
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
.filter-left, .filter-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.log-card {
  max-height: 600px;
  overflow-y: auto;
}
.log-entry {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.log-message {
  font-size: 14px;
}
.log-entry.log-error .log-message {
  color: var(--danger);
  font-weight: 600;
}
.log-entry.log-warning .log-message {
  color: var(--warning);
}
.log-type-tag, .log-level-tag {
  flex-shrink: 0;
}
.cleanup-form {
  margin-top: 16px;
}
.cleanup-form :deep(.el-select),
.cleanup-form :deep(.el-date-editor),
.cleanup-form :deep(.el-input) {
  width: 100%;
}

@media (max-width: 768px) {
  .filter-bar { flex-direction: column; align-items: stretch; }
  .filter-left { flex-direction: column; }
  .filter-left .el-select,
  .filter-left .el-input,
  .filter-left :deep(.el-date-editor) { width: 100% !important; }
}
</style>
