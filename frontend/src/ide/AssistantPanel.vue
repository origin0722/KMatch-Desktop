<template>
  <div class="assistant-panel" :class="{ wide: variant === 'wide' }">
    <!-- 头部 -->
    <div class="assistant-header">
      <span class="assistant-title">
        <el-icon :size="15"><ChatDotRound /></el-icon>&nbsp;AI 助手
        <el-tag v-if="chat.streaming" type="warning" size="small" class="status-tag">回复中</el-tag>
      </span>
      <div class="header-actions">
        <el-icon v-if="variant === 'wide'" class="icon-btn" :title="sideCollapsed ? '展开辅助面板' : '收起辅助面板'" data-test="side-toggle" @click="sideCollapsed = !sideCollapsed">
          <Menu />
        </el-icon>
        <el-icon class="icon-btn" title="清空对话" @click="chat.clearMessages()" v-if="chat.hasMessages">
          <Delete />
        </el-icon>
        <el-icon class="icon-btn" title="收起" @click="sidebar.toggleAiPanel()" v-if="variant === 'side'"><Close /></el-icon>
      </div>
    </div>

    <!-- 场景二快捷引导 (有项目时) -->
    <div class="quick-actions" v-if="ws.hasProject">
      <el-button size="small" plain @click="quickAction('解析这个项目的代码结构')">解析项目</el-button>
      <el-button size="small" plain @click="sidebar.setView('project-graph')">看图谱</el-button>
      <el-button size="small" plain @click="quickAction('请带我导读这个项目：从入口开始，按调用链逐层讲解')">项目导读</el-button>
      <el-button size="small" plain @click="quickAction('审查当前打开文件的代码')">审查代码</el-button>
      <el-button size="small" plain @click="quickAction('为当前文件生成单元测试')">测试代码</el-button>
      <el-button size="small" plain @click="sidebar.setView('dashboard')">数据看板</el-button>
      <el-button size="small" plain @click="sidebar.setView('learning')">学习资源</el-button>
      <el-button size="small" plain @click="sidebar.setView('runs')">运行历史</el-button>
    </div>

    <!-- 消息列表 -->
    <div ref="msgContainer" class="assistant-body">
      <!-- 空状态 (issue-64: 去掉装饰性小字与 feature 列表, 建议 chip 居中聚焦) -->
      <div v-if="!chat.hasMessages" class="placeholder">
        <div class="ph-icon-badge"><el-icon :size="26"><ChatLineSquare /></el-icon></div>
        <p class="ph-title">AI 助手</p>
        <!-- T4 wide 形态: Codex 式建议 chip (点击直接发送) -->
        <div v-if="variant === 'wide'" class="ph-chips">
          <button class="ph-chip" @click="quickAction('根据我的学情画像, 我现在最该学什么?')">🎯 我该学什么</button>
          <button class="ph-chip" @click="quickAction(GUIDE_PROMPT)">🧭 知识图谱导读</button>
          <button class="ph-chip" @click="quickAction('请结合我的学情画像薄弱点，搜索相关教程并逐条给我讲解（按薄弱点搜索）')">📚 补薄弱点</button>
          <button class="ph-chip" @click="quickAction('给我出一道 Python 基础练习题, 我做完你帮我批改')">📝 来道练习题</button>
          <button class="ph-chip" @click="quickAction('结合知识图谱, 给我规划一条从零到爬虫的学习路径')">🕸️ 规划学习路径</button>
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
              <el-icon :size="15"><Cpu /></el-icon>
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
                      {{ isThinking(msg) ? '思考中…' : `已思考 · ${thinkCharCount(msg)} 字` }}
                    </span>
                  </button>
                  <transition name="expand">
                  <div v-show="isThinkExpanded(msg.id)" class="think-content">
                    <pre>{{ chunk.content }}</pre>
                  </div>
                  </transition>
                </div>
                <!-- 正文 -->
                <MarkdownViewer v-else-if="chunk.type === 'content'" :content="chunk.content" />
                <!-- 工具调用: 内联卡 (状态机 pending→in_progress→completed→error) -->
                <div v-else-if="chunk.type === 'tool_call'" class="tool-call-card">
                  <div
                    class="tool-header"
                    :class="{ clickable: !(chunk.result?.error) }"
                    @click="toggleTool(toolKey(msg, ci), chunk)"
                  >
                    <el-tag size="small" :type="chunk.result?.error ? 'danger' : ''">{{ chunk.tool }}</el-tag>
                    <code class="tool-path">{{ chunk.args?.path || chunk.result?.sourcePath || chunk.args?.filename || '' }}</code>
                    <span class="tool-status" :class="chunk.status">● {{ statusLabel(chunk.status) }}</span>
                    <span class="tool-summary">{{ toolSummary(chunk) }}</span>
                    <svg
                      v-if="!chunk.result?.error"
                      class="tool-chevron"
                      :class="{ expanded: isToolExpanded(toolKey(msg, ci), chunk) }"
                      width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
                    >
                      <path d="M9 18l6-6-6-6"/>
                    </svg>
                  </div>
                  <transition name="expand">
                  <div v-show="isToolExpanded(toolKey(msg, ci), chunk)" class="tool-body">
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
                  </transition>
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

          <!-- 用户消息: 纯文本气泡 + 附件缩略图 -->
          <div v-else class="msg-body user-msg">
            <div class="msg-content">
              <div v-if="msg._attachments?.length" class="msg-attachments">
                <img
                  v-for="a in msg._attachments"
                  :key="a.id"
                  :src="a.thumbDataUrl"
                  :alt="a.name"
                  class="msg-attachment-thumb"
                  @click="openImagePreview(a.base64DataUrl)"
                />
              </div>
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
      <div
        class="input-box"
        @dragover.prevent
        @drop.prevent="onDrop"
      >
        <div v-if="chat.pendingAttachments.length" class="attachments-strip">
          <div v-for="a in chat.pendingAttachments" :key="a.id" class="attachment-item">
            <img :src="a.thumbDataUrl" :alt="a.name" />
            <span class="attachment-meta">{{ a.name }} · {{ formatBytes(a.size) }}</span>
            <el-button size="small" text @click="chat.removeAttachment(a.id)">✕</el-button>
          </div>
        </div>
        <el-input
          ref="inputRef"
          v-model="inputText"
          type="textarea"
          :rows="2"
          :disabled="chat.isBusy || backend.status === false"
          :placeholder="inputPlaceholder"
          resize="none"
          class="input-main"
          @keydown="onKeydown"
        />
      <div class="input-toolbar">
        <input
          ref="fileInputRef"
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          multiple
          hidden
          @change="onFilesPicked"
        />
        <!-- 附件 (内嵌输入框左侧) -->
        <el-tooltip :content="attachTooltip" placement="top">
          <button
            type="button"
            class="ib-tool"
            :disabled="attachDisabled"
            @click="onAttachClick"
          >
            <span v-if="visionPending">⋯</span>
            <span v-else>📎</span>
          </button>
        </el-tooltip>
        <!-- 启发式导学模式 (赛题(4)②) -->
        <el-tooltip
          :content="chat.tutorMode ? '导学模式开启: AI 以引导式回答+追问, 不直接给答案。点击关闭' : '开启启发式导学: AI 不直接给答案, 用提问和提示引导你思考'"
          placement="top"
        >
          <button
            type="button"
            class="ib-tool"
            :class="{ on: chat.tutorMode }"
            :disabled="chat.streaming"
            @click="chat.setTutorMode(!chat.tutorMode)"
          >
            <el-icon :size="13"><MagicStick /></el-icon>
            <span v-if="chat.tutorMode" class="ib-tool-label">导学</span>
          </button>
        </el-tooltip>
        <!-- 模型与配置入口 (弹层不动, 芯片内嵌工具栏) -->
        <el-popover
          v-model:visible="configPopoverVisible"
          placement="top-start"
          :width="300"
          trigger="click"
          popper-class="input-config-popper"
        >
          <template #reference>
            <button
              type="button"
              class="model-chip"
              :class="{ unset: !aiSettings.apiKey }"
              :disabled="chat.streaming"
              :title="aiSettings.apiKey ? '点击切换厂商 / 模型 / 思考模式' : '未设置 API Key, 点击配置'"
            >
              <img :src="iconUrlOf(aiSettings.providerMeta().iconKey)" class="provider-icon" alt="" />
              <span class="model-chip-name">{{ aiSettings.model }}</span>
              <el-icon :size="11" class="model-chip-caret"><CaretBottom /></el-icon>
            </button>
          </template>
          <div class="config-panel">
            <div class="config-row">
              <label>厂商</label>
              <el-select
                :model-value="providerSelectValue"
                size="small"
                :disabled="chat.streaming"
                style="width: 100%"
                @change="onProviderChange"
              >
                <template #prefix>
                  <img :src="iconUrlOf(aiSettings.providerMeta().iconKey)" class="provider-icon" alt="" />
                </template>
                <el-option v-for="p in PROVIDERS" :key="p.id" :label="p.label" :value="p.id">
                  <span class="provider-row">
                    <img :src="iconUrlOf(p.iconKey)" class="provider-icon" alt="" />
                    <span>{{ p.label }}</span>
                  </span>
                </el-option>
              </el-select>
            </div>
            <div class="config-row">
              <label>模型</label>
              <el-select
                :model-value="aiSettings.model"
                size="small"
                :disabled="chat.streaming"
                style="width: 100%"
                @change="aiSettings.setModel"
              >
                <el-option v-for="m in aiSettings.models" :key="m" :label="m" :value="m">
                  <span class="model-row">
                    <span class="model-name">{{ m }}</span>
                    <span class="model-badges">
                      <el-tag v-if="capOf(m).vision === true" size="small" type="success" effect="plain">👁</el-tag>
                      <el-tag v-else-if="capOf(m).vision === undefined && capOf(m).pending" size="small" type="info" effect="plain">⋯</el-tag>
                      <el-tag v-if="capOf(m).reasoning === 'native'" size="small" type="warning" effect="plain">🧠</el-tag>
                      <el-tag v-if="capOf(m).context" size="small" type="info" effect="plain">{{ formatContext(capOf(m).context) }}</el-tag>
                    </span>
                  </span>
                </el-option>
              </el-select>
            </div>
            <div class="config-row">
              <label>思考模式</label>
              <SegmentedControl
                :model-value="aiSettings.reasoningMode"
                :options="REASONING_OPTIONS"
                :disabled="chat.streaming"
                @update:model-value="aiSettings.setReasoningMode"
              />
            </div>
            <el-button
              size="small"
              class="config-apikey"
              :class="{ set: !!aiSettings.apiKey }"
              style="width: 100%; margin-top: 2px;"
              @click="openApiKeyDialog(); configPopoverVisible = false"
            >
              {{ aiSettings.apiKey ? '🔑  API Key 已设置' : '🔑  设置 API Key' }}
            </el-button>
          </div>
        </el-popover>

        <div class="ib-right">
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
        <el-form-item v-if="isCustomProvider(aiSettings.provider) || aiSettings.provider === 'custom'" label="API Base URL">
          <el-input
            v-model="baseUrlInput"
            placeholder="https://api.example.com/v1"
            clearable
          />
        </el-form-item>
        <div class="apikey-tip">
          当前厂商: {{ PROVIDERS.find((p) => p.id === aiSettings.provider)?.label || aiSettings.providerMeta()?.label || aiSettings.provider }}
          <span v-if="!(isCustomProvider(aiSettings.provider) || aiSettings.provider === 'custom')">· Base URL 已预置</span>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="apiKeyDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveApiKey">保存</el-button>
      </template>
    </el-dialog>

    <!-- 附件大图预览 (点击缩略图触发) -->
    <el-image-viewer
      v-if="previewUrl"
      :url-list="[previewUrl]"
      hide-on-click-modal
      @close="closeImagePreview"
    />

    <!-- issue-81: wide 形态右侧多面板 (任务/文件/日志) -->
    <AssistantSidePanel v-if="variant === 'wide' && !sideCollapsed" />
  </div>
</template>

<script setup>
import { ref, reactive, watch, nextTick, computed } from 'vue'
import { Delete, VideoPause, Promotion, EditPen, Check, MagicStick, RefreshRight, CaretBottom, Menu } from '@element-plus/icons-vue'
import AssistantSidePanel from './AssistantSidePanel.vue'
import { useSidebarStore } from '@/stores/sidebar'
import { useWorkspaceStore } from '@/stores/workspace'
import { useChatStore, contentTextOf, activeChunksOf } from '@/stores/chat'
import { useAiSettingsStore, PROVIDERS, isCustomProvider, customProviderUuid } from '@/stores/aiSettings'
import { useCustomProvidersStore } from '@/stores/customProviders'
import { useProjectGraphStore } from '@/stores/projectGraph'
import { useBackendHealthStore } from '@/stores/backendHealth'
import { ElMessage } from 'element-plus'
import MarkdownViewer from '@/components/MarkdownViewer.vue'
import { capabilityOf, formatContext } from '@/services/llm/modelCapabilities'
import { iconUrlOf } from '@/services/llm/icons'
import { useModelVisionStore } from '@/stores/modelVision'
import { GRAPH_GUIDE_PROMPT as GUIDE_PROMPT } from '@/utils/askAi'
import SegmentedControl from '@/ide/settings/SegmentedControl.vue'

const sidebar = useSidebarStore()
const chat = useChatStore()
const ws = useWorkspaceStore()

// T4 双形态: side = 右侧可折叠分栏 (默认, 行为不变); wide = 主区 chat 视图 (Codex 式居中对话)
// 仅影响模板分支与样式层, 对话逻辑 (chat store) 两形态共享零改动
const props = defineProps({
  variant: { type: String, default: 'side' },
})

// 场景二快捷引导: 一键发消息
function quickAction(text) { chat.sendMessage(text) }
const aiSettings = useAiSettingsStore()
const customProviders = useCustomProvidersStore()
const projectGraph = useProjectGraphStore()
const backend = useBackendHealthStore()
const modelVision = useModelVisionStore()

// 输入框绑定 chat.draft (store): 图谱/项目图谱详情"问 AI"按钮预填后,
// 切到 chat 视图 (或右侧分栏) 都能带出, 可编辑后再发送
const inputText = computed({
  get: () => chat.draft,
  set: (v) => { chat.draft = v },
})
// B4: 未配 Key 时输入框提示 CTA 化 (ollama 本地免 key)
const inputPlaceholder = computed(() => {
  if (!aiSettings.apiKey && aiSettings.provider !== 'ollama')
    return '未配置 API Key, 点击下方芯片设置… (Enter 发送)'
  return chat.tutorMode
    ? '导学模式: 提问后 AI 会用追问和提示引导你思考, 不直接给答案… (Enter 发送)'
    : '输入消息… (Enter 发送, Shift+Enter 换行)'
})
const inputRef = ref(null)
const configPopoverVisible = ref(false)
const msgContainer = ref(null)
// issue-81: wide 形态右侧辅助面板收起状态 (持久化)
const sideCollapsed = ref(false)
try { sideCollapsed.value = localStorage.getItem('kmatch-chat-side-collapsed') === '1' } catch { /* ignore */ }
watch(sideCollapsed, (v) => {
  try { localStorage.setItem('kmatch-chat-side-collapsed', v ? '1' : '0') } catch { /* ignore */ }
})

// ---- 附件缩略图大图预览 (ElImageViewer 全局注册, 仅用 tag) ----
const previewUrl = ref(null)
function openImagePreview(url) { previewUrl.value = url }
function closeImagePreview() { previewUrl.value = null }

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

// Think 状态: 默认收起 (反馈: 思考过程噪音大, 何时想看再点开), 单行"已思考 · N 字"摘要;
// 用户手动展开记入集合, 流式思考中也保持单行 (呼吸动画提示进行中)
const thinkExpanded = reactive({})
function isThinkExpanded(msgId) {
  return !!thinkExpanded[msgId]
}
function toggleThink(msgId) {
  thinkExpanded[msgId] = !thinkExpanded[msgId]
}
/** 一条消息内 think chunks 总字数 (收起态摘要) */
function thinkCharCount(msg) {
  return activeChunksOf(msg)
    .filter((c) => c.type === 'think')
    .reduce((n, c) => n + (c.content?.length || 0), 0)
}

// 工具调用卡: 默认收起, 头部一句话摘要; 错误结果始终展开 (不能把失败藏起来)
const toolExpanded = reactive({})
function toolKey(msg, ci) { return `${msg.id}:${ci}` }
function isToolExpanded(key, chunk) {
  if (chunk?.result?.error) return true
  return !!toolExpanded[key]
}
function toggleTool(key, chunk) {
  if (chunk?.result?.error) return // 错误不可收起
  toolExpanded[key] = !toolExpanded[key]
}
/** 收起态头部摘要: 按 result 形状生成一句话 */
function toolSummary(chunk) {
  const r = chunk.result
  if (!r) return chunk.status === 'in_progress' ? '执行中…' : ''
  if (r.error) return String(r.error).slice(0, 80)
  if (r.tool === 'generate_project_graph') {
    const st = r.stats || {}
    return `${(st.module || 0) + (st.class || 0) + (st.function || 0) + (st.method || 0)} 实体${r.written ? ' · 已落库' : ''}`
  }
  if (r.tool === 'code_review') {
    const s = Math.round((r.review?.overall_score || 0) * 100)
    return r.review?.verdict === 'pass' ? `通过 · 总分 ${s}%` : `打回 · 总分 ${s}%`
  }
  if (r.tool === 'code_test') {
    const s = r.report?.summary
    return `${s?.passed || 0}/${s?.total || 0} 用例通过 · 行覆盖 ${Math.round((r.report?.coverage?.line_coverage || 0) * 100)}%`
  }
  if (r.tool === 'web_search') return `搜索到 ${r.count || 0} 条结果`
  if (r.tool === 'search_weak_topics') return `按薄弱点搜到 ${r.count || 0} 条资源`
  if (r.tool === 'search_knowledge') return `命中 ${r.count || 0} 个知识节点`
  if (r.tool === 'get_knowledge_node') return r.name || r.node_id || ''
  if (r.tool === 'get_learning_path') return r.count != null ? `路径 ${r.count} 个节点` : (r.hint ? '需先完成测评' : '')
  if (r.tool === 'query_project_graph') return r.entity_count != null ? `${r.entity_count} 实体 · ${r.relation_count} 关系` : (r.hint ? '需先解析项目' : '')
  if (r.tool === 'generate_learning_resources') return r.count != null ? `生成 ${r.count} 份资源` : (r.hint ? '需先完成测评' : '')
  if (chunk.tool === 'write_file' && r.written) return `已写入 ${r.bytes ?? 0} 字节`
  if (typeof r.content === 'string') return `${r.content.length} 字符`
  if (Array.isArray(r.files)) return `${r.files.length} 个文件`
  return ''
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
  // B4: 未配 Key 拦截 (ollama 本地免 key) - 提示并打开配置, 不发请求
  if (!aiSettings.apiKey && aiSettings.provider !== 'ollama') {
    ElMessage.warning('请先配置 API Key 再发送消息')
    openApiKeyDialog()
    return
  }
  inputText.value = ''
  chat.sendMessage(text)
}

function onProviderChange(pid) {
  if (pid === 'custom') {
    // 用户从下拉选 "自定义": 确保 customProviders[default] 存在再切到 custom:default
    if (!customProviders.get('default')) {
      customProviders.add({ id: 'default', name: '自定义', baseUrl: '', apiKey: '', protocol: 'openai' })
    }
    return aiSettings.setProvider('custom:default')
  }
  return aiSettings.setProvider(pid)
}

// 下拉值映射: custom:<uuid> 在选项列表中没有对应项, 显示 'custom' 占位 (Task 22 会改为图标分组)
const providerSelectValue = computed(() =>
  isCustomProvider(aiSettings.provider) ? 'custom' : aiSettings.provider,
)

// 模型能力徽章: 静态 (reasoning/context) + 运行时 vision 三态 (true/false/undefined)
function capOf(m) {
  const base = capabilityOf(aiSettings.provider, m)
  const baseUrl = aiSettings.getBaseUrl()
  return {
    ...base,
    vision: modelVision.hasVision(baseUrl, m),       // true/false/undefined
    pending: modelVision.isPending(baseUrl, m),
  }
}

// reasoning deep 按钮 disabled: 当前模型不支持原生 reasoning
const deepDisabled = computed(() =>
  capabilityOf(aiSettings.provider, aiSettings.model).reasoning !== 'native')

const deepDisabledTooltip = computed(() =>
  `当前模型 (${aiSettings.model}) 不支持原生推理；如需思考请用「快速/自动」+ 提示词`)

// #38 思考程度分段控件 (四档: off/default/high/max 递进)
const REASONING_OPTIONS = computed(() => [
  { label: '关闭', value: 'off', title: '关闭 - 不思考直接回答' },
  { label: '默认', value: 'default', title: '默认 - 由模型默认决定' },
  { label: '高', value: 'high', disabled: deepDisabled.value, title: deepDisabled.value ? deepDisabledTooltip.value : '高 - 增强思考' },
  { label: '最高', value: 'max', disabled: deepDisabled.value, title: deepDisabled.value ? deepDisabledTooltip.value : '最高 - 最充分思考' },
])

// ---- 附件上传 (Spec A 图片上传, 阶段PR-5) ----
// 仅 vision 确认 (===true) 的模型启用上传; false/undefined 禁用并提示
const fileInputRef = ref(null)

const visionState = computed(() => {
  const base = aiSettings.getBaseUrl()
  return modelVision.hasVision(base, aiSettings.model)   // true/false/undefined
})
const visionPending = computed(() => modelVision.isPending(aiSettings.getBaseUrl(), aiSettings.model))

const attachDisabled = computed(() => {
  if (chat.streaming) return true
  if (visionState.value === true) return false
  return true   // false / undefined → 都不允许点
})

const attachTooltip = computed(() => {
  if (visionState.value === true) return '上传图片 (≤5MB × ≤5)'
  if (visionState.value === false) return `当前模型不支持图像 (${aiSettings.model})`
  if (visionPending.value) return '正在检测视觉能力…'
  return '当前模型未知是否支持图像 (切换模型自动探测)'
})

function onAttachClick() {
  if (visionState.value !== true) return
  fileInputRef.value?.click()
}

async function onFilesPicked(e) {
  const files = Array.from(e.target.files || [])
  e.target.value = ''   // 允许选同名文件重传
  for (const f of files) {
    try { await chat.addAttachment(f) }
    catch (err) { ElMessage.error(err.message || '附件添加失败') }
  }
}

async function onDrop(e) {
  if (visionState.value !== true) {
    ElMessage.warning(attachTooltip.value)
    return
  }
  const files = Array.from(e.dataTransfer?.files || [])
  for (const f of files) {
    try { await chat.addAttachment(f) }
    catch (err) { ElMessage.error(err.message || '附件添加失败') }
  }
}

function formatBytes(n) {
  if (n < 1024) return `${n}B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)}KB`
  return `${(n / 1024 / 1024).toFixed(1)}MB`
}

// ---- API Key 设置对话框 (Electron 不支持 window.prompt, 用 el-dialog) ----
const apiKeyDialogVisible = ref(false)
const apiKeyInput = ref('')
const baseUrlInput = ref('')

function openApiKeyDialog() {
  apiKeyInput.value = aiSettings.apiKey || ''
  // baseUrl 来源: custom:<uuid> → customProviders entry; plain 'custom' → 空 (首次填写)
  if (isCustomProvider(aiSettings.provider)) {
    const cp = customProviders.get(customProviderUuid(aiSettings.provider))
    baseUrlInput.value = cp?.baseUrl || ''
  } else {
    baseUrlInput.value = ''
  }
  apiKeyDialogVisible.value = true
}

async function saveApiKey() {
  const key = apiKeyInput.value.trim()
  const url = baseUrlInput.value.trim()
  if (aiSettings.provider === 'custom') {
    // 首次配置自定义: 建 customProviders[default] 并切到 custom:default
    customProviders.add({
      id: 'default', name: '自定义', baseUrl: url, apiKey: key, protocol: 'openai',
    })
    await aiSettings.setProvider('custom:default')
  } else if (isCustomProvider(aiSettings.provider)) {
    const uuid = customProviderUuid(aiSettings.provider)
    customProviders.update(uuid, { baseUrl: url })
    await aiSettings.setApiKey(key)
  } else {
    await aiSettings.setApiKey(key)
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
  width: 100%; /* #25 宽度由外层 ResizablePanel 控制 */
  background: var(--km-bg-layer-0);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  height: 100%;
  border-left: 1px solid var(--km-border);
}

/* ---- 头部 ---- */
.quick-actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px; padding: 8px 12px; border-bottom: 1px solid var(--km-border-light); background: var(--km-bg-layer-1); }
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
  border-radius: var(--km-radius-sm);
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
.ph-icon-badge {
  width: 52px; height: 52px;
  display: flex; align-items: center; justify-content: center;
  border-radius: var(--km-radius-lg);
  background: var(--km-primary-light);
  color: var(--km-primary);
  box-shadow: 0 6px 18px -8px var(--km-primary, #3b82f6);
  margin-bottom: 4px;
}
.ph-title { font-size: 17px; font-weight: 600; color: var(--km-gray-700); margin-top: 6px; letter-spacing: 0.3px; }

/* ---- 消息 ---- */
.message {
  display: flex;
  position: relative;
  animation: msgIn 0.28s var(--km-ease-out);
}
@keyframes msgIn {
  from { opacity: 0; transform: translateY(6px) scale(0.99); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.msg-body {
  display: flex; gap: 8px;
  max-width: 100%;
}
.msg-body.user-msg { justify-content: flex-end; width: 100%; }

/* 助手消息 */
.assistant-msg { width: 100%; }
.msg-avatar {
  flex-shrink: 0; width: 26px; height: 26px;
  border-radius: 50%;
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
  color: var(--km-gray-600);
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
  color: var(--km-gray-600);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--km-font-ui);
}

/* 展开/收起过渡 (think / tool body) */
.expand-enter-active, .expand-leave-active {
  transition: opacity 0.22s var(--km-ease-out), transform 0.22s var(--km-ease-out);
}
.expand-enter-from, .expand-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.msg-content {
  flex: 1; min-width: 0;
  font-size: 13px; line-height: 1.65;
  color: var(--km-gray-700);
}
/* 助手消息软气泡 (Phase B: Codex 式质感 — 卡片底 + 细边框 + 左圆角朝向头像) */
.assistant-msg .msg-content {
  padding: 2px 0 0;
}
.msg-content :deep(pre) {
  max-height: 200px; overflow-y: auto;
  background: var(--km-gray-100);
  border: 1px solid var(--km-border-light);
  border-radius: var(--km-radius-sm);
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
/* 用户消息: 去 AI 味 - 轻底色块 (primary-light 主题自适应) + 深色文字 + 细边框, 右对齐 */
.user-text {
  background: var(--km-primary-light);
  color: var(--km-gray-700);
  border: 1px solid var(--km-border-light);
  padding: 8px 12px;
  border-radius: var(--km-radius-lg) var(--km-radius-lg) var(--km-radius-xs) var(--km-radius-lg);
  font-size: 13px; line-height: 1.5;
  white-space: pre-wrap; word-break: break-word;
  margin: 0;
  font-family: var(--km-font-ui);
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
  border-radius: var(--km-radius-sm); background: var(--km-info-light);
  display: flex; align-items: center; justify-content: center;
  color: var(--km-info);
}
.tool-header {
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 4px;
}
.tool-path {
  font-size: 11px;
  color: var(--km-gray-600);
  background: var(--km-gray-200);
  padding: 1px 6px;
  border-radius: var(--km-radius-xs);
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
  border-radius: var(--km-radius-xs);
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
  padding: 2px 4px;
  margin: 0 -4px;
  border-radius: var(--km-radius-xs);
  transition: background 0.15s var(--km-ease);
}
.tool-call-card .tool-header.clickable { cursor: pointer; }
.tool-call-card .tool-header.clickable:hover { background: var(--km-gray-100); }
.tool-call-card .tool-header.clickable:active { background: var(--km-gray-200); }
.tool-status {
  font-size: 11px;
  display: inline-flex; align-items: center; gap: 3px;
  white-space: nowrap;
}
.tool-status.pending    { color: var(--km-gray-400); }
.tool-status.in_progress { color: var(--km-info); animation: thinkPulse 1.2s ease-in-out infinite; }
.tool-status.completed  { color: var(--km-success, #67c23a); }
.tool-status.error      { color: var(--km-danger, #f56c6c); font-weight: 600; }
.tool-summary {
  font-size: 11px;
  color: var(--km-gray-600);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  min-width: 0;
}
.tool-chevron {
  margin-left: auto;
  flex-shrink: 0;
  color: var(--km-gray-400);
  transition: transform 0.2s var(--km-ease), color 0.15s var(--km-ease);
}
.tool-chevron.expanded { transform: rotate(90deg); }
.tool-call-card .tool-header.clickable:hover .tool-chevron { color: var(--km-gray-600); }
.tool-body { margin-top: 6px; }
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

/* ---- 输入区 (B5: 一体化大圆角输入框, 附件/模型/发送内嵌; 聚焦光圈) ---- */
.assistant-input {
  padding: 12px 14px;
  border-top: 1px solid var(--km-border-light);
  flex-shrink: 0;
  background: var(--km-bg-layer-0);
}
.input-box {
  border: 1px solid var(--km-border);
  border-radius: var(--km-radius);
  background: var(--km-bg-layer-2);
  padding: 6px 8px 8px;
  transition: border-color 0.25s var(--km-ease), box-shadow 0.25s var(--km-ease);
}
.input-box:hover {
  border-color: var(--km-border-focus);
}
.input-box:focus-within {
  border-color: var(--km-primary);
  box-shadow: 0 0 0 3px var(--km-primary-light);
}
.input-box .input-main :deep(.el-textarea__inner) {
  border: none;
  box-shadow: none;
  background: transparent;
  color: var(--km-gray-700);
  font-size: 13px;
  padding: 4px 6px 6px;
  border-radius: 0;
  line-height: 1.55;
}
.input-box .input-main :deep(.el-textarea__inner:focus) {
  border: none;
  box-shadow: none;
}
.input-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
}
/* 内嵌工具按钮 (附件/导学): 无边框图标钮, hover 浅底 */
.ib-tool {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 26px;
  min-width: 26px;
  padding: 0 7px;
  border: none;
  border-radius: var(--km-radius-xs);
  background: transparent;
  color: var(--km-gray-500);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s var(--km-ease), color 0.15s var(--km-ease);
}
.ib-tool:hover:not(:disabled) { background: var(--km-gray-100); color: var(--km-gray-700); }
.ib-tool:disabled { opacity: 0.4; cursor: not-allowed; }
.ib-tool.on { color: var(--km-primary); background: var(--km-primary-light); }
.ib-tool-label { font-size: 11px; font-weight: 600; }
.ib-right { margin-left: auto; display: flex; align-items: center; gap: 6px; }
/* 模型配置芯片: 收纳厂商/模型/思考模式/API Key, 内嵌输入框工具栏 (B5) */
.model-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 8px 0 6px;
  font-size: 12px;
  color: var(--km-gray-700);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--km-radius-sm);
  cursor: pointer;
  max-width: 200px;
  transition: all 0.2s var(--km-ease);
}
.model-chip:hover:not(:disabled) {
  background: var(--km-gray-100);
  border-color: var(--km-border);
}
.model-chip:disabled { opacity: 0.6; cursor: not-allowed; }
.model-chip.unset {
  color: var(--km-warning, #e6a23c);
}
.model-chip.unset:hover { border-color: var(--km-warning, #e6a23c); }
.model-chip .provider-icon { width: 14px; height: 14px; border-radius: var(--km-radius-xs); flex-shrink: 0; }
.model-chip-name {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}
.model-chip-caret { opacity: 0.45; flex-shrink: 0; }
/* 弹层内配置面板 */
.config-panel { display: flex; flex-direction: column; gap: 12px; }
.config-row { display: flex; flex-direction: column; gap: 5px; }
.config-row > label { font-size: 11px; color: var(--km-gray-500); font-weight: 500; }
.config-apikey {
  justify-content: flex-start;
  border-radius: var(--km-radius-sm);
  opacity: 0.85;
  transition: all 0.2s var(--km-ease);
}
.config-apikey.set {
  opacity: 1;
  background: var(--km-primary-light);
  border-color: var(--km-primary);
  color: var(--km-primary);
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
  border-radius: var(--km-radius-xs);
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
  border-radius: var(--km-radius-xs);
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
  border-radius: var(--km-radius-xs);
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
.issue-item code { background: var(--km-gray-200); padding: 0 4px; border-radius: var(--km-radius-xs); font-size: 11px; }
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
  color: var(--km-gray-600); border-radius: var(--km-radius-xs); width: 18px; height: 18px;
  cursor: pointer; font-size: 12px; line-height: 1; padding: 0;
}
.ver-btn:hover:not(:disabled) { border-color: var(--km-primary); color: var(--km-primary); }
.ver-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.ver-count { font-family: var(--km-font-mono); }

.regen-btn {
  position: absolute; right: 4px; bottom: 4px;
  border: 0; background: transparent; color: var(--km-gray-400);
  cursor: pointer; padding: 4px; border-radius: var(--km-radius-xs);
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

/* ---- 模型 select + 能力徽章 (Task 17) ---- */
.model-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.model-name { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.model-badges { display: inline-flex; gap: 4px; }
.model-badges .el-tag { padding: 0 6px; height: 18px; line-height: 18px; }

/* ---- 附件上传 (Spec A, 阶段PR-5; B5: 条带内嵌输入框顶部; 附件按钮移入工具栏 .ib-tool) ---- */
.attachments-strip {
  display: flex; flex-wrap: wrap; gap: 6px;
  padding: 2px 4px 6px;
}
.attachment-item {
  display: flex; align-items: center; gap: 6px;
  background: var(--km-bg-layer-1); padding: 2px 6px; border-radius: var(--km-radius-xs);
  border: 1px solid var(--el-border-color-lighter);
}
.attachment-item img { width: 32px; height: 32px; object-fit: cover; border-radius: var(--km-radius-xs); }
.attachment-meta { font-size: 12px; color: var(--el-text-color-secondary); max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ---- 用户消息附件缩略图 (Task 21) ---- */
.msg-attachments { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
.msg-attachment-thumb {
  width: 80px; height: 80px; object-fit: cover; border-radius: var(--km-radius-xs); cursor: zoom-in;
  border: 1px solid var(--el-border-color-lighter);
}

/* ---- 厂商下拉图标 (Task 22) ---- */
.provider-icon { width: 16px; height: 16px; object-fit: contain; vertical-align: middle; }
.provider-row { display: inline-flex; align-items: center; gap: 6px; }

/* ---- T4 wide 形态 (主区 chat 视图; issue-81: 左对话 + 右侧辅助面板双栏) ---- */
.assistant-panel.wide {
  border-left: 0;
  background: transparent;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-rows: auto auto 1fr auto;
  height: 100%;
  min-height: 0;
}
.assistant-panel.wide > *:not(.assistant-side) {
  grid-column: 1;
  justify-self: center;
  width: 100%;
  max-width: 760px;
  min-width: 0;
}
.assistant-panel.wide > .assistant-side {
  grid-column: 2;
  grid-row: 1 / -1;
  min-height: 0;
}
.assistant-panel.wide .assistant-header { background: transparent; }
.assistant-panel.wide .quick-actions { background: transparent; border-bottom: 0; padding: 10px 4px 0; }
.assistant-panel.wide .assistant-body { padding: 24px 8px; gap: 16px; }
.assistant-panel.wide .placeholder { padding: 48px 20px; }
/* 建议 chip */
.ph-chips { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin-top: 14px; }
.ph-chip {
  height: 32px;
  padding: 0 16px;
  font-size: 12.5px;
  color: var(--km-gray-700);
  background: var(--km-bg-layer-1);
  border: 1px solid var(--km-border);
  border-radius: var(--km-radius-lg); /* 胶囊 */
  cursor: pointer;
  transition: all 0.18s var(--km-ease);
}
.ph-chip:hover {
  color: var(--km-primary-active);
  border-color: var(--km-primary);
  background: var(--km-primary-light);
  transform: translateY(-1px);
}
/* 气泡: user 右对齐收窄, assistant 加大内边距 */
.assistant-panel.wide .user-msg .msg-content { max-width: 72%; }
.assistant-panel.wide .user-text { border-radius: var(--km-radius); padding: 10px 14px; font-size: 13.5px; }
.assistant-panel.wide .assistant-msg .msg-content { font-size: 14px; }
/* 输入区: 融入主区, 胶囊化 */
.assistant-panel.wide .assistant-input { background: transparent; border-top: 0; padding: 12px 4px 20px; }
.assistant-panel.wide .input-box {
  border-radius: var(--km-radius-lg);
  padding: 10px 12px 10px;
  box-shadow: var(--km-shadow-sm);
}
.assistant-panel.wide .input-box .input-main :deep(.el-textarea__inner) {
  padding: 6px 10px 8px;
  font-size: 13.5px;
}
.assistant-panel.wide .input-toolbar { margin-top: 8px; }
</style>
