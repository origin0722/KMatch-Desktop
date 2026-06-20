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
        <span class="score-threshold">
          （阈值 {{ threshold }}%）
        </span>
      </div>
    </div>

    <!-- 四维度卡片 -->
    <div class="dimensions-grid">
      <el-card
        v-for="dim in dimensionList"
        :key="dim.key"
        :class="['dim-card', dim.scoreClass]"
        shadow="hover"
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
          <el-icon color="#52c41a"><CircleCheckFilled /></el-icon>
          <span>无问题</span>
        </div>
      </el-card>
    </div>

    <!-- 打回提示 -->
    <el-alert
      v-if="!passed && retryHint"
      :title="'打回原因'"
      :description="retryHint"
      type="warning"
      show-icon
      :closable="false"
    />
  </div>
</template>

<script setup>
/**
 * 内容审核报告面板
 *
 * 展示 review_results 对象:
 *   { passed, overall_score, dimensions, verdict, retry_hint, reviewed_at }
 *
 * dimensions 四维度（对齐 backend/app/agents/reviewer.py）:
 *   factual_accuracy (40%) / hallucination (30%) / logic_consistency (20%) / teaching_appropriateness (10%)
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

// --- 常量 ---

const DIM_META = {
  factual_accuracy:        { label: '事实准确性',   weight: '40%', order: 1 },
  hallucination:           { label: '幻觉检测',     weight: '30%', order: 2 },
  logic_consistency:       { label: '逻辑一致性',   weight: '20%', order: 3 },
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
  if (overallScore.value >= t) return '#52c41a'
  if (overallScore.value >= 0.6) return '#faad14'
  return '#f56c6c'
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
        progressColor: score >= 0.8 ? '#52c41a' : score >= 0.6 ? '#faad14' : '#f56c6c',
        scoreClass: score >= 0.8 ? 'score-good' : score >= 0.6 ? 'score-ok' : 'score-bad',
      }
    })
})
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
  background: #fafafa;
  border-radius: 8px;
}

.verdict-score {
  display: flex;
  align-items: center;
  flex: 1;
}

.score-label {
  color: #909399;
  font-size: 13px;
}

.score-value {
  font-size: 20px;
  font-weight: 700;
  color: #303133;
}

.score-threshold {
  color: #c0c4cc;
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

.dim-card.score-good { border-top: 3px solid #52c41a; }
.dim-card.score-ok   { border-top: 3px solid #faad14; }
.dim-card.score-bad  { border-top: 3px solid #f56c6c; }

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
  color: #606266;
}

.dim-no-issues {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #52c41a;
  font-size: 13px;
}
</style>
