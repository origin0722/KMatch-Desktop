<template>
  <div class="assistant-panel">
    <!-- 头部 -->
    <div class="assistant-header">
      <span class="assistant-title">
        <el-icon :size="15"><ChatDotRound /></el-icon>&nbsp;AI 助手
        <el-tag v-if="chat.streaming" type="warning" size="small" class="status-tag">回复中</el-tag>
      </span>
      <div class="header-actions">
        <el-icon class="icon-btn" title="清空对话" @click="chat.clearMessages()" v-if="chat.hasMessages">
          <Delete />
        </el-icon>
        <el-icon class="icon-btn" title="收起" @click="sidebar.toggleAiPanel()"><Close /></el-icon>
      </div>
    </div>

    <!-- 消息列表 -->
    <div ref="msgContainer" class="assistant-body">
      <!-- 空状态 -->
      <div v-if="!chat.hasMessages" class="placeholder">
        <el-icon :size="40" color="var(--ktext-muted)"><ChatLineSquare /></el-icon>
        <p class="ph-title">AI 助手</p>
        <p class="ph-hint">基于 DeepSeek V4 Pro，可阅读项目代码并协助开发</p>
        <div class="ph-features">
          <div class="feat">💬 解释代码逻辑 & 提供改进建议</div>
          <div class="feat">🐛 帮助调试 & 分析错误</div>
          <div class="feat">📝 生成代码片段 & 单元测试</div>
          <div class="feat">📖 解读项目架构 & 依赖关系</div>
        </div>
      </div>

      <!-- 消息列表 -->
      <template v-else>
        <div
          v-for="msg in chat.messages"
          :key="msg.id"
          class="message"
          :class="msg.role"
        >
          <!-- 助手消息: Think 折叠 + Markdown 渲染 -->
          <div v-if="msg.role === 'assistant'" class="msg-body assistant-msg">
            <div class="msg-avatar">
              <el-icon :size="18"><Cpu /></el-icon>
            </div>
            <div class="msg-content">
              <!-- 思考过程 (可折叠) -->
              <div v-if="msg.think || (chat.streaming && chat.currentStreamId === msg.id)" class="think-block">
                <button
                  class="think-toggle"
                  @click="toggleThink(msg.id)"
                >
                  <svg class="think-icon" :class="{ expanded: isThinkExpanded(msg.id) }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <path d="M9 18l6-6-6-6"/>
                  </svg>
                  <span class="think-label" :class="{ breathing: chat.streaming && chat.currentStreamId === msg.id && !msg.content }">
                    {{ chat.streaming && chat.currentStreamId === msg.id
                       ? (msg.content ? '已思考' : '思考中…')
                       : '已思考' }}
                  </span>
                </button>
                <div v-show="isThinkExpanded(msg.id)" class="think-content">
                  <pre>{{ msg.think }}</pre>
                </div>
              </div>
              <!-- 正文 -->
              <MarkdownViewer v-if="msg.content" :content="cleanToolCalls(msg.content)" />
              <span v-else-if="chat.streaming && chat.currentStreamId === msg.id && !msg.think" class="typing">
                <span class="dot"></span><span class="dot"></span><span class="dot"></span>
              </span>
              <span v-else-if="!msg.content" class="empty-msg">—</span>
              <div class="msg-actions" v-if="msg.content && !chat.streaming">
                <el-button size="small" text @click="copyText(msg.content)">复制</el-button>
              </div>
            </div>
          </div>

          <!-- 工具消息: 文件读取/目录列表 -->
          <div v-else-if="msg.role === 'tool'" class="msg-body tool-msg">
            <div class="msg-avatar tool-avatar">
              <el-icon :size="16"><FolderOpened /></el-icon>
            </div>
            <div class="msg-content">
              <div class="tool-header">
                <el-tag size="small" :type="msg.toolResult?.error ? 'danger' : ''">
                  {{ msg.toolCall?.tool || 'tool' }}
                </el-tag>
                <code class="tool-path">{{ msg.toolCall?.path || '' }}</code>
              </div>
              <div v-if="msg.toolResult?.error" class="tool-error">{{ msg.toolResult.error }}</div>
              <div v-else-if="msg.toolResult?.content" class="tool-content">
                <pre><code>{{ msg.toolResult.content.slice(0, 2000) }}</code></pre>
                <span v-if="msg.toolResult.content.length > 2000" class="truncated">… 内容已截断</span>
              </div>
              <div v-else-if="msg.toolResult?.files" class="tool-files">
                <div v-for="f in msg.toolResult.files.slice(0, 20)" :key="f" class="tool-file">
                  {{ f }}
                </div>
              </div>
            </div>
          </div>

          <!-- 用户消息: 纯文本气泡 -->
          <div v-else class="msg-body user-msg">
            <div class="msg-content">
              <pre class="user-text">{{ msg.content }}</pre>
            </div>
          </div>
        </div>

        <!-- 错误提示 -->
        <div v-if="chat.error" class="error-bar">
          <el-icon><WarningFilled /></el-icon> {{ chat.error }}
          <el-button size="small" text @click="chat.error = null">✕</el-button>
        </div>
      </template>
    </div>

    <!-- 输入区 -->
    <div class="assistant-input">
      <el-input
        ref="inputRef"
        v-model="inputText"
        type="textarea"
        :rows="2"
        :disabled="chat.streaming"
        placeholder="输入消息… (Enter 发送, Shift+Enter 换行)"
        resize="none"
        @keydown="onKeydown"
      />
      <div class="input-bar-row">
        <!-- 厂商选择 -->
        <el-select
          :model-value="chat.provider"
          size="small"
          class="provider-select"
          :disabled="chat.streaming"
          @change="onProviderChange"
        >
          <el-option
            v-for="p in chat.PROVIDERS"
            :key="p.id"
            :label="p.label"
            :value="p.id"
          />
        </el-select>
        <!-- API Key -->
        <el-button
          size="small"
          class="apikey-btn"
          :class="{ set: !!chat.apiKey }"
          :title="chat.apiKey ? '已设置 API Key' : '设置 API Key'"
          :disabled="chat.streaming"
          @click="onSetApiKey"
        >
          🔑
        </el-button>
        <!-- 模型 (自动) -->
        <span class="model-hint" :title="'当前模型: ' + (chat.model || '未选择')">
          {{ chat.model || '—' }}
        </span>
        <el-button
          v-if="chat.streaming"
          type="danger"
          size="small"
          plain
          @click="chat.stopStreaming()"
        >
          <el-icon :size="14"><VideoPause /></el-icon>&nbsp;停止
        </el-button>
        <el-button
          v-else
          type="primary"
          size="small"
          :disabled="!inputText.trim()"
          @click="handleSend"
        >
          <el-icon :size="14"><Promotion /></el-icon>&nbsp;发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch, nextTick } from 'vue'
import { Delete, VideoPause, Promotion } from '@element-plus/icons-vue'
import { useSidebarStore } from '@/stores/sidebar'
import { useChatStore } from '@/stores/chat'
import { ElMessage } from 'element-plus'
import MarkdownViewer from '@/components/MarkdownViewer.vue'

const sidebar = useSidebarStore()
const chat = useChatStore()

const inputText = ref('')
const inputRef = ref(null)
const msgContainer = ref(null)

// Think 折叠状态: { [msgId]: boolean }
const thinkExpanded = reactive({})
function isThinkExpanded(msgId) {
  // 流式传输中默认展开
  if (chat.streaming && chat.currentStreamId === msgId) return true
  return !!thinkExpanded[msgId]
}
function toggleThink(msgId) {
  thinkExpanded[msgId] = !thinkExpanded[msgId]
}

// ---------------------------------------------------------------
// 自动滚动到底部
// ---------------------------------------------------------------
function scrollToBottom() {
  if (msgContainer.value) {
    msgContainer.value.scrollTop = msgContainer.value.scrollHeight
  }
}

// 消息变化时滚动
watch(() => chat.messages.length, () => nextTick(scrollToBottom))
// 流式内容更新时滚动
watch(() => {
  const msgs = chat.messages
  if (msgs.length > 0) return msgs[msgs.length - 1].content
  return ''
}, () => nextTick(scrollToBottom))

// ---------------------------------------------------------------
// 发送
// ---------------------------------------------------------------
function handleSend() {
  const text = inputText.value.trim()
  if (!text || chat.streaming) return
  inputText.value = ''
  chat.sendMessage(text)
}

function onProviderChange(val) {
  chat.setProvider(val)
}

async function onSetApiKey() {
  const current = chat.apiKey || ''
  // 使用 prompt 简单获取 (后续可改为 Dialog)
  // eslint-disable-next-line no-alert
  const key = window.prompt('请输入 API Key', current)
  if (key !== null) {
    chat.setApiKey(key.trim())
  }
}

function onKeydown(e) {
  // Enter 发送 (无 Shift)
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

// ---------------------------------------------------------------
// 复制
// ---------------------------------------------------------------
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败')
  }
}

/** 从助手消息中移除 tool_call 代码块 (展示用) */
function cleanToolCalls(content) {
  if (!content) return ''
  return content.replace(/```tool_call\n[\s\S]*?```/g, '')
}
</script>

<style scoped>
.assistant-panel {
  width: 340px;
  background: var(--km-bg-layer-0);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  height: 100%;
  border-left: 1px solid var(--km-border);
}

/* ---- 头部 ---- */
.assistant-header {
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  border-bottom: 1px solid var(--km-border-light);
  flex-shrink: 0;
  background: var(--km-bg-layer-0);
}
.assistant-title {
  display: flex; align-items: center; gap: 7px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--km-gray-600);
  font-weight: 600;
}
.status-tag { margin-left: 4px; }
.header-actions { display: flex; gap: 4px; }
.icon-btn {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 6px;
  cursor: pointer; color: var(--km-gray-500);
  transition: all 0.15s var(--km-ease);
}
.icon-btn:hover { color: var(--km-gray-700); background: var(--km-gray-200); }

/* ---- 消息区域 ---- */
.assistant-body {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  padding: 12px 10px;
  gap: 12px;
}

/* 空状态 */
.placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 28px;
  text-align: center;
}
.ph-title { font-size: 15px; font-weight: 600; color: var(--km-gray-700); margin-top: 8px; }
.ph-hint { font-size: 12px; color: var(--km-gray-500); margin-bottom: 16px; line-height: 1.6; }
.ph-features {
  display: flex; flex-direction: column; gap: 8px;
  width: 100%; text-align: left;
}
.feat {
  font-size: 12px;
  color: var(--km-gray-600);
  background: var(--km-gray-200);
  padding: 10px 14px;
  border-radius: var(--km-radius-sm);
  transition: all 0.2s var(--km-ease);
  cursor: default;
}
.feat:hover {
  background: var(--km-primary-light);
  color: var(--km-primary-active);
}

/* ---- 消息 ---- */
.message {
  display: flex;
  animation: msgIn 0.3s var(--km-ease-out);
}
@keyframes msgIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.msg-body {
  display: flex; gap: 8px;
  max-width: 100%;
}
.msg-body.user-msg { justify-content: flex-end; width: 100%; }

/* 助手消息 */
.assistant-msg { width: 100%; }
.msg-avatar {
  flex-shrink: 0; width: 30px; height: 30px;
  border-radius: var(--km-radius-sm);
  background: var(--km-primary-light);
  display: flex; align-items: center; justify-content: center;
  color: var(--km-primary);
}
/* Think 思考过程 */
.think-block {
  margin-bottom: 10px;
  background: var(--km-gray-100);
  border-radius: var(--km-radius-sm);
  padding: 8px 10px;
}
.think-toggle {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--km-gray-500);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.15s var(--km-ease);
}
.think-toggle:hover { color: var(--km-gray-700); }
.think-icon {
  flex-shrink: 0;
  transition: transform 0.25s var(--km-ease);
}
.think-icon.expanded { transform: rotate(90deg); }
.think-label { white-space: nowrap; }
.think-label.breathing {
  animation: thinkPulse 1.5s ease-in-out infinite;
}
@keyframes thinkPulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}
.think-content {
  margin-top: 6px;
  border-left: 2px solid var(--km-primary);
  padding: 4px 0 4px 12px;
}
.think-content pre {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--km-gray-500);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--km-font-ui);
}

.msg-content {
  flex: 1; min-width: 0;
  font-size: 13px; line-height: 1.65;
  color: var(--km-gray-700);
}
.msg-content :deep(pre) {
  max-height: 200px; overflow-y: auto;
  background: var(--km-bg-layer-2);
}
.msg-content :deep(code) {
  background: var(--km-gray-200);
  color: var(--km-gray-700);
}
.msg-actions {
  margin-top: 4px;
  opacity: 0;
  transition: opacity 0.15s var(--km-ease);
}
.msg-body:hover .msg-actions { opacity: 1; }

/* 用户消息 */
.user-msg .msg-content {
  max-width: 85%;
}
.user-text {
  background: linear-gradient(135deg, var(--km-primary), var(--km-primary-active));
  color: var(--km-primary-text);
  padding: 8px 12px;
  border-radius: 12px 12px 4px 12px;
  font-size: 13px; line-height: 1.5;
  white-space: pre-wrap; word-break: break-word;
  margin: 0;
  font-family: var(--km-font-ui);
  box-shadow: var(--km-shadow-sm);
}

/* 打字动画 */
.typing { display: inline-flex; gap: 4px; padding: 6px 0; }
.typing .dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--km-primary);
  opacity: 0.5;
  animation: bounce 1.2s infinite;
}
.typing .dot:nth-child(2) { animation-delay: 0.2s; }
.typing .dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
  30% { transform: translateY(-6px); opacity: 1; }
}

.empty-msg { color: var(--km-gray-400); }

/* 工具消息 */
.tool-msg { width: 100%; }
.tool-avatar {
  flex-shrink: 0; width: 28px; height: 28px;
  border-radius: 6px; background: var(--km-info-light);
  display: flex; align-items: center; justify-content: center;
  color: var(--km-info);
}
.tool-header {
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 4px;
}
.tool-path {
  font-size: 11px;
  color: var(--km-gray-500);
  background: var(--km-gray-200);
  padding: 1px 6px;
  border-radius: 4px;
}
.tool-content pre {
  background: var(--km-bg-layer-2);
  border-radius: var(--km-radius-sm);
  padding: 8px 12px;
  font-size: 12px;
  max-height: 160px; overflow-y: auto;
}
.tool-error { color: var(--km-danger); font-size: 12px; }
.tool-files { display: flex; flex-wrap: wrap; gap: 4px; }
.tool-file {
  font-size: 11px;
  color: var(--km-gray-600);
  background: var(--km-gray-200);
  padding: 2px 8px;
  border-radius: 4px;
}
.truncated {
  font-size: 11px; color: var(--km-gray-400);
  display: block; margin-top: 4px;
}

/* 错误栏 */
.error-bar {
  display: flex; align-items: center; gap: 6px;
  padding: 10px 14px; border-radius: var(--km-radius-sm);
  background: var(--km-danger-light);
  color: var(--km-danger);
  font-size: 12px;
}

/* ---- 输入区 ---- */
.assistant-input {
  padding: 12px 14px;
  border-top: 1px solid var(--km-border-light);
  flex-shrink: 0;
  background: var(--km-bg-layer-0);
}
.assistant-input :deep(.el-textarea__inner) {
  background: var(--km-bg-layer-2);
  color: var(--km-gray-700);
  border-color: var(--km-border);
  border-radius: var(--km-radius);
  font-size: 13px;
  padding: 10px 12px;
  transition: border-color 0.2s var(--km-ease);
}
.assistant-input :deep(.el-textarea__inner:focus) {
  border-color: var(--km-border-focus);
}
.input-bar-row {
  display: flex;
  align-items: center;
  margin-top: 10px;
  gap: 8px;
}
.input-bar-row > :last-child {
  margin-left: auto;
}
.provider-select {
  width: 120px;
  flex-shrink: 0;
}
.provider-select :deep(.el-input__inner) {
  font-size: 12px;
}
.apikey-btn {
  width: 30px; height: 30px; padding: 0;
  font-size: 15px;
  border-radius: var(--km-radius-sm);
  opacity: 0.45;
  transition: all 0.2s var(--km-ease);
}
.apikey-btn.set {
  opacity: 1;
  background: var(--km-primary-light);
  border-color: var(--km-primary);
}
.model-hint {
  font-size: 11px;
  color: var(--km-gray-500);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
}
</style>
