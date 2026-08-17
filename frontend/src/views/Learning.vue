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
      <el-button type="primary" @click="sidebar.setView('learning-session')">
        前往学习会话
      </el-button>
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
            <el-empty description="暂无讲义" :image-size="80" />
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
                <MarkdownViewer :content="res.content || ''" />
              </div>
              <!-- 答题入口：第4周后半对接 interactive 流程 -->
              <div class="quiz-action">
                <el-button type="primary" size="small" @click="startQuiz(res)">
                  开始答题
                </el-button>
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
          <!-- 工具行: 任意搜索 + 按薄弱点批量丰富 (让联网资源从几篇变十几篇) -->
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
            <span v-if="weakTopics.length" class="web-weak-hint">
              {{ weakTopics.length }} 个薄弱点可搜
            </span>
          </div>

          <div v-if="webList.length === 0" class="empty-tab">
            <el-empty description="尚无联网资源 — 在上方搜索, 或在 AI 助手中让它搜索某个知识点" :image-size="80" />
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

    <!-- ============================================================ -->
    <!-- 答题对话框（第4周后半实现 QuizCard 组件） -->
    <!-- ============================================================ -->
    <el-dialog
      v-model="quizDialogVisible"
      :title="currentQuiz ? resTitle(currentQuiz, 0) : '答题'"
      width="700px"
      destroy-on-close
    >
      <div class="quiz-placeholder">
        <p>第4周后半实现：QuizCard 交互组件</p>
        <ul>
          <li>选择题 / 填空题 / 代码题 三种题型</li>
          <li>提交后展示判分结果与动态反馈（降维解释 / 进阶挑战）</li>
          <li>对接 POST /api/diagnostics/submit + /feedback</li>
        </ul>
      </div>
      <template #footer>
        <el-button @click="quizDialogVisible = false">关闭</el-button>
        <el-button type="primary" disabled>提交答案（待实现）</el-button>
      </template>
    </el-dialog>
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
import { ref, computed } from 'vue'
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
const webList = computed(() => webResources.value)

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
// 答题对话框
// ---------------------------------------------------------------
const quizDialogVisible = ref(false)
const currentQuiz = ref(null)

function startQuiz(res) {
  currentQuiz.value = res
  quizDialogVisible.value = true
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
.learning-page { padding: 0; }

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
