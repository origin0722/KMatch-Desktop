<template>
  <div class="learning-page km-workbench">
    <!-- ============================================================ -->
    <!-- 空状态：尚未生成资源 -->
    <!-- ============================================================ -->
    <el-empty
      v-if="!hasResources"
      description="尚未生成学习资源"
      :image-size="120"
    >
      <template #description>
        <p class="empty-desc">
          讲义/实操/测试由「学情测评 → 获取针对性反馈」或 AI 助手「生成学习资源」产出（需配置 LLM）；
          联网资源另需 Tavily Key。
        </p>
      </template>
      <div class="empty-actions">
        <el-button
          v-if="store.profile && store.feedbackStrategy"
          type="primary"
          :loading="store.loading"
          @click="generateLecture"
        >生成学习资源 →</el-button>
        <el-button @click="sidebar.setView('learning-session')">前往学习会话</el-button>
      </div>
      <el-alert
        v-if="generateError"
        type="error"
        :title="generateError"
        :closable="true"
        show-icon
        class="gen-error"
        @close="generateError = null"
      />
    </el-empty>

    <!-- ============================================================ -->
    <!-- 有资源时 -->
    <!-- ============================================================ -->
    <template v-else>
      <!-- 资源摘要条 -->
      <div class="summary-bar">
        <el-tag
          v-for="type in resourceTypes"
          :key="type.key"
          :type="activeTab === type.key ? '' : 'info'"
          :effect="activeTab === type.key ? 'dark' : 'plain'"
          class="summary-tag"
        >
          {{ type.label }}: {{ countByType(type.key) }} 篇
        </el-tag>
        <span class="node-count">覆盖 {{ resourceNodeCount }} 个知识点</span>
      </div>

      <!-- 资源类型 Tab -->
      <el-tabs v-model="activeTab" class="resource-tabs">
        <!-- 讲义 -->
        <el-tab-pane label="分层讲义" name="lecture">
          <div v-if="lectureList.length === 0" class="empty-tab">
            <el-empty description="暂无讲义" :image-size="80">
              <template #description>
                <p class="empty-desc">
                  讲义由「学情测评 → 获取针对性反馈」或 AI 助手「生成学习资源」产出（需在设置中配置 LLM）；
                  联网资源另需 Tavily Key。
                </p>
              </template>
              <el-button
                v-if="store.profile && store.feedbackStrategy"
                type="primary"
                :loading="store.loading"
                @click="generateLecture"
              >生成分层讲义 →</el-button>
              <span v-else-if="store.profile" class="empty-desc muted">完成学情测评（答题提交）后即可生成讲义</span>
            </el-empty>
            <el-alert
              v-if="generateError"
              type="error"
              :title="generateError"
              :closable="true"
              show-icon
              class="gen-error"
              @close="generateError = null"
            />
          </div>
          <div v-else class="resource-list">
            <el-card
              v-for="(res, idx) in lectureList"
              :key="idx"
              shadow="never"
              class="resource-card"
            >
              <template #header>
                <div class="resource-card-header">
                  <span class="resource-title">{{ resTitle(res, idx) }}</span>
                  <el-tag
                    v-if="res.difficulty_level"
                    size="small"
                    :type="difficultyTagType(res.difficulty_level)"
                  >
                    {{ '⭐'.repeat(res.difficulty_level) }}
                  </el-tag>
                </div>
              </template>
              <div class="resource-body">
                <MarkdownViewer :content="res.content || ''" />
              </div>
              <div v-if="res.source_nodes?.length" class="source-nodes">
                <span class="source-label">溯源：</span>
                <el-tag
                  v-for="nodeId in res.source_nodes"
                  :key="nodeId"
                  size="small"
                  class="source-tag"
                  @click="goToNode(nodeId)"
                >
                  {{ nodeId }}
                </el-tag>
              </div>
            </el-card>
          </div>
        </el-tab-pane>

        <!-- 实操指南 -->
        <el-tab-pane label="实操指南" name="practice_guide">
          <div v-if="guideList.length === 0" class="empty-tab">
            <el-empty description="暂无实操指南" :image-size="80" />
          </div>
          <div v-else class="resource-list">
            <el-card
              v-for="(res, idx) in guideList"
              :key="idx"
              shadow="never"
              class="resource-card"
            >
              <template #header>
                <div class="resource-card-header">
                  <span class="resource-title">{{ resTitle(res, idx) }}</span>
                  <el-tag
                    v-if="res.difficulty_level"
                    size="small"
                    :type="difficultyTagType(res.difficulty_level)"
                  >
                    {{ '⭐'.repeat(res.difficulty_level) }}
                  </el-tag>
                </div>
              </template>
              <div class="resource-body">
                <ScaffoldGuide :content="res.content || ''" />
              </div>
              <div v-if="res.source_nodes?.length" class="source-nodes">
                <span class="source-label">溯源：</span>
                <el-tag
                  v-for="nodeId in res.source_nodes"
                  :key="nodeId"
                  size="small"
                  class="source-tag"
                  @click="goToNode(nodeId)"
                >
                  {{ nodeId }}
                </el-tag>
              </div>
            </el-card>
          </div>
        </el-tab-pane>

        <!-- 分阶测试题 -->
        <el-tab-pane label="分阶测试题" name="test">
          <div v-if="testList.length === 0" class="empty-tab">
            <el-empty description="暂无测试题" :image-size="80" />
          </div>
          <div v-else class="resource-list">
            <el-card
              v-for="(res, idx) in testList"
              :key="idx"
              shadow="never"
              class="resource-card"
            >
              <template #header>
                <div class="resource-card-header">
                  <span class="resource-title">{{ resTitle(res, idx) }}</span>
                  <el-tag
                    v-if="res.difficulty_level"
                    size="small"
                    :type="difficultyTagType(res.difficulty_level)"
                  >
                    {{ '⭐'.repeat(res.difficulty_level) }}
                  </el-tag>
                </div>
              </template>
              <div class="resource-body">
                <!-- 分阶测试题: 提交/显式对照前不渲染原文(生成原文内嵌 **答案**/**解析**,
                     避免答题前直接泄露答案); 其他资源正常渲染 -->
                <MarkdownViewer v-if="!isTestResource(res) || testRevealed(res)" :content="res.content || ''" />
              </div>
              <!-- 答题交互 (本地即时判分: 解析题目/选项/答案, 提交比对) -->
              <!-- 门控: parsedTest(res)?.parsed —— 只有能解析出题目+答案的资源才显示答题入口 (修复 issue-02) -->
              <div v-if="parsedTest(res)?.parsed" class="test-quiz">
                <template v-if="!testState(res).started">
                  <el-button type="primary" size="small" @click="startTest(res)">开始答题</el-button>
                  <span class="test-quiz-hint">{{ parsedTest(res).options.length ? `${parsedTest(res).options.length} 个选项` : '填空/代码题' }}</span>
                </template>
                <template v-else>
                  <div class="test-quiz-body">
                    <p class="tq-question">{{ parsedTest(res).question }}</p>
                    <el-radio-group v-if="parsedTest(res).options.length" v-model="testState(res).selected" class="tq-options">
                      <el-radio v-for="o in parsedTest(res).options" :key="o.key" :value="o.key" class="tq-option">
                        {{ o.text }}
                      </el-radio>
                    </el-radio-group>
                    <el-input v-else v-model="testState(res).selected" placeholder="输入你的答案" class="tq-fill" />
                    <div v-if="!testState(res).submitted" class="tq-actions">
                      <el-button type="primary" size="small" @click="submitTest(res)">提交答案</el-button>
                      <el-button size="small" @click="testState(res).reveal = true">直接看答案</el-button>
                    </div>
                    <div v-if="testState(res).submitted || testState(res).reveal" class="tq-result" :class="testState(res).correct === null ? 'neutral' : testState(res).correct ? 'ok' : 'bad'">
                      <template v-if="testState(res).submitted">
                        <b>{{ testState(res).correct ? '✓ 回答正确' : `✗ 回答错误, 正确答案 ${ansKey(parsedTest(res))}` }}</b>
                      </template>
                      <template v-else><b>参考答案: {{ ansKey(parsedTest(res)) }}</b></template>
                      <p v-if="parsedTest(res).explanation">{{ parsedTest(res).explanation }}</p>
                    </div>
                  </div>
                </template>
              </div>
              <div v-if="res.source_nodes?.length" class="source-nodes">
                <span class="source-label">溯源：</span>
                <el-tag
                  v-for="nodeId in res.source_nodes"
                  :key="nodeId"
                  size="small"
                  class="source-tag"
                  @click="goToNode(nodeId)"
                >
                  {{ nodeId }}
                </el-tag>
              </div>
            </el-card>
          </div>
        </el-tab-pane>

        <!-- 联网资源 (AI 助手 web_search 结果 + 页内直接搜索/批量丰富, transition-group 平滑入场) -->
        <el-tab-pane label="联网资源" name="web_link">
          <!-- 工具行: 任意搜索 + 按薄弱点批量丰富 + 薄弱点筛选 (让联网资源从几篇变十几篇且可追溯) -->
          <div class="web-tools">
            <el-input
              v-model="webQuery"
              placeholder="搜索任意知识点/技术… (如: Python 装饰器)"
              clearable
              :prefix-icon="Search"
              class="web-search-input"
              @keyup.enter="searchWeb"
            />
            <el-button type="primary" :loading="webSearching" @click="searchWeb">搜索</el-button>
            <el-button :loading="weakSearching" :disabled="!weakTopics.length" @click="searchWeakTopics">
              按薄弱点批量丰富
            </el-button>
            <el-button :type="webOnlyWeak ? 'warning' : ''" :disabled="!webList.length" @click="webOnlyWeak = !webOnlyWeak">
              {{ webOnlyWeak ? '显示全部' : '只看薄弱点' }}
            </el-button>
            <span v-if="weakTopics.length" class="web-weak-hint">
              {{ weakTopics.length }} 个薄弱点可搜
            </span>
          </div>

          <div v-if="webList.length === 0" class="empty-tab">
            <el-empty :description="webOnlyWeak ? '暂无匹配薄弱点的联网资源 — 试试「按薄弱点批量丰富」' : '尚无联网资源 — 在上方搜索, 或在 AI 助手中让它搜索某个知识点'" :image-size="80" />
          </div>
          <transition-group v-else name="res-flow" tag="div" class="resource-list">
            <el-card
              v-for="(res, idx) in webList"
              :key="res.url || idx"
              shadow="never"
              class="resource-card web-card"
            >
              <template #header>
                <div class="resource-card-header">
                  <span class="resource-title">{{ res.title || res.url }}</span>
                  <!-- issue-68: 命中画像薄弱点的联网资源打标识, 贴合度一目了然 -->
                  <el-tag v-if="isWeakResource(res)" size="small" type="warning">薄弱点</el-tag>
                  <el-tag size="small" type="success">🌐 联网</el-tag>
                </div>
              </template>
              <div class="resource-body web-snippet">{{ res.content || '(无摘要)' }}</div>
              <div class="web-actions">
                <code class="web-url">{{ res.url }}</code>
                <el-button size="small" type="primary" @click="openUrl(res.url)">打开 ↗</el-button>
              </div>
            </el-card>
          </transition-group>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup>
/**
 * KMatch 学习资源页 — 第4周字段对齐 + Markdown 渲染
 *
 * 数据源：assessment store → generatedContent.resources[]
 * 字段对齐：content_type / difficulty_level / content（后端实际字段名）
 * 渲染：MarkdownViewer 组件（marked）
 */
import { ref, computed, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { useAssessmentStore } from '@/stores/assessment'
import { useSidebarStore } from '@/stores/sidebar'
import { useLearningResourcesStore } from '@/stores/learningResources'
import { useAiSettingsStore } from '@/stores/aiSettings'
import { extractTitle, difficultyTagType, contentTypeLabel } from '@/utils/format'
import MarkdownViewer from '@/components/MarkdownViewer.vue'
import ScaffoldGuide from '@/components/ScaffoldGuide.vue'
import http from '@/api'

const store = useAssessmentStore()
const sidebar = useSidebarStore()
const learningRes = useLearningResourcesStore()
const aiSettings = useAiSettingsStore()

// ---------------------------------------------------------------
// 资源类型定义
// ---------------------------------------------------------------
const resourceTypes = [
  { key: 'lecture', label: '讲义' },
  { key: 'practice_guide', label: '实操指南' },
  { key: 'test', label: '测试题' },
  { key: 'web_link', label: '联网资源' },
]

const activeTab = ref('lecture')

// ---------------------------------------------------------------
// 从 store 取资源数据（字段对齐 backend content_generator）
// ---------------------------------------------------------------
const resources = computed(() => store.generatedContent?.resources || [])

// AI 联网搜索结果 (web_link, 来自 learningResources store, 独立于学情生成资源)
const webResources = computed(() => learningRes.webResources || [])

const hasResources = computed(() => resources.value.length > 0 || webResources.value.length > 0)

const resourceNodeCount = computed(() => store.generatedContent?.node_count ?? 0)

function countByType(type) {
  if (type === 'web_link') return webResources.value.length
  return resources.value.filter((r) => r.content_type === type).length
}

const lectureList = computed(() =>
  resources.value.filter((r) => r.content_type === 'lecture'),
)
const guideList = computed(() =>
  resources.value.filter((r) => r.content_type === 'practice_guide'),
)
const testList = computed(() =>
  resources.value.filter((r) => r.content_type === 'test'),
)
const webList = computed(() => {
  const all = webResources.value
  return webOnlyWeak.value ? all.filter((r) => isWeakResource(r)) : all
})

// ---- issue-68: 薄弱点标识与筛选 ----
const webOnlyWeak = ref(false)
const weakNodeIds = computed(() => new Set(
  (store.profile?.weak_topics || []).map((t) => t.node_id).filter(Boolean),
))
function isWeakResource(res) {
  return !!(res?.target_node_id && weakNodeIds.value.has(res.target_node_id))
}

// ---------------------------------------------------------------
// 资源标题：从 markdown 首行提取，fallback 到类型中文名+序号
// ---------------------------------------------------------------
function resTitle(res, idx) {
  const extracted = extractTitle(res.content)
  if (extracted) return extracted
  return `${contentTypeLabel(res.content_type)} #${idx + 1}`
}

function openUrl(url) {
  if (url) window.open(url, '_blank', 'noopener')
}

// ---------------------------------------------------------------
// 分层讲义生成 (Learning 页空态入口: 复用学情反馈链路, 无需回学习会话再点一次)
// 生成 lecture/practice_guide/test 三类资源并落入本页; 失败展示可读错误 (LLM 未配置等)
// ---------------------------------------------------------------
const generateError = ref(null)

async function generateLecture() {
  if (!store.profile || !store.feedbackStrategy || store.loading) return
  generateError.value = null
  store.error = null
  await store.fetchFeedback()
  // fetchFeedback 失败时把错误写入 store.error (不抛出), 此处转本地展示
  generateError.value = store.error
}

// ---------------------------------------------------------------
// 联网搜索 (资源页直接搜 + 按薄弱点批量丰富)
// ---------------------------------------------------------------
const webQuery = ref('')
const webSearching = ref(false)
const weakSearching = ref(false)

// 薄弱点列表 (学情画像 weak_topics, 名称映射到图谱可读名, 最多 5 个)
const weakTopics = computed(() => {
  const profile = store.profile || {}
  const path = store.knowledgeGraph?.learning_path || []
  const lookup = {}
  for (const n of path) if (n?.node_id) lookup[n.node_id] = n
  return (profile.weak_topics || []).slice(0, 5).map((t) => ({
    node_id: t?.node_id,
    name: (t?.node_id && lookup[t.node_id]?.name) || t?.node_id || '',
  })).filter((t) => t.node_id)
})

async function searchWeb() {
  const q = webQuery.value.trim()
  if (!q || webSearching.value) return
  webSearching.value = true
  try {
    const data = await http.post('/api/search/web', {
      query: q,
      max_results: 8,   // 上限 8, 让一次搜索更丰富
      tavily_key: aiSettings.tavilyKey || undefined,
    })
    learningRes.addWebResources(q, data?.results || [])
    if (!data?.results?.length) ElMessage.warning('没有搜到结果, 换个关键词试试')
    else ElMessage.success(`已添加 ${data.results.length} 篇联网资源`)
  } catch (e) {
    ElMessage.error(e?.message || '搜索失败, 请检查 Tavily Key 配置')
  } finally {
    webSearching.value = false
  }
}

async function searchWeakTopics() {
  if (weakSearching.value || !weakTopics.value.length) return
  weakSearching.value = true
  try {
    const data = await http.post('/api/search/weak-topics', {
      topics: weakTopics.value,
      max_per_topic: 3,
      direction: store.profile?.target_direction || undefined,
      tavily_key: aiSettings.tavilyKey || undefined,
    })
    learningRes.addFeedbackLinks(data?.results || [])
    const n = data?.results?.length || 0
    if (n) ElMessage.success(`已按 ${data.topics} 个薄弱点拉取 ${n} 篇学习资源`)
    else ElMessage.warning('没有搜到结果, 稍后再试')
  } catch (e) {
    ElMessage.error(e?.message || '批量搜索失败, 请检查 Tavily Key 配置')
  } finally {
    weakSearching.value = false
  }
}

// ---------------------------------------------------------------
// 分阶测试题 - 本地即时判分 (纯前端, 解析 markdown 题目/选项/答案)
// ---------------------------------------------------------------
// 解析 test 资源 content (生成器格式: **题目**：… / A. 选项 / **答案**：X / **解析**：…)
// 健壮化 (issue-02): 题目截断到 **答案** 之前; 答案支持选择题字母与非字母填空答案;
// 选项只取题干段内 (避免把答案/解析里的 A. 吞进来)
function parseTestContent(content) {
  const c = content || ''
  const qm = c.match(/\*\*\s*题目\s*\*\*[:：]\s*([\s\S]*?)(?=\n\s*\*\*\s*答案\s*\*\*|\n\s*[A-E][\.、．]|$)/)
  const question = qm?.[1]?.trim() || ''
  // 选项段 = 题干结束(qEnd) 到 **答案** 标记之间 (避免把答案/解析里的 A. 吞进来)
  const qEnd = qm ? qm.index + qm[0].length : 0
  const amIdx = c.search(/\*\*\s*答案\s*\*\*/)
  const optEnd = amIdx === -1 ? c.length : amIdx
  const optSlice = c.slice(qEnd, optEnd)
  const opts = []
  const re2 = /(?:^|\n)\s*([A-E])([\.、．])\s*([^\n]+)/g
  let mm
  while ((mm = re2.exec(optSlice))) {
    const text = mm[3].trim()
    if (text) opts.push({ key: mm[1], text })
  }
  // 答案: 选择题取字母归一; 填空/代码题取到行尾 (支持非字母答案, 如 -1 / 一句话)
  const am = c.match(/\*\*\s*答案\s*\*\*[:：]\s*([^\n*]+)/)
  let answer = (am?.[1] || '').trim()
  if (opts.length) {
    const letter = answer.match(/[A-Ea-e]/)
    answer = letter ? letter[0].toUpperCase() : ''
  }
  const em = c.match(/\*\*\s*解析\s*\*\*[:：]\s*([\s\S]*?)(?=\n\s*\*\w|$)/)
  const explanation = em?.[1]?.trim() || ''
  return {
    question,
    options: opts,
    answer,
    explanation,
    parsed: !!(question && answer),
  }
}

// per-resource 答题状态。
// 修复 issue-01: 状态对象必须经 reactive() 包装 (普通 Map+普通对象无依赖追踪,
// mutation 不触发 Vue 重渲染 → 答题交互"点了没反应")。
const testStates = new Map()
const parsedCache = new Map()
function _testId(res) {
  return res?.target_node_id || res?.content?.slice(0, 40) || 'q'
}
function testState(res) {
  const id = _testId(res)
  if (!testStates.has(id)) {
    testStates.set(id, reactive({ started: false, selected: '', submitted: false, correct: null, reveal: false }))
  }
  return testStates.get(id)
}

/** 分阶测试题资源 (答题交互门控: 提交/对照前隐藏原文, 防答案泄露) */
function isTestResource(res) {
  return res?.content_type === 'test'
}

function testRevealed(res) {
  const st = testState(res)
  return !isTestResource(res) || st.submitted || st.reveal
}
function parsedTest(res) {
  const id = _testId(res)
  if (!parsedCache.has(id)) parsedCache.set(id, parseTestContent(res?.content))
  return parsedCache.get(id)
}
function startTest(res) { testState(res).started = true }
function ansKey(p) { return p.answer || '—' }
function submitTest(res) {
  const st = testState(res)
  const p = parsedTest(res)
  const sel = String(st.selected || '').trim().toLowerCase()
  const ans = String(p.answer || '').trim().toLowerCase()
  if (p.options.length) {
    // 选择题: 选项字母精确匹配
    st.correct = !!sel && sel === ans
  } else {
    // 填空/代码题: 归一精确匹配 (多候选答案用 / 分隔; 不用 includes 子串, 避免误判)
    st.correct = !!sel && ans.split(/[／/]/).some((a) => a.trim().toLowerCase() === sel)
  }
  st.submitted = true
}

// ---------------------------------------------------------------
// 溯源节点跳转
// ---------------------------------------------------------------
function goToNode(nodeId) {
  // IDE 内切换至图谱视图 (query 暂不传递, 阶段2 起可增强)
  sidebar.setView('graph')
}
</script>

<style scoped>
.learning-page { padding: 0; display: flex; flex-direction: column; min-height: 0; }
/* issue-84: 空态 (无资源) 在卡片可视区域垂直+水平居中 */
.learning-page > .el-empty {
  flex: 1;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
}

/* ---- 摘要条 ---- */
.summary-bar {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 16px; flex-wrap: wrap;
}
.summary-tag { font-size: 13px; }
.node-count {
  margin-left: auto; color: var(--km-gray-500); font-size: 13px;
  font-family: var(--km-font-mono);
}

/* ---- 资源 Tab ---- */
.empty-tab { padding: 40px 0; }
.empty-desc { margin: 0 0 12px; font-size: 12px; color: var(--km-gray-500); line-height: 1.6; }
.empty-desc.muted { margin: 0; }
.empty-actions { display: flex; gap: 8px; justify-content: center; margin-top: 4px; }
.gen-error { margin-top: 12px; }

/* ---- 资源卡片列表 ---- */
.resource-list {
  display: flex; flex-direction: column; gap: 12px;
}
.resource-card :deep(.el-card) {
  --el-card-bg-color: var(--km-bg-layer-2);
  --el-card-border-color: var(--km-border-light);
}
.resource-card :deep(.el-card__header) {
  padding: 10px 16px;
  border-bottom: 1px solid var(--km-border-light);
}
.resource-card :deep(.el-card__body) { padding: 12px 16px; }
.resource-card-header {
  display: flex; align-items: center; gap: 10px;
}
.resource-title {
  font-weight: 600; font-size: 14px; flex: 1;
  color: var(--km-gray-800);
}

/* ---- 资源正文 ---- */
.resource-body { min-height: 40px; }

/* ---- 答题入口 ---- */
.quiz-action {
  margin-top: 10px; padding-top: 10px;
  border-top: 1px dashed var(--km-border);
}

/* ---- 溯源节点 ---- */
.source-nodes {
  margin-top: 10px; padding-top: 10px;
  border-top: 1px dashed var(--km-border);
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
}
.source-label {
  font-size: 12px; color: var(--km-gray-500); flex-shrink: 0;
}
.source-tag { cursor: pointer; font-size: 11px; }
.source-tag:hover { opacity: 0.8; }

/* ---- 答题占位 ---- */
.quiz-placeholder {
  background: var(--km-bg-layer-1);
  border-radius: var(--km-radius-sm);
  padding: 24px; text-align: center;
  color: var(--km-gray-500); font-size: 13px;
}
.quiz-placeholder ul {
  text-align: left; margin: 10px 0 0;
  padding-left: 20px; line-height: 1.8;
}

/* ---- 联网资源卡 ---- */
.web-tools {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 14px; flex-wrap: wrap;
}
.web-search-input { width: 280px; }
.web-weak-hint {
  font-size: 12px; color: var(--km-gray-500);
}
.web-card .web-snippet {
  font-size: 13px; color: var(--km-gray-600); line-height: 1.6;
}
.web-actions {
  display: flex; align-items: center; gap: 8px; margin-top: 10px;
}
.web-url {
  flex: 1; min-width: 0; font-size: 11px; color: var(--km-gray-500);
  background: var(--km-bg-layer-1); padding: 2px 8px; border-radius: 4px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* ---- 资源卡入场动画 (平滑生动, cubic-bezier 非线性, 非死板线性) ---- */
.res-flow-enter-active {
  transition: all 0.4s cubic-bezier(0.22, 1, 0.36, 1);
}
.res-flow-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 1, 1);
  position: absolute;
}
.res-flow-enter-from {
  opacity: 0; transform: translateY(12px) scale(0.98);
}
.res-flow-leave-to {
  opacity: 0; transform: translateX(20px);
}
.res-flow-move {
  transition: transform 0.4s cubic-bezier(0.22, 1, 0.36, 1);
}
@media (prefers-reduced-motion: reduce) {
  .res-flow-enter-active, .res-flow-leave-active, .res-flow-move { transition: none; }
}
</style>
