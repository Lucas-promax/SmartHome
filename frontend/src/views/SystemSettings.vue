<template>
  <div class="settings-page">
    <div class="page-header">
      <div>
        <h2>系统配置</h2>
        <p>配置首页告警和智能助手参数，保存后会写入后端数据库。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="loadSettings">刷新</el-button>
    </div>

    <HardwareSettings />
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="150px"
      class="settings-form"
    >
      <section class="settings-section">
        <div class="section-title">横幅告警</div>
        <el-form-item label="启用上方横幅">
          <el-switch
            v-model="form.banner_enabled"
            active-text="开启"
            inactive-text="关闭"
          />
        </el-form-item>
        <el-form-item label="横幅滞留时间" prop="banner_stay_seconds">
          <el-input-number v-model="form.banner_stay_seconds" :min="1" :max="3600" :step="1" controls-position="right" />
          <span class="unit">秒</span>
        </el-form-item>
      </section>

      <section class="settings-section">
        <!-- 温湿度阈值仅控制网页提醒，不修改 Arduino 的风扇温控阈值。 -->
        <div class="section-title">温湿度告警阈值</div>
        <el-row :gutter="16">
          <el-col :xs="24" :sm="12">
            <el-form-item label="温度过高阈值" prop="temperature_high">
              <el-input-number v-model="form.temperature_high" :min="-50" :max="80" :step="0.5" controls-position="right" />
              <span class="unit">°C</span>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="温度过低阈值" prop="temperature_low">
              <el-input-number v-model="form.temperature_low" :min="-50" :max="80" :step="0.5" controls-position="right" />
              <span class="unit">°C</span>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="湿度过高阈值" prop="humidity_high">
              <el-input-number v-model="form.humidity_high" :min="0" :max="100" :step="1" controls-position="right" />
              <span class="unit">%</span>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="湿度过低阈值" prop="humidity_low">
              <el-input-number v-model="form.humidity_low" :min="0" :max="100" :step="1" controls-position="right" />
              <span class="unit">%</span>
            </el-form-item>
          </el-col>
        </el-row>
      </section>

      <section class="settings-section">
        <!-- 主门超时时间仅控制网页提醒，不发送关门指令。 -->
        <div class="section-title">主门打开超时提醒</div>
        <el-form-item label="超时提醒时间" prop="door_open_seconds">
          <el-input-number v-model="form.door_open_seconds" :min="10" :max="86400" :step="10" controls-position="right" />
          <span class="unit">秒</span>
        </el-form-item>
      </section>

      <section class="settings-section">
        <div class="section-title">智能助手 Agent</div>
        <el-alert
          v-if="agentForm.api_key_configured"
          title="API Key 已配置，留空保存时会继续沿用原 Key。"
          type="success"
          :closable="false"
          class="agent-alert"
        />
        <el-form-item label="API Key">
          <el-input v-model="agentForm.api_key" type="password" show-password placeholder="sk-..." autocomplete="off" />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="agentForm.base_url" placeholder="https://api.deepseek.com" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :xs="24" :sm="12">
            <el-form-item label="模型">
              <el-input v-model="agentForm.model" placeholder="deepseek-v4-pro" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="Max Tokens">
              <el-input-number v-model="agentForm.max_tokens" :min="1" :max="32000" :step="256" controls-position="right" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="对话轮次上限">
              <el-input-number v-model="agentForm.max_rounds" :min="1" :max="100" :step="1" controls-position="right" />
              <span class="unit">轮</span>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="Temperature">
              <el-slider v-model="agentForm.temperature" :min="0" :max="2" :step="0.1" show-input />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="Top P">
              <el-slider v-model="agentForm.top_p" :min="0" :max="1" :step="0.05" show-input />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="Presence Penalty">
              <el-slider v-model="agentForm.presence_penalty" :min="-2" :max="2" :step="0.1" show-input />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="Frequency Penalty">
              <el-slider v-model="agentForm.frequency_penalty" :min="-2" :max="2" :step="0.1" show-input />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="Reasoning Effort">
              <el-select v-model="agentForm.reasoning_effort" clearable placeholder="默认">
                <el-option label="默认" value="" />
                <el-option label="low" value="low" />
                <el-option label="medium" value="medium" />
                <el-option label="high" value="high" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="启用 Thinking">
              <el-switch v-model="agentForm.thinking_enabled" active-text="开启" inactive-text="关闭" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="请求超时">
              <el-input-number v-model="agentForm.timeout_seconds" :min="5" :max="300" :step="5" controls-position="right" />
              <span class="unit">秒</span>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="系统提示词">
          <el-input v-model="agentForm.system_prompt" type="textarea" :rows="4" resize="none" />
        </el-form-item>
      </section>

      <div class="form-actions">
        <el-button @click="resetDefaults">恢复默认值</el-button>
        <el-button type="primary" :icon="Check" :loading="saving" @click="saveSettings">保存配置</el-button>
      </div>
    </el-form>
  </div>
</template>

<script setup>
import HardwareSettings from '../components/HardwareSettings.vue'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Refresh } from '@element-plus/icons-vue'
import { agentApi, settingsApi } from '../utils/http'

const DEFAULTS = {
  banner_enabled: true,
  banner_stay_seconds: 5,
  temperature_high: 30,
  temperature_low: 16,
  humidity_high: 75,
  humidity_low: 30,
  door_open_seconds: 300
}

const formRef = ref(null)
const loading = ref(false)
const saving = ref(false)
const form = reactive({ ...DEFAULTS })
const agentForm = reactive({
  api_key: '',
  api_key_configured: false,
  base_url: 'https://api.deepseek.com',
  model: 'deepseek-v4-pro',
  max_tokens: 1024,
  max_rounds: 15,
  temperature: 0.7,
  top_p: 1,
  presence_penalty: 0,
  frequency_penalty: 0,
  reasoning_effort: 'high',
  thinking_enabled: true,
  timeout_seconds: 60,
  system_prompt: '你是智能家居系统助手。回答要简洁、准确，优先帮助用户理解系统状态、日志、设备和配置。'
})

const rules = {
  temperature_high: [{ validator: validateTemperature, trigger: 'change' }],
  temperature_low: [{ validator: validateTemperature, trigger: 'change' }],
  humidity_high: [{ validator: validateHumidity, trigger: 'change' }],
  humidity_low: [{ validator: validateHumidity, trigger: 'change' }]
}

onMounted(loadSettings)

async function loadSettings() {
  loading.value = true
  try {
    const [data, agentData] = await Promise.all([
      settingsApi.getAlertSettings(),
      agentApi.settings()
    ])
    Object.assign(form, {
      banner_enabled: data.banner_enabled,
      banner_stay_seconds: data.banner_stay_seconds || 5,
      temperature_high: data.temperature_high,
      temperature_low: data.temperature_low,
      humidity_high: data.humidity_high,
      humidity_low: data.humidity_low,
      door_open_seconds: Math.max(10, data.door_open_seconds || 300)
    })
    Object.assign(agentForm, {
      api_key: '',
      api_key_configured: Boolean(agentData.api_key_configured),
      base_url: agentData.base_url || 'https://api.deepseek.com',
      model: agentData.model || 'deepseek-v4-pro',
      max_tokens: agentData.max_tokens || 1024,
      max_rounds: agentData.max_rounds || 15,
      temperature: agentData.temperature ?? 0.7,
      top_p: agentData.top_p ?? 1,
      presence_penalty: agentData.presence_penalty ?? 0,
      frequency_penalty: agentData.frequency_penalty ?? 0,
      reasoning_effort: agentData.reasoning_effort || '',
      thinking_enabled: Boolean(agentData.thinking_enabled),
      timeout_seconds: agentData.timeout_seconds || 60,
      system_prompt: agentData.system_prompt || ''
    })
  } catch (error) {
    ElMessage.error(`读取配置失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  await formRef.value?.validate()
  saving.value = true
  try {
    await settingsApi.updateAlertSettings({
      banner_enabled: form.banner_enabled,
      temperature_high: form.temperature_high,
      temperature_low: form.temperature_low,
      humidity_high: form.humidity_high,
      humidity_low: form.humidity_low,
      banner_stay_seconds: form.banner_stay_seconds,
      door_open_seconds: form.door_open_seconds
    })
    const agentData = await agentApi.updateSettings({
      api_key: agentForm.api_key,
      base_url: agentForm.base_url,
      model: agentForm.model,
      max_tokens: agentForm.max_tokens,
      max_rounds: agentForm.max_rounds,
      temperature: agentForm.temperature,
      top_p: agentForm.top_p,
      presence_penalty: agentForm.presence_penalty,
      frequency_penalty: agentForm.frequency_penalty,
      reasoning_effort: agentForm.reasoning_effort,
      thinking_enabled: agentForm.thinking_enabled,
      timeout_seconds: agentForm.timeout_seconds,
      system_prompt: agentForm.system_prompt
    })
    agentForm.api_key = ''
    agentForm.api_key_configured = Boolean(agentData.api_key_configured)
    ElMessage.success('配置已保存')
  } catch (error) {
    ElMessage.error(`保存配置失败：${error.message}`)
  } finally {
    saving.value = false
  }
}

function resetDefaults() {
  const apiKeyConfigured = agentForm.api_key_configured
  Object.assign(form, DEFAULTS)
  Object.assign(agentForm, {
    api_key: '',
    api_key_configured: apiKeyConfigured,
    base_url: 'https://api.deepseek.com',
    model: 'deepseek-v4-pro',
    max_tokens: 1024,
    max_rounds: 15,
    temperature: 0.7,
    top_p: 1,
    presence_penalty: 0,
    frequency_penalty: 0,
    reasoning_effort: 'high',
    thinking_enabled: true,
    timeout_seconds: 60,
    system_prompt: '你是智能家居系统助手。回答要简洁、准确，优先帮助用户理解系统状态、日志、设备和配置。'
  })
}

function validateTemperature(rule, value, callback) {
  if (form.temperature_low >= form.temperature_high) {
    callback(new Error('温度下限必须小于温度上限'))
    return
  }
  callback()
}

function validateHumidity(rule, value, callback) {
  if (form.humidity_low >= form.humidity_high) {
    callback(new Error('湿度下限必须小于湿度上限'))
    return
  }
  callback()
}
</script>

<style scoped>
.settings-page {
  max-width: 980px;
  margin: 0 auto;
  padding-bottom: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 18px;
}

.page-header h2 {
  margin: 0 0 6px;
  font-size: 22px;
  color: var(--text-primary);
}

.page-header p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
}

.settings-form {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 18px;
}

.settings-section {
  padding: 14px 0;
  border-bottom: 1px solid var(--border-color);
}

.settings-section:last-of-type {
  border-bottom: none;
}

.section-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 14px;
}

.unit {
  margin-left: 8px;
  color: var(--text-secondary);
}

.agent-alert {
  margin-bottom: 14px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}

@media (max-width: 767px) {
  .page-header {
    flex-direction: column;
  }

  .settings-form {
    padding: 14px;
  }

  .form-actions {
    flex-direction: column;
  }
}
</style>
