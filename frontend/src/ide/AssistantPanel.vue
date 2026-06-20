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
          <!-- 助手消息: Markdown 渲染 (过滤 tool_call 块) -->
          <div v-if="msg.role === 'assistant'" class="msg-body assistant-msg">
            <div class="msg-avatar">
              <el-icon :size="18"><Cpu /></el-icon>
            </div>
            <div class="msg-content">
              <MarkdownViewer v-if="msg.content" :content="cleanToolCalls(msg.content)" />
              <span v-else-if="chat.streaming && chat.currentStreamId === msg.id" class="typing">
                <span class="dot"></span><span class="dot"></span><span class="dot"></span>
              </span>
              <span v-else class="empty-msg">—</span>
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
      <div class="input-actions">
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
import { ref, watch, nextTick } from 'vue'
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
  background: var(--kbg-sidebar);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  height: 100%;
  border-left: 1px solid var(--kborder);
}

/* ---- 头部 ---- */
.assistant-header {
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  border-bottom: 1px solid var(--kborder);
  flex-shrink: 0;
}
.assistant-title {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--ktext-secondary);
  font-weight: 600;
}
.status-tag { margin-left: 4px; }
.header-actions { display: flex; gap: 6px; }
.icon-btn { cursor: pointer; color: var(--ktext-secondary); }
.icon-btn:hover { color: var(--ktext); }

/* ---- 消息区域 ---- */
.assistant-body {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  padding: 10px;
  gap: 10px;
}

/* 空状态 */
.placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 24px;
  text-align: center;
}
.ph-title { font-size: 15px; font-weight: 600; color: var(--ktext); margin-top: 6px; }
.ph-hint { font-size: 12px; color: var(--ktext-muted); margin-bottom: 14px; line-height: 1.5; }
.ph-features {
  display: flex; flex-direction: column; gap: 8px;
  width: 100%; text-align: left;
}
.feat {
  font-size: 12px;
  color: var(--ktext-secondary);
  background: var(--kbg-hover);
  padding: 8px 12px;
  border-radius: 6px;
}

/* ---- 消息 ---- */
.message { display: flex; }

.msg-body {
  display: flex; gap: 8px;
  max-width: 100%;
}
.msg-body.user-msg { justify-content: flex-end; width: 100%; }

/* 助手消息 */
.assistant-msg { width: 100%; }
.msg-avatar {
  flex-shrink: 0; width: 28px; height: 28px;
  border-radius: 6px; background: var(--kbg-active);
  display: flex; align-items: center; justify-content: center;
  color: var(--ktext-secondary);
}
.msg-content {
  flex: 1; min-width: 0;
  font-size: 13px; line-height: 1.65;
  color: var(--ktext);
}
.msg-content :deep(pre) {
  max-height: 200px; overflow-y: auto;
  background: var(--kbg); /* 暗色下适配 */
}
.msg-content :deep(code) {
  background: var(--kbg-hover);
  color: var(--ktext);
}
.msg-actions {
  margin-top: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}
.msg-body:hover .msg-actions { opacity: 1; }

/* 用户消息 */
.user-msg .msg-content {
  max-width: 85%;
}
.user-text {
  background: var(--kaccent);
  color: #fff;
  padding: 8px 12px;
  border-radius: 10px 10px 2px 10px;
  font-size: 13px; line-height: 1.5;
  white-space: pre-wrap; word-break: break-word;
  margin: 0;
  font-family: var(--kfont-ui);
}

/* 打字动画 */
.typing { display: inline-flex; gap: 3px; padding: 4px 0; }
.typing .dot {
  width: 6px; height: 6px;
  border-radius: 50%; background: var(--ktext-muted);
  animation: bounce 1.2s infinite;
}
.typing .dot:nth-child(2) { animation-delay: 0.2s; }
.typing .dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}

.empty-msg { color: var(--ktext-muted); }

/* 错误栏 */
.error-bar {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 12px; border-radius: 6px;
  background: var(--kdanger-light, #fef0f0);
  color: var(--kdanger, #f56c6c);
  font-size: 12px;
}

/* ---- 输入区 ---- */
.assistant-input {
  padding: 10px 12px;
  border-top: 1px solid var(--kborder);
  flex-shrink: 0;
}
.assistant-input :deep(.el-textarea__inner) {
  background: var(--kbg);
  color: var(--ktext);
  border-color: var(--kborder);
  font-size: 13px;
}
.input-actions {
  display: flex; justify-content: flex-end;
  margin-top: 8px; gap: 6px;
}
</style>
