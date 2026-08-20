<template>
  <section class="stage-card stage-quiz km-surface" :class="{ active: isActive }">
    <header class="stage-head">
      <span class="stage-no">02</span>
      <h4>学情答题</h4>
      <span v-if="store.phase === 'feedback'" class="stage-done">✓ 已完成</span>
    </header>
    <div class="stage-body">
      <!-- answering 阶段 -->
      <template v-if="store.phase === 'answering' && !store.loading">
        <div class="quiz-header">
          <div class="quiz-progress">
            <span class="progress-text">已答 {{ answeredCount }} / {{ store.pendingQuestions.length }} 题</span>
            <div class="progress-track"><div class="progress-fill" :style="{ width: progressPct + '%' }" /></div>
          </div>
          <el-button size="small" @click="store.backToInput()">← 返回</el-button>
        </div>
        <div v-for="(q, idx) in store.pendingQuestions" :key="idx" class="quiz-item" :class="{ answered: isAnswered(idx) }">
          <div class="quiz-question">
            <el-tag size="small" type="info">{{ idx + 1 }}</el-tag>
            <el-tag size="small">{{ typeLabel(q.type) }}</el-tag>
            <span class="q-text">{{ q.question }}</span>
          </div>
          <el-radio-group v-if="q.type === 'choice'" v-model="store.userAnswers[idx]" class="quiz-options">
            <el-radio v-for="opt in q.options" :key="opt" :value="optLabel(opt)" class="quiz-option">{{ opt }}</el-radio>
          </el-radio-group>
          <el-input v-else-if="q.type === 'fill'" v-model="store.userAnswers[idx]" placeholder="请输入答案" class="quiz-fill" />
          <el-input v-else v-model="store.userAnswers[idx]" type="textarea" :rows="3" placeholder="请输入答案" />
        </div>
        <div class="quiz-submit">
          <el-button type="primary" size="large" :disabled="answeredCount === 0" @click="handleSubmitAnswers">提交答题 →</el-button>
        </div>
        <!-- 判分失败/超时: 内联错误 + 重试, 不白屏不卡死 (成功则 phase 切 feedback) -->
        <div v-if="store.error" class="quiz-error">
          <el-alert type="error" :title="store.error" :closable="false" show-icon />
          <div class="quiz-error-actions">
            <el-button type="primary" size="small" @click="handleSubmitAnswers">重试提交</el-button>
            <el-button size="small" @click="store.backToInput()">返回修改</el-button>
          </div>
        </div>
      </template>

      <!-- feedback 阶段 -->
      <template v-if="store.phase === 'feedback'">
        <el-descriptions :column="3" border size="small" style="margin-bottom: 12px;">
          <el-descriptions-item label="正确率">
            {{ store.assessment?.correct_count }} / {{ store.assessment?.total_count }} ({{ (store.accuracy * 100).toFixed(0) }}%)
          </el-descriptions-item>
          <el-descriptions-item label="理论水平">{{ levelLabel(store.profile?.theory_level) }}</el-descriptions-item>
          <el-descriptions-item label="反馈策略">
            <el-tag :type="strategyTagType(store.feedbackStrategy)" size="small">{{ strategyLabel(store.feedbackStrategy) }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>
        <!-- 画像跨次进化: 本次相对上次的变化 -->
        <div v-if="store.profileDiff" class="profile-diff">
          <div class="pd-title">📈 画像进化 · 本次变化</div>
          <div class="pd-list">
            <span v-for="(p, i) in diffParts" :key="i" class="pd-item" :class="p.kind">{{ p.text }}</span>
            <span v-if="!diffParts.length" class="pd-none">掌握度稳定，无新增变化</span>
            <span v-if="staleCount" class="pd-item warn">⚠️ {{ staleCount }} 个知识点已超 30 天未重测，建议复习/重测</span>
          </div>
        </div>
        <div style="margin-bottom: 12px;">
          <ProfileRadar :profile="store.profile" />
        </div>
        <!-- 题目明细与错题回顾 (默认折叠, 展开看逐题对错) -->
        <el-collapse class="report-collapse" style="margin-bottom: 12px;">
          <el-collapse-item title="题目明细与错题回顾" name="report">
            <AssessmentReport :assessment="store.assessment" />
          </el-collapse-item>
        </el-collapse>
        <div class="feedback-actions">
          <el-button v-if="store.feedbackStrategy && !store.feedbackContent" size="small" type="primary" :loading="store.loading" @click="store.fetchFeedback()">
            获取针对性反馈 →
          </el-button>
          <el-button size="small" @click="store.reset()">重新测评</el-button>
        </div>
        <!-- #30 后续: 反馈内容已落入「学习资源」页 (Learning.vue), 此处只留轻提示 + 跳转 -->
        <div v-if="store.feedbackContent" class="feedback-done">
          <el-tag type="success" size="small" effect="dark">✓ 已生成</el-tag>
          <span class="feedback-done-text">
            共 {{ store.feedbackContent.resources?.length || 0 }} 份针对性内容（知识点 + 相关网址），已放入「学习资源」
          </span>
          <el-button size="small" type="primary" plain @click="openLearning()">在学习资源中查看 →</el-button>
        </div>
      </template>

      <!-- interactive loading: 按 phase 区分文案 (出题 / 判分 / 取反馈), 三阶段都不白屏 -->
      <div v-if="store.loading" class="quiz-loading" v-loading="true" :element-loading-text="loadingText"></div>    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'
import { useSessionStore } from '@/stores/session'
import AssessmentReport from '@/components/AssessmentReport.vue'
import ProfileRadar from '@/components/ProfileRadar.vue'

const store = useAssessmentStore()
const session = useSessionStore()
const isActive = computed(() => session.activeStage === 'quiz')

const answeredCount = computed(() => store.userAnswers.filter((a) => a && String(a).trim()).length)

// 加载等待计时: 判分/生成期间显示已等待秒数, 杜绝"卡死"错觉 (一直卡 = 无反馈)
const loadingElapsed = ref(0)
let _timer = null
watch(() => store.loading, (v) => {
  if (_timer) { clearInterval(_timer); _timer = null }
  loadingElapsed.value = 0
  if (v) _timer = setInterval(() => { loadingElapsed.value += 1 }, 1000)
})
onBeforeUnmount(() => { if (_timer) clearInterval(_timer) })

// loading 文案按阶段: 出题(idle, 新领域含建域) / 判分(answering) / 取反馈(feeddown) -- 内容生成只在提交答题之后
const loadingText = computed(() => {
  if (store.phase === 'answering') return `正在判分并生成学情画像…（已等待 ${loadingElapsed.value}s，最长约 1 分钟，超时会自动提示）`
  if (store.phase === 'feedback') return `正在生成针对性学习内容（约 1 分钟，含联网搜索；已等待 ${loadingElapsed.value}s）…`
  return '正在根据学习目标定制题目（若为新领域将检索资料并构建知识图谱，最长约 3 分钟）…'
})
const progressPct = computed(() => store.pendingQuestions.length ? (answeredCount.value / store.pendingQuestions.length) * 100 : 0)
function isAnswered(idx) { const a = store.userAnswers[idx]; return !!(a && String(a).trim()) }

function typeLabel(t) { return { choice: '选择题', fill: '填空题', code: '代码题', judge: '判断题' }[t] || t || '题' }
function optLabel(opt) { const m = String(opt).match(/^([A-Z])[.、．]/); return m ? m[1] : String(opt) }
function levelLabel(l) { return { 1: '零基础', 2: '入门', 3: '进阶', 4: '高级', 5: '专家' }[l] ?? `Lv.${l}` }
const STRATEGY = { advance: '进阶挑战（正确率高，提升难度）', remediate: '降维解释（正确率中等，换角度讲解）', scaffold: '补前置基础（正确率低，巩固基础）' }
function strategyLabel(s) { return STRATEGY[s] || s || '-' }
function strategyTagType(s) { return { advance: 'success', remediate: 'warning', scaffold: 'danger' }[s] || 'info' }

// 画像进化 diff 展示：diff.summary 计数 + recovered/regressed 节点名
const diffParts = computed(() => {
  const d = store.profileDiff
  if (!d || !d.summary) return []
  const parts = []
  const names = (k) => (Array.isArray(d[k]) && d[k].length ? d[k].join('、') : '')
  if (d.summary.recovered) parts.push({ kind: 'up', text: `✅ 恢复掌握 ×${d.summary.recovered}` + (names('recovered') ? `（${names('recovered')}）` : '') })
  if (d.summary.newly_known) parts.push({ kind: 'up', text: `✨ 新掌握 ×${d.summary.newly_known}` + (names('newly_known') ? `（${names('newly_known')}）` : '') })
  if (d.summary.newly_weak) parts.push({ kind: 'down', text: `🔻 新薄弱 ×${d.summary.newly_weak}` + (names('newly_weak') ? `（${names('newly_weak')}）` : '') })
  if (d.summary.regressed) parts.push({ kind: 'down', text: `⚠️ 掌握回落 ×${d.summary.regressed}` + (names('regressed') ? `（${names('regressed')}）` : '') })
  return parts
})

const staleCount = computed(() => {
  const p = store.profile
  const items = [...(p?.known_topics || []), ...(p?.weak_topics || [])]
  return items.filter((it) => it && it.recheck_due).length
})

async function handleSubmitAnswers() {
  const unanswered = store.userAnswers.filter((a) => !a || String(a).trim() === '').length
  if (unanswered === store.pendingQuestions.length) return
  await store.submitAssessmentAnswers()
}
function openLearning() {
  session.setSplitView('learning')
}
</script>

<style scoped>
.stage-card { border-left: 3px solid var(--km-border-light); border-radius: var(--km-radius); overflow: hidden; transition: border-color 0.3s var(--km-ease); }
.stage-card.active { border-left-color: var(--km-primary); }
.stage-head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--km-border-light); }
.stage-no { font-family: var(--km-font-mono); font-size: 12px; color: var(--km-gray-500); }
.stage-head h4 { margin: 0; font-size: 14px; color: var(--km-gray-800); }
.stage-done { margin-left: auto; color: var(--km-success); font-size: 12px; }
.stage-body { padding: 16px; }
.quiz-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }
.quiz-progress { flex: 1; display: flex; align-items: center; gap: 10px; }
.progress-text { font-size: 12px; color: var(--km-gray-600); white-space: nowrap; }
.progress-track { flex: 1; height: 6px; border-radius: 3px; background: var(--km-bg-layer-3); overflow: hidden; }
.progress-fill { height: 100%; border-radius: 3px; background: var(--km-primary); transition: width 0.3s var(--km-ease); }
.profile-diff { margin: 8px 0 12px; padding: 8px 12px; border: 1px solid var(--km-border-light); border-radius: var(--km-radius-sm); background: var(--km-bg-layer-2); }
.pd-title { font-size: 12px; font-weight: 650; color: var(--km-gray-700); margin-bottom: 6px; }
.pd-list { display: flex; flex-wrap: wrap; gap: 6px; }
.pd-item { font-size: 12px; padding: 2px 8px; border-radius: 8px; }
.pd-item.up { background: rgba(52,179,126,0.12); color: var(--km-success); }
.pd-item.down { background: rgba(217,139,60,0.14); color: #b9680d; }
.pd-item.warn { background: rgba(240,160,64,0.14); color: #b9680d; }
.pd-none { font-size: 12px; color: var(--km-gray-500); }
.quiz-item {
  padding: 14px 16px; margin-bottom: 10px;
  border: 1px solid var(--km-border-light); border-left: 3px solid var(--km-border-light);
  border-radius: var(--km-radius-sm); background: var(--km-bg-layer-2);
  transition: border-color 0.2s var(--km-ease), background 0.2s var(--km-ease);
}
.quiz-item.answered { border-left-color: var(--km-success); background: color-mix(in srgb, var(--km-success) 5%, var(--km-bg-layer-2)); }
.quiz-question { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 8px; font-size: 13px; }
.q-text { flex: 1; }
.quiz-options { display: flex; flex-direction: column; gap: 8px; padding-left: 28px; }
.quiz-option { margin-right: 0 !important; width: 100%; height: auto; }
.quiz-option :deep(.el-radio__label) { white-space: normal; word-break: break-word; line-height: 1.5; }
.quiz-fill { max-width: 360px; }
.quiz-submit { display: flex; gap: 12px; margin-top: 16px; }
.quiz-error { margin-top: 14px; display: flex; flex-direction: column; gap: 8px; }
.quiz-error-actions { display: flex; gap: 8px; }
.feedback-actions { display: flex; gap: 8px; margin-bottom: 12px; }
.feedback-done {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin-top: 12px; padding: 10px 12px;
  background: var(--km-bg-layer-1); border: 1px dashed var(--km-success);
  border-radius: var(--km-radius-sm);
}
.feedback-done-text { font-size: 13px; color: var(--km-gray-700); flex: 1; min-width: 180px; }
.quiz-loading { min-height: 140px; display: flex; align-items: center; justify-content: center; }
</style>
