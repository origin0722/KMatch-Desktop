<template>
  <div class="graph-page">
    <!-- ============================================================ -->
    <!-- 页面标题栏 -->
    <!-- ============================================================ -->
    <div class="page-header">
      <h3>知识图谱可视化</h3>
      <p class="page-desc">
        四层知识图谱交互式浏览：领域元知识 → 项目框架 → 代码实体 → 演化扩展
      </p>
    </div>

    <!-- ============================================================ -->
    <!-- 空状态：无学习路径时显示引导 -->
    <!-- ============================================================ -->
    <el-empty
      v-if="!hasPathData && !graphReady"
      description="尚未生成学习路径图谱"
      :image-size="120"
    >
      <el-button type="primary" @click="goAssessment">
        前往学情测评
      </el-button>
    </el-empty>

    <!-- ============================================================ -->
    <!-- 有数据时：工具栏 + 主内容区 -->
    <!-- ============================================================ -->
    <template v-if="hasPathData || graphReady">
      <!-- 工具栏 -->
      <el-card class="toolbar-card" shadow="never">
        <div class="toolbar">
          <el-input
            v-model="searchQuery"
            placeholder="搜索知识点（语义检索）…"
            :prefix-icon="Search"
            clearable
            class="search-input"
            @keyup.enter="handleSearch"
            @clear="handleSearchClear"
          />
          <el-button type="primary" :icon="Search" @click="handleSearch" :loading="searching">
            搜索
          </el-button>

          <el-divider direction="vertical" />

          <el-select
            v-model="categoryFilter"
            placeholder="全部分类"
            clearable
            class="filter-select"
            @change="handleFilterChange"
          >
            <el-option v-for="cat in categories" :key="cat" :label="cat" :value="cat" />
          </el-select>

          <el-select
            v-model="difficultyFilter"
            placeholder="全部难度"
            clearable
            class="filter-select"
            @change="handleFilterChange"
          >
            <el-option label="⭐ 入门 (1)" :value="1" />
            <el-option label="⭐⭐ 基础 (2)" :value="2" />
            <el-option label="⭐⭐⭐ 进阶 (3)" :value="3" />
            <el-option label="⭐⭐⭐⭐ 高级 (4)" :value="4" />
            <el-option label="⭐⭐⭐⭐⭐ 专家 (5)" :value="5" />
          </el-select>

          <el-divider direction="vertical" />

          <el-button :icon="Switch" @click="toggleLayout" :disabled="!graphReady">
            {{ layoutLabel }}
          </el-button>
          <el-button :icon="RefreshRight" @click="resetGraph" :disabled="!graphReady">
            重置
          </el-button>

          <el-popover placement="bottom" :width="200" trigger="click">
            <template #reference>
              <el-button class="legend-btn">图例</el-button>
            </template>
            <div class="legend-popover">
              <div class="legend-item"><span class="dot mastered"></span> 已掌握 (≥80%)</div>
              <div class="legend-item"><span class="dot learning"></span> 学习中 (50-80%)</div>
              <div class="legend-item"><span class="dot weak"></span> 未掌握 (<50%)</div>
              <div class="legend-item"><span class="dot untouched"></span> 未学习</div>
            </div>
          </el-popover>

          <span class="graph-stats">
            节点: {{ data.nodeCount.value }} | 边: {{ data.edgeCount.value }}
          </span>
        </div>
      </el-card>

      <!-- 搜索无结果提示 (BUG-046) -->
      <el-alert
        v-if="searchNoResult"
        title="未找到匹配节点"
        type="info"
        :closable="true"
        @close="searchNoResult = false"
        show-icon
        class="search-alert"
      />

      <!-- 主内容区 -->
      <div class="main-area">
        <!-- 图谱画布 -->
        <div class="canvas-area">
          <div ref="graphContainer" class="g6-container"></div>
        </div>

        <!-- 侧边面板 -->
        <div class="side-panel">
          <!-- 学习路径摘要 -->
          <el-card shadow="never" class="panel-card">
            <template #header>
              <span>📖 学习路径摘要</span>
            </template>
            <div class="path-summary">
              <div class="summary-row">
                <span class="label">路径节点</span>
                <span class="value">{{ data.nodeCount.value }} 个</span>
              </div>
              <div class="summary-row">
                <span class="label">预计学时</span>
                <span class="value">{{ estimatedHours }} 小时</span>
              </div>
              <div class="summary-row">
                <span class="label">当前阶段</span>
                <el-tag size="small" type="warning">{{ currentPhase }}</el-tag>
              </div>
              <!-- BUG-045: 前置依赖加载状态 -->
              <div v-if="loadingPrereqs" class="prereq-loading">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>加载前置依赖…</span>
              </div>
            </div>
          </el-card>

          <!-- 节点详情 -->
          <el-card shadow="never" class="panel-card" v-if="selectedNode">
            <template #header>
              <span>🔍 节点详情</span>
            </template>
            <div class="node-detail">
              <h4>{{ selectedNode.name || selectedNode.node_id }}</h4>
              <div class="detail-row">
                <span class="label">ID</span>
                <code>{{ selectedNode.node_id }}</code>
              </div>
              <div class="detail-row" v-if="selectedNode.category">
                <span class="label">分类</span>
                <span>{{ selectedNode.category }}</span>
              </div>
              <div class="detail-row">
                <span class="label">难度</span>
                <span>{{ '⭐'.repeat(selectedNode.difficulty ?? 1) }}</span>
              </div>
              <div class="detail-row">
                <span class="label">掌握程度</span>
                <el-progress
                  :percentage="Math.round((selectedNode.mastery ?? 0) * 100)"
                  :color="masteryColor(selectedNode.mastery ?? 0)"
                  :stroke-width="8"
                />
              </div>
              <p class="detail-summary" v-if="selectedNode.summary">{{ selectedNode.summary }}</p>
              <!-- 前置依赖 -->
              <div v-if="prereqNodes.length" class="prereq-section">
                <span class="label">前置依赖</span>
                <div class="prereq-list">
                  <el-tag
                    v-for="p in prereqNodes"
                    :key="p.node_id"
                    size="small"
                    type="info"
                    class="prereq-tag"
                    @click="selectNode(p)"
                  >
                    {{ p.name || p.node_id }}
                  </el-tag>
                </div>
              </div>
            </div>
          </el-card>

          <!-- 未选中节点 -->
          <el-card v-else shadow="never" class="panel-card">
            <template #header>
              <span>🔍 节点详情</span>
            </template>
            <el-empty description="点击图谱节点查看详情" :image-size="60" />
          </el-card>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
/**
 * KMatch 知识图谱可视化页 — 第3周 G6 真实渲染
 *
 * 修复记录:
 *   BUG-045: 批量 API 获取 prerequisites（Neo4j 关系→前端边）
 *   BUG-046: 空搜索结果 guard（空 Set→null）
 *   BUG-047: 搜索时仅 dim 非高亮边
 *   BUG-048: handleSearch 竞态控制（searchSeq）
 *   BUG-049: G6 initGraph + render 异常保护
 *   BUG-052: handleFilterChange 双 API 均失败时清除 highlightIds
 */
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { Search, Switch, RefreshRight, Loading } from '@element-plus/icons-vue'
import { Graph } from '@antv/g6'
import { useAssessmentStore } from '@/stores/assessment'
import { useGraphData } from '@/composables/useGraphData'
import { masteryColor } from '@/utils/format'
import { semanticSearch, getByCategory, getByDifficulty, getNode, getPrerequisites } from '@/api/graph'
import { ElMessage } from 'element-plus'
import { useSidebarStore } from '@/stores/sidebar'

const store = useAssessmentStore()
const data = useGraphData()
const sidebar = useSidebarStore()

// 前往学情测评 (IDE 内切主区视图, 非路由跳转)
const goAssessment = () => sidebar.setView('assessment')

// ---------------------------------------------------------------
// 搜索 & 筛选状态
// ---------------------------------------------------------------
const searchQuery = ref('')
const searching = ref(false)
const searchNoResult = ref(false)
const categoryFilter = ref('')
const difficultyFilter = ref(null)

const categories = [
  '基础语法', '数据结构与算法', '面向对象编程',
  'Python进阶', '常用库与工具', '项目实战',
]

// ---------------------------------------------------------------
// 图谱状态
// ---------------------------------------------------------------
const graphContainer = ref(null)
const graphReady = ref(false)
const currentLayout = ref('force')
const selectedNode = ref(null)
const prereqNodes = ref([])
/** 搜索/筛选高亮节点 ID 集合 */
const highlightIds = ref(null)
/** 搜索/筛选的额外节点（不在当前路径中的） */
const extraNodes = ref([])
/** BUG-048: 搜索序列号，丢弃过期响应 */
let searchSeq = 0
/** BUG-045: 前置依赖加载中 */
const loadingPrereqs = ref(false)

let graph = null

// ---------------------------------------------------------------
// 计算属性
// ---------------------------------------------------------------
const hasPathData = computed(() => data.rawNodes.value.length > 0)

const estimatedHours = computed(() =>
  store.knowledgeGraph?.estimated_total_hours ?? '--',
)

const currentPhase = computed(() => {
  const total = data.nodeCount.value
  if (total === 0) return '待测评'
  if (total <= 5) return '入门阶段'
  if (total <= 12) return '基础夯实'
  if (total <= 20) return '进阶提升'
  return '全面覆盖'
})

const layoutLabel = computed(() =>
  currentLayout.value === 'force' ? '层次布局' : '力导向布局',
)

// ---------------------------------------------------------------
// BUG-045: 批量获取前置依赖，注入 useGraphData
// ---------------------------------------------------------------
async function fetchPrerequisites() {
  const nodes = data.rawNodes.value
  if (nodes.length === 0) return

  loadingPrereqs.value = true
  const ids = nodes.map((n) => n.node_id).filter(Boolean)
  const map = {}

  // 并行获取所有节点的前置依赖（最多 20 个并行请求，后端 API 无副作用）
  const results = await Promise.all(
    ids.map(async (nid) => {
      try {
        const prereqs = await getPrerequisites(nid)
        return { nid, prereqIds: (prereqs || []).map((p) => p.node_id).filter(Boolean) }
      } catch {
        return { nid, prereqIds: [] }
      }
    }),
  )

  for (const { nid, prereqIds } of results) {
    map[nid] = prereqIds
  }

  data.setPrereqMap(map)
  loadingPrereqs.value = false
}

// ---------------------------------------------------------------
// G6 渲染
// ---------------------------------------------------------------
function buildG6Data() {
  const baseNodes = [...data.g6Nodes.value]

  // 合并搜索结果中不在当前路径中的额外节点
  for (const en of extraNodes.value) {
    if (!baseNodes.find((n) => n.id === en.id)) {
      baseNodes.push(en)
    }
  }

  // 高亮处理 (BUG-046: highlightIds 为 null 则全量展示，非空才过滤)
  let nodes, edges
  const baseEdges = [...data.g6Edges.value]

  if (highlightIds.value && highlightIds.value.size > 0) {
    nodes = baseNodes.map((n) => ({
      ...n,
      data: {
        ...n.data,
        nodeColor: highlightIds.value.has(n.id)
          ? n.data.nodeColor
          : '#d9d9d9',
        nodeSize: highlightIds.value.has(n.id) ? 35 : 22,
        dimmed: !highlightIds.value.has(n.id),
      },
    }))
    // BUG-047: 仅 dim 两端均不在高亮集合中的边
    edges = baseEdges.map((e) => {
      const bothHighlighted = highlightIds.value.has(e.source) && highlightIds.value.has(e.target)
      return {
        ...e,
        data: { ...e.data, dimmed: !bothHighlighted },
      }
    })
  } else {
    nodes = baseNodes.map((n) => ({
      ...n,
      data: { ...n.data, dimmed: false },
    }))
    edges = baseEdges.map((e) => ({
      ...e,
      data: { ...e.data, dimmed: false },
    }))
  }

  return { nodes, edges }
}

function initGraph(layoutType = 'force') {
  if (!graphContainer.value) return

  // BUG-049: 异常保护
  try {
    const containerWidth = graphContainer.value.offsetWidth || 800

    const layoutConfig = layoutType === 'force'
      ? { type: 'force', preventOverlap: true, nodeStrength: -200, linkDistance: 150 }
      : { type: 'dagre', rankdir: 'TB', nodesep: 40, ranksep: 80 }

    const { nodes, edges } = buildG6Data()

    graph = new Graph({
      container: graphContainer.value,
      width: containerWidth,
      height: 480,
      data: { nodes, edges },
      layout: layoutConfig,
      node: {
        style: {
          fill: (d) => d.data?.nodeColor || '#5b8ff9',
          size: (d) => [d.data?.nodeSize || 30],
          labelText: (d) => d.data?.label || d.id,
          labelPlacement: 'bottom',
          labelMaxWidth: 100,
          labelOffsetY: 6,
          labelFontSize: 11,
          opacity: (d) => d.data?.dimmed ? 0.35 : 1,
        },
        state: { hover: { lineWidth: 3, shadowBlur: 10, shadowColor: '#1890ff' } },
      },
      edge: {
        style: {
          stroke: '#c2c8d5',
          lineWidth: 1.5,
          endArrow: true,
          opacity: (d) => d.data?.dimmed ? 0.2 : 1,
        },
      },
      behaviors: [
        'drag-canvas',
        'zoom-canvas',
        'drag-element',
        { type: 'hover-activate', degree: 1, direction: 'both' },
      ],
    })

    graph.on('node:click', async (evt) => {
      const nodeId = evt.target?.id
      if (!nodeId) return
      await selectNode(nodeId)
    })

    graph.render()
    graphReady.value = true
  } catch (e) {
    console.error('[Graph] 初始化失败:', e)
    ElMessage.error('图谱渲染失败，请刷新页面重试')
    graphReady.value = false
    graph = null
  }
}

function destroyGraph() {
  if (graph) {
    try { graph.destroy() } catch { /* 忽略销毁异常 */ }
    graph = null
  }
}

// ---------------------------------------------------------------
// 节点选择
// ---------------------------------------------------------------
async function selectNode(nodeOrId) {
  if (typeof nodeOrId === 'string') {
    const found = data.nodeMap.value[nodeOrId]
    if (found) {
      // BUG-051: 注入画像 mastery
      const profileMastery = data.masteryMap.value[nodeOrId]
      selectedNode.value = profileMastery != null
        ? { ...found, mastery: profileMastery }
        : found
    } else {
      try {
        selectedNode.value = await getNode(nodeOrId)
      } catch {
        selectedNode.value = { node_id: nodeOrId, name: nodeOrId, summary: '' }
      }
    }
  } else {
    selectedNode.value = nodeOrId
  }

  // 查询前置依赖
  if (selectedNode.value?.node_id) {
    try {
      const prereqs = await getPrerequisites(selectedNode.value.node_id)
      prereqNodes.value = Array.isArray(prereqs) ? prereqs : []
    } catch {
      prereqNodes.value = []
    }
  }
}

// ---------------------------------------------------------------
// 搜索 (BUG-048: searchSeq 竞态控制)
// ---------------------------------------------------------------
async function handleSearch() {
  const q = searchQuery.value.trim()
  if (!q || q.length < 2) return

  const currentSeq = ++searchSeq
  searching.value = true
  searchNoResult.value = false

  try {
    const result = await semanticSearch(q, 10)
    // BUG-048: 丢弃过期响应
    if (currentSeq !== searchSeq) return

    const searchNodes = result.nodes || []

    // BUG-046: 空结果 → null (不强转空 Set)
    if (searchNodes.length === 0) {
      highlightIds.value = null
      extraNodes.value = []
      searchNoResult.value = true
    } else {
      // 搜索结果中不在当前路径的节点加入 extraNodes
      extraNodes.value = searchNodes
        .filter((n) => !data.nodeMap.value[n.node_id])
        .map((n) => ({
          id: n.node_id,
          data: {
            label: n.name || n.node_id,
            mastery: 0,
            nodeColor: '#a0a0a0',
            nodeSize: 28,
            category: n.category || '',
            difficulty: n.difficulty || 1,
          },
        }))
      highlightIds.value = new Set(searchNodes.map((n) => n.node_id))
    }

    rebuildGraph()
  } catch {
    if (currentSeq === searchSeq) {
      // 只有当前请求出错才清状态
    }
  } finally {
    if (currentSeq === searchSeq) {
      searching.value = false
    }
  }
}

function handleSearchClear() {
  if (!searchQuery.value) {
    clearHighlight()
  }
}

// ---------------------------------------------------------------
// 筛选 (BUG-052: 双 API 均失败时清除 highlightIds)
// ---------------------------------------------------------------
async function handleFilterChange() {
  const cat = categoryFilter.value
  const diff = difficultyFilter.value

  if (!cat && diff == null) {
    clearHighlight()
    return
  }

  const sets = []

  if (cat) {
    try {
      const result = await getByCategory(cat)
      sets.push(new Set((result || []).map((n) => n.node_id)))
    } catch { /* ignore */ }
  }

  if (diff != null) {
    try {
      const result = await getByDifficulty(diff, diff)
      sets.push(new Set((result || []).map((n) => n.node_id)))
    } catch { /* ignore */ }
  }

  // BUG-052: 双 API 均失败 → 清除
  if (sets.length === 0) {
    highlightIds.value = null
  } else if (sets.length === 1) {
    highlightIds.value = sets[0]
  } else {
    highlightIds.value = new Set(
      [...sets[0]].filter((id) => sets[1].has(id)),
    )
  }

  extraNodes.value = []
  searchNoResult.value = false
  rebuildGraph()
}

function clearHighlight() {
  highlightIds.value = null
  extraNodes.value = []
  searchNoResult.value = false
  searchQuery.value = ''
  categoryFilter.value = ''
  difficultyFilter.value = null
  rebuildGraph()
}

// ---------------------------------------------------------------
// 布局 & 重置
// ---------------------------------------------------------------
function toggleLayout() {
  currentLayout.value = currentLayout.value === 'force' ? 'dagre' : 'force'
  rebuildGraph()
}

function resetGraph() {
  clearHighlight()
  selectedNode.value = null
  prereqNodes.value = []
  currentLayout.value = 'force'
  rebuildGraph()
}

function rebuildGraph() {
  destroyGraph()
  if (hasPathData.value || extraNodes.value.length > 0) {
    initGraph(currentLayout.value)
  }
}

// ---------------------------------------------------------------
// 生命周期
// ---------------------------------------------------------------
onMounted(async () => {
  if (hasPathData.value) {
    // BUG-045: 先获取前置依赖，再初始化图谱（使边可渲染）
    await fetchPrerequisites()
    initGraph('force')
  }
})

// 当 store 的 learning_path 变化时（测评完成后跳转过来）
watch(() => store.knowledgeGraph, async (newVal) => {
  if (newVal?.learning_path?.length > 0) {
    destroyGraph()
    await fetchPrerequisites()
    initGraph(currentLayout.value)
  }
}, { deep: true })

onBeforeUnmount(() => {
  destroyGraph()
})
</script>

<style scoped>
.graph-page { padding: 0; }

/* ---- 页面标题 ---- */
.page-header { margin-bottom: 16px; }
.page-header h3 { margin: 0 0 4px; font-size: 20px; }
.page-desc { margin: 0; color: #909399; font-size: 13px; }

/* ---- 工具栏 ---- */
.toolbar-card { margin-bottom: 16px; }
.toolbar-card :deep(.el-card__body) { padding: 12px 16px; }
.toolbar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.search-input { width: 260px; }
.filter-select { width: 150px; }
.legend-btn { margin-left: auto; }
.graph-stats { color: #909399; font-size: 13px; white-space: nowrap; }

/* ---- 图例弹窗 ---- */
.legend-popover {
  display: flex; flex-direction: column; gap: 8px; font-size: 13px;
}
.legend-item { display: flex; align-items: center; gap: 8px; }
.dot {
  width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0;
}
.dot.mastered  { background: #52c41a; }
.dot.learning  { background: #faad14; }
.dot.weak      { background: #ff7a45; }
.dot.untouched { background: #d9d9d9; }

/* ---- 搜索无结果 ---- */
.search-alert { margin-bottom: 16px; }

/* ---- 主内容区 ---- */
.main-area { display: flex; gap: 16px; min-height: 500px; }

/* ---- 图谱画布 ---- */
.canvas-area { flex: 1; min-width: 0; }
.g6-container {
  width: 100%; height: 480px;
  border: 1px solid #e4e7ed; border-radius: 4px; background: #fff;
}

/* ---- 侧边面板 ---- */
.side-panel {
  width: 300px; flex-shrink: 0;
  display: flex; flex-direction: column; gap: 12px;
}
.panel-card :deep(.el-card__header) {
  padding: 10px 16px; font-weight: 600; font-size: 14px;
}
.panel-card :deep(.el-card__body) { padding: 12px 16px; }

/* ---- 路径摘要 ---- */
.path-summary {
  display: flex; flex-direction: column; gap: 10px;
}
.summary-row {
  display: flex; justify-content: space-between; align-items: center;
}
.summary-row .label { color: #909399; font-size: 13px; }
.summary-row .value { font-weight: 600; font-size: 14px; }
.prereq-loading {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: #909399; padding-top: 4px;
}

/* ---- 节点详情 ---- */
.node-detail h4 { margin: 0 0 10px; font-size: 15px; }
.detail-row {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 8px; font-size: 13px;
}
.detail-row .label { color: #909399; width: 56px; flex-shrink: 0; }
.detail-row code {
  background: #f5f7fa; padding: 1px 6px; border-radius: 3px; font-size: 12px;
}
.detail-summary {
  margin: 10px 0 0; color: #606266; font-size: 13px; line-height: 1.6;
}
.prereq-section { margin-top: 12px; }
.prereq-section > .label {
  display: block; color: #909399; font-size: 13px; margin-bottom: 6px;
}
.prereq-list { display: flex; flex-wrap: wrap; gap: 4px; }
.prereq-tag { cursor: pointer; }
.prereq-tag:hover { opacity: 0.8; }
</style>
