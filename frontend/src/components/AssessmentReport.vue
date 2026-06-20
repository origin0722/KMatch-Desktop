<template>
  <div class="assessment-report">
    <!-- 汇总 -->
    <div class="summary-bar">
      <el-statistic title="正确 / 总题数" :value="`${correctCount} / ${totalCount}`" />
      <el-progress
        :percentage="Math.round(accuracy * 100)"
        :color="accuracyColor"
        :stroke-width="16"
        style="flex: 1; margin-left: 24px;"
      />
      <el-tag :type="accuracyTagType" size="large" style="margin-left: 16px;">
        {{ (accuracy * 100).toFixed(0) }}%
      </el-tag>
    </div>

    <!-- 按节点汇总 -->
    <div v-if="perNodeEntries.length" class="per-node-section">
      <h4>按知识点汇总</h4>
      <div class="node-tags">
        <el-tag
          v-for="[nid, results] in perNodeEntries"
          :key="nid"
          :type="nodeTagType(results)"
          size="default"
        >
          {{ nid }} — {{ nodeCorrect(results) }}/{{ results.length }} 正确
        </el-tag>
      </div>
    </div>

    <!-- 题目明细 -->
    <div class="questions-section">
      <h4>题目明细</h4>
      <el-collapse accordion>
        <el-collapse-item
          v-for="q in questionList"
          :key="q.index"
        >
          <template #title>
            <div class="question-title">
              <el-tag
                :type="gradeTagType(q.grade?.correct)"
                size="small"
                effect="dark"
              >
                {{ gradeLabel(q.grade?.correct) }}
              </el-tag>
              <el-tag size="small" style="margin: 0 8px;">{{ typeLabel(q.type) }}</el-tag>
              <el-tag size="small" type="warning">难度 {{ q.difficulty ?? '?' }}</el-tag>
              <span class="q-text">{{ q.question }}</span>
            </div>
          </template>
          <div class="question-detail">
            <p><strong>选项：</strong>{{ (q.options || ['对', '错']).join('  |  ') }}</p>
            <p>
              <strong>你的答案：</strong>
              <span :class="answerClass(q.grade?.correct)">{{ q.answer ?? '（未作答）' }}</span>
            </p>
            <p v-if="q.grade?.correct === false">
              <strong>正确答案：</strong>
              <span class="correct">{{ q.raw?.answer }}</span>
            </p>
            <p><strong>关联节点：</strong><el-tag size="small">{{ q.raw?.node_id }}</el-tag></p>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script setup>
/**
 * 测评明细面板
 *
 * 展示 assessment 对象: questions / answers / per_node / 正确率
 * 数据源: useAssessmentStore.assessment
 *    { questions, answers, per_node, correct_count, total_count }
 */
import { computed } from 'vue'

const props = defineProps({
  assessment: {
    type: Object,
    required: true,
  },
})

// --- 基础数据 ---
const totalCount = computed(() => props.assessment?.total_count ?? 0)
const correctCount = computed(() => props.assessment?.correct_count ?? 0)
const accuracy = computed(() =>
  totalCount.value ? correctCount.value / totalCount.value : 0,
)

// --- 颜色 ---
const accuracyColor = computed(() => {
  if (accuracy.value >= 0.8) return '#52c41a'
  if (accuracy.value >= 0.5) return '#faad14'
  return '#f56c6c'
})

const accuracyTagType = computed(() => {
  if (accuracy.value >= 0.8) return 'success'
  if (accuracy.value >= 0.5) return 'warning'
  return 'danger'
})

// --- 按节点汇总 ---
const perNode = computed(() => props.assessment?.per_node ?? {})
const perNodeEntries = computed(() => Object.entries(perNode.value))

// per_node 新结构: [{question_index, correct}, ...]
// 不能用 filter(Boolean) — 每个 grade 都是对象（truthy），会全部计入 → 永远满分。
function nodeCorrect(results) {
  return (results || []).filter(g => g && g.correct === true).length
}

function nodeTagType(results) {
  const ok = nodeCorrect(results)
  const n = (results || []).length
  if (n === 0) return 'info'
  if (ok === n) return 'success'
  if (ok > 0) return 'warning'
  return 'danger'
}

// --- 构建 question_index → grade 映射 ---
const questionGrades = computed(() => {
  const map = {}
  const perNode = props.assessment?.per_node ?? {}
  for (const [nid, grades] of Object.entries(perNode)) {
    for (const g of (grades || [])) {
      map[g.question_index] = { node_id: nid, correct: g.correct }
    }
  }
  return map
})

// --- 题目列表（合并作答 + 判分） ---
const questionList = computed(() => {
  const questions = props.assessment?.questions ?? []
  const answers = props.assessment?.answers ?? []

  return questions.map((q, idx) => ({
    index: idx,
    raw: q,
    question: q.question,
    type: q.type,
    difficulty: q.difficulty,
    options: q.options,
    answer: answers[idx] ?? null,  // BUG-029: 保留 null 让模板的 ?? 兜底生效（'' 不触发 ??）
    grade: { correct: questionGrades.value[idx]?.correct ?? null },
  }))
})

// --- 工具 ---
const TYPE_LABELS = { choice: '选择题', judge: '判断题', code: '代码题' }
function typeLabel(type) {
  return TYPE_LABELS[type] ?? type ?? '未知'
}

// BUG-019: 三态判断 — null=未评分, true=正确, false=错误
function gradeTagType(correct) {
  if (correct === true) return 'success'
  if (correct === false) return 'danger'
  return 'info'  // null / undefined → 未评分
}

function gradeLabel(correct) {
  if (correct === true) return '✓'
  if (correct === false) return '✗'
  return '?'  // 未评分
}

/** 答案文字颜色 — null 未评分时不划线 */
function answerClass(correct) {
  if (correct === true) return 'correct'
  if (correct === false) return 'wrong'
  return 'ungraded'
}
</script>

<style scoped>
.assessment-report {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.summary-bar {
  display: flex;
  align-items: center;
  padding: 16px;
  background: #fafafa;
  border-radius: 8px;
}

.per-node-section h4,
.questions-section h4 {
  margin: 0 0 12px 0;
  color: #303133;
}

.node-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.question-title {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
}

.q-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-left: 4px;
  color: #303133;
}

.question-detail {
  padding: 0 16px 8px;
  color: #606266;
  line-height: 2;
}

.correct  { color: #52c41a; font-weight: 600; }
.wrong    { color: #f56c6c; font-weight: 600; text-decoration: line-through; }
.ungraded { color: #909399; }
</style>
