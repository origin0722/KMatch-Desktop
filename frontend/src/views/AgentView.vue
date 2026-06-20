<template>
  <div class="agent-page">
    <!-- ============================================================ -->
    <!-- 页面标题栏 -->
    <!-- ============================================================ -->
    <div class="page-header">
      <h3>Agent 协同可视化</h3>
      <p class="page-desc">
        多智能体协同调度过程可视化，展示"辩论与交叉验证"的审核博弈闭环
      </p>
    </div>

    <!-- ============================================================ -->
    <!-- 空状态 -->
    <!-- ============================================================ -->
    <el-empty
      v-if="!hasLogs"
      description="完成学情测评后，可在此查看多 Agent 协同调度全过程"
      :image-size="120"
    >
      <el-button type="primary" @click="$router.push('/assessment')">
        前往学情测评
      </el-button>
    </el-empty>

    <!-- ============================================================ -->
    <!-- 有日志时 -->
    <!-- ============================================================ -->
    <template v-else>
      <!-- Agent 流转管道图 -->
      <el-card shadow="never" class="pipeline-card">
        <template #header>
          <span>🔄 调度流程</span>
          <el-tag
            :type="status.pipelineRunning.value ? 'warning' : 'success'"
            size="small"
            class="pipeline-status"
          >
            {{ status.pipelineRunning.value ? '运行中' : '已完成' }}
          </el-tag>
        </template>

        <div class="agent-pipeline">
          <template v-for="(agent, idx) in status.agentNodes.value" :key="agent.key">
            <!-- Agent 节点卡片 -->
            <div
              class="agent-node"
              :class="[`status-${agent.status}`, { active: agent.status === 'running' }]"
              @click="selectedAgent = agent"
            >
              <div class="agent-icon">{{ agent.icon }}</div>
              <div class="agent-name">{{ agent.label }}</div>
              <div class="agent-status-tag">
                <el-tag :type="statusTagType(agent.status)" size="small" disable-transitions>
                  {{ statusLabel(agent.status) }}
                </el-tag>
              </div>
              <div v-if="agent.retryCount > 0" class="retry-badge">
                🔄{{ agent.retryCount }}
              </div>
            </div>

            <!-- 流转箭头（最后一个不渲染） -->
            <div v-if="idx < status.agentNodes.value.length - 1" class="agent-arrow">
              <span class="arrow-line">→</span>
              <!-- reviewer → content_generator 打回路径 -->
              <span v-if="agent.key === 'reviewer' && agent.retryCount > 0" class="reject-path">
                ← 打回
              </span>
            </div>
          </template>
        </div>
      </el-card>

      <!-- 下半区：详情面板 + 日志 -->
      <div class="bottom-area">
        <!-- Agent 详情面板 -->
        <el-card shadow="never" class="detail-card" v-if="selectedAgent">
          <template #header>
            <span>{{ selectedAgent.icon }} {{ selectedAgent.label }} — 详情</span>
          </template>
          <div class="agent-detail">
            <div class="detail-row">
              <span class="detail-label">状态</span>
              <el-tag :type="statusTagType(selectedAgent.status)" size="small">
                {{ statusLabel(selectedAgent.status) }}
              </el-tag>
            </div>
            <div class="detail-row">
              <span class="detail-label">职责</span>
              <span class="detail-value">{{ selectedAgent.role }}</span>
            </div>
            <div class="detail-row" v-if="selectedAgent.retryCount > 0">
              <span class="detail-label">打回次数</span>
              <span class="detail-value">{{ selectedAgent.retryCount }} 次</span>
            </div>

            <!-- 各 Agent 专属数据 -->
            <template v-if="selectedAgent.key === 'diagnostics' && store.assessment">
              <el-divider />
              <div class="detail-row">
                <span class="detail-label">答题正确率</span>
                <span class="detail-value">{{ (store.accuracy * 100).toFixed(0) }}%</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">总题数</span>
                <span class="detail-value">{{ store.assessment.total_count ?? '--' }}</span>
              </div>
            </template>

            <template v-if="selectedAgent.key === 'reviewer' && store.reviewResults">
              <el-divider />
              <div class="detail-row">
                <span class="detail-label">审核总分</span>
                <span class="detail-value">{{ ((store.reviewResults.overall_score ?? 0) * 100).toFixed(0) }}%</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">阈值</span>
                <span class="detail-value">{{ ((store.reviewResults.threshold ?? 0) * 100).toFixed(0) }}%</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">判定</span>
                <el-tag
                  :type="store.reviewResults.passed ? 'success' : 'danger'"
                  size="small"
                >
                  {{ store.reviewResults.passed ? '通过' : '打回' }}
                </el-tag>
              </div>
              <div v-if="store.reviewResults.retry_hint" class="retry-hint">
                {{ store.reviewResults.retry_hint }}
              </div>
            </template>

            <template v-if="selectedAgent.key === 'graph_controller' && store.knowledgeGraph">
              <el-divider />
              <div class="detail-row">
                <span class="detail-label">路径节点</span>
                <span class="detail-value">{{ store.knowledgeGraph.learning_path?.length ?? 0 }} 个</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">预计学时</span>
                <span class="detail-value">{{ store.knowledgeGraph.estimated_total_hours ?? '--' }}h</span>
              </div>
            </template>

            <template v-if="selectedAgent.key === 'content_generator' && store.generatedContent">
              <el-divider />
              <div class="detail-row">
                <span class="detail-label">生成资源</span>
                <span class="detail-value">{{ store.generatedContent.resources?.length ?? 0 }} 段</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">覆盖节点</span>
                <span class="detail-value">{{ store.generatedContent.node_count ?? 0 }} 个</span>
              </div>
            </template>
          </div>
        </el-card>

        <el-card v-else shadow="never" class="detail-card">
          <template #header>
            <span>📋 Agent 详情</span>
          </template>
          <el-empty description="点击上方 Agent 节点查看详情" :image-size="50" />
        </el-card>

        <!-- 运行日志面板 -->
        <el-card shadow="never" class="log-card">
          <template #header>
            <div class="log-header">
              <span>📜 运行日志</span>
              <el-button size="small" text @click="logAutoScroll = !logAutoScroll">
                {{ logAutoScroll ? '自动滚动' : '手动' }}
              </el-button>
            </div>
          </template>
          <div ref="logContainer" class="log-body">
            <div
              v-for="(entry, idx) in parsedLogs"
              :key="idx"
              class="log-entry"
              :class="{ 'log-reject': entry.isReject }"
            >
              <span class="log-time">{{ entry.time }}</span>
              <span class="log-msg">{{ entry.msg }}</span>
            </div>
          </div>
        </el-card>
      </div>
    </template>
  </div>
</template>

<script setup>
/**
 * KMatch Agent 协同可视化页 — 第4周日志驱动
 *
 * 数据源：assessment store → orchestrationLog[]
 * 状态推导：useAgentStatus composable
 * 详情面板：展示各 Agent 对应的 store 数据
 */
import { ref, computed, watch, nextTick } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'
import { useAgentStatus } from '@/composables/useAgentStatus'

const store = useAssessmentStore()
const status = useAgentStatus()

// ---------------------------------------------------------------
// 状态
// ---------------------------------------------------------------
const selectedAgent = ref(null)
const logAutoScroll = ref(true)
const logContainer = ref(null)

// ---------------------------------------------------------------
// 日志
// ---------------------------------------------------------------
const rawLogs = computed(() => store.orchestrationLog || [])
const hasLogs = computed(() => rawLogs.value.length > 0)

/** 解析后的日志：连续无时间戳行继承上行时间 */
const parsedLogs = computed(() => {
  const result = []
  let lastTime = ''
  for (const entry of rawLogs.value) {
    const m = entry?.match(/^\[(.+?)\]/)
    const time = m ? m[1] : lastTime
    const msgStart = entry?.indexOf('] ')
    const msg = msgStart >= 0 ? entry.slice(msgStart + 2) : entry
    lastTime = time
    result.push({
      time,
      msg,
      isReject: entry.includes('❌') || entry.includes('打回'),
    })
  }
  return result
})

watch(parsedLogs, async () => {
  if (logAutoScroll.value && logContainer.value) {
    await nextTick()
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
})

// ---------------------------------------------------------------
// 状态映射
// ---------------------------------------------------------------
function statusLabel(s) {
  return { idle: '待命', running: '执行中', done: '完成', failed: '失败' }[s] || s
}
function statusTagType(s) {
  return { idle: 'info', running: 'warning', done: 'success', failed: 'danger' }[s] || 'info'
}
</script>

<style scoped>
.agent-page { padding: 0; }

/* ---- 页面标题 ---- */
.page-header { margin-bottom: 16px; }
.page-header h3 { margin: 0 0 4px; font-size: 20px; }
.page-desc { margin: 0; color: #909399; font-size: 13px; }

/* ---- 管道图 ---- */
.pipeline-card { margin-bottom: 16px; }
.pipeline-card :deep(.el-card__header) {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 16px; font-weight: 600;
}
.pipeline-status { margin-left: auto; }

.agent-pipeline {
  display: flex; align-items: flex-start; gap: 0;
  padding: 16px 8px; overflow-x: auto;
}

/* Agent 节点卡片 */
.agent-node {
  flex-shrink: 0; width: 110px; padding: 12px 8px;
  border-radius: 8px; border: 2px solid #e4e7ed;
  background: #fff; text-align: center; cursor: pointer;
  transition: all 0.2s;
}
.agent-node:hover {
  border-color: #409eff; box-shadow: 0 2px 8px rgba(64,158,255,0.15);
}
.agent-node.active {
  border-color: #409eff; animation: pulse 1.2s ease-in-out infinite;
}
.agent-node.status-done   { border-color: #67c23a; background: #f0f9eb; }
.agent-node.status-failed { border-color: #f56c6c; background: #fef0f0; }
.agent-node.status-running { border-color: #e6a23c; background: #fdf6ec; }
.agent-icon   { font-size: 24px; margin-bottom: 6px; }
.agent-name   { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.agent-status-tag { margin-bottom: 4px; }
.retry-badge  { font-size: 11px; color: #e6a23c; font-weight: 600; }

/* 流转箭头 */
.agent-arrow {
  flex-shrink: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: 0 6px; min-width: 40px; position: relative;
}
.arrow-line  { font-size: 20px; color: #c0c4cc; font-weight: 300; line-height: 1; }
.reject-path {
  font-size: 10px; color: #f56c6c; background: #fef0f0;
  padding: 1px 4px; border-radius: 3px; margin-top: 2px; white-space: nowrap;
}

@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(64,158,255,0.3); }
  50%      { box-shadow: 0 0 0 6px rgba(64,158,255,0); }
}

/* ---- 下半区 ---- */
.bottom-area { display: flex; gap: 16px; min-height: 300px; }

/* 详情面板 */
.detail-card { width: 340px; flex-shrink: 0; }
.detail-card :deep(.el-card__header) {
  padding: 10px 16px; font-weight: 600; font-size: 14px;
}
.detail-card :deep(.el-card__body) { padding: 12px 16px; }
.agent-detail { display: flex; flex-direction: column; gap: 10px; }
.detail-row {
  display: flex; align-items: center; gap: 8px; font-size: 13px;
}
.detail-label { color: #909399; width: 64px; flex-shrink: 0; }
.detail-value { color: #303133; }
.retry-hint {
  font-size: 12px; color: #f56c6c; background: #fef0f0;
  padding: 6px 8px; border-radius: 4px; line-height: 1.5;
}

/* 日志面板 */
.log-card { flex: 1; min-width: 0; }
.log-card :deep(.el-card__header) { padding: 10px 16px; }
.log-card :deep(.el-card__body) { padding: 0; }
.log-header {
  display: flex; align-items: center; font-weight: 600; font-size: 14px;
}
.log-header .el-button { margin-left: auto; }
.log-body {
  height: 260px; overflow-y: auto; padding: 10px 16px;
  font-family: 'Cascadia Code','Fira Code','Consolas',monospace;
  font-size: 12px; line-height: 1.8; background: #fafafa;
}
.log-entry {
  display: flex; gap: 10px; padding: 2px 0;
  border-bottom: 1px solid #f0f0f0;
}
.log-entry.log-reject {
  background: #fef0f0; margin: 0 -16px;
  padding-left: 16px; padding-right: 16px;
}
.log-time { color: #909399; flex-shrink: 0; }
.log-msg  { color: #303133; word-break: break-all; }
</style>
