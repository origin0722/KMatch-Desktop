<template>
  <div class="graph-page km-workbench">
    <!-- issue-91: 空态 = 页面标题 + 一句话说明 + 主按钮, 居中 -->
    <div v-if="!hasPathData && !graphReady" class="page-empty" data-test="graph-empty">
      <div class="pe-badge">🕸️</div>
      <h2 class="pe-title">知识图谱</h2>
      <p class="pe-line">完成学情测评后，这里展示你的个性化学习路径图谱</p>
      <div class="empty-actions">
        <el-button type="primary" @click="goSession">前往学习会话</el-button>
      </div>
      <!-- issue: 学情知识图谱历史 (本地快照, 无需重新测评即可回看) -->
      <div v-if="learningHistoryItems.length" class="gh-history">
        <div class="gh-history-title">历史图谱 · 学习图谱</div>
        <div
          v-for="h in learningHistoryItems"
          :key="h.id"
          class="gh-history-item"
          :title="`点击查看 ${h.name} 的学习路径图谱`"
          @click="loadLearningHistory(h)"
        >
          <span class="ph-name">🎓 {{ h.name }}</span>
          <span class="ph-time">{{ fmtTs(h.ts) }}</span>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- 有数据时：工具栏 + 主内容区 -->
    <!-- ============================================================ -->
    <template v-if="hasPathData || graphReady">
      <!-- 历史回看横幅: 明示"只读回看"并提供一键返回当前图谱 -->
      <div v-if="graphHistory.learningViewing" class="history-banner" data-test="history-banner">
        <span class="hb-text">
          🖼 正在查看历史快照「<b>{{ graphHistory.learningViewing.name }}</b> · {{ fmtTs(graphHistory.learningViewing.ts) }}」（只读回看，不影响当前测评数据）
        </span>
        <el-button size="small" type="primary" data-test="back-to-live" @click="graphHistory.backToLiveLearning()">返回当前图谱</el-button>
      </div>
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

          <el-divider direction="vertical" />

          <!-- 筛选 popover: 3 select 收纳, 带已选 badge -->
          <el-popover placement="bottom" :width="300" trigger="click">
            <template #reference>
              <el-button :class="{ 'filter-active': activeFilterCount > 0 }">
                筛选<span v-if="activeFilterCount" class="filter-badge">{{ activeFilterCount }}</span>
              </el-button>
            </template>
            <div class="filter-pop">
              <div class="filter-row">
                <span class="filter-label">分类</span>
                <el-select v-model="categoryFilter" placeholder="全部分类" clearable class="filter-select" @change="handleFilterChange">
                  <el-option v-for="cat in categories" :key="cat" :label="cat" :value="cat" />
                </el-select>
              </div>
              <div class="filter-row">
                <span class="filter-label">难度</span>
                <el-select v-model="difficultyFilter" placeholder="全部难度" clearable class="filter-select" @change="handleFilterChange">
                  <el-option label="⭐ 入门 (1)" :value="1" />
                  <el-option label="⭐⭐ 基础 (2)" :value="2" />
                  <el-option label="⭐⭐⭐ 进阶 (3)" :value="3" />
                  <el-option label="⭐⭐⭐⭐ 高级 (4)" :value="4" />
                  <el-option label="⭐⭐⭐⭐⭐ 专家 (5)" :value="5" />
                </el-select>
              </div>
              <div class="filter-row">
                <span class="filter-label">掌握度</span>
                <el-select v-model="masteryFilter" placeholder="全部掌握度" clearable class="filter-select" @change="handleFilterChange">
                  <el-option label="已掌握 (≥80%)" value="mastered" />
                  <el-option label="学习中 (50-80%)" value="learning" />
                  <el-option label="未掌握 (<50%)" value="weak" />
                </el-select>
              </div>
              <div class="filter-pop-actions">
                <el-button size="small" @click="clearAllFilters" :disabled="activeFilterCount === 0">清空筛选</el-button>
              </div>
            </div>
          </el-popover>

          <!-- 布局切换 (治 TB 纵向 6 层占满 / 宽屏横向空置): 层次 TB / 层次 LR / 力导向聚类 -->
          <div class="layout-selector">
            <button
              v-for="l in LAYOUT_MODES"
              :key="l.id"
              class="persona-btn"
              :class="{ active: layoutMode === l.id }"
              :title="l.desc"
              @click="setLayoutMode(l.id)"
            >{{ l.label }}</button>
          </div>

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

          <!-- 历史快照回看 (常驻入口): 有数据时也能切换历史 / 返回当前 (此前只在空态可见) -->
          <el-popover placement="bottom" :width="280" trigger="click">
            <template #reference>
              <el-button size="small" data-test="history-toggle" :class="{ 'filter-active': !!graphHistory.learningViewing }">
                历史<span v-if="graphHistory.learningViewing" class="filter-badge">回看中</span>
              </el-button>
            </template>
            <div class="history-pop">
              <div v-if="!learningHistoryItems.length" class="history-pop-empty">暂无历史快照（完成学情测评后自动记录）</div>
              <template v-else>
                <div class="history-pop-title">学习图谱快照</div>
                <div
                  v-for="h in learningHistoryItems"
                  :key="h.id"
                  class="history-pop-item"
                  :class="{ active: graphHistory.learningViewing?.id === h.id }"
                  @click="graphHistory.viewLearning(h)"
                >
                  <span class="hp-name">{{ h.name }}</span>
                  <span class="hp-time">{{ fmtTs(h.ts) }}</span>
                </div>
              </template>
              <el-button
                size="small"
                class="history-pop-back"
                data-test="history-back"
                :disabled="!graphHistory.learningViewing"
                @click="graphHistory.backToLiveLearning()"
              >返回当前图谱</el-button>
            </div>
          </el-popover>

          <!-- 缩放控制 (治"放大看不全 / 缩小看不清"): 滚轮可缩放, 提供步进 + 一键适应全图 -->
          <div class="zoom-controls">
            <button class="persona-btn" :disabled="!graphReady" title="放大" @click="zoomIn">＋</button>
            <button class="persona-btn" :disabled="!graphReady" title="缩小" @click="zoomOut">－</button>
            <button class="persona-btn" :disabled="!graphReady" title="整个图谱适应画布" @click="fitGraph">适应画布</button>
          </div>

          <!-- 更多 popover: 重置/导出/图例/快捷键 收纳 -->
          <el-popover placement="bottom" :width="240" trigger="click">
            <template #reference>
              <el-button>更多</el-button>
            </template>
            <div class="more-pop">
              <div class="more-actions">
                <el-button size="small" :icon="RefreshRight" @click="resetGraph" :disabled="!graphReady">重置</el-button>
                <el-button size="small" @click="exportGraph" :disabled="!graphReady">导出 JSON</el-button>
                <el-button size="small" data-test="export-excalidraw" @click="exportExcalidraw" :disabled="!graphReady">导出 .excalidraw</el-button>
              </div>
              <div class="more-section">
                <div class="more-section-title">节点颜色 · 难度</div>
                <div class="legend-item">
                  <span class="dot" :style="{ background: difficultyColor(1) }"></span> ⭐ 入门 (1-2)
                </div>
                <div class="legend-item">
                  <span class="dot" :style="{ background: difficultyColor(3) }"></span> ⭐⭐⭐ 进阶 (3)
                </div>
                <div class="legend-item">
                  <span class="dot" :style="{ background: difficultyColor(4) }"></span> ⭐⭐⭐⭐⭐ 高级 (4-5)
                </div>
                <div class="more-section-title">节点边框 · 掌握度</div>
                <div class="legend-item"><span class="dot mastered-dot"></span> 已掌握 (≥80%)</div>
                <div class="legend-item"><span class="dot" :style="{ border: `1px solid ${difficultyColor(1)}` }"></span> 未掌握 (细灰框)</div>
              </div>
              <div class="more-section">
                <div class="more-section-title">快捷键</div>
                <div class="legend-item"><code>Esc</code> 清除高亮/搜索</div>
                <div class="legend-item"><code>滚轮</code> 缩放</div>
                <div class="legend-item"><code>拖拽空白</code> 平移画布</div>
                <div class="legend-item"><code>点击节点</code> 查看详情</div>
                <div class="legend-item"><code>拖拽节点</code> 调整位置</div>
              </div>
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

        <!-- 侧边面板 (split 分栏 + 可折叠, flex 推挤画布不压节点; T3 由浮层改占位) -->
        <div class="side-panel" :class="{ collapsed: panelCollapsed }">
          <button class="panel-toggle" @click="panelCollapsed = !panelCollapsed"
                  :title="panelCollapsed ? '展开详情面板' : '收起详情面板'">
            <el-icon><ArrowUp v-if="panelCollapsed" /><ArrowDown v-else /></el-icon>
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
                <span class="value">{{ estimatedHours }}h · ≈{{ estimatedWeeks }}周</span>
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
              <!-- 不懂就问 / 重测该点: 概念不熟→问 AI; 想判断"会不会"→重测该知识点 -->
              <div class="detail-actions">
                <el-button
                  type="primary"
                  plain
                  size="small"
                  class="ask-ai-btn"
                  data-test="ask-ai"
                  @click="askAiAboutNode"
                >问 AI 助手</el-button>
                <!-- issue-70: 以对话形式导读图谱 (预填导读请求 → 切 chat 视图) -->
                <el-button
                  size="small"
                  data-test="graph-guide"
                  @click="graphGuide"
                >图谱导读</el-button>
                <el-button
                  size="small"
                  data-test="reassess-node"
                  @click="reassessNode"
                >重测该点</el-button>
                <!-- issue-64: 移除装饰性引导小字 (按钮文案已自说明) -->
              </div>
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
import { Search, RefreshRight, Loading, ArrowDown, ArrowUp } from '@element-plus/icons-vue'
import { Graph } from '@antv/g6'
import { useAssessmentStore } from '@/stores/assessment'
import { useGraphData } from '@/composables/useGraphData'
import { useGraphHistoryStore } from '@/stores/graphHistory'
import { masteryColor, difficultyColor } from '@/utils/format'
import { cjkAwareWidth } from '@/utils/nodeSize'
import { graphToExcalidraw, downloadExcalidraw, collectG6Positions } from '@/utils/excalidrawExport'
import { semanticSearch, getByCategory, getByDifficulty, getNode, getPrerequisites } from '@/api/graph'
import { ElMessage } from 'element-plus'
import { useSidebarStore } from '@/stores/sidebar'
import { useChatStore } from '@/stores/chat'
import { buildNodeQuestion, graphGuidePrompt } from '@/utils/askAi'
import PathFinderModal from '@/components/PathFinderModal.vue'

const store = useAssessmentStore()
const sidebar = useSidebarStore()
const chat = useChatStore()

// 历史回看态 (graphHistory store): learningSnapshot 非空 = 只读回看历史快照,
// 显示层覆写 (displayGraph), live 图谱 (store.knowledgeGraph) 永不被覆盖 → 任意时刻可返回
const graphHistory = useGraphHistoryStore()
const displayGraph = computed(() => graphHistory.learningSnapshot || store.knowledgeGraph)
const data = useGraphData(displayGraph)

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
// W2 布局优化: 高度保持三档, 宽度改按标签 CJK 感知动态计算 (utils/nodeSize) —
// 固定宽对长中文名截断、短名空旷; [wMin,wMax] 为各 persona 的宽度钳制区间
const PERSONA = {
  beginner:     { h: 84, wMin: 200, wMax: 300, label: (d) => `${d?.label || d.id}\n${d?.category || ''} · ${'⭐'.repeat(d?.difficulty || 1)}` },
  intermediate: { h: 72, wMin: 176, wMax: 264, label: (d) => `${d?.label || d.id}\n${'⭐'.repeat(d?.difficulty || 1)}` },
  advanced:     { h: 60, wMin: 152, wMax: 232, label: (d) => `${d?.label || d.id}` },
}
const personaCfg = () => PERSONA[sidebar.persona] || PERSONA.intermediate

// 节点多自动收窄一档 (>12 节点时宽度 ×0.85, 让 dagre 少占横向空间、fitView 后字仍可读)
const NODE_COUNT_COMPACT_THRESHOLD = 12
const COMPACT_SCALE = 0.85
function nodeCountScale(count) {
  return count > NODE_COUNT_COMPACT_THRESHOLD ? COMPACT_SCALE : 1
}
// 单节点宽度 (闭包注入 persona cfg 与缩放系数): 标签最宽行 CJK 感知估算 + 32px 内边距
function nodeWidthFor(d, cfg, scale) {
  return Math.round(cjkAwareWidth(cfg.label(d), { min: cfg.wMin, max: cfg.wMax, padding: 32 }) * scale)
}

// issue: 学习图谱历史 (只读回看, 不覆盖 live; 渲染源经 displayGraph 覆写)
const learningHistoryItems = computed(() => graphHistory.items.filter((i) => i.type === 'learning').slice(0, 5))
function loadLearningHistory(item) {
  graphHistory.viewLearning(item)
}
function fmtTs(ts) {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch { return '' }
}

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

// issue-70: 知识图谱专业导读 — 以对话形式在 AI 助手中逐步导航 (预填导读请求)
function graphGuide() {
  chat.setDraft(graphGuidePrompt())
  sidebar.setView('chat')
}

// 重测该点: 以该知识点为目标方向重新测评 (判掌握度), 进入学习会话
function reassessNode() {
  const n = selectedNode.value
  if (!n) return
  const target = n.name || n.node_id
  store.startAssessment({ targetDirection: target })
  sidebar.setView('learning-session')
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
// 筛选 popover 已选数 (驱动 badge): 仅统计非默认值
const activeFilterCount = computed(() => {
  let n = 0
  if (categoryFilter.value) n++
  if (difficultyFilter.value !== null && difficultyFilter.value !== '') n++
  if (masteryFilter.value) n++
  return n
})

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
// 布局切换 (借鉴 Understand-Anything 混合布局): TB 层次深 / LR 宽屏友好 / 力导向聚类疏朗浏览
// ---------------------------------------------------------------
const LAYOUT_MODES = [
  { id: 'tb', label: '层次·上下', desc: '按前置依赖自顶向下分层 (默认)' },
  { id: 'lr', label: '层次·左右', desc: '横向展开, 宽屏显示器更省纵向空间' },
  { id: 'force', label: '力导向聚类', desc: '按分类聚簇 + 斥力散开, 浏览模式更疏朗' },
]
const layoutMode = ref('tb')

function setLayoutMode(id) {
  if (layoutMode.value === id) return
  layoutMode.value = id
}

// 各布局的配置 (cfg: persona 节点尺寸; dims: 当前数据的宽度统计 — 间距随节点尺寸联动,
// 治"固定间距 + 大节点 = 挤/空两极")
function getLayoutConfig(cfg, dims = { maxW: 240, avgW: 220, h: 72 }) {
  if (layoutMode.value === 'lr') {
    // LR: 横向展开, ranksep 沿流向(横向)随节点宽拉大, nodesep 纵向随高度
    return {
      type: 'dagre', rankdir: 'LR',
      nodesep: dims.h + 26,
      ranksep: Math.max(150, dims.maxW + 50),
      nodeSize: [dims.maxW, dims.h],
    }
  }
  if (layoutMode.value === 'force') {
    // 力导向 + 按分类聚簇 (d3-force clustering): 同分类相互吸引成簇, 簇间斥力散开
    // collide/linkDistance 随节点宽联动, 防大卡片互压
    return {
      type: 'd3-force',
      linkDistance: Math.max(150, dims.avgW + 60),
      nodeStrength: -120,
      preventOverlap: true,
      collide: { radius: Math.round(dims.avgW / 2) + 28 },
      clustering: true,
      clusterBy: (n) => n?.data?.category || '未分类',
    }
  }
  // TB: 层间纵向间距随节点高联动; nodeSize 取当前数据最大宽 (dagre 保守防重叠)
  return {
    type: 'dagre', rankdir: 'TB', nodesep: 90,
    ranksep: Math.max(140, dims.h + 70),
    nodeSize: [dims.maxW, dims.h],
  }
}

// ---------------------------------------------------------------
// 图谱状态
// ---------------------------------------------------------------
const graphContainer = ref(null)
// 容器尺寸自适应 ResizeObserver (AI 分屏显隐/面板拖宽时画布跟随)
let _ro = null
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
  displayGraph.value?.estimated_total_hours ?? '--',
)

// issue-78: 节奏语境 — 按每周 6h 折周
const estimatedWeeks = computed(() => {
  const h = Number(displayGraph.value?.estimated_total_hours || 0)
  return h > 0 ? Math.max(1, Math.ceil(h / 6)) : 0
})

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
// tooltip 内容 (悬停即见: 名称 + 分类/难度/掌握度 + 摘要 + 关键点前 2 条)
// summary/key_points 来自知识库, 经 escapeHtml 防注入
function escapeHtml(s) {
  return String(s ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;')
}

function buildTooltipHtml(d) {
  if (!d) return ''
  const mastery = Math.round((d.mastery ?? 0) * 100)
  const kps = (Array.isArray(d.key_points) ? d.key_points : [])
    .slice(0, 2)
    .map((k) => `<li>${escapeHtml(k)}</li>`)
    .join('')
  const summary = d.summary
    ? escapeHtml(d.summary.length > 100 ? d.summary.slice(0, 100) + '…' : d.summary)
    : ''
  return `
    <div class="kg-tip">
      <div class="kg-tip-title">${escapeHtml(d.label || '')}</div>
      <div class="kg-tip-meta">${escapeHtml(d.category || '未分类')} · ${'⭐'.repeat(d.difficulty || 1)} · 掌握 ${mastery}%</div>
      ${summary ? `<div class="kg-tip-summary">${summary}</div>` : ''}
      ${kps ? `<ul class="kg-tip-kps">${kps}</ul>` : ''}
    </div>`
}

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
    // 详情面板改底部抽屉, 画布拿满全宽 (不避让)
    const containerWidth = graphContainer.value.offsetWidth || 800
    const containerHeight = graphContainer.value.offsetHeight || 600

    // 布局随 layoutMode 切换 (dagre TB/LR 层次 or d3-force 聚类); 间距/尺寸随 persona + 实际标签联动
    const cfg = personaCfg()
    const { nodes, edges } = buildG6Data()
    // 宽度统计: 每节点标签 CJK 感知估宽 → max (dagre 保守防重叠) / avg (force 间距)
    const scale = nodeCountScale(nodes.length)
    const nodeWs = nodes.map((n) => nodeWidthFor(n.data, cfg, scale))
    const dims = {
      maxW: Math.max(cfg.wMin, ...nodeWs),
      avgW: Math.round(nodeWs.reduce((a, b) => a + b, 0) / Math.max(1, nodeWs.length)),
      h: cfg.h,
    }
    const layoutConfig = getLayoutConfig(cfg, dims)
    const isForce = layoutMode.value === 'force'

    graph = new Graph({
      container: graphContainer.value,
      width: containerWidth,
      height: containerHeight,
      data: { nodes, edges },
      layout: layoutConfig,
      // 界面太小导致"放大看不全/缩小看不清": render 后自动把整个图谱适应到画布,
      // 并限制滚轮缩放范围 (0.3 倍以下标签不可读, 4 倍以上无意义)
      autoFit: { type: 'view', options: { when: 'always', direction: 'both' } },
      zoomRange: [0.3, 4],
      node: {
        type: 'rect',
        style: {
          // 难度着色 (单域路径全同 category, 按分类着色会全图同色; 难度天然有梯度)
          fill: (d) => difficultyColor(d.data?.difficulty || 1),
          // W2: 宽度按标签 CJK 感知动态计算 (长名不截断/短名不空旷), 高度按 persona
          size: (d) => [nodeWidthFor(d.data, cfg, scale), cfg.h],
          labelText: (d) => cfg.label(d.data),
          labelPlacement: 'center',
          labelFontSize: 13,
          labelFill: '#ffffff',
          labelLineHeight: 20,
          // labelMaxWidth 跟随自身卡片宽 (宽 - 左右内边距), 达到 wMax 上限才截断
          labelMaxWidth: (d) => nodeWidthFor(d.data, cfg, scale) - 24,
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
        // force 布局下用 drag-element-force: 拖动时固定节点参与力仿真, 松手跟随,
        // 普通 drag-element 会被力仿真持续拉回原位
        isForce ? 'drag-element-force' : 'drag-element',
        { type: 'hover-activate', degree: 1, direction: 'both' },
      ],
      plugins: [
        // 悬停即见摘要 (治"看不到具体信息"): 不开面板不点节点, 扫一眼全图获取节点信息
        {
          type: 'tooltip',
          trigger: 'hover',
          getContent: (_evt, items) => buildTooltipHtml(items?.[0]?.data),
        },
        // 小地图 (治缩放后迷路): 左下角缩略导航, 避开右侧详情浮层
        { type: 'minimap', size: [180, 110], position: 'right-top' },
      ],
    })

    graph.on('node:click', async (evt) => {
      const nodeId = evt.target?.id
      if (!nodeId) return
      await selectNode(nodeId)
    })

    // 防御: G6 5.1.1 部分环境渲染完成后 afterrender 事件未达 (headless 实测),
    // minimap 依赖该事件初始化 (debounced renderMinimap), 显式补发一次;
    // 事件正常时重复触发仅幂等重绘, 无副作用
    graph.render().then(() => {
      try { graph.emit('afterrender', { type: 'afterrender' }) } catch { /* ignore */ }
    })
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

// 筛选 popover "清空筛选": 复位三个筛选条件并重算高亮 (C2)
function clearAllFilters() {
  categoryFilter.value = ''
  difficultyFilter.value = null
  masteryFilter.value = ''
  handleFilterChange()
}

// 面包屑: 点击分类过滤 (借鉴 Breadcrumb)
function setCategoryFilter(cat) {
  categoryFilter.value = cat || ''
  handleFilterChange()
}

// 导出学习路径 JSON (借鉴 ExportMenu); 导出当前正在查看的图谱 (历史回看时即快照)
function exportGraph() {
  const payload = JSON.stringify({
    target_direction: store.profile?.target_direction,
    knowledge_graph: displayGraph.value,
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

// W3: 确定性导出 .excalidraw (借鉴 excalidraw-skill 的设计规范, 转换全程确定性:
// 坐标取 G6 render 后实际位置, 拖动节点连线跟随; excalidraw.com / VS Code 插件可继续编辑)
function exportExcalidraw() {
  if (!graph) return
  const base = data.g6Nodes.value
  if (!base.length) return
  const scale = nodeCountScale(base.length)
  const cfg = personaCfg()
  const exNodes = base.map((n) => ({
    id: n.id,
    label: n.data?.label || n.id,
    color: difficultyColor(n.data?.difficulty || 1),
  }))
  const exEdges = data.g6Edges.value.map((e) => ({ source: e.source, target: e.target }))
  const sizeOf = (id) => {
    const n = base.find((x) => x.id === id)
    return { width: nodeWidthFor(n?.data || {}, cfg, scale), height: cfg.h }
  }
  const positions = collectG6Positions(graph, base.map((n) => n.id), sizeOf)
  const scene = graphToExcalidraw(exNodes, exEdges, positions)
  const name = store.profile?.name || '学习图谱'
  downloadExcalidraw(scene, `KMatch-${name}-${Date.now()}.excalidraw`)
  ElMessage.success('已导出 .excalidraw — excalidraw.com 或 VS Code Excalidraw 插件可打开编辑')
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

// 缩放控制: 步进放大/缩小 + 一键适应全图 (滚轮缩放由 zoom-canvas 行为提供)
function zoomIn() { graph?.zoomBy(1.25, true) }
function zoomOut() { graph?.zoomBy(0.8, true) }
function fitGraph() { graph?.fitView({ when: 'always', direction: 'both' }) }

function rebuildGraph() {
  destroyGraph()
  if (hasPathData.value || extraNodes.value.length > 0) {
    initGraph()
  }
}

// 性能(C): persona/Layout 快速切换 → rAF 合并重建 (一帧内多次只重建一次, 防大图谱重排卡顿)
let _rebuildRaf = 0
function scheduleRebuild() {
  if (_rebuildRaf) return
  _rebuildRaf = requestAnimationFrame(() => { _rebuildRaf = 0; rebuildGraph() })
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
  // 容器尺寸自适应: AI 助手分屏显隐 / ResizablePanel 拖宽 / 窗口缩放时画布跟随,
  // 否则隐藏右侧分屏后图谱仍停在旧宽度, 留大片空白 (用户反馈"占不满全屏")
  if (typeof ResizeObserver !== 'undefined') {
    _ro = new ResizeObserver(() => {
      if (graph && graphContainer.value) {
        graph.resize()
      }
    })
    if (graphContainer.value) _ro.observe(graphContainer.value)
  }
  // issue-76: 用户拖拽移动画布 → 详情面板自动收起 (点击节点再展开)
  if (graphContainer.value) disposeCanvasCollapse = bindCanvasCollapse(graphContainer.value)
})

// issue-76: pointer 位移超阈值视为"移动图谱", 收起详情抽屉
function bindCanvasCollapse(el) {
  let downX = 0
  let downY = 0
  let tracking = false
  const onDown = (e) => { downX = e.clientX; downY = e.clientY; tracking = true }
  const onMove = (e) => {
    if (!tracking) return
    if (Math.hypot(e.clientX - downX, e.clientY - downY) > 8) {
      tracking = false
      if (!panelCollapsed.value) panelCollapsed.value = true
    }
  }
  const onUp = () => { tracking = false }
  el.addEventListener('pointerdown', onDown)
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
  return () => {
    el.removeEventListener('pointerdown', onDown)
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }
}
let disposeCanvasCollapse = null

// 当显示源变化时重建 (live 图谱更新 / 进入·退出历史回看 / 历史快照间切换)
watch(displayGraph, async (newVal) => {
  if (newVal?.learning_path?.length > 0) {
    destroyGraph()
    await fetchPrerequisites()
    initGraph()
  } else {
    // 回到无数据态 (如 live 为空时退出历史回看) → 回空态页, 历史列表可见
    destroyGraph()
    graphReady.value = false
  }
}, { deep: true })

// 新测评完成 (live 图谱更新) → 自动退出历史回看态, 展示最新结果
watch(() => store.knowledgeGraph, (nv) => {
  if (nv) graphHistory.backToLiveLearning()
})

// 快捷键 (借鉴 KeyboardShortcutsHelp): Esc 收起详情抽屉 / 清除高亮
function handleKeydown(e) {
  if (e.key !== 'Escape') return
  if (!panelCollapsed.value && selectedNode.value) { panelCollapsed.value = true; return }
  clearHighlight()
}
onMounted(() => { window.addEventListener('keydown', handleKeydown) })

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  disposeCanvasCollapse?.()
  disposeCanvasCollapse = null
  if (_rebuildRaf) { cancelAnimationFrame(_rebuildRaf); _rebuildRaf = 0 }
  _ro?.disconnect()
  _ro = null
  destroyGraph()
})

// 角色切换 -> 重建图谱 (节点详略变化)   (rAF 合并防连点卡顿)
watch(() => sidebar.persona, () => { scheduleRebuild() })

// 布局切换 -> 重建图谱 (layout 配置在 init 时注入)
watch(layoutMode, () => { scheduleRebuild() })
</script>

<style scoped>
.graph-page { padding: 0; height: 100%; display: flex; flex-direction: column; min-height: 0; }
/* issue-84: 空态 (未生成图谱) 在可用区域垂直+水平居中 */
.graph-page > .el-empty {
  flex: 1;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
}

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
.stale-banner { margin-bottom: 8px; }
.graph-stats { margin-left: auto; }
.cat-dist-section { display: flex; flex-direction: column; gap: 4px; margin-top: 4px; }
.cat-dist-section > .label { color: var(--km-gray-500); font-size: 13px; margin-bottom: 2px; }
.cat-dist { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--km-gray-700); }
.cat-name { flex: 1; }
.cat-count { font-family: var(--km-font-mono); color: var(--km-gray-800); font-weight: 600; }
.breadcrumb { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--km-gray-500); padding: 8px 12px; background: var(--km-bg-layer-2); border-radius: var(--km-radius-sm); flex-wrap: wrap; }
.bc-item { white-space: nowrap; }
.bc-clickable { cursor: pointer; color: var(--km-primary); }
.bc-clickable:hover { text-decoration: underline; }
.bc-current { color: var(--km-gray-800); font-weight: 600; }
.bc-sep { color: var(--km-gray-400); }
.persona-selector { display: inline-flex; gap: 2px; background: var(--km-bg-layer-2); border-radius: var(--km-radius-sm); padding: 2px; }
.persona-btn { border: 0; background: transparent; color: var(--km-gray-500); font-size: 12px; padding: 3px 10px; border-radius: var(--km-radius-xs); cursor: pointer; transition: color 0.15s, background 0.15s; }
.persona-btn:hover { color: var(--km-gray-700); }
.persona-btn.active { background: var(--km-primary); color: #fff; }
/* 布局切换按钮组 (复用 persona-btn 视觉) */
.layout-selector { display: inline-flex; gap: 2px; background: var(--km-bg-layer-2); border: 1px solid var(--km-border-light); border-radius: var(--km-radius-sm); padding: 2px; }
/* 缩放控制按钮组 */
.zoom-controls { display: inline-flex; gap: 2px; background: var(--km-bg-layer-2); border: 1px solid var(--km-border-light); border-radius: var(--km-radius-sm); padding: 2px; }
.zoom-controls .persona-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.graph-stats {
  color: var(--km-gray-500); font-size: 13px; white-space: nowrap;
  font-family: var(--km-font-mono);
}

/* ---- 筛选 popover (C2: 3 select 收纳 + 已选 badge) ---- */
.filter-active { color: var(--km-primary); border-color: var(--km-primary); }
.filter-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 16px; height: 16px; padding: 0 4px; margin-left: 4px;
  border-radius: 999px; background: var(--km-primary); color: #fff;
  font-size: 10px; font-weight: 700; line-height: 1;
}
.filter-pop { display: flex; flex-direction: column; gap: 10px; }
.filter-row { display: flex; align-items: center; gap: 10px; }
.filter-label { flex-shrink: 0; width: 56px; font-size: 12px; color: var(--km-gray-600); }
.filter-pop .filter-select { flex: 1; width: 100%; }
.filter-pop-actions { display: flex; justify-content: flex-end; }

/* ---- 更多 popover (重置/导出/图例/快捷键) ---- */
.more-pop { display: flex; flex-direction: column; gap: 6px; }
.more-pop .more-actions { display: flex; gap: 6px; }
.more-section {
  margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--km-border-light);
  display: flex; flex-direction: column; gap: 6px;
}
.more-section:first-child { margin-top: 0; padding-top: 0; border-top: 0; }
.more-section-title {
  font-size: 11px; font-weight: 600; color: var(--km-gray-500);
  text-transform: uppercase; letter-spacing: 0.3px;
}
.legend-item { display: flex; align-items: center; gap: 8px; }
.legend-item code {
  font-size: 11px; background: var(--km-gray-100);
  padding: 1px 5px; border-radius: var(--km-radius-xs);
  color: var(--km-gray-700);
}
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

/* ---- 历史回看横幅 + 历史弹层 (issue: 钻入历史后无返回路径) ---- */
.history-banner {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 8px 14px; margin-bottom: 12px;
  border: 1px dashed var(--km-primary); border-radius: var(--km-radius-sm);
  background: color-mix(in srgb, var(--km-primary) 7%, transparent);
}
.history-banner .hb-text { font-size: 12.5px; color: var(--km-gray-700); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-banner .hb-text b { color: var(--km-primary); }
.history-pop { display: flex; flex-direction: column; gap: 6px; }
.history-pop-empty { font-size: 12px; color: var(--km-gray-500); padding: 4px 0; }
.history-pop-title { font-size: 11px; color: var(--km-gray-500); margin-bottom: 2px; }
.history-pop-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; border: 1px solid var(--km-border); border-radius: var(--km-radius-xs);
  cursor: pointer; font-size: 12.5px;
}
.history-pop-item:hover { border-color: var(--km-primary); background: var(--km-primary-light); }
.history-pop-item.active { border-color: var(--km-primary); background: color-mix(in srgb, var(--km-primary) 12%, transparent); }
.history-pop-item .hp-name { flex: 1; color: var(--km-gray-700); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-pop-item .hp-time { font-size: 11px; color: var(--km-gray-400); font-family: var(--km-font-mono); }
.history-pop-back { margin-top: 2px; }

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

/* ---- 详情面板 (底部抽屉, 画布全宽不避让; 可折叠; 复用 ProjectGraphView 模式) ---- */
.side-panel {
  position: absolute; bottom: 0; left: 0; right: 0;
  max-height: 240px; overflow-y: auto;
  display: flex; flex-direction: column; gap: 10px;
  z-index: 5;
  background: var(--km-bg-layer-2);
  border-top: 1px solid var(--km-border-light);
  box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.08);
  transition: max-height 0.2s ease;
}
.side-panel.collapsed { max-height: 36px; overflow: hidden; }
.side-panel.collapsed > *:not(.panel-toggle) { display: none; }
.panel-toggle {
  position: sticky; top: 0; align-self: flex-end; z-index: 6;
  width: 28px; height: 28px; margin: 6px 10px 0 0;
  border: 1px solid var(--km-border);
  border-radius: var(--km-radius-xs); background: var(--km-bg-layer-2); color: var(--km-gray-500);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  font-size: 13px;
}
.panel-toggle:hover { color: var(--km-primary); border-color: var(--km-primary); }
/* 折叠态: 全宽细条, primary 底, 明确可点展开 */
.side-panel.collapsed .panel-toggle {
  align-self: stretch;
  width: auto; height: 36px; margin: 0;
  border-radius: 0; border: none;
  background: var(--km-primary); color: #fff; font-size: 16px;
}
.side-panel.collapsed .panel-toggle:hover { background: var(--km-primary-active); }
.panel-card :deep(.el-card) {
  --el-card-bg-color: transparent;
  --el-card-border-color: transparent;
  box-shadow: none;
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
  border-radius: var(--km-radius-xs); font-size: 12px;
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
.ask-ai-btn { margin-top: 14px; }
.detail-actions { margin-top: 14px; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.prereq-section > .label {
  display: block; color: var(--km-gray-500);
  font-size: 13px; margin-bottom: 6px;
}
.prereq-list { display: flex; flex-wrap: wrap; gap: 4px; }
.prereq-tag { cursor: pointer; }
.prereq-tag:hover { opacity: 0.8; }
/* issue: 学习图谱历史列表 (空态内) */
.gh-history { margin-top: 18px; width: min(420px, 90%); text-align: left; }
.gh-history-title { font-size: 11px; color: var(--km-gray-500); margin-bottom: 6px; }
.gh-history-item {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 12px; margin-bottom: 4px;
  border: 1px solid var(--km-border-light); border-radius: var(--km-radius-sm);
  background: var(--km-bg-layer-2); cursor: pointer;
  transition: border-color 0.15s var(--km-ease), background 0.15s var(--km-ease);
}
.gh-history-item:hover { border-color: var(--km-primary); background: var(--km-primary-light); }
.gh-history-item .ph-name { flex: 1; font-size: 12.5px; color: var(--km-gray-700); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gh-history-item .ph-time { font-size: 11px; color: var(--km-gray-400); font-family: var(--km-font-mono); }
</style>

<!-- tooltip 内容样式 (非 scoped: G6 tooltip 插件生成的 HTML 不带本组件 data-v, scoped 选不中;
     底色为插件默认白卡, 文字用固定中性色保证可读) -->
<style>
.kg-tip { max-width: 280px; padding: 2px 0; text-align: left; }
.kg-tip-title { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 4px; }
.kg-tip-meta { font-size: 11px; color: #909399; margin-bottom: 6px; }
.kg-tip-summary { font-size: 12px; color: #606266; line-height: 1.6; margin-bottom: 4px; }
.kg-tip-kps { margin: 0; padding-left: 16px; font-size: 12px; color: #606266; line-height: 1.7; }
</style>
