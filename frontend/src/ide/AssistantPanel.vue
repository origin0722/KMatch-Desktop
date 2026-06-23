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
          v-for="msg in chat.visibleMessages"
          :key="msg.id"
          class="message"
          :class="msg.role"
        >
          <!-- 助手消息: chunks 判别联合 (think / content / tool_call) -->
          <div v-if="msg.role === 'assistant'" class="msg-body assistant-msg">
            <div class="msg-avatar">
              <el-icon :size="18"><Cpu /></el-icon>
            </div>
            <div class="msg-content">
              <template v-for="(chunk, ci) in (msg.versions?.[msg.activeVersion ?? 0]?.chunks || msg.chunks)" :key="ci">
                <!-- 思考过程 (可折叠) -->
                <div v-if="chunk.type === 'think'" class="think-block">
                  <button class="think-toggle" @click="toggleThink(msg.id)">
                    <svg class="think-icon" :class="{ expanded: isThinkExpanded(msg.id) }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                      <path d="M9 18l6-6-6-6"/>
                    </svg>
                    <span class="think-label" :class="{ breathing: isThinking(msg) }">
                      {{ isThinking(msg) ? '思考中…' : '已思考' }}
                    </span>
                  </button>
                  <div v-show="isThinkExpanded(msg.id)" class="think-content">
                    <pre>{{ chunk.content }}</pre>
                  </div>
                </div>
                <!-- 正文 -->
                <MarkdownViewer v-else-if="chunk.type === 'content'" :content="chunk.content" />
                <!-- 工具调用: 内联卡 (状态机 pending→in_progress→completed→error) -->
                <div v-else-if="chunk.type === 'tool_call'" class="tool-call-card">
                  <div class="tool-header">
                    <el-tag size="small" :type="chunk.result?.error ? 'danger' : ''">{{ chunk.tool }}</el-tag>
                    <code class="tool-path">{{ chunk.args?.path || chunk.result?.sourcePath || chunk.args?.filename || '' }}</code>
                    <span class="tool-status" :class="chunk.status">● {{ statusLabel(chunk.status) }}</span>
                  </div>
                  <template v-if="chunk.result">
                    <div v-if="chunk.result.error" class="tool-error">{{ chunk.result.error }}</div>
                    <div v-else-if="chunk.tool === 'write_file' && chunk.result.written" class="tool-ok">
                      📝 已写入 {{ chunk.result.bytes ?? 0 }} 字节
                    </div>
                    <!-- generate_project_graph: 实体列表 (可点击跳转 Monaco) -->
                    <div v-else-if="chunk.result.tool === 'generate_project_graph'" class="delegate-card">
                      <div class="delegate-stats">
                        <span>模块 {{ chunk.result.stats?.module || 0 }}</span>
                        <span>类 {{ chunk.result.stats?.class || 0 }}</span>
                        <span>函数 {{ chunk.result.stats?.function || 0 }}</span>
                        <span>方法 {{ chunk.result.stats?.method || 0 }}</span>
                        <el-tag v-if="chunk.result.written" size="small" type="success">已落库</el-tag>
                      </div>
                      <!-- 阶段8: 源文件被外部改动 → 图谱过期, 禁用跳转避免指错行 -->
                      <el-alert
                        v-if="projectGraph.stale"
                        type="warning"
                        :closable="false"
                        show-icon
                        class="graph-stale-alert"
                      >
                        图谱已过期（源文件已变动），重新生成以刷新行号
                      </el-alert>
                      <div class="entity-list" :class="{ disabled: projectGraph.stale }">
                        <div
                          v-for="e in (chunk.result.entities || []).slice(0, 30)"
                          :key="e.id"
                          class="entity-item"
                          :class="{ active: projectGraph.activeEntityId === e.id }"
                          :title="projectGraph.stale ? '图谱已过期, 重新生成后再跳转' : `${e.kind} · 行 ${e.line_start}-${e.line_end}`"
                          @click="revealEntity(e)"
                        >
                          <span class="entity-kind" :class="e.kind">{{ kindLabel(e.kind) }}</span>
                          <span class="entity-name">{{ e.qualified_name || e.name }}</span>
                          <span class="entity-line">:{{ e.line_start || '?' }}</span>
                        </div>
                        <span v-if="(chunk.result.entities?.length || 0) > 30" class="truncated">
                          … 共 {{ chunk.result.entities.length }} 个实体
                        </span>
                      </div>
                    </div>
                    <!-- code_review: 四维度评分 -->
                    <div v-else-if="chunk.result.tool === 'code_review'" class="delegate-card">
                      <div class="review-verdict">
                        <el-tag size="small" :type="chunk.result.review?.verdict === 'pass' ? 'success' : 'danger'">
                          {{ chunk.result.review?.verdict === 'pass' ? '通过' : '打回' }}
                        </el-tag>
                        <span class="review-score">总分 {{ pct(chunk.result.review?.overall_score) }}</span>
                        <span class="review-thresh">(阈值 85%)</span>
                      </div>
                      <div class="dim-list">
                        <div v-for="(v, k) in (chunk.result.review?.dimensions || {})" :key="k" class="dim-row">
                          <span class="dim-name">{{ dimName(k) }}</span>
                          <el-progress :percentage="pctNum(v.score)" :stroke-width="6" :color="dimColor(v.score)" />
                        </div>
                      </div>
                      <div v-if="highIssues(chunk.result.review).length" class="issue-list">
                        <div v-for="(iss, i) in highIssues(chunk.result.review)" :key="i" class="issue-item high">
                          ⚠ {{ iss.problem }}
                        </div>
                      </div>
                      <div v-if="chunk.result.review?.retry_hint" class="review-hint">💡 {{ chunk.result.review.retry_hint }}</div>
                    </div>
                    <!-- code_test: 通过率 + 覆盖率 + 失败用例 -->
                    <div v-else-if="chunk.result.tool === 'code_test'" class="delegate-card">
                      <div class="test-summary">
                        <el-tag size="small" :type="testPass(chunk.result.report) ? 'success' : 'warning'">
                          {{ chunk.result.report?.summary?.passed || 0 }}/{{ chunk.result.report?.summary?.total || 0 }} 通过
                        </el-tag>
                        <span v-if="chunk.result.report?.note" class="test-note">{{ chunk.result.report.note }}</span>
                      </div>
                      <div class="cov-row">
                        <span>行覆盖 {{ pct(chunk.result.report?.coverage?.line_coverage) }}</span>
                        <span>分支 {{ pct(chunk.result.report?.coverage?.branch_coverage) }}</span>
                        <span>函数 {{ pct(chunk.result.report?.coverage?.function_coverage) }}</span>
                      </div>
                      <div v-if="(chunk.result.report?.failed_tests || []).length" class="issue-list">
                        <div v-for="(f, i) in (chunk.result.report?.failed_tests || []).slice(0, 8)" :key="i" class="issue-item">
                          <code>{{ f.test_name }}</code>
                          <span v-if="f.suggestion" class="fail-sug"> — {{ f.suggestion }}</span>
                        </div>
                      </div>
                    </div>
                    <div v-else-if="chunk.result.content" class="tool-content">
                      <pre><code>{{ chunk.result.content.slice(0, 2000) }}</code></pre>
                      <span v-if="chunk.result.content.length > 2000" class="truncated">… 内容已截断</span>
                    </div>
                    <div v-else-if="chunk.result.files" class="tool-files">
                      <div v-for="f in chunk.result.files.slice(0, 20)" :key="f" class="tool-file">
                        {{ f }}
                      </div>
                    </div>
                  </template>
                  <div v-else-if="chunk.status === 'in_progress'" class="tool-running">执行中…</div>
                </div>
              </template>
              <!-- 版本切换器: 多版本才显示, hover 浮现 -->
              <div v-if="msg.versions && msg.versions.length > 1" class="version-bar">
                <button class="ver-btn" :disabled="msg.activeVersion === 0" title="上一版" @click="chat.setVersion(msg.id, msg.activeVersion - 1)">‹</button>
                <span class="ver-count">{{ msg.activeVersion + 1 }}/{{ msg.versions.length }}</span>
                <button class="ver-btn" :disabled="msg.activeVersion === msg.versions.length - 1" title="下一版" @click="chat.setVersion(msg.id, msg.activeVersion + 1)">›</button>
              </div>
              <!-- 重生成钮: hover 浮现, isBusy (streaming/审批门/工具循环) 中禁用 -->
              <button
                class="regen-btn"
                :disabled="chat.isBusy"
                :title="chat.isBusy ? '生成中…' : '重新生成'"
                @click="chat.regenMessage(msg.id)"
              >
                <el-icon :size="14"><RefreshRight /></el-icon>
              </button>
              <!-- 流式占位 (空 chunks) -->
              <span v-if="chat.streaming && chat.currentStreamId === msg.id && !hasContent(msg) && !hasThink(msg)" class="typing">
                <span class="dot"></span><span class="dot"></span><span class="dot"></span>
              </span>
              <span v-else-if="!hasContent(msg) && !hasThink(msg)" class="empty-msg">—</span>
              <div class="msg-actions" v-if="hasContent(msg) && !chat.streaming">
                <el-button size="small" text @click="copyText(contentText(msg))">复制</el-button>
              </div>
            </div>
          </div>

          <!-- 用户消息: 纯文本气泡 -->
          <div v-else class="msg-body user-msg">
            <div class="msg-content">
              <pre class="user-text">{{ contentText(msg) }}</pre>
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

    <!-- write_file 权限审批门 (阶段3.1) -->
    <div v-if="chat.pendingApproval" class="approval-card">
      <div class="approval-header">
        <el-icon :size="15"><EditPen /></el-icon>
        <span class="approval-title">写入审批</span>
        <el-tag size="small" type="warning">write_file</el-tag>
        <code class="approval-path">{{ chat.pendingApproval.call.path }}</code>
      </div>

      <!-- 安全预检结果 -->
      <div class="safety-block">
        <template v-if="!chat.pendingApproval.checked">
          <div class="safety-line skipped">安全预检已跳过（非 Python 文件或预检失败）</div>
          <div v-if="chat.pendingApproval.safetyError" class="safety-line warn">
            预检请求: {{ chat.pendingApproval.safetyError }}
          </div>
        </template>
        <template v-else-if="chat.pendingApproval.safe && chat.pendingApproval.safetyIssues.length === 0">
          <div class="safety-line ok">✓ AST 安全预检通过，未发现高危调用</div>
        </template>
        <template v-else>
          <div class="safety-line" :class="chat.pendingApproval.safe ? 'warn' : 'danger'">
            {{ chat.pendingApproval.safe ? '⚠ 预检发现提示项' : '✗ 预检发现高危项，请谨慎审批' }}
          </div>
          <div
            v-for="(iss, i) in chat.pendingApproval.safetyIssues"
            :key="i"
            class="safety-issue"
            :class="iss.severity"
          >
            <el-tag size="small" :type="iss.severity === 'high' ? 'danger' : 'warning'">
              {{ iss.severity }}
            </el-tag>
            <span class="iss-dim">{{ iss.dimension }}</span>
            <span class="iss-problem">{{ iss.problem }}</span>
          </div>
        </template>
      </div>

      <!-- 可编辑内容预览 -->
      <div class="approval-content-label">文件内容 (可编辑):</div>
      <textarea
        v-model="approvalContent"
        class="approval-content"
        spellcheck="false"
      ></textarea>

      <div class="approval-actions">
        <el-button size="small" @click="rejectApproval">拒绝</el-button>
        <el-button size="small" type="primary" @click="approveApproval">
          <el-icon :size="14"><Check /></el-icon>&nbsp;批准写入
        </el-button>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="assistant-input">
      <!-- F14: 后端宕机提示 (统一 backendHealth store) -->
      <el-alert
        v-if="backend.status === false"
        class="backend-down-alert"
        type="error"
        :closable="false"
        show-icon
        title="后端未运行"
        description="localhost:8000 无响应, AI 对话/测评/图谱功能不可用。请启动后端 (见 scripts/start_all.py 或 CLAUDE.md 快速启动)。"
      />
      <el-input
        ref="inputRef"
        v-model="inputText"
        type="textarea"
        :rows="2"
        :disabled="chat.isBusy || backend.status === false"
        :placeholder="chat.tutorMode ? '导学模式: 提问后 AI 会用追问和提示引导你思考, 不直接给答案… (Enter 发送)' : '输入消息… (Enter 发送, Shift+Enter 换行)'"
        resize="none"
        @keydown="onKeydown"
      />
      <div class="input-bar-row">
        <!-- 厂商选择 -->
        <el-select
          :model-value="aiSettings.provider"
          size="small"
          class="provider-select"
          :disabled="chat.streaming"
          @change="onProviderChange"
        >
          <el-option
            v-for="p in PROVIDERS"
            :key="p.id"
            :label="p.label"
            :value="p.id"
          />
        </el-select>
        <!-- API Key -->
        <el-button
          size="small"
          class="apikey-btn"
          :class="{ set: !!aiSettings.apiKey }"
          :title="aiSettings.apiKey ? '已设置 API Key' : '设置 API Key'"
          :disabled="chat.streaming"
          @click="openApiKeyDialog"
        >
          🔑
        </el-button>
        <!-- 启发式导学模式 (赛题(4)②) -->
        <el-tooltip
          :content="chat.tutorMode ? '导学模式开启: AI 以引导式回答+追问, 不直接给答案。点击关闭' : '开启启发式导学: AI 不直接给答案, 用提问和提示引导你思考'"
          placement="top"
        >
          <el-button
            size="small"
            class="tutor-btn"
            :class="{ on: chat.tutorMode }"
            :disabled="chat.streaming"
            @click="chat.setTutorMode(!chat.tutorMode)"
          >
            <el-icon :size="14"><MagicStick /></el-icon>
            <span v-if="chat.tutorMode" class="tutor-label">导学</span>
          </el-button>
        </el-tooltip>
        <!-- 模型 (自动) -->
        <span class="model-hint" :title="'当前模型: ' + (aiSettings.model || '未选择')">
          {{ aiSettings.model || '—' }}
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
          :disabled="!inputText.trim() || chat.isBusy || backend.status === false"
          @click="handleSend"
        >
          <el-icon :size="14"><Promotion /></el-icon>&nbsp;发送
        </el-button>
      </div>
    </div>

    <!-- API Key 设置对话框 (Electron 不支持 window.prompt) -->
    <el-dialog
      v-model="apiKeyDialogVisible"
      title="API 设置"
      width="420px"
      :close-on-click-modal="false"
      append-to-body
    >
      <el-form label-position="top">
        <el-form-item label="API Key">
          <el-input
            v-model="apiKeyInput"
            type="password"
            show-password
            placeholder="sk-..."
            clearable
          />
        </el-form-item>
        <el-form-item v-if="aiSettings.provider === 'custom'" label="API Base URL">
          <el-input
            v-model="baseUrlInput"
            placeholder="https://api.example.com/v1"
            clearable
          />
        </el-form-item>
        <div class="apikey-tip">
          当前厂商: {{ PROVIDERS.find((p) => p.id === aiSettings.provider)?.label || aiSettings.provider }}
          <span v-if="aiSettings.provider !== 'custom'">· Base URL 已预置</span>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="apiKeyDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveApiKey">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, watch, nextTick } from 'vue'
import { Delete, VideoPause, Promotion, EditPen, Check, MagicStick, RefreshRight } from '@element-plus/icons-vue'
import { useSidebarStore } from '@/stores/sidebar'
import { useChatStore, contentTextOf, activeChunksOf } from '@/stores/chat'
import { useAiSettingsStore, PROVIDERS } from '@/stores/aiSettings'
import { useProjectGraphStore } from '@/stores/projectGraph'
import { useBackendHealthStore } from '@/stores/backendHealth'
import { ElMessage } from 'element-plus'
import MarkdownViewer from '@/components/MarkdownViewer.vue'

const sidebar = useSidebarStore()
const chat = useChatStore()
const aiSettings = useAiSettingsStore()
const projectGraph = useProjectGraphStore()
const backend = useBackendHealthStore()

const inputText = ref('')
const inputRef = ref(null)
const msgContainer = ref(null)

// ---- write_file 审批门: 可编辑内容 (随 pendingApproval 出现而初始化) ----
const approvalContent = ref('')
watch(
  () => chat.pendingApproval?.id,
  (id) => {
    if (id && chat.pendingApproval) {
      approvalContent.value = chat.pendingApproval.content || ''
    }
  },
  { immediate: true },
)

function approveApproval() {
  chat.resolveApproval({ approved: true, content: approvalContent.value })
}
function rejectApproval() {
  chat.resolveApproval({ approved: false })
}

// ---- 阶段4: 委派工具结果卡辅助 + 实体联动 ----
function pct(v) { return v == null ? '—' : (v * 100).toFixed(0) + '%' }
function pctNum(v) { return v == null ? 0 : Math.round(v * 100) }
function dimName(k) {
  return { logic_correctness: '逻辑正确性', security: '安全性', code_quality: '代码规范', domain_compliance: '领域合规' }[k] || k
}
function dimColor(score) {
  const n = pctNum(score)
  return n >= 85 ? '#52c41a' : n >= 60 ? '#faad14' : '#f56c6c'
}
function highIssues(review) {
  const dims = review?.dimensions || {}
  return Object.values(dims).flatMap((d) => d.issues || []).filter((i) => i.severity === 'high')
}
function testPass(report) {
  const s = report?.summary
  return s && s.total > 0 && s.failed === 0 && s.error === 0
}
function kindLabel(kind) {
  return { module: 'M', class: 'C', function: 'F', method: 'm' }[kind] || '?'
}
function revealEntity(e) {
  if (e.line_start == null) return
  // 阶段8: 图谱过期时禁用跳转 (行号可能已漂移, 跳转会指错)
  if (projectGraph.stale) return
  projectGraph.requestReveal(e.line_start, e.line_end, e.qualified_name || e.name)
  sidebar.setView('code')
}

// ---- chunks 模型辅助 (借鉴 Apix MessageChunk) ----
// 助手消息读 versions[activeVersion].chunks (经 activeChunksOf), 用户/旧消息读 msg.chunks
function hasContent(msg) {
  return activeChunksOf(msg).some((c) => c.type === 'content' && c.content)
}
function hasThink(msg) {
  return activeChunksOf(msg).some((c) => c.type === 'think' && c.content)
}
function contentText(msg) {
  return contentTextOf(msg)
}
/** 当前正在思考: 流式中且尚无正文 */
function isThinking(msg) {
  return chat.streaming && chat.currentStreamId === msg.id && !hasContent(msg)
}
const STATUS_LABEL = { pending: '待执行', in_progress: '执行中', completed: '完成', error: '失败' }
function statusLabel(s) { return STATUS_LABEL[s] || s }

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
  if (msgs.length > 0) return contentTextOf(msgs[msgs.length - 1])
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
  aiSettings.setProvider(val)
}

// ---- API Key 设置对话框 (Electron 不支持 window.prompt, 用 el-dialog) ----
const apiKeyDialogVisible = ref(false)
const apiKeyInput = ref('')
const baseUrlInput = ref('')

function openApiKeyDialog() {
  apiKeyInput.value = aiSettings.apiKey || ''
  baseUrlInput.value = aiSettings.customBaseUrl || ''
  apiKeyDialogVisible.value = true
}

function saveApiKey() {
  aiSettings.setApiKey(apiKeyInput.value.trim())
  if (aiSettings.provider === 'custom') {
    aiSettings.setCustomBaseUrl(baseUrlInput.value.trim())
  }
  apiKeyDialogVisible.value = false
  ElMessage.success(aiSettings.apiKey ? 'API 设置已保存' : '已清除 API Key')
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
  position: relative;
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

/* 内联工具调用卡 (chunks 模型, 取代原 tool 消息) */
.tool-call-card {
  margin-top: 6px;
  padding: 8px 10px;
  background: var(--km-bg-layer-1, var(--km-gray-100));
  border: 1px solid var(--km-border-light);
  border-radius: var(--km-radius-sm);
  font-size: 12px;
}
.tool-call-card .tool-header {
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 4px;
}
.tool-status {
  margin-left: auto;
  font-size: 11px;
  display: inline-flex; align-items: center; gap: 3px;
  white-space: nowrap;
}
.tool-status.pending    { color: var(--km-gray-400); }
.tool-status.in_progress { color: var(--km-info); animation: thinkPulse 1.2s ease-in-out infinite; }
.tool-status.completed  { color: var(--km-success, #67c23a); }
.tool-status.error      { color: var(--km-danger, #f56c6c); font-weight: 600; }
.tool-ok { color: var(--km-success, #67c23a); }
.tool-running { color: var(--km-gray-500); font-size: 11px; }

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
/* 启发式导学模式按钮 */
.tutor-btn {
  height: 30px;
  padding: 0 8px;
  display: flex; align-items: center; gap: 3px;
  font-size: 12px;
  border-radius: var(--km-radius-sm);
  opacity: 0.55;
  transition: all 0.2s var(--km-ease);
}
.tutor-btn.on {
  opacity: 1;
  background: var(--km-primary-light);
  border-color: var(--km-primary);
  color: var(--km-primary);
}
.tutor-label { font-size: 11px; font-weight: 600; }
.apikey-tip { font-size: 12px; color: var(--km-gray-500); margin-top: -4px; }
.model-hint {
  font-size: 11px;
  color: var(--km-gray-500);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
}

/* ---- write_file 审批门 ---- */
.approval-card {
  flex-shrink: 0;
  margin: 0 10px 8px;
  padding: 12px;
  border: 1px solid var(--km-warning, #e6a23c);
  border-radius: var(--km-radius);
  background: var(--km-bg-layer-1, var(--km-bg-layer-0));
  box-shadow: var(--km-shadow-sm);
  animation: msgIn 0.25s var(--km-ease-out);
}
.approval-header {
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 10px;
  color: var(--km-gray-700);
  font-size: 12px; font-weight: 600;
}
.approval-title { margin-right: 2px; }
.approval-path {
  font-size: 11px;
  color: var(--km-gray-600);
  background: var(--km-gray-200);
  padding: 1px 6px;
  border-radius: 4px;
  margin-left: auto;
  max-width: 140px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.safety-block {
  margin-bottom: 10px;
  padding: 8px 10px;
  background: var(--km-bg-layer-2);
  border-radius: var(--km-radius-sm);
  font-size: 11.5px;
}
.safety-line { line-height: 1.6; }
.safety-line.ok { color: var(--km-success, #67c23a); }
.safety-line.warn { color: var(--km-warning, #e6a23c); }
.safety-line.danger { color: var(--km-danger, #f56c6c); font-weight: 600; }
.safety-line.skipped { color: var(--km-gray-500); }
.safety-issue {
  display: flex; align-items: center; gap: 6px;
  margin-top: 6px;
  font-size: 11px;
}
.safety-issue .iss-dim {
  color: var(--km-gray-500);
  font-size: 10px;
}
.safety-issue .iss-problem {
  color: var(--km-gray-700);
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.approval-content-label {
  font-size: 11px;
  color: var(--km-gray-500);
  margin-bottom: 4px;
}
.approval-content {
  width: 100%;
  min-height: 120px;
  max-height: 200px;
  resize: vertical;
  font-family: var(--km-font-mono, 'Consolas', monospace);
  font-size: 12px;
  line-height: 1.5;
  padding: 8px 10px;
  border: 1px solid var(--km-border);
  border-radius: var(--km-radius-sm);
  background: var(--km-bg-layer-2);
  color: var(--km-gray-700);
  box-sizing: border-box;
}
.approval-content:focus {
  outline: none;
  border-color: var(--km-border-focus, var(--km-primary));
}
.approval-actions {
  display: flex; justify-content: flex-end; gap: 8px;
  margin-top: 10px;
}

/* ---- 阶段4: 委派工具结果卡 ---- */
.delegate-card {
  margin-top: 6px;
  display: flex; flex-direction: column; gap: 8px;
}
.graph-stale-alert {
  margin: 2px 0;
}
.entity-list.disabled .entity-item {
  opacity: 0.5;
  cursor: not-allowed;
}
.delegate-stats {
  display: flex; flex-wrap: wrap; gap: 8px;
  font-size: 11.5px; color: var(--km-gray-600);
}
.entity-list {
  display: flex; flex-direction: column; gap: 2px;
  max-height: 220px; overflow-y: auto;
  background: var(--km-bg-layer-2);
  border-radius: var(--km-radius-sm);
  padding: 4px;
}
.entity-item {
  display: flex; align-items: center; gap: 6px;
  font-size: 11.5px;
  padding: 3px 6px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.12s var(--km-ease);
}
.entity-item:hover { background: var(--km-primary-light); }
.entity-item.active {
  background: var(--km-primary);
  color: var(--km-primary-text);
}
.entity-item.active .entity-line { color: var(--km-primary-text); opacity: 0.8; }
.entity-kind {
  flex-shrink: 0; width: 16px; height: 16px;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 700;
  border-radius: 3px;
  background: var(--km-gray-300); color: var(--km-gray-700);
}
.entity-kind.class { background: #e6f4ff; color: #1890ff; }
.entity-kind.function { background: #f6ffed; color: #52c41a; }
.entity-kind.method { background: #fff7e6; color: #fa8c16; }
.entity-kind.module { background: #f9f0ff; color: #722ed1; }
.entity-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--km-font-mono, monospace); }
.entity-line { flex-shrink: 0; color: var(--km-gray-400); font-size: 10px; }

/* code_review */
.review-verdict { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.review-score { font-weight: 600; color: var(--km-gray-700); }
.review-thresh { font-size: 11px; color: var(--km-gray-400); }
.dim-list { display: flex; flex-direction: column; gap: 4px; }
.dim-row { display: flex; align-items: center; gap: 8px; font-size: 11.5px; }
.dim-name { width: 80px; flex-shrink: 0; color: var(--km-gray-600); }
.dim-row :deep(.el-progress) { flex: 1; }
.issue-list { display: flex; flex-direction: column; gap: 3px; }
.issue-item { font-size: 11.5px; color: var(--km-gray-600); line-height: 1.5; }
.issue-item.high { color: var(--km-danger); }
.issue-item code { background: var(--km-gray-200); padding: 0 4px; border-radius: 3px; font-size: 11px; }
.fail-sug { color: var(--km-gray-500); }
.review-hint { font-size: 11.5px; color: var(--km-gray-500); }

/* code_test */
.test-summary { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.test-note { font-size: 11px; color: var(--km-warning, #e6a23c); }
.cov-row { display: flex; gap: 10px; font-size: 11px; color: var(--km-gray-600); }

/* ---- 版本分支: 切换器 + 重生成钮 ---- */
.version-bar {
  display: inline-flex; align-items: center; gap: 4px;
  margin-top: 6px; opacity: 0; transition: opacity 0.12s var(--km-ease);
  font-size: 11px; color: var(--km-gray-500);
}
.message.assistant:hover .version-bar { opacity: 1; }
.ver-btn {
  border: 1px solid var(--km-border); background: var(--km-bg-layer-3);
  color: var(--km-gray-600); border-radius: 4px; width: 18px; height: 18px;
  cursor: pointer; font-size: 12px; line-height: 1; padding: 0;
}
.ver-btn:hover:not(:disabled) { border-color: var(--km-primary); color: var(--km-primary); }
.ver-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.ver-count { font-family: var(--km-font-mono); }

.regen-btn {
  position: absolute; right: 4px; bottom: 4px;
  border: 0; background: transparent; color: var(--km-gray-400);
  cursor: pointer; padding: 4px; border-radius: 4px;
  opacity: 0; transition: opacity 0.12s var(--km-ease);
}
.message.assistant:hover .regen-btn { opacity: 1; }
.regen-btn:hover:not(:disabled) { color: var(--km-primary); background: var(--km-primary-light); }
.regen-btn:disabled { opacity: 0.3; cursor: not-allowed; }

/* 版本切换淡入淡出 */
.msg-content { transition: opacity 0.15s var(--km-ease); }

@media (prefers-reduced-motion: reduce) {
  .version-bar, .regen-btn { opacity: 1; transition: none; }
  .msg-content { transition: none; }
}
</style>
