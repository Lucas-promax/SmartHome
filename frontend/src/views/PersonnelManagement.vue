<!--
  PersonnelManagement.vue - 授权人员管理页面
  人员列表表格 + 新增授权人员弹窗(上传人脸图片)
-->
<template>
  <div class="page-container personnel-page">
    <h2 class="page-title">
      <el-icon><User /></el-icon>
      授权人员管理
      <el-tag size="small" type="info" effect="plain" style="margin-left:8px;">
        共 {{ personnel.length }} 人
      </el-tag>
    </h2>

    <!-- 操作栏 -->
    <div class="dashboard-card action-bar">
      <el-button type="primary" @click="showAddDialog = true">
        <el-icon><Plus /></el-icon>
        新增授权人员
      </el-button>
      <el-button :loading="loading" @click="loadPersonnel">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
      <el-input
        v-model="searchQuery"
        placeholder="搜索姓名..."
        clearable
        style="width: 200px;"
        :prefix-icon="Search"
      />
    </div>

    <!-- 人员列表表格 -->
    <div class="dashboard-card table-card">
      <el-table
        :data="filteredPersonnel"
        stripe
        style="width: 100%"
        :default-sort="{ prop: 'createdAt', order: 'descending' }"
      >
        <el-table-column label="人脸预览" width="100">
          <template #default="{ row }">
            <el-avatar :src="faceImageUrl(row)" :size="50" shape="square" />
          </template>
        </el-table-column>
        <el-table-column prop="name" label="姓名" width="120" sortable />
        <el-table-column label="角色" width="110">
          <template #default="{ row }">
            <el-tag :type="roleTagType(row.role)">{{ roleText(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="授权状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.authorized ? 'success' : 'danger'" effect="dark">
              {{ row.authorized ? '有权限' : '无权限' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="录入时间" sortable min-width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="权限操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!row.authorized"
              type="success"
              size="small"
              text
              @click="restorePerson(row.id)"
            >
              <el-icon><CircleCheck /></el-icon>
              恢复授权
            </el-button>
            <el-popconfirm
              title="确定撤销该人员的门禁授权？照片和数据库记录会保留。"
              confirm-button-text="确定"
              cancel-button-text="取消"
              @confirm="revokePerson(row.id)"
            >
              <template #reference>
                <el-button type="danger" size="small" text :disabled="!row.authorized">
                  <el-icon><Delete /></el-icon>
                  撤销授权
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
        <el-table-column label="删除" width="110" fixed="right">
          <template #default="{ row }">
            <el-popconfirm
              title="确定删除该人员？数据库记录和已录入照片都会删除。"
              confirm-button-text="确定删除"
              cancel-button-text="取消"
              @confirm="deletePerson(row.id)"
            >
              <template #reference>
                <el-button type="danger" size="small" text>
                  <el-icon><Delete /></el-icon>
                  删除人员
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="filteredPersonnel.length === 0" description="暂无授权人员" />
    </div>

    <!-- 新增授权人员弹窗 -->
    <el-dialog
      v-model="showAddDialog"
      title="新增授权人员"
      width="460px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="addForm"
        :rules="formRules"
        label-width="80px"
        @submit.prevent
      >
        <el-form-item label="姓名" prop="name">
          <el-input v-model="addForm.name" placeholder="请输入姓名" maxlength="20" show-word-limit />
        </el-form-item>

        <el-form-item label="角色" prop="role">
          <el-select v-model="addForm.role" style="width: 100%;">
            <el-option label="住户" value="resident" />
            <el-option label="访客" value="guest" />
          </el-select>
        </el-form-item>

        <el-form-item label="人脸照片" prop="faceImage">
          <el-upload
            class="face-upload"
            :auto-upload="false"
            :limit="1"
            :on-change="onFileChange"
            :on-remove="onFileRemove"
            :file-list="fileList"
            list-type="picture-card"
            accept="image/*"
          >
            <el-icon><Plus /></el-icon>
          </el-upload>
          <template #extra>
            <span class="upload-tip">支持 JPG/PNG 格式，建议正面清晰人脸照</span>
          </template>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="submitAddPerson" :loading="submitting">
          <el-icon><Check /></el-icon>
          确认录入
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus, Delete, Check, Search, Refresh, CircleCheck } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { apiUrl, personnelApi } from '../utils/http'

// 人员列表
const personnel = ref([])
const searchQuery = ref('')
const loading = ref(false)

// 搜索过滤
const filteredPersonnel = computed(() => {
  if (!searchQuery.value) return personnel.value
  const q = searchQuery.value.toLowerCase()
  return personnel.value.filter(p => p.name.toLowerCase().includes(q))
})

// 新增弹窗
const showAddDialog = ref(false)
const submitting = ref(false)
const formRef = ref(null)
const fileList = ref([])

const addForm = reactive({
  name: '',
  role: 'resident',
  faceImage: null
})

const formRules = {
  name: [
    { required: true, message: '请输入姓名', trigger: 'blur' },
    { min: 1, max: 20, message: '姓名长度 1~20', trigger: 'blur' }
  ],
  faceImage: [
    { required: true, message: '请上传人脸照片', trigger: 'change' }
  ]
}

onMounted(loadPersonnel)

async function loadPersonnel() {
  loading.value = true
  try {
    personnel.value = await personnelApi.list()
  } catch (e) {
    ElMessage.error('加载授权人员失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function resetAddForm() {
  addForm.name = ''
  addForm.role = 'resident'
  addForm.faceImage = null
  fileList.value = []
  formRef.value?.clearValidate?.()
}

function onFileChange(file) {
  addForm.faceImage = file.raw
  formRef.value?.validateField('faceImage')
}

function onFileRemove() {
  addForm.faceImage = null
}

async function submitAddPerson() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitting.value = true
  try {
    const formData = new FormData()
    formData.append('name', addForm.name)
    formData.append('role', addForm.role)
    formData.append('enabled', 'true')
    formData.append('file', addForm.faceImage, addForm.faceImage.name || '0.jpg')
    await personnelApi.add(formData)
    ElMessage.success(`已添加授权人员: ${addForm.name}`)
    showAddDialog.value = false
    resetAddForm()
    await loadPersonnel()
  } catch (e) {
    ElMessage.error('添加失败: ' + e.message)
  } finally {
    submitting.value = false
  }
}

async function revokePerson(id) {
  const person = personnel.value.find(p => p.id === id)
  if (!person) return
  try {
    await personnelApi.delete(id)
    ElMessage.success(`已撤销授权: ${person.name}`)
    await loadPersonnel()
  } catch (e) {
    ElMessage.error('撤销授权失败: ' + e.message)
  }
}

async function deletePerson(id) {
  const person = personnel.value.find(p => p.id === id)
  if (!person) return
  try {
    await personnelApi.hardDelete(id)
    ElMessage.success(`已删除人员: ${person.name}`)
    await loadPersonnel()
  } catch (e) {
    ElMessage.error('删除人员失败: ' + e.message)
  }
}

async function restorePerson(id) {
  const person = personnel.value.find(p => p.id === id)
  if (!person) return
  try {
    await personnelApi.restore(id, 'resident')
    ElMessage.success(`已恢复授权: ${person.name}`)
    await loadPersonnel()
  } catch (e) {
    ElMessage.error('恢复授权失败: ' + e.message)
  }
}

function faceImageUrl(row) {
  return row.face_image_url ? apiUrl(row.face_image_url) : ''
}

function roleText(role) {
  const map = { resident: '住户', guest: '访客', blocked: '无权限' }
  return map[role] || role || '-'
}

function roleTagType(role) {
  if (role === 'resident') return 'success'
  if (role === 'guest') return 'warning'
  return 'danger'
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}
</script>

<style scoped>
.personnel-page {
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
.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.table-card {
  padding: 0;
  overflow: hidden;
}
.face-upload :deep(.el-upload--picture-card) {
  width: 100px;
  height: 100px;
}
.upload-tip {
  font-size: 11px;
  color: var(--text-muted);
}

@media (max-width: 768px) {
  .action-bar .el-input { width: 100% !important; }
}
</style>
