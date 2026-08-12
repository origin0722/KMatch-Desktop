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
          <span>共 {{ store.pendingQuestions.length }} 题</span>
          <el-button size="small" @click="store.backToInput()">← 返回</el-button>
        </div>
        <div v-for="(q, idx) in store.pendingQuestions" :key="idx" class="quiz-item">
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
          <el-button type="primary" size="large" @click="handleSubmitAnswers">提交答题 →</el-button>
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
        <div v-if="store.feedbackContent" class="feedback-resources">
          <el-card v-for="(r, i) in (store.feedbackContent.resources || [])" :key="i" shadow="never" class="resource-item">
            <template #header>
              <el-tag size="small" :type="r.content_type === 'web_link' ? 'success' : ''">{{ contentTypeLabel(r.content_type) }}</el-tag>
              <span style="margin-left: 8px;">{{ r.title || r.target_node_id }}</span>
              <el-button v-if="r.content_type === 'web_link' && r.url" size="small" type="primary" link
                         class="web-link-btn" @click="openUrl(r.url)">打开网站 ↗</el-button>
            </template>
            <MarkdownViewer v-if="r.content_type !== 'web_link' && r.content_type !== 'practice_guide'" :content="r.content" />
            <ScaffoldGuide v-else-if="r.content_type === 'practice_guide'" :content="r.content" />
            <p v-else class="web-link-snippet">{{ r.content }}</p>
          </el-card>
        </div>
      </template>

      <!-- interactive loading (判分/取反馈, 不进阶段③) -->
      <div v-if="store.loading && store.phase !== 'answering'" class="quiz-loading" v-loading="true" element-loading-text="处理中…"></div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'
import { useSessionStore } from '@/stores/session'
import MarkdownViewer from '@/components/MarkdownViewer.vue'
import ScaffoldGuide from '@/components/ScaffoldGuide.vue'
import AssessmentReport from '@/components/AssessmentReport.vue'
import ProfileRadar from '@/components/ProfileRadar.vue'

const store = useAssessmentStore()
const session = useSessionStore()
const isActive = computed(() => session.activeStage === 'quiz')

function typeLabel(t) { return { choice: '选择题', fill: '填空题', code: '代码题', judge: '判断题' }[t] || t || '题' }
function optLabel(opt) { const m = String(opt).match(/^([A-Z])[.、．]/); return m ? m[1] : String(opt) }
function levelLabel(l) { return { 1: '零基础', 2: '入门', 3: '进阶', 4: '高级', 5: '专家' }[l] ?? `Lv.${l}` }
const STRATEGY = { advance: '进阶挑战（正确率高，提升难度）', remediate: '降维解释（正确率中等，换角度讲解）', scaffold: '补前置基础（正确率低，巩固基础）' }
function strategyLabel(s) { return STRATEGY[s] || s || '-' }
function strategyTagType(s) { return { advance: 'success', remediate: 'warning', scaffold: 'danger' }[s] || 'info' }
const CT = { lecture: '讲义', practice_guide: '实操指南', quiz: '测试题', explanation: '讲解', exercise: '练习', web_link: '相关网站' }
function contentTypeLabel(t) { return CT[t] || t || '资源' }

async function handleSubmitAnswers() {
  const unanswered = store.userAnswers.filter((a) => !a || String(a).trim() === '').length
  if (unanswered === store.pendingQuestions.length) return
  await store.submitAssessmentAnswers()
}
function openUrl(url) {
  if (url) window.open(url, '_blank', 'noopener')
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
.quiz-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.quiz-item { padding: 12px 0; border-bottom: 1px solid var(--km-border-light); }
.quiz-question { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 8px; font-size: 13px; }
.q-text { flex: 1; }
.quiz-options { display: flex; flex-direction: column; gap: 8px; padding-left: 28px; }
.quiz-option { margin-right: 0 !important; width: 100%; height: auto; }
.quiz-option :deep(.el-radio__label) { white-space: normal; word-break: break-word; line-height: 1.5; }
.quiz-fill { max-width: 360px; }
.quiz-submit { display: flex; gap: 12px; margin-top: 16px; }
.feedback-actions { display: flex; gap: 8px; margin-bottom: 12px; }
.feedback-resources { display: flex; flex-direction: column; gap: 12px; margin-top: 12px; }
.resource-item { background: var(--km-bg-layer-1); }
.quiz-loading { min-height: 140px; display: flex; align-items: center; justify-content: center; }
</style>
