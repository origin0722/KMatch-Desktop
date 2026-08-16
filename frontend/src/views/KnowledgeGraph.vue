<template>
  <div class="graph-page km-workbench">
    <!-- ============================================================ -->
    <!-- 页面标题栏 (km-workbench-header) -->
    <!-- ============================================================ -->
    <div class="km-workbench-header">
      <div>
        <p class="km-workbench-kicker">knowledge graph</p>
        <h3 class="km-workbench-title">知识图谱</h3>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- 空状态：无学习路径时显示引导 -->
    <!-- ============================================================ -->
    <el-empty
      v-if="!hasPathData && !graphReady"
      description="尚未生成学习路径图谱"
      :image-size="120"
    >
      <el-button type="primary" @click="goSession">
        前往学习会话
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

          <el-select
            v-model="masteryFilter"
            placeholder="全部掌握度"
            clearable
            class="filter-select"
            @change="handleFilterChange"
          >
            <el-option label="已掌握 (≥80%)" value="mastered" />
            <el-option label="学习中 (50-80%)" value="learning" />
            <el-option label="未掌握 (<50%)" value="weak" />
          </el-select>

          <el-divider direction="vertical" />

          <el-button :icon="RefreshRight" @click="resetGraph" :disabled="!graphReady">
            重置
          </el-button>

          <el-divider direction="vertical" />

          <div class="persona-selector">
            <button
              v-for="p in personas"
              :key="p.id"
              class="persona-btn"
              :class="{ active: sidebar.persona === p.id }"
              :title="p.desc"
              @click="sidebar.setPersona(p.id)"
            >{{ p.label }}</button>
          </div>

          <el-button size="small" @click="pathFinderVisible = true" :disabled="!graphReady">
            路径查找
          </el-button>

          <el-popover placement="bottom" :width="200" trigger="click">
            <template #reference>
              <el-button class="legend-btn">图例</el-button>
            </template>
            <div class="legend-popover">
              <div class="legend-title">节点颜色 · 难度</div>
              <div class="legend-item">
                <span class="dot" :style="{ background: difficultyColor(1) }"></span> ⭐ 入门 (1-2)
              </div>
              <div class="legend-item">
                <span class="dot" :style="{ background: difficultyColor(3) }"></span> ⭐⭐⭐ 进阶 (3)
              </div>
              <div class="legend-item">
                <span class="dot" :style="{ background: difficultyColor(4) }"></span> ⭐⭐⭐⭐⭐ 高级 (4-5)
              </div>
              <div class="legend-title">节点边框 · 掌握度</div>
              <div class="legend-item"><span class="dot mastered-dot"></span> 已掌握 (≥80%)</div>
              <div class="legend-item"><span class="dot" :style="{ border: `1px solid ${difficultyColor(1)}` }"></span> 未掌握 (细灰框)</div>
            </div>
          </el-popover>

          <el-popover placement="bottom" :width="240" trigger="click">
            <template #reference>
              <el-button size="small">快捷键</el-button>
            </template>
            <div class="legend-popover">
              <div class="legend-item"><code>Esc</code> 清除高亮/搜索</div>
              <div class="legend-item"><code>滚轮</code> 缩放</div>
              <div class="legend-item"><code>拖拽空白</code> 平移画布</div>
              <div class="legend-item"><code>点击节点</code> 查看详情</div>
              <div class="legend-item"><code>拖拽节点</code> 调整位置</div>
            </div>
          </el-popover>

          <el-button size="small" @click="exportGraph" :disabled="!graphReady">导出</el-button>

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

        <!-- 侧边面板 (split 分栏 + 可折叠, flex 推挤画布不压节点; T3 由浮层改占位) -->
        <div class="side-panel" :class="{ collapsed: panelCollapsed }">
          <button class="panel-toggle" @click="panelCollapsed = !panelCollapsed"
                  :title="panelCollapsed ? '展开详情面板' : '收起详情面板'">
            <el-icon><ArrowRight v-if="panelCollapsed" /><ArrowLeft v-else /></el-icon>
          </button>
          <!-- 新鲜度提示 (借鉴 StalenessBanner): 画像过期 -->
          <el-alert v-if="profileStale" type="warning" :closable="false" class="stale-banner" show-icon>
            学情画像已过期 (超过 7 天), 建议重新测评
          </el-alert>

          <!-- 面包屑导航 (借鉴 Breadcrumb): 知识图谱 / 分类 / 节点 -->
          <div v-if="selectedNode" class="breadcrumb">
            <span class="bc-item">知识图谱</span>
            <span class="bc-sep">/</span>
            <span class="bc-item bc-clickable" @click="setCategoryFilter(selectedNode.category)">{{ selectedNode.category || '未分类' }}</span>
            <span class="bc-sep">/</span>
            <span class="bc-item bc-current">{{ selectedNode.name || selectedNode.node_id }}</span>
          </div>

          <!-- 图谱详情单卡 (T3: 路径摘要 + 节点详情两段融合, 减一层卡壳) -->
          <el-card shadow="never" class="panel-card">
            <template #header>
              <span>图谱详情</span>
            </template>
            <div class="panel-section-title">学习路径摘要</div>
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
              <!-- 分类分布 (借鉴 ProjectOverview) -->
              <div v-if="Object.keys(categoryDistribution).length" class="cat-dist-section">
                <span class="label">分类分布</span>
                <div v-for="(count, cat) in categoryDistribution" :key="cat" class="cat-dist">
                  <span class="dot" :style="{ background: categoryColor(cat) }"></span>
                  <span class="cat-name">{{ cat }}</span>
                  <span class="cat-count">{{ count }}</span>
                </div>
              </div>
              <!-- BUG-045: 前置依赖加载状态 -->
              <div v-if="loadingPrereqs" class="prereq-loading">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>加载前置依赖…</span>
              </div>
            </div>

            <el-divider class="panel-divider" />

            <!-- 节点详情段 -->
            <template v-if="selectedNode">
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
              <!-- 关键点 (persona 进阶/高级: "关键点 + 原理") -->
              <div v-if="selectedNode.key_points?.length" class="keypoints-section">
                <span class="label">关键点</span>
                <ul class="keypoints-list">
                  <li v-for="(kp, i) in selectedNode.key_points" :key="i">{{ kp }}</li>
                </ul>
              </div>
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
              <!-- 不懂就问: 节点上下文预填到 AI 助手 (可编辑后发送, 不自动发) -->
              <el-button
                type="primary"
                plain
                size="small"
                class="ask-ai-btn"
                data-test="ask-ai"
                @click="askAiAboutNode"
              >问 AI 助手</el-button>
            </div>
            </template>
            <el-empty v-else description="点击图谱节点查看详情" :image-size="60" />
          </el-card>
        </div>
      </div>

      <PathFinderModal v-model="pathFinderVisible" :nodes="data.g6Nodes.value" :prereq-map="data.prereqMap.value" />
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
 *
 * 配色: THEME 常量镜像 --km-* token (G6 canvas 不能读 CSS 变量, 故用 hex)。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { Search, RefreshRight, Loading, ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { Graph } from '@antv/g6'
import { useAssessmentStore } from '@/stores/assessment'
import { useGraphData } from '@/composables/useGraphData'
import { masteryColor, difficultyColor } from '@/utils/format'
import { semanticSearch, getByCategory, getByDifficulty, getNode, getPrerequisites } from '@/api/graph'
import { ElMessage } from 'element-plus'
import { useSidebarStore } from '@/stores/sidebar'
import { useChatStore } from '@/stores/chat'
import { buildNodeQuestion } from '@/utils/askAi'
import PathFinderModal from '@/components/PathFinderModal.vue'

const store = useAssessmentStore()
const data = useGraphData()
const sidebar = useSidebarStore()
const chat = useChatStore()

// 主题色常量 (镜像 styles/theme.css 的 --km-* token, 供 G6 canvas 使用)
const THEME = {
  primary: '#6c7ce0',
  success: '#34b37e',
  warning: '#f0a040',
  danger: '#e05555',
  gray300: '#e4e3e1',
  gray400: '#c8c6c4',
}

// 分类配色 (借鉴 Understand-Anything 层级颜色编码: 同分类同色 + 力导向聚类防挤)
const CATEGORY_COLORS = {
  '基础语法': '#5b8ff9',
  '数据结构与算法': '#5ad8a6',
  '面向对象编程': '#f6bd16',
  'Python进阶': '#6dc8ec',
  '常用库与工具': '#e86452',
  '项目实战': '#945fb9',
  // 2026-08 扩域新增 5 分类 (色相与原 6 色错开: 青/玫红/橙/靛/黄绿, 避免三紫挤簇)
  '机器学习': '#61c0bf',
  '数据分析与可视化': '#f25f9e',
  'Web后端开发': '#ff9d6c',
  '数据库与缓存': '#4253a4',
  '工程化实践': '#82b366',
}
const categoryColor = (cat) => CATEGORY_COLORS[cat] || THEME.gray400

// 角色详略 (persona 接线: 初学详/进阶中/高级简, 真正改变节点密度与信息量, 非死功能)
// beginner 显示分类+难度(信息全), intermediate 仅难度, advanced 仅名称(最紧凑 -> 画布最不挤)
// 阶段C 图谱待办"矩形加大": 节点尺寸整体上调, labelMax 同步, 治"节点太小看不清"
const PERSONA = {
  beginner:     { node: [215, 70], layout: [235, 105], labelMax: 205, label: (d) => `${d?.label || d.id}\n${d?.category || ''} · ${'⭐'.repeat(d?.difficulty || 1)}` },
  intermediate: { node: [190, 60], layout: [210, 90], labelMax: 180, label: (d) => `${d?.label || d.id}\n${'⭐'.repeat(d?.difficulty || 1)}` },
  advanced:     { node: [160, 48], layout: [180, 75], labelMax: 150, label: (d) => `${d?.label || d.id}` },
}
const personaCfg = () => PERSONA[sidebar.persona] || PERSONA.intermediate

// 前往学习会话 (IDE 内切主区视图, 非路由跳转)
const goSession = () => sidebar.setView('learning-session')

// 不懂就问: 节点上下文预填 AI 助手输入框并切到 chat 视图 (用户可编辑后发送)
function askAiAboutNode() {
  const n = selectedNode.value
  if (!n) return
  chat.setDraft(buildNodeQuestion(
    n, (prereqNodes.value || []).map((p) => p.name || p.node_id)))
  sidebar.setView('chat')
}

// ---------------------------------------------------------------
// 搜索 & 筛选状态
// ---------------------------------------------------------------
const searchQuery = ref('')
const searching = ref(false)
const searchNoResult = ref(false)
const categoryFilter = ref('')
const difficultyFilter = ref(null)
const masteryFilter = ref('')

const categories = [
  '基础语法', '数据结构与算法', '面向对象编程',
  'Python进阶', '常用库与工具', '项目实战',
  '机器学习', '数据分析与可视化', 'Web后端开发',
  '数据库与缓存', '工程化实践',
]

// 学习角色 (借鉴 Understand-Anything PersonaSelector): 调整节点卡片详略
const personas = [
  { id: 'beginner', label: '初学', desc: '详细摘要, 适合入门' },
  { id: 'intermediate', label: '进阶', desc: '关键点 + 原理' },
  { id: 'advanced', label: '高级', desc: '关键点 + 误区, 直指核心' },
]

// ---------------------------------------------------------------
// 图谱状态
// ---------------------------------------------------------------
const graphContainer = ref(null)
const graphReady = ref(false)
const pathFinderVisible = ref(false)
const panelCollapsed = ref(false)
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

// 画像新鲜度 (借鉴 StalenessBanner): 超 7 天提示过期
const profileStale = computed(() => {
  const created = store.profile?.created_at
  if (!created) return false
  const age = Date.now() - new Date(created).getTime()
  return age > 7 * 24 * 60 * 60 * 1000
})

// 分类分布 (借鉴 ProjectOverview): 各分类节点数
const categoryDistribution = computed(() => {
  const dist = {}
  data.rawNodes.value.forEach((n) => {
    const cat = n.category || '未分类'
    dist[cat] = (dist[cat] || 0) + 1
  })
  return dist
})

const currentPhase = computed(() => {
  const total = data.nodeCount.value
  if (total === 0) return '待测评'
  if (total <= 5) return '入门阶段'
  if (total <= 12) return '基础夯实'
  if (total <= 20) return '进阶提升'
  return '全面覆盖'
})

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
      data: { ...n.data, dimmed: !highlightIds.value.has(n.id) },
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

function initGraph() {
  if (!graphContainer.value) return

  // BUG-049: 异常保护
  try {
    // 浮层避让: 详情面板展开时画布逻辑宽度避让右侧 (面板宽300 + 右偏移12 + 余量),
    // dagre 在剩余区布局, 节点不进浮层底下; 收起时画布拿满全宽
    const panelGap = panelCollapsed.value ? 0 : 320
    const containerWidth = (graphContainer.value.offsetWidth || 800) - panelGap
    const containerHeight = graphContainer.value.offsetHeight || 600

    // 单一布局: dagre 层次 (借鉴 Understand-Anything ELK layered); 间距加大治"还是挤", nodeSize 随 persona
    // 阶段C 图谱待办"间距": nodesep 70->90, ranksep 150->180, 节点更宽松不挤
    const cfg = personaCfg()
    const layoutConfig = { type: 'dagre', rankdir: 'TB', nodesep: 90, ranksep: 180, nodeSize: cfg.layout }

    const { nodes, edges } = buildG6Data()

    graph = new Graph({
      container: graphContainer.value,
      width: containerWidth,
      height: containerHeight,
      data: { nodes, edges },
      layout: layoutConfig,
      node: {
        type: 'rect',
        style: {
          // 难度着色 (单域路径全同 category, 按分类着色会全图同色; 难度天然有梯度)
          fill: (d) => difficultyColor(d.data?.difficulty || 1),
          size: cfg.node,
          labelText: (d) => cfg.label(d.data),
          labelPlacement: 'center',
          labelFontSize: 12,
          labelFill: '#ffffff',
          labelMaxWidth: cfg.labelMax,
          labelLineHeight: 18,
          // 掌握度改由边框表达 (已掌握 ≥0.8 绿色加粗)
          stroke: (d) => (d.data?.mastery ?? 0) >= 0.8 ? '#34b37e' : THEME.gray300,
          lineWidth: (d) => (d.data?.mastery ?? 0) >= 0.8 ? 2.5 : 1,
          radius: 8,
          opacity: (d) => d.data?.dimmed ? 0.35 : 1,
        },
        state: { hover: { lineWidth: 3.5, shadowBlur: 12, shadowColor: THEME.primary } },
      },
      edge: {
        style: {
          stroke: THEME.gray300,
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
  // 面板已收起时点击节点 → 自动展开 (收起后最自然的重入口: 想看详情就点节点)
  if (panelCollapsed.value) panelCollapsed.value = false

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
            nodeColor: THEME.gray400,
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
  const mas = masteryFilter.value

  if (!cat && diff == null && !mas) {
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

  // 掌握度过滤 (前端按画像 mastery 筛, 借鉴 FilterPanel 多维过滤)
  if (mas) {
    const masterySet = new Set(
      data.g6Nodes.value
        .filter((n) => {
          const m = n.data?.mastery ?? 0
          if (mas === 'mastered') return m >= 0.8
          if (mas === 'learning') return m >= 0.5 && m < 0.8
          if (mas === 'weak') return m < 0.5
          return false
        })
        .map((n) => n.id),
    )
    sets.push(masterySet)
  }

  // BUG-052: 双 API 均失败 → 清除
  if (sets.length === 0) {
    highlightIds.value = null
  } else {
    highlightIds.value = new Set(
      [...sets[0]].filter((id) => sets.every((s) => s.has(id))),
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
  masteryFilter.value = ''
  rebuildGraph()
}

// 面包屑: 点击分类过滤 (借鉴 Breadcrumb)
function setCategoryFilter(cat) {
  categoryFilter.value = cat || ''
  handleFilterChange()
}

// 导出学习路径 JSON (借鉴 ExportMenu)
function exportGraph() {
  const payload = JSON.stringify({
    target_direction: store.profile?.target_direction,
    knowledge_graph: store.knowledgeGraph,
    profile: store.profile,
    exported_at: new Date().toISOString(),
  }, null, 2)
  const blob = new Blob([payload], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `kmatch-graph-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
}

// ---------------------------------------------------------------
// 布局 & 重置
// ---------------------------------------------------------------
function resetGraph() {
  clearHighlight()
  selectedNode.value = null
  prereqNodes.value = []
  rebuildGraph()
}

function rebuildGraph() {
  destroyGraph()
  if (hasPathData.value || extraNodes.value.length > 0) {
    initGraph()
  }
}

// ---------------------------------------------------------------
// 生命周期
// ---------------------------------------------------------------
onMounted(async () => {
  if (hasPathData.value) {
    // BUG-045: 先获取前置依赖，再初始化图谱（使边可渲染）
    await fetchPrerequisites()
    initGraph()
  }
})

// 当 store 的 learning_path 变化时（测评完成后跳转过来）
watch(() => store.knowledgeGraph, async (newVal) => {
  if (newVal?.learning_path?.length > 0) {
    destroyGraph()
    await fetchPrerequisites()
    initGraph()
  }
}, { deep: true })

// 快捷键 (借鉴 KeyboardShortcutsHelp): Esc 清除高亮
function handleKeydown(e) {
  if (e.key === 'Escape') clearHighlight()
}
onMounted(() => { window.addEventListener('keydown', handleKeydown) })

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  destroyGraph()
})

// 角色切换 -> 重建图谱 (节点详略变化, 借鉴 PersonaSelector)
watch(() => sidebar.persona, () => { rebuildGraph() })

// 侧栏折叠 -> 重建图谱 (画布避让宽度变化)
// T3 split: 折叠切换 -> 侧栏宽度过渡 (0.2s) 结束后再重建, 避免 dagre 读到过渡中的中间宽度
watch(panelCollapsed, () => { setTimeout(() => rebuildGraph(), 220) })
</script>

<style scoped>
.graph-page { padding: 0; height: 100%; display: flex; flex-direction: column; min-height: 0; }

/* ---- 工具栏 ---- */
.toolbar-card { margin-bottom: 16px; }
.toolbar-card :deep(.el-card) {
  --el-card-bg-color: var(--km-bg-layer-2);
  --el-card-border-color: var(--km-border-light);
}
.toolbar-card :deep(.el-card__body) { padding: 12px 16px; }
.toolbar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.search-input { width: 260px; }
.filter-select { width: 150px; }
.legend-btn { margin-left: auto; }
.stale-banner { margin-bottom: 8px; }
.cat-dist-section { display: flex; flex-direction: column; gap: 4px; margin-top: 4px; }
.cat-dist-section > .label { color: var(--km-gray-500); font-size: 13px; margin-bottom: 2px; }
.cat-dist { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--km-gray-700); }
.cat-name { flex: 1; }
.cat-count { font-family: var(--km-font-mono); color: var(--km-gray-800); font-weight: 600; }
.breadcrumb { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--km-gray-500); padding: 8px 12px; background: var(--km-bg-layer-2); border-radius: 8px; flex-wrap: wrap; }
.bc-item { white-space: nowrap; }
.bc-clickable { cursor: pointer; color: var(--km-primary); }
.bc-clickable:hover { text-decoration: underline; }
.bc-current { color: var(--km-gray-800); font-weight: 600; }
.bc-sep { color: var(--km-gray-400); }
.persona-selector { display: inline-flex; gap: 2px; background: var(--km-bg-layer-2); border-radius: 6px; padding: 2px; }
.persona-btn { border: 0; background: transparent; color: var(--km-gray-500); font-size: 12px; padding: 3px 10px; border-radius: 4px; cursor: pointer; transition: color 0.15s, background 0.15s; }
.persona-btn:hover { color: var(--km-gray-700); }
.persona-btn.active { background: var(--km-primary); color: #fff; }
.graph-stats {
  color: var(--km-gray-500); font-size: 13px; white-space: nowrap;
  font-family: var(--km-font-mono);
}

/* ---- 图例弹窗 ---- */
.legend-popover {
  display: flex; flex-direction: column; gap: 8px; font-size: 13px;
}
.legend-item { display: flex; align-items: center; gap: 8px; }
.legend-title { font-size: 11px; font-weight: 600; color: var(--km-gray-500); margin: 6px 0 2px; text-transform: uppercase; letter-spacing: 0.3px; }
.legend-title:first-child { margin-top: 0; }
.dot {
  width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0;
}
/* 图例: 已掌握绿框样式 (对齐节点 mastery≥0.8 的加粗绿边框) */
.mastered-dot {
  background: transparent; border: 2.5px solid #34b37e; box-sizing: border-box;
}
/* 难度/分类色经 inline style 注入, 见 template legend */

/* ---- 搜索无结果 ---- */
.search-alert { margin-bottom: 16px; }

/* ---- 主内容区 ---- */
.main-area { display: flex; flex: 1; min-height: 0; position: relative; }

/* ---- 图谱画布 (占满主区, 详情浮层叠加其上) ---- */
.canvas-area { flex: 1; min-width: 0; min-height: 0; }
.g6-container {
  width: 100%; height: 100%;
  border: 1px solid var(--km-border);
  border-radius: var(--km-radius-sm);
  background: var(--km-bg-layer-3);
}

/* ---- 浮层详情面板 (悬浮图谱上, 画布逻辑宽度避让; 可折叠; 复用 ProjectGraphView 模式) ---- */
.side-panel {
  position: absolute; top: 12px; right: 12px;
  width: 300px; max-height: calc(100% - 24px);
  overflow-y: auto;
  display: flex; flex-direction: column; gap: 10px;
  z-index: 5;
  transition: width 0.2s ease;
}
/* 浮层卡片加投影, 与画布拉开层次 */
.side-panel:not(.collapsed) .panel-card {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}
.side-panel.collapsed { width: 36px; overflow: hidden; }
.side-panel.collapsed > *:not(.panel-toggle) { display: none; }
.panel-toggle {
  position: absolute; top: 8px; right: 6px; z-index: 6;
  width: 24px; height: 24px; border: 1px solid var(--km-border);
  border-radius: 4px; background: var(--km-bg-layer-2); color: var(--km-gray-500);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  font-size: 12px;
}
.panel-toggle:hover { color: var(--km-primary); border-color: var(--km-primary); }
/* 折叠态: 按钮占满侧栏顶部, primary 底白图标, 明确可点展开 (修折叠后展不开) */
.side-panel.collapsed .panel-toggle {
  top: 12px; left: 0; right: 0; width: 100%; height: 36px;
  border-radius: var(--km-radius-sm); border-color: var(--km-primary);
  background: var(--km-primary); color: #fff; font-size: 16px;
}
.side-panel.collapsed .panel-toggle:hover { background: var(--km-primary-active); }
.panel-card :deep(.el-card) {
  --el-card-bg-color: var(--km-bg-layer-2);
  --el-card-border-color: var(--km-border-light);
}
/* T3 单卡两段: 段标题 + 段间分隔 */
.panel-section-title { font-size: 13px; font-weight: 600; color: var(--km-gray-800); margin-bottom: 10px; }
.panel-divider { margin: 14px 0; }
.panel-card :deep(.el-card__header) {
  padding: 10px 16px; font-weight: 600; font-size: 14px;
  color: var(--km-gray-800);
  border-bottom: 1px solid var(--km-border-light);
}
.panel-card :deep(.el-card__body) { padding: 12px 16px; }

/* ---- 路径摘要 ---- */
.path-summary {
  display: flex; flex-direction: column; gap: 10px;
}
.summary-row {
  display: flex; justify-content: space-between; align-items: center;
}
.summary-row .label { color: var(--km-gray-500); font-size: 13px; }
.summary-row .value {
  font-weight: 600; font-size: 14px;
  color: var(--km-gray-800);
  font-family: var(--km-font-mono);
}
.prereq-loading {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--km-gray-500); padding-top: 4px;
}

/* ---- 节点详情 ---- */
.node-detail h4 {
  margin: 0 0 10px; font-size: 15px;
  color: var(--km-gray-800);
}
.detail-row {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 8px; font-size: 13px;
  color: var(--km-gray-700);
}
.detail-row .label { color: var(--km-gray-500); width: 56px; flex-shrink: 0; }
.detail-row code {
  background: var(--km-bg-layer-1); padding: 1px 6px;
  border-radius: 3px; font-size: 12px;
  color: var(--km-gray-800);
}
.detail-summary {
  margin: 10px 0 0; color: var(--km-gray-600);
  font-size: 13px; line-height: 1.6;
}
.keypoints-section { margin-top: 12px; }
.keypoints-section > .label {
  display: block; color: var(--km-gray-500);
  font-size: 13px; margin-bottom: 6px;
}
.keypoints-list {
  margin: 0; padding-left: 18px;
  color: var(--km-gray-700); font-size: 13px; line-height: 1.7;
}
.prereq-section { margin-top: 12px; }
.ask-ai-btn { margin-top: 14px; width: 100%; }
.prereq-section > .label {
  display: block; color: var(--km-gray-500);
  font-size: 13px; margin-bottom: 6px;
}
.prereq-list { display: flex; flex-wrap: wrap; gap: 4px; }
.prereq-tag { cursor: pointer; }
.prereq-tag:hover { opacity: 0.8; }
</style>
