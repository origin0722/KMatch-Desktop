<template>
  <section class="stage-card stage-goal km-surface">
    <header class="stage-head">
      <span class="stage-no">01</span>
      <h4>目标设定</h4>
    </header>
    <div class="stage-body">
      <!-- #30: 学习目标方向压成一行 — 顶部胶囊标签 (点击即选) + 内联自定义输入, 不换行可横向滚动 -->
      <div class="direction-row">
        <el-tag
          v-for="d in presetDirections"
          :key="d"
          :effect="form.targetDirection === d ? 'dark' : 'plain'"
          :type="form.targetDirection === d ? 'primary' : 'info'"
          class="preset-tag"
          @click="form.targetDirection = d"
        >{{ d }}</el-tag>
        <el-input
          v-model="form.targetDirection"
          placeholder="自定义方向…"
          :maxlength="120"
          class="direction-input"
        />
      </div>
      <!-- W5 三维测评: VARK 学习风格快问卷 (可折叠可跳过 — 未答时画像带 style_source=default 占位) -->
      <div class="style-quiz">
        <button class="quiz-toggle" type="button" @click="quizOpen = !quizOpen">
          {{ quizOpen ? '▾' : '▸' }} 学习风格快问卷 (可选 · 5 题 · 让资源更贴合你的学习方式)
          <span v-if="quizAnswered" class="quiz-done">已答 {{ quizAnswered }}/5</span>
        </button>
        <div v-if="quizOpen" class="quiz-body">
          <div v-for="(q, qi) in QUIZ" :key="qi" class="quiz-q">
            <div class="quiz-q-text">{{ qi + 1 }}. {{ q.text }}</div>
            <div class="quiz-opts">
              <button
                v-for="o in q.options"
                :key="o.key"
                type="button"
                class="quiz-opt"
                :class="{ active: store.styleQuiz[qi] === o.key }"
                :title="o.label"
                @click="pick(qi, o.key)"
              >{{ o.label }}</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 赛题(2) 先验画像: 学习背景 + 投入节奏 (可选采集 — 学历/专业/年龄段/经验/学时让资源生成贴合背景) -->
      <div class="style-quiz">
        <button class="quiz-toggle" type="button" @click="bgOpen = !bgOpen">
          {{ bgOpen ? '▾' : '▸' }} 学习背景 · 投入节奏 (可选 · 让内容贴合你的背景与学时可投入)
          <span v-if="bgFilled" class="quiz-done">已填</span>
        </button>
        <div v-if="bgOpen" class="quiz-body bg-grid">
          <div class="bg-field"><span class="bg-label">教育背景</span>
            <el-select v-model="demo.education" placeholder="学历" clearable size="small" style="width: 150px" data-test="bg-education">
              <el-option v-for="e in EDU_OPTIONS" :key="e" :label="e" :value="e" />
            </el-select>
          </div>
          <div class="bg-field"><span class="bg-label">专业</span>
            <el-input v-model="demo.major" placeholder="如: 会计学 / 计算机科学, 可留空" size="small"
                      style="width: 230px" :maxlength="60" data-test="bg-major" />
          </div>
          <div class="bg-field"><span class="bg-label">年龄段</span>
            <el-select v-model="demo.age_range" placeholder="可选" clearable size="small" style="width: 110px" data-test="bg-age">
              <el-option v-for="a in AGE_OPTIONS" :key="a" :label="a" :value="a" />
            </el-select>
          </div>
          <div class="bg-field"><span class="bg-label">编程经验</span>
            <el-input-number v-model="demo.programming_experience_months" :min="0" :max="10000"
                             controls-position="right" size="small" style="width: 130px"
                             placeholder="月" data-test="bg-prog-months" />
          </div>
          <div class="bg-field"><span class="bg-label">Python 经验</span>
            <el-input-number v-model="demo.python_experience_months" :min="0" :max="10000"
                             controls-position="right" size="small" style="width: 130px"
                             placeholder="月" data-test="bg-py-months" />
          </div>
          <div class="bg-field"><span class="bg-label">每周可投入</span>
            <el-input-number v-model="pace.timePerWeek" :min="1" :max="168"
                             controls-position="right" size="small" style="width: 130px"
                             placeholder="小时" data-test="bg-hours-week" />
          </div>
          <div class="bg-field"><span class="bg-label">学习节奏</span>
            <el-select v-model="pace.preferredPace" placeholder="跟随推荐" clearable size="small" style="width: 140px" data-test="bg-pace">
              <el-option v-for="p in PACE_OPTIONS" :key="p.value" :label="p.label" :value="p.value" />
            </el-select>
          </div>
        </div>
      </div>

      <!-- #30 反馈: 学习会话是"无项目技能训练"场景一专属, 不暴露"有项目二次开发"选项 (场景二走项目图谱视图) -->
      <div class="control-row actions">
        <el-button type="primary" size="large" :disabled="!canStart" :loading="store.loading" @click="handleStart">
          开始测评 →
        </el-button>
        <span v-if="!canStart" class="hint-text">请选择或输入学习目标方向</span>
      </div>

      <!-- issue-65: 返回学习会话时题目仍在准备 → 明确展示在途状态, 不误以为卡住/重置 -->
      <div v-if="store.loading && store.phase === 'idle'" class="preparing-hint">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在准备「{{ form.targetDirection }}」的题目… 可先浏览其他功能，就绪后自动出题</span>
      </div>

      <!-- issue-65: 准备失败 → 目标卡内直接展示错误 + 重试 (此前静默无提示) -->
      <div v-if="store.error && store.phase === 'idle' && !store.loading" class="goal-error">
        <span class="err-text">{{ store.error }}</span>
        <el-button v-if="isAuthError(store.error)" size="small" @click="goSettings">前往设置</el-button>
        <el-button size="small" type="primary" @click="handleStart">重试测评</el-button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { reactive, ref, computed, onMounted, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useAssessmentStore } from '@/stores/assessment'
import { useSidebarStore } from '@/stores/sidebar'

const store = useAssessmentStore()
const sidebar = useSidebarStore()

// issue: 401/API Key 错误 → 给"前往设置"入口
function isAuthError(text) {
  return /401|API Key|api key/i.test(text || '')
}
function goSettings() { sidebar.setView('settings') }

// issue-65: 目标方向与 store 双向同步 — 优先恢复最近一次目标 (切视图返回不丢),
// 仅当从未选择过时才用引导预填值兜底
const form = reactive({ targetDirection: store.pendingTargetDirection || '' })
const presetDirections = [
  'Python 基础语法入门', '数据结构与算法', '面向对象编程',
  'Python 进阶', '常用库与工具', '项目实战',
  '机器学习入门', '数据分析与可视化', 'Web 后端开发',
  '数据库与缓存', '工程化实践',
]
const canStart = computed(() => form.targetDirection.trim().length > 0)

// P4: 引导选的方向 (kmatch-onboard-direction) 仅在本地表单为空时预填一次
onMounted(() => {
  if (form.targetDirection) return
  try {
    const dir = localStorage.getItem('kmatch-onboard-direction')
    if (dir) form.targetDirection = dir
  } catch { /* localStorage 不可用时忽略 */ }
})

// 用户改目标即时写回 store (供 StageGoal 重挂载恢复)
watch(() => form.targetDirection, (v) => {
  if (store.pendingTargetDirection !== v) store.pendingTargetDirection = v
})

async function handleStart() {
  if (!canStart.value) return
  // 学习会话固定场景一 (无项目技能训练), scene 默认 no_project
  await store.startAssessment({ targetDirection: form.targetDirection.trim(), scene: 'no_project' })
}

// ---- W5 三维测评: VARK 学习风格快问卷 ----
// v=视觉图示 / a=听觉讲解 / r=读写文字 / k=动手实操; 答案存 store.styleQuiz, submit 时上送
const QUIZ = [
  { text: '你更愿意用哪种方式了解一个新工具？', options: [
    { key: 'v', label: '看图示/流程图' }, { key: 'a', label: '听人讲解' },
    { key: 'r', label: '读文档' }, { key: 'k', label: '直接上手试' },
  ] },
  { text: '记概念时, 什么对你最有效？', options: [
    { key: 'v', label: '画成图' }, { key: 'a', label: '口述复述' },
    { key: 'r', label: '抄写笔记' }, { key: 'k', label: '做题练熟' },
  ] },
  { text: '遇到报错, 你的第一反应是？', options: [
    { key: 'v', label: '看调用关系图定位' }, { key: 'a', label: '找人讨论' },
    { key: 'r', label: '搜报错信息/读源码' }, { key: 'k', label: '改代码反复试' },
  ] },
  { text: '你偏好的教程节奏是？', options: [
    { key: 'v', label: '先看全景架构图' }, { key: 'a', label: '先听整体思路' },
    { key: 'r', label: '先通读章节目录' }, { key: 'k', label: '先跑通示例再说' },
  ] },
  { text: '学完一个知识点, 你通常靠什么巩固？', options: [
    { key: 'v', label: '画知识图谱/脑图' }, { key: 'a', label: '给别人讲一遍' },
    { key: 'r', label: '整理成笔记' }, { key: 'k', label: '写个小项目练手' },
  ] },
]
const quizOpen = ref(false)
// 防御: learning-session 等测试环境可能注入精简 store mock (无 styleQuiz 字段)
const quizAnswered = computed(() => (store.styleQuiz || []).filter(Boolean).length)

// ---- 赛题(2) 先验画像: 学习背景 + 投入节奏 (可选采集, 双向同步 store) ----
const EDU_OPTIONS = ['高中及以下', '大专', '本科', '硕士', '博士', '非科班自学者']
const AGE_OPTIONS = ['<18', '18-25', '26-35', '36+']
const PACE_OPTIONS = [
  { label: '跟随推荐 (normal)', value: 'normal' },
  { label: '稳扎稳打 (slow)', value: 'slow' },
  { label: '快速推进 (fast)', value: 'fast' },
]
const bgOpen = ref(false)
const demo = reactive({
  education: store.demographics?.education || '',
  major: store.demographics?.major || '',
  age_range: store.demographics?.age_range || '',
  programming_experience_months: store.demographics?.programming_experience_months ?? null,
  python_experience_months: store.demographics?.python_experience_months ?? null,
})
watch(demo, (v) => { store.demographics = { ...v } }, { deep: true })
// 画像字段真实化: 每周可投入学时 + 学习节奏 (0/空 → 后端默认 6/normal)
const pace = reactive({
  timePerWeek: store.timePerWeek || null,
  preferredPace: store.preferredPace || '',
})
watch(pace, (v) => { store.timePerWeek = v.timePerWeek; store.preferredPace = v.preferredPace }, { deep: true })
const bgFilled = computed(() =>
  !!(demo.education || demo.major || demo.age_range || demo.programming_experience_months
     || demo.python_experience_months || pace.timePerWeek || pace.preferredPace),
)

function pick(qi, key) {
  const cur = store.styleQuiz || []
  const next = [...cur]
  // 再点一次同选项 = 取消 (允许只答有把握的题)
  next[qi] = next[qi] === key ? undefined : key
  store.styleQuiz = next
}
</script>

<style scoped>
.stage-card { border-left: 3px solid var(--km-border-light); border-radius: var(--km-radius); overflow: hidden; }
.stage-head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--km-border-light); }
.stage-no { font-family: var(--km-font-mono); font-size: 12px; color: var(--km-gray-500); }
.stage-head h4 { margin: 0; font-size: 14px; color: var(--km-gray-800); }
.stage-body { padding: 16px; }

/* #30: 单行方向 — 胶囊 + 输入同行, 溢出横向滚动 (隐藏滚动条) */
.direction-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding-bottom: 2px; margin-bottom: 4px; }
.direction-row::-webkit-scrollbar { display: none; }
.preset-tag { cursor: pointer; font-size: 13px; user-select: none; flex-shrink: 0; margin: 0 !important; }
.preset-tag:hover { opacity: 0.85; }
.direction-input { flex: 1; min-width: 200px; }
.control-row { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
.field-label { font-size: 13px; font-weight: 600; color: var(--km-gray-700); flex-shrink: 0; }
.actions { margin-top: 16px; }
.hint-text { color: var(--km-gray-500); font-size: 13px; }
/* issue-65: 在途准备态提示 */
.preparing-hint {
  display: flex; align-items: center; gap: 8px;
  margin-top: 12px; padding: 10px 12px;
  border-radius: var(--km-radius-sm);
  background: rgba(108,124,224,0.08);
  color: var(--km-gray-600); font-size: 13px;
}
/* issue-65: 准备失败 → 错误 + 重试 */
.goal-error {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  margin-top: 12px; padding: 10px 12px;
  border-radius: var(--km-radius-sm);
  border: 1px solid color-mix(in srgb, var(--km-danger) 35%, transparent);
  background: color-mix(in srgb, var(--km-danger) 6%, transparent);
}
.err-text { flex: 1; min-width: 200px; font-size: 12.5px; color: var(--km-danger); }

/* W5: VARK 快问卷 (可折叠) */
.style-quiz { margin-top: 12px; border: 1px solid var(--km-border-light); border-radius: var(--km-radius-sm); }
.quiz-toggle {
  width: 100%; display: flex; align-items: center; gap: 6px;
  padding: 8px 12px; background: none; border: none; cursor: pointer;
  font-size: 12.5px; color: var(--km-gray-600); text-align: left;
}
.quiz-toggle:hover { background: rgba(108,124,224,0.05); }
.quiz-done { margin-left: auto; color: var(--km-success, #34b37e); font-size: 12px; }
.quiz-body { padding: 4px 12px 12px; display: grid; gap: 10px; }
.quiz-q-text { font-size: 12.5px; color: var(--km-gray-700); margin-bottom: 6px; }
.quiz-opts { display: flex; gap: 6px; flex-wrap: wrap; }
.quiz-opt {
  padding: 4px 10px; font-size: 12px; cursor: pointer;
  border: 1px solid var(--km-border-light); border-radius: 999px;
  background: none; color: var(--km-gray-600);
}
.quiz-opt:hover { border-color: var(--km-primary, #6c7ce0); }
.quiz-opt.active {
  border-color: var(--km-primary, #6c7ce0);
  background: color-mix(in srgb, var(--km-primary, #6c7ce0) 12%, transparent);
  color: var(--km-primary, #6c7ce0);
}
/* 学习背景 + 投入节奏 (可选采集) */
.bg-grid { display: flex; gap: 10px 12px; flex-wrap: wrap; align-items: center; }
.bg-field { display: inline-flex; align-items: center; gap: 6px; }
.bg-label { font-size: 12px; color: var(--km-gray-500); flex-shrink: 0; }
</style>
