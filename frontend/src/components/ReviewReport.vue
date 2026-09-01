<template>
  <div class="review-report">
    <!-- 审核结论 -->
    <div class="verdict-bar">
      <el-tag :type="passed ? 'success' : 'danger'" size="large" effect="dark">
        {{ passed ? '审核通过 ✓' : '审核不通过 ✗' }}
      </el-tag>
      <div class="verdict-score">
        <span class="score-label">综合得分</span>
        <el-progress
          :percentage="Math.round(overallScore * 100)"
          :color="scoreColor"
          :stroke-width="18"
          style="width: 160px; margin: 0 12px;"
        />
        <span class="score-value">{{ (overallScore * 100).toFixed(0) }}%</span>
        <span class="score-threshold">（阈值 {{ threshold }}%）</span>
      </div>
    </div>

    <!-- 四维度卡片 -->
    <div class="dimensions-grid">
      <el-card
        v-for="dim in dimensionList"
        :key="dim.key"
        :class="['dim-card', dim.scoreClass]"
        shadow="never"
      >
        <template #header>
          <div class="dim-header">
            <span>{{ dim.label }}</span>
            <el-tag :type="dim.tagType" size="small">{{ dim.weight }}</el-tag>
          </div>
        </template>
        <div class="dim-score">
          <el-progress
            :percentage="Math.round(dim.score * 100)"
            :color="dim.progressColor"
            :stroke-width="12"
            type="circle"
            :width="80"
          />
        </div>
        <div v-if="dim.issues.length" class="dim-issues">
          <div
            v-for="(issue, i) in dim.issues"
            :key="i"
            class="issue-item"
          >
            <el-tag :type="issue.severity === 'high' ? 'danger' : 'warning'" size="small">
              {{ issue.severity === 'high' ? '高' : '中' }}
            </el-tag>
            <span>{{ issue.problem }}</span>
          </div>
        </div>
        <div v-else class="dim-no-issues">
          <el-icon :color="scoreColors.good"><CircleCheckFilled /></el-icon>
          <span>无问题</span>
        </div>
      </el-card>
    </div>

    <!-- 申诉-复审辩论轨迹 (赛题(4)①: 生成↔审核辩论, reviewer 逐条裁定) -->
    <el-card v-if="rebuttalVerdicts.length" shadow="never" class="debate-card" data-test="debate-panel">
      <template #header>
        <div class="section-head">
          <span>⚖️ 申诉-复审（生成 Agent 举证 ↔ 审核 Agent 裁定）</span>
          <el-tag size="small" :type="acceptedCount === rebuttalVerdicts.length ? 'success' : 'warning'">
            采纳 {{ acceptedCount }}/{{ rebuttalVerdicts.length }}
          </el-tag>
        </div>
      </template>
      <div class="debate-list">
        <div v-for="(v, i) in rebuttalVerdicts" :key="i" class="debate-item">
          <el-tag :type="v.verdict === 'accepted' ? 'success' : 'danger'" size="small">
            {{ v.verdict === 'accepted' ? '申诉成立' : '申诉驳回' }}
          </el-tag>
          <div class="debate-body">
            <div class="debate-issue">{{ v.issue }}</div>
            <div class="debate-reason">{{ v.reason }}</div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 独立裁判盲判结论 (赛题(4)① 交叉验证: 裁判独立配置, 不输入生成过程/审核结论) -->
    <el-card v-if="judgeSummary" shadow="never" class="debate-card" data-test="judge-panel">
      <template #header>
        <div class="section-head">
          <span>🧑‍⚖️ 独立裁判盲判</span>
          <el-tag size="small" :type="judgeSummary.same_source ? 'warning' : 'success'">
            {{ judgeSummary.same_source ? '同源裁判（参考）' : '异源独立裁判' }}
          </el-tag>
        </div>
      </template>
      <div class="judge-stats">
        <el-tag type="success" size="small">锚定 {{ judgeSummary.grounded }}</el-tag>
        <el-tag type="danger" size="small">幻觉 {{ judgeSummary.hallucinated }}</el-tag>
        <el-tag type="info" size="small">无法核验 {{ judgeSummary.unverifiable }}</el-tag>
        <span class="judge-total">共 {{ judgeSummary.judged }} 条资源</span>
      </div>
      <div v-if="judgeVerdictIssues.length" class="debate-list">
        <div v-for="(v, i) in judgeVerdictIssues" :key="i" class="debate-item">
          <el-tag :type="v.verdict === 'hallucinated' ? 'danger' : 'info'" size="small">
            {{ v.verdict === 'hallucinated' ? '幻觉' : v.verdict }}
          </el-tag>
          <div class="debate-body"><div class="debate-reason">{{ v.reason }}</div></div>
        </div>
      </div>
    </el-card>

    <!-- 打回提示 -->
    <el-alert
      v-if="!passed && retryHint"
      title="打回原因"
      :description="retryHint"
      type="warning"
      show-icon
      :closable="false"
    />
  </div>
</template>

<script setup>
/**
 * 内容审核报告面板（阶段13 T2，借鉴源仓 KMatch）
 *
 * 展示 review_results 对象:
 *   { passed, overall_score, dimensions, verdict, retry_hint, reviewed_at }
 *
 * dimensions 四维度（对齐 backend/app/agents/reviewer.py）:
 *   factual_accuracy (40%) / hallucination (30%) / logic_consistency (20%) / teaching_appropriateness (10%)
 *
 * 进度色用 hex 常量 (el-progress :color 走 inline style, 不能读 CSS 变量),
 * 镜像 Dashboard THEME / --km-* token 保持全看板配色一致。
 */
import { computed } from 'vue'
import { CircleCheckFilled } from '@element-plus/icons-vue'

const props = defineProps({
  /** review_results 对象 */
  reviewResults: {
    type: Object,
    required: true,
  },
})

// 进度色常量 (镜像 --km-success/warning/danger, 与 Dashboard THEME 一致)
const scoreColors = {
  good: '#34b37e',
  ok: '#f0a040',
  bad: '#e05555',
}
function scoreToColor(score) {
  if (score >= 0.8) return scoreColors.good
  if (score >= 0.6) return scoreColors.ok
  return scoreColors.bad
}

// --- 常量 ---
const DIM_META = {
  factual_accuracy:         { label: '事实准确性',   weight: '40%', order: 1 },
  hallucination:            { label: '幻觉检测',     weight: '30%', order: 2 },
  logic_consistency:        { label: '逻辑一致性',   weight: '20%', order: 3 },
  teaching_appropriateness: { label: '教学适当性',   weight: '10%', order: 4 },
}

// --- 基础数据 ---
const passed = computed(() => props.reviewResults?.passed ?? false)
const overallScore = computed(() => props.reviewResults?.overall_score ?? 0)
const threshold = computed(() => {
  const t = props.reviewResults?.threshold
  return t != null ? (t * 100).toFixed(0) : '85'
})
const retryHint = computed(() => props.reviewResults?.retry_hint ?? '')

const scoreColor = computed(() => {
  const t = props.reviewResults?.threshold ?? 0.85
  if (overallScore.value >= t) return scoreColors.good
  if (overallScore.value >= 0.6) return scoreColors.ok
  return scoreColors.bad
})

// --- 四维度列表 ---
const dimensionList = computed(() => {
  const dims = props.reviewResults?.dimensions ?? {}
  return Object.entries(DIM_META)
    .sort(([, a], [, b]) => a.order - b.order)
    .map(([key, meta]) => {
      const data = dims[key] ?? { score: 0, issues: [] }
      const score = data.score ?? 0
      const issues = data.issues ?? []

      return {
        key,
        label: meta.label,
        weight: meta.weight,
        score,
        issues,
        tagType: score >= 0.8 ? 'success' : score >= 0.6 ? 'warning' : 'danger',
        progressColor: scoreToColor(score),
        scoreClass: score >= 0.8 ? 'score-good' : score >= 0.6 ? 'score-ok' : 'score-bad',
      }
    })
})

// --- 申诉-复审辩论 (赛题(4)①, reviewer rebuttal_verdicts) ---
const rebuttalVerdicts = computed(() => props.reviewResults?.rebuttal_verdicts ?? [])
const acceptedCount = computed(() => rebuttalVerdicts.value.filter((v) => v.verdict === 'accepted').length)

// --- 独立裁判盲判 (judge_summary, 仅报告回环产出) ---
const judgeSummary = computed(() => props.reviewResults?.judge_summary ?? null)
const judgeVerdictIssues = computed(() =>
  (judgeSummary.value?.verdicts ?? []).filter((v) => v.verdict !== 'grounded'))
</script>

<style scoped>
.review-report {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.verdict-bar {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 16px;
  background: var(--km-bg-layer-1);
  border-radius: var(--km-radius);
}

.verdict-score {
  display: flex;
  align-items: center;
  flex: 1;
}

.score-label {
  color: var(--km-gray-500);
  font-size: 13px;
}

.score-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--km-gray-800);
}

.score-threshold {
  color: var(--km-gray-400);
  font-size: 12px;
  margin-left: 8px;
}

.dimensions-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.dim-card {
  text-align: center;
}

.dim-card.score-good { border-top: 3px solid var(--km-success); }
.dim-card.score-ok   { border-top: 3px solid var(--km-warning); }
.dim-card.score-bad  { border-top: 3px solid var(--km-danger); }

.dim-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.dim-score {
  margin: 12px 0;
}

.dim-issues {
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.issue-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 13px;
  color: var(--km-gray-600);
}

.dim-no-issues {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--km-success);
  font-size: 13px;
}

/* 申诉-复审辩论 + 独立裁判 */
.section-head { display: flex; align-items: center; justify-content: space-between; }
.debate-list { display: flex; flex-direction: column; gap: 10px; }
.debate-item { display: flex; align-items: flex-start; gap: 8px; }
.debate-body { flex: 1; min-width: 0; }
.debate-issue { font-size: 13px; color: var(--km-gray-700); margin-bottom: 2px; }
.debate-reason { font-size: 12.5px; color: var(--km-gray-500); line-height: 1.5; }
.judge-stats { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.judge-total { font-size: 12px; color: var(--km-gray-500); }
</style>
