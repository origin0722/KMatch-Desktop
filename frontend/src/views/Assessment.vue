<template>
  <div class="assessment-page">
    <h3>学情测评</h3>

    <!-- ============================================================ -->
    <!-- 状态A: 测评输入区 -->
    <!-- ============================================================ -->
    <template v-if="!store.hasResults && !store.loading">
      <el-card class="input-card">
        <el-form
          :model="form"
          label-width="120px"
          label-position="left"
          @submit.prevent="handleStart"
        >
          <!-- 学习目标方向（问题1：预设按钮 + 自由输入） -->
          <el-form-item label="学习目标方向" required>
            <div class="preset-directions">
              <el-tag
                v-for="d in presetDirections"
                :key="d"
                :effect="form.targetDirection === d ? 'dark' : 'plain'"
                :type="form.targetDirection === d ? '' : 'info'"
                class="preset-tag"
                @click="form.targetDirection = d"
              >
                {{ d }}
              </el-tag>
            </div>
            <el-input
              v-model="form.targetDirection"
              placeholder="或自定义方向（如：Python 基础语法入门）"
              :maxlength="200"
              show-word-limit
              class="direction-input"
            />
          </el-form-item>

          <!-- 场景 -->
          <el-form-item label="场景">
            <el-select v-model="form.scene" style="width: 200px;">
              <el-option label="无项目技能训练" value="no_project" />
              <el-option label="有项目二次开发" value="with_project" />
            </el-select>
            <span class="hint-text">选择学习场景类型</span>
          </el-form-item>

          <!-- 操作按钮 -->
          <el-form-item>
            <el-button
              type="primary"
              size="large"
              :disabled="!canStart"
              @click="handleStart"
            >
              开始测评 →
            </el-button>
            <el-button
              size="large"
              @click="handleQuickDemo"
              :loading="store.loading"
            >
              ⚡ 快速体验（自动作答）
            </el-button>
            <span v-if="!canStart" class="hint-text">请选择或输入学习目标方向</span>
          </el-form-item>
        </el-form>
      </el-card>
    </template>

    <!-- ============================================================ -->
    <!-- Loading — SSE 流式进度（demo） / 阻塞等待（interactive） -->
    <!-- ============================================================ -->
    <el-card v-if="store.loading" class="loading-card">
      <!-- SSE 流式进度条 -->
      <template v-if="store.currentStep">
        <div class="stream-progress">
          <h4>Agent 协作中…</h4>
          <div class="step-list">
            <div
              v-for="step in progressSteps"
              :key="step.node"
              class="step-item"
              :class="{ active: step.active, done: step.done }"
            >
              <span class="step-icon">{{ step.done ? '✅' : step.active ? '⏳' : '○' }}</span>
              <span class="step-label">{{ step.label }}</span>
            </div>
          </div>
          <p class="step-message">{{ store.currentStep.message }}</p>
        </div>
      </template>

      <!-- interactive 阻塞等待（无 SSE 进度） -->
      <template v-else>
        <div class="loading-hint" v-loading="true" element-loading-text="Agent 协作中，请稍候…">
          <p>正在进行：学情检测 → 内容审核</p>
          <p class="sub-hint">LLM 出题、作答、判分、四维审核……预计 10-20 秒</p>
        </div>
      </template>
    </el-card>

    <!-- ============================================================ -->
    <!-- 错误 -->
    <!-- ============================================================ -->
    <el-alert
      v-if="store.error && !store.loading"
      title="测评失败"
      type="error"
      show-icon
      :closable="true"
      @close="store.error = null"
      style="margin-bottom: 16px;"
    >
      <template #default>
        <p style="margin: 0 0 8px;">{{ store.error }}</p>
        <el-button size="small" type="primary" @click="retry">重新测评</el-button>
      </template>
    </el-alert>

    <!-- ============================================================ -->
    <!-- 状态B: 测评报告区 -->
    <!-- ============================================================ -->
    <template v-if="store.hasResults">
      <!-- 头部信息 -->
      <div class="result-header">
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="会话 ID">{{ store.sessionId }}</el-descriptions-item>
          <el-descriptions-item label="画像 ID">{{ store.profile?.profile_id ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="审核结论">
            <el-tag :type="store.reviewPassed ? 'success' : 'danger'" size="small">
              {{ store.reviewPassed ? '通过' : '打回' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
        <el-button type="default" size="small" style="margin-top: 12px;" @click="store.reset()">
          ← 重新测评
        </el-button>
      </div>

      <!-- 报告三大块 -->
      <el-row :gutter="16" style="margin-top: 16px;">
        <el-col :span="8">
          <el-card>
            <template #header>能力画像（雷达图）</template>
            <ProfileRadar :profile="store.profile" />
          </el-card>
        </el-col>

        <el-col :span="8">
          <el-card>
            <template #header>画像概要</template>
            <el-descriptions :column="1" size="small" border>
              <el-descriptions-item label="理论水平">
                <el-tag>{{ levelLabel(store.profile?.theory_level) }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="实操能力">
                <el-tag>{{ levelLabel(store.profile?.practical_level) }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="学习风格">
                {{ styleLabel(store.profile?.learning_style) }}
              </el-descriptions-item>
              <el-descriptions-item label="学习节奏">
                {{ paceLabel(store.profile?.preferred_pace) }}
              </el-descriptions-item>
              <el-descriptions-item label="周投入时间">
                {{ store.profile?.time_per_week ?? '-' }} 小时
              </el-descriptions-item>
              <el-descriptions-item label="答题正确率">
                {{ (store.accuracy * 100).toFixed(0) }}%
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>

        <el-col :span="8">
          <el-card>
            <template #header>薄弱环节</template>
            <div v-if="store.profile?.weakness_areas?.length">
              <ul class="weakness-list">
                <li v-for="(area, idx) in store.profile.weakness_areas" :key="idx">{{ area }}</li>
              </ul>
            </div>
            <el-empty v-else description="暂无薄弱环节" :image-size="60" />
          </el-card>
        </el-col>
      </el-row>

      <!-- 掌握/薄弱节点 -->
      <el-row :gutter="16" style="margin-top: 16px;">
        <el-col :span="12">
          <el-card>
            <template #header>
              已掌握节点（{{ store.profile?.known_topics?.length ?? 0 }}）
            </template>
            <div v-if="store.profile?.known_topics?.length" class="topic-tags">
              <el-tag
                v-for="t in store.profile.known_topics"
                :key="t.node_id"
                :color="masteryColor(t.mastery)"
                effect="dark"
                size="default"
              >
                {{ t.node_id }} — {{ (t.mastery * 100).toFixed(0) }}%
              </el-tag>
            </div>
            <el-empty v-else description="暂无已掌握节点" :image-size="40" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card>
            <template #header>
              薄弱节点（{{ store.profile?.weak_topics?.length ?? 0 }}）
            </template>
            <div v-if="store.profile?.weak_topics?.length" class="topic-tags">
              <el-tag
                v-for="t in store.profile.weak_topics"
                :key="t.node_id"
                type="warning"
                size="default"
              >
                {{ t.node_id }} — {{ (t.mastery * 100).toFixed(0) }}%
                <el-tooltip
                  v-if="t.error_patterns?.length"
                  :content="t.error_patterns.join('；')"
                  placement="top"
                >
                  <el-icon style="margin-left: 4px;"><WarningFilled /></el-icon>
                </el-tooltip>
              </el-tag>
            </div>
            <el-empty v-else description="暂无薄弱节点" :image-size="40" />
          </el-card>
        </el-col>
      </el-row>

      <!-- 审核报告 -->
      <el-card style="margin-top: 16px;">
        <template #header>审核报告</template>
        <ReviewReport :review-results="store.reviewResults" />
      </el-card>

      <!-- 测评明细 -->
      <el-card style="margin-top: 16px;">
        <template #header>测评明细</template>
        <AssessmentReport :assessment="store.assessment" />
      </el-card>

      <!-- Agent 执行日志 -->
      <el-card style="margin-top: 16px;">
        <template #header>Agent 执行日志</template>
        <el-timeline v-if="store.orchestrationLog.length">
          <el-timeline-item
            v-for="(entry, idx) in store.orchestrationLog"
            :key="idx"
            :timestamp="parseLogTimestamp(entry)"
            placement="top"
            :type="logType(entry)"
            size="small"
          >
            {{ parseLogMessage(entry) }}
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无日志" :image-size="40" />
      </el-card>
    </template>
  </div>
</template>

<script setup>
/**
 * 学情测评页面
 *
 * W7③ 体验优化（对齐 docs/B端_测评页体验优化指引.md）:
 *   问题1 — 学习目标方向：6 个预设按钮 + 自由输入
 *   问题2 — 已掌握知识点：删除（由测评自动推断）
 *   问题3 — 测评模式：默认 interactive，"快速体验"按钮触发 demo SSE
 *   问题4 — 最大重试轮数：删除（内部调度参数，后端默认 3）
 *
 * SSE 流式进度（对齐 docs/B端_SSE流式测评对接.md）:
 *   demo 模式用 POST /assess/stream，实时展示节点进度，防 2-4min 超时
 */
import { ref, reactive, computed } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import { useAssessmentStore } from '@/stores/assessment'
import ProfileRadar from '@/components/ProfileRadar.vue'
import AssessmentReport from '@/components/AssessmentReport.vue'
import ReviewReport from '@/components/ReviewReport.vue'

const store = useAssessmentStore()

// ---------------------------------------------------------------
// 表单（只保留用户真正需要的字段）
// ---------------------------------------------------------------
const form = reactive({
  targetDirection: '',
  scene: 'no_project',
})

/** 预设方向（对齐知识库 6 个分类） */
const presetDirections = [
  'Python 基础语法入门',
  '数据结构与算法',
  '面向对象编程',
  'Python 进阶',
  '常用库与工具',
  '项目实战',
]

const canStart = computed(() => form.targetDirection.trim().length > 0)

// ---------------------------------------------------------------
// SSE 流式进度步骤定义
// ---------------------------------------------------------------
const PROGRESS_DEFS = [
  { node: 'diagnostics', label: '学情检测' },
  { node: 'reviewer', label: '内容审核' },
  { node: 'graph_controller', label: '图谱组装' },
  { node: 'content_generator', label: '内容生成' },
  { node: 'finish', label: '组装报告' },
]

const progressSteps = computed(() => {
  const current = store.currentStep?.node
  if (!current) return PROGRESS_DEFS.map((d) => ({ ...d, active: false, done: false }))
  let passed = true
  return PROGRESS_DEFS.map((d) => {
    if (d.node === current) {
      passed = false
      return { ...d, active: true, done: false }
    }
    return { ...d, active: false, done: passed }
  })
})

// ---------------------------------------------------------------
// 提交
// ---------------------------------------------------------------

/** interactive 模式 — 开始测评 */
async function handleStart() {
  if (!canStart.value) return
  await store.startAssessment({
    targetDirection: form.targetDirection.trim(),
    scene: form.scene,
  })
}

/** demo 模式 — 快速体验（SSE 流式） */
async function handleQuickDemo() {
  if (!canStart.value) return
  await store.startDemoStream({
    targetDirection: form.targetDirection.trim(),
    scene: form.scene,
  })
}

function retry() {
  store.reset()
}

// ---------------------------------------------------------------
// 展示工具
// ---------------------------------------------------------------
const LEVEL_LABELS = { 1: '零基础', 2: '入门', 3: '进阶', 4: '高级', 5: '专家' }
function levelLabel(level) {
  return LEVEL_LABELS[level] ?? `Lv.${level}`
}

const STYLE_LABELS = {
  visual: '视觉型（图表/视频）',
  auditory: '听觉型（讲解/讨论）',
  read_write: '阅读型（文档/笔记）',
  kinesthetic: '动手型（练习/实验）',
}
function styleLabel(style) {
  return STYLE_LABELS[style] ?? style ?? '-'
}

const PACE_LABELS = { slow: '慢速详细', normal: '正常节奏', fast: '快速挑战' }
function paceLabel(pace) {
  return PACE_LABELS[pace] ?? pace ?? '-'
}

function masteryColor(mastery) {
  if (mastery >= 0.8) return '#52c41a'
  if (mastery >= 0.5) return '#faad14'
  return '#f56c6c'
}

function parseLogTimestamp(entry) {
  const match = entry.match(/^\[([^\]]+)\]/)
  return match ? match[1] : entry.slice(0, 20)
}

function parseLogMessage(entry) {
  const idx = entry.indexOf('] ')
  return idx >= 0 ? entry.slice(idx + 2) : entry
}

function logType(entry) {
  if (entry.includes('✅')) return 'success'
  if (entry.includes('❌') || entry.includes('⚠️')) return 'warning'
  return 'primary'
}
</script>

<style scoped>
.assessment-page {
  max-width: 1200px;
  margin: 0 auto;
}

.assessment-page h3 {
  margin: 0 0 16px 0;
  color: #303133;
}

.input-card {
  max-width: 700px;
}

/* ---- 预设方向按钮 ---- */
.preset-directions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.preset-tag {
  cursor: pointer;
  font-size: 13px;
  user-select: none;
}
.preset-tag:hover {
  opacity: 0.85;
}
.direction-input {
  /* 自由输入紧跟预设按钮 */
}

.hint-text {
  margin-left: 12px;
  color: #c0c4cc;
  font-size: 13px;
}

/* ---- Loading: SSE 流式进度 ---- */
.loading-card {
  max-width: 700px;
}
.stream-progress {
  text-align: center;
  padding: 20px 0;
}
.stream-progress h4 {
  margin: 0 0 20px;
  font-size: 16px;
  color: #303133;
}
.step-list {
  display: flex;
  justify-content: center;
  gap: 0;
  margin-bottom: 20px;
}
.step-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #c0c4cc;
  min-width: 64px;
}
.step-item.active {
  color: #409eff;
  font-weight: 600;
}
.step-item.done {
  color: #67c23a;
}
.step-icon {
  font-size: 18px;
}
.step-label {
  white-space: nowrap;
}
.step-message {
  color: #909399;
  font-size: 14px;
  margin: 0;
}

/* ---- Loading: 阻塞等待 ---- */
.loading-hint {
  text-align: center;
  padding: 40px 0;
}
.loading-hint p {
  color: #909399;
}
.loading-hint .sub-hint {
  font-size: 13px;
  color: #c0c4cc;
  margin-top: 8px;
}

/* ---- 结果区 ---- */
.result-header {
  display: flex;
  flex-direction: column;
}

.weakness-list {
  padding-left: 20px;
  color: #606266;
  line-height: 2;
}

.topic-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
