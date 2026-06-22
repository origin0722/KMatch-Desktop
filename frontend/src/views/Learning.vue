<template>
  <div class="learning-page km-workbench">
    <!-- ============================================================ -->
    <!-- 页面标题栏 (km-workbench-header) -->
    <!-- ============================================================ -->
    <div class="km-workbench-header">
      <div>
        <p class="km-workbench-kicker">learning resources</p>
        <h3 class="km-workbench-title">学习资源</h3>
        <p class="km-workbench-desc">
          基于知识图谱与学情画像生成的个性化学习资源，每项内容可溯源至图谱节点
        </p>
      </div>
    </div>

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
import { useAssessmentStore } from '@/stores/assessment'
import { useSidebarStore } from '@/stores/sidebar'
import { extractTitle, difficultyTagType, contentTypeLabel } from '@/utils/format'
import MarkdownViewer from '@/components/MarkdownViewer.vue'

const store = useAssessmentStore()
const sidebar = useSidebarStore()

// ---------------------------------------------------------------
// 资源类型定义
// ---------------------------------------------------------------
const resourceTypes = [
  { key: 'lecture', label: '讲义' },
  { key: 'practice_guide', label: '实操指南' },
  { key: 'test', label: '测试题' },
]

const activeTab = ref('lecture')

// ---------------------------------------------------------------
// 从 store 取资源数据（字段对齐 backend content_generator）
// ---------------------------------------------------------------
const resources = computed(() => store.generatedContent?.resources || [])

const hasResources = computed(() => resources.value.length > 0)

const resourceNodeCount = computed(() => store.generatedContent?.node_count ?? 0)

function countByType(type) {
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

// ---------------------------------------------------------------
// 资源标题：从 markdown 首行提取，fallback 到类型中文名+序号
// ---------------------------------------------------------------
function resTitle(res, idx) {
  const extracted = extractTitle(res.content)
  if (extracted) return extracted
  return `${contentTypeLabel(res.content_type)} #${idx + 1}`
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
</style>
