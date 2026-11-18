<template>
  <div class="assistant-page">
    <aside class="conversation-panel">
      <div class="panel-top">
        <el-button type="primary" :icon="Plus" @click="newConversation">新对话</el-button>
      </div>
      <div class="conversation-list">
        <div
          v-for="item in conversations"
          :key="item.id"
          class="conversation-item"
          :class="{ active: item.id === activeConversationId }"
        >
          <button class="conversation-main" @click="selectConversation(item.id)">
            <span>{{ item.title }}</span>
            <small>{{ item.message_count || item.messages?.length || 0 }} 条消息</small>
          </button>
          <div class="conversation-actions">
            <el-button text :icon="EditPen" aria-label="重命名对话" @click.stop="renameConversation(item)" />
            <el-button text :icon="Delete" aria-label="删除对话" @click.stop="removeConversation(item)" />
          </div>
        </div>
      </div>
      <div class="agent-status" :class="{ ready: apiKeyConfigured }">
        {{ apiKeyConfigured ? `已配置 ${settings.model}` : '未配置 API Key' }}
      </div>
    </aside>

    <section class="chat-shell">
      <header class="chat-header">
        <div>
          <h2>智能助手</h2>
          <p>流式对话模式，对话记录保存到后端。</p>
        </div>
      </header>

      <main ref="messageListRef" class="message-list">
        <div v-if="!messages.length" class="empty-state">
          <h3>开始一次新的对话</h3>
          <p>让Agent帮你管理家居。试试：目前有几个授权人员？</p>
        </div>
        <div v-for="message in messages" :key="message.id" class="message-row" :class="message.role">
          <div class="avatar" :class="message.role">
            <UserFilled v-if="message.role === 'user'" />
            <Service v-else />
          </div>
          <div class="message-bubble">
            <div v-for="(status, index) in message.toolStatuses" :key="index" class="tool-status">{{ status.text }}</div>
            <div v-if="message.role === 'assistant'" class="message-content markdown-content"
              v-html="renderMarkdown(message.content || (sending ? '正在思考...' : ''))"></div>
            <div v-else class="message-content">{{ message.content }}</div>
            <div class="message-time">{{ message.createdAt }}</div>
          </div>
        </div>
      </main>

      <footer class="composer">
        <el-input
          v-model="draft"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          resize="none"
          placeholder="输入消息，Enter 发送，Shift + Enter 换行"
          @keydown="onComposerKeydown"
        />
        <el-button type="primary" :icon="Promotion" :disabled="!draft.trim() || sending" :loading="sending" @click="sendMessage">
          发送
        </el-button>
      </footer>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, EditPen, Plus, Promotion, Service, UserFilled } from '@element-plus/icons-vue'
import { agentApi } from '../utils/http'
import { renderMarkdown } from '../utils/markdown'

const sending = ref(false)
const draft = ref('')
const messageListRef = ref(null)
const settings = ref({ model: 'deepseek-v4-pro', api_key_configured: false })
const activeConversationId = ref('')
const conversations = ref([])

const activeConversation = computed(() => conversations.value.find(item => item.id === activeConversationId.value))
const messages = computed(() => activeConversation.value?.messages || [])
const apiKeyConfigured = computed(() => Boolean(settings.value.api_key_configured))

onMounted(async () => {
  await Promise.all([loadSettings(), loadConversations()])
  if (!conversations.value.length) newConversation()
})

async function loadSettings() {
  try {
    settings.value = await agentApi.settings()
  } catch (error) {
    ElMessage.error(`读取 Agent 配置失败：${error.message}`)
  }
}

async function loadConversations() {
  try {
    conversations.value = await agentApi.conversations()
    if (!activeConversationId.value && conversations.value.length) {
      await selectConversation(conversations.value[0].id)
    }
  } catch (error) {
    ElMessage.error(`读取对话记录失败：${error.message}`)
  }
}

function newConversation() {
  const conversation = {
    id: `local-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    title: '新对话',
    message_count: 0,
    messages: []
  }
  conversations.value.unshift(conversation)
  activeConversationId.value = conversation.id
  draft.value = ''
}

async function selectConversation(id) {
  if (sending.value) return
  activeConversationId.value = id
  const conversation = conversations.value.find(item => item.id === id)
  if (!conversation || conversation.messages) return
  try {
    const data = await agentApi.conversation(id)
    conversation.title = data.title || conversation.title
    conversation.message_count = data.messages?.length || 0
    conversation.messages = (data.messages || []).map((message, index) => createMessage(
      message.role,
      message.content,
      message.created_at ? new Date(message.created_at).toLocaleTimeString('zh-CN', { hour12: false }) : undefined,
      `${id}-${index}`
    ))
    await scrollToBottom()
  } catch (error) {
    ElMessage.error(`读取对话失败：${error.message}`)
  }
}

async function renameConversation(item) {
  if (sending.value || item.id.startsWith('local-')) {
    ElMessage.info('新对话发送第一条消息后才能重命名')
    return
  }
  try {
    const { value } = await ElMessageBox.prompt('请输入新的会话名称', '重命名对话', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: item.title,
      inputPattern: /\S/,
      inputErrorMessage: '会话名称不能为空'
    })
    const data = await agentApi.updateConversation(item.id, { title: value.trim() })
    item.title = data.title
    item.updated_at = data.updated_at
    ElMessage.success('会话名称已更新')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(`重命名失败：${error.message || error}`)
  }
}

async function removeConversation(item) {
  if (sending.value) return
  try {
    await ElMessageBox.confirm(`确认删除“${item.title}”？`, '删除对话', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
    if (!item.id.startsWith('local-')) {
      await agentApi.deleteConversation(item.id)
    }
    const index = conversations.value.findIndex(conversation => conversation.id === item.id)
    if (index >= 0) conversations.value.splice(index, 1)
    if (activeConversationId.value === item.id) {
      if (conversations.value.length) await selectConversation(conversations.value[0].id)
      else newConversation()
    }
    ElMessage.success('对话已删除')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(`删除失败：${error.message || error}`)
  }
}

function onComposerKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

async function sendMessage() {
  const content = draft.value.trim()
  if (!content || sending.value) return
  if (!apiKeyConfigured.value) {
    ElMessage.warning('请先在系统配置中填写 Agent API Key')
    return
  }
  const conversation = activeConversation.value
  if (!conversation) return
  const userMessage = createMessage('user', content)
  conversation.messages.push(userMessage)
  if (conversation.title === '新对话') {
    conversation.title = content.slice(0, 20)
  }
  conversation.message_count = conversation.messages.length
  draft.value = ''
  sending.value = true
  const assistantMessage = createMessage('assistant', '')
  conversation.messages.push(assistantMessage)
  conversation.message_count = conversation.messages.length
  await scrollToBottom()
  try {
    await runAssistantStream(conversation, assistantMessage)
  } catch (error) {
    assistantMessage.content = appendStatusLine(assistantMessage.content, `请求失败：${error.message}`)
  } finally {
    conversation.message_count = conversation.messages.length
    sending.value = false
    await scrollToBottom()
  }
}

async function runAssistantStream(conversation, assistantMessage, extraPayload = {}) {
  let pendingConfirmation = null
  let pendingClientTool = null
  const payload = buildChatPayload(conversation, assistantMessage, extraPayload)
  await agentApi.streamChat(payload, async (event) => {
    if (event.type === 'delta') {
      assistantMessage.content += event.content || ''
      await scrollToBottom()
    } else if (event.type === 'tool') {
      const label = event.status === 'running' ? '正在执行' : event.status === 'failed' ? '执行失败' : '已完成'
      const status = { name: event.name, text: `${label}：${event.description}` }
      const previous = assistantMessage.toolStatuses.findLastIndex(item => item.name === event.name)
      if (event.status !== 'running' && previous >= 0) assistantMessage.toolStatuses[previous] = status
      else assistantMessage.toolStatuses.push(status)
      await scrollToBottom()
    } else if (event.type === 'confirm_required') {
      pendingConfirmation = event.tool
      assistantMessage.content = appendStatusLine(assistantMessage.content, event.message || `危险操作需要确认：${event.tool?.description || ''}`)
      await scrollToBottom()
    } else if (event.type === 'client_tool_request') {
      pendingClientTool = event.tool
      assistantMessage.content = appendStatusLine(assistantMessage.content, `正在执行本地操作：${event.tool?.description || ''}`)
      await scrollToBottom()
    } else if (event.type === 'done' && event.conversation) {
      conversation.id = event.conversation.id
      conversation.title = event.conversation.title || conversation.title
      activeConversationId.value = conversation.id
    }
  })
  if (!pendingConfirmation && !pendingClientTool && !assistantMessage.content.trim()) {
    throw new Error('模型未返回回复正文，请检查网络认证、模型配置或最大 Token 限制后重试')
  }
  if (pendingConfirmation) {
    await confirmDangerousTool(conversation, assistantMessage, pendingConfirmation)
  }
  if (pendingClientTool) {
    await runClientTool(conversation, assistantMessage, pendingClientTool)
  }
}

function buildChatPayload(conversation, assistantMessage, extraPayload = {}) {
  const payloadMessages = conversation.messages
    .filter(item => item.id !== assistantMessage.id)
    .filter(item => (item.role === 'user' || item.role === 'assistant') && item.content.trim())
    .map(item => ({ role: item.role, content: item.content }))
  return {
    conversation_id: conversation.id.startsWith('local-') ? null : conversation.id,
    title: conversation.title,
    messages: payloadMessages,
    ...extraPayload
  }
}

async function confirmDangerousTool(conversation, assistantMessage, tool) {
  try {
    await ElMessageBox.confirm(tool.description || '确认执行危险操作？', '危险操作确认', {
      type: 'warning',
      confirmButtonText: '确认执行',
      cancelButtonText: '取消'
    })
  } catch (error) {
    assistantMessage.content = appendStatusLine(assistantMessage.content, '用户已取消，危险操作未执行。')
    if (error !== 'cancel' && error !== 'close') ElMessage.error(`确认处理失败：${error.message || error}`)
    return
  }
  assistantMessage.content = appendStatusLine(assistantMessage.content, '用户已确认，继续执行危险操作。')
  await runAssistantStream(conversation, assistantMessage, { confirmed_tool: { name: tool.name, arguments: tool.arguments || {} } })
}

async function runClientTool(conversation, assistantMessage, tool) {
  const result = executeClientTool(tool)
  assistantMessage.content = appendStatusLine(assistantMessage.content, result.ok ? '本地操作已完成。' : `本地操作失败：${result.error}`)
  await runAssistantStream(conversation, assistantMessage, {
    client_tool_result: {
      name: tool.name,
      arguments: tool.arguments || {},
      result
    }
  })
}

function executeClientTool(tool) {
  if (tool.name !== 'set_theme') return { ok: false, error: `不支持的本地工具：${tool.name}` }
  const theme = tool.arguments?.theme
  if (theme !== 'light' && theme !== 'dark') return { ok: false, error: '主题只能是 light 或 dark' }
  document.documentElement.classList.toggle('dark', theme === 'dark')
  localStorage.setItem('theme', theme)
  window.dispatchEvent(new CustomEvent('theme-change', { detail: { theme } }))
  return { ok: true, theme }
}

function appendStatusLine(content, line) {
  const prefix = content ? `${content.trimEnd()}\n\n` : ''
  return `${prefix}${line}\n\n`
}

function createMessage(role, content, createdAt, id) {
  return {
    id: id || `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    toolStatuses: [],
    createdAt: createdAt || new Date().toLocaleTimeString('zh-CN', { hour12: false })
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}
</script>

<style scoped>
.assistant-page {
  height: calc(100vh - 104px);
  min-height: 620px;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 16px;
  overflow: hidden;
}
.conversation-panel,
.chat-shell {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}
.conversation-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.panel-top {
  padding: 14px;
  border-bottom: 1px solid var(--border-color);
}
.panel-top .el-button {
  width: 100%;
}
.conversation-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 8px;
}
.conversation-item {
  width: 100%;
  border: none;
  background: transparent;
  color: var(--text-primary);
  border-radius: 8px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 4px;
}
.conversation-item:hover,
.conversation-item.active {
  background: var(--hover-bg);
}
.conversation-main {
  min-width: 0;
  border: none;
  background: transparent;
  color: inherit;
  padding: 10px;
  text-align: left;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.conversation-main span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conversation-main small,
.agent-status {
  color: var(--text-secondary);
  font-size: 12px;
}
.conversation-actions {
  display: flex;
  opacity: 0;
  padding-right: 4px;
}
.conversation-item:hover .conversation-actions,
.conversation-item.active .conversation-actions {
  opacity: 1;
}
.conversation-actions .el-button {
  width: 26px;
  height: 26px;
  padding: 0;
}
.agent-status {
  padding: 12px 14px;
  border-top: 1px solid var(--border-color);
}
.agent-status.ready {
  color: #67c23a;
}
.chat-shell {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.chat-header {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}
.chat-header h2 {
  margin: 0 0 4px;
  font-size: 20px;
}
.chat-header p {
  margin: 0;
  color: var(--text-secondary);
}
.message-list {
  overflow: auto;
  padding: 24px;
  min-height: 0;
}
.empty-state {
  height: 100%;
  min-height: 280px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  color: var(--text-secondary);
}
.empty-state h3 {
  margin: 0 0 8px;
  color: var(--text-primary);
}
.message-row {
  display: grid;
  grid-template-columns: 34px minmax(0, 760px);
  gap: 10px;
  margin-bottom: 18px;
}
.message-row.user {
  grid-template-columns: minmax(0, 760px) 34px;
  justify-content: end;
}
.message-row.user .avatar {
  grid-column: 2;
  grid-row: 1;
  background: #409eff;
}
.message-row.user .message-bubble {
  grid-column: 1;
  grid-row: 1;
  background: rgba(64, 158, 255, 0.12);
}
.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: #303133;
  color: #fff;
  font-size: 18px;
  font-weight: 700;
}
.avatar.assistant {
  background: #67c23a;
}
.avatar.user {
  background: #409eff;
}
.message-bubble {
  padding: 12px 14px;
  border-radius: 8px;
  background: var(--hover-bg);
  color: var(--text-primary);
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}
.message-bubble.pending {
  color: var(--text-secondary);
}
.tool-status {
  color: var(--text-secondary);
  font-size: 12px;
  white-space: normal;
  margin-bottom: 6px;
}
.markdown-content {
  white-space: normal;
  overflow-wrap: anywhere;
}
.markdown-content :deep(> :first-child) { margin-top: 0; }
.markdown-content :deep(> :last-child) { margin-bottom: 0; }
.markdown-content :deep(p) { margin: 0 0 10px; }
.markdown-content :deep(h1), .markdown-content :deep(h2), .markdown-content :deep(h3) {
  margin: 16px 0 8px;
  line-height: 1.4;
  font-size: 1.15em;
}
.markdown-content :deep(ul), .markdown-content :deep(ol) { padding-left: 24px; margin: 8px 0; }
.markdown-content :deep(pre) {
  padding: 12px;
  border-radius: 6px;
  background: var(--bg-primary);
  overflow-x: auto;
  white-space: pre;
}
.markdown-content :deep(code) {
  font-family: Consolas, monospace;
  background: var(--bg-primary);
  border-radius: 3px;
  padding: 2px 4px;
}
.markdown-content :deep(pre code) { padding: 0; }
.markdown-content :deep(table) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
  border-collapse: collapse;
  margin: 10px 0;
}
.markdown-content :deep(th), .markdown-content :deep(td) {
  padding: 6px 10px;
  border: 1px solid var(--border-color);
  text-align: left;
}
.markdown-content :deep(blockquote) {
  border-left: 3px solid var(--border-color);
  padding-left: 12px;
  margin: 10px 0;
  color: var(--text-secondary);
}
.markdown-content :deep(a) { color: var(--primary-color, #409eff); }
.message-time {
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}
.composer {
  padding: 14px;
  border-top: 1px solid var(--border-color);
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: end;
}

@media (max-width: 900px) {
  .assistant-page {
    height: auto;
    grid-template-columns: 1fr;
  }
  .conversation-panel {
    min-height: 180px;
  }
  .chat-shell {
    min-height: 620px;
  }
}
</style>
