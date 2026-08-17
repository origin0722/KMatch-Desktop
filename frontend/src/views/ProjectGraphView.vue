<template>
  <div class="project-graph-page km-workbench">
    <!-- 页面标题栏已去除 (左侧导航已标识当前视图, 避免重复; 统计并入工具栏右侧) -->

    <!-- 技术栈自动检测 (AST 数据驱动, 零 LLM) -->
    <div v-if="techStack.length" class="pg-tech-bar">
      <span class="pg-tech-label">技术栈</span>
      <el-tag
        v-for="t in techStack"
        :key="t.name"
        size="small"
        class="pg-tech-tag"
        @click="searchTechResource(t.name)"
      >{{ t.name }} <span class="pg-tech-cat">{{ t.category }}</span></el-tag>
    </div>

    <!-- 过期提示 (源文件被外部改动, 行号漂移) -->
    <el-alert v-if="pg.stale" type="warning" :closable="false" show-icon class="pg-stale">
      项目图谱已过期 (源文件被外部改动, 行号可能漂移), 建议在 AI 助手中重新解析
    </el-alert>

    <!-- 空状态 / 解析中 / 解析失败 -->
    <div v-if="!pg.graph" class="pg-empty-wrap">
      <!-- 解析中 -->
      <div v-if="pg.parsing" class="pg-empty-state">
        <el-icon class="is-loading pg-spin" :size="48"><Loading /></el-icon>
        <p class="pg-empty-title">正在解析项目代码…</p>
        <p class="pg-hint">提取函数 / 类 / 方法与调用关系, 同时写入知识图谱</p>
      </div>
      <!-- 解析失败 -->
      <div v-else-if="pg.parseError" class="pg-empty-state">
        <el-empty :description="pg.parseError" :image-size="100" />
        <el-button type="primary" :icon="RefreshRight" @click="handleParse">重新解析</el-button>
      </div>
      <!-- 未解析 -->
      <el-empty v-else description="尚未生成项目图谱" :image-size="120">
        <p class="pg-hint">打开项目后自动解析, 也可手动触发</p>
        <div class="pg-empty-actions">
          <el-button type="primary" :icon="RefreshRight" :disabled="!ws.hasProject" @click="handleParse">解析当前项目</el-button>
          <el-button @click="goCode">前往代码视图</el-button>
        </div>
      </el-empty>
    </div>

    <template v-else>
      <!-- 工具栏 (C2: 图例+深度分析收"更多", 重置+重新解析合并, 统计移入页头, 主行 6 组) -->
      <el-card class="toolbar-card" shadow="never">
        <div class="toolbar">
          <el-input
            v-model="searchQuery"
            placeholder="搜索实体名…"
            :prefix-icon="Search"
            clearable
            class="search-input"
            @input="rebuildGraph"
            @clear="rebuildGraph"
          />
          <el-divider direction="vertical" />
          <el-select
            v-model="kindFilter"
            placeholder="全部类型"
            clearable
            class="filter-select"
            @change="rebuildGraph"
          >
            <el-option label="function 函数" value="function" />
            <el-option label="class 类" value="class" />
            <el-option label="method 方法" value="method" />
            <el-option label="module 模块" value="module" />
          </el-select>
          <!-- 重置+重新解析合并: 一次操作复位视图并拉取最新源码 -->
          <el-button :icon="RefreshRight" :loading="pg.parsing" @click="handleReparse">重新解析</el-button>
          <el-divider direction="vertical" />
          <!-- 视图模式: 分层 dagre (调用层级) / 模块分组 combo (架构视角) -->
          <div class="view-mode-selector">
            <button
              v-for="m in VIEW_MODES"
              :key="m.id"
              class="vm-btn"
              :class="{ active: viewMode === m.id }"
              :title="m.desc"
              @click="setViewMode(m.id)"
            >{{ m.label }}</button>
          </div>
          <el-button
            type="primary"
            plain
            :disabled="!pg.graph?.entities?.length"
            @click="startTour"
          >项目导读</el-button>

          <!-- 更多 popover: 图例 + 深度分析 收纳 -->
          <el-popover placement="bottom" :width="220" trigger="click">
            <template #reference>
              <el-button>更多</el-button>
            </template>
            <div class="more-pop">
              <div class="more-section">
                <div class="more-section-title">节点颜色</div>
                <div v-for="k in KINDS" :key="k" class="legend-item">
                  <span class="dot" :style="{ background: KIND_COLORS[k] }"></span> {{ k }}
                </div>
              </div>
              <div class="more-section">
                <div class="more-section-title">AI 分析</div>
                <el-button
                  type="warning"
                  plain
                  size="small"
                  :loading="pg.analyzing"
                  :disabled="!pg.graph?.projectId"
                  @click="handleAnalyze"
                >{{ pg.analysis ? '查看分析' : '深度分析' }}</el-button>
              </div>
            </div>
          </el-popover>

          <span v-if="pg.graph" class="pg-stats">
            实体 {{ filteredEntities.length }} / {{ pg.graph.entities.length }} | 关系 {{ filteredEdges.length }}
          </span>
        </div>
      </el-card>

      <!-- 主区: 画布 + 浮层详情 -->
      <div class="main-area">
        <div class="canvas-area">
          <div ref="containerRef" class="pg-canvas"></div>
        </div>

        <!-- 浮层详情面板 (可折叠, 画布避让不压节点) -->
        <div class="side-panel" :class="{ collapsed: panelCollapsed }">
          <button
            class="panel-toggle"
            @click="panelCollapsed = !panelCollapsed"
            :title="panelCollapsed ? '展开详情面板' : '收起详情面板'"
          >
            <el-icon><ArrowUp v-if="panelCollapsed" /><ArrowDown v-else /></el-icon>
          </button>

          <el-card v-if="selectedEntity" shadow="never" class="panel-card">
            <template #header><span>实体详情</span></template>
            <div class="entity-detail">
              <h4>{{ selectedEntity.name }}</h4>
              <div class="detail-row">
                <span class="label">类型</span>
                <el-tag
                  size="small"
                  :style="{ background: KIND_COLORS[selectedEntity.kind] || KIND_COLORS.default, color: '#fff', border: 'none' }"
                >{{ selectedEntity.kind || '未知' }}</el-tag>
              </div>
              <div class="detail-row" v-if="selectedEntity.qualified_name">
                <span class="label">全名</span>
                <code>{{ selectedEntity.qualified_name }}</code>
              </div>
              <div class="detail-row" v-if="selectedEntity.module_name">
                <span class="label">模块</span>
                <code>{{ selectedEntity.module_name }}</code>
              </div>
              <div class="detail-row" v-if="selectedEntity.line_start != null">
                <span class="label">行范围</span>
                <code>{{ selectedEntity.line_start }}-{{ selectedEntity.line_end }}</code>
              </div>
              <!-- docstring (折叠展示) -->
              <div v-if="selectedEntity.docstring" class="rel-section">
                <span class="label">文档字符串</span>
                <pre class="entity-docstring" @click="docstringExpanded = !docstringExpanded">{{ docstringExpanded ? selectedEntity.docstring : selectedEntity.docstring.slice(0, 120) + (selectedEntity.docstring.length > 120 ? '…' : '') }}</pre>
              </div>
              <!-- 参数列表 -->
              <div v-if="entityParams.length" class="rel-section">
                <span class="label">参数 ({{ entityParams.length }})</span>
                <div class="param-list">
                  <code v-for="p in entityParams" :key="p.name" class="param-item">{{ p.name }}<span v-if="p.annotation" class="param-type">: {{ p.annotation }}</span></code>
                </div>
              </div>
              <!-- 继承基类 -->
              <div v-if="selectedEntity.bases?.length" class="rel-section">
                <span class="label">继承</span>
                <div class="rel-list">
                  <el-tag v-for="b in selectedEntity.bases" :key="b" size="small" type="warning" class="rel-tag">{{ b }}</el-tag>
                </div>
              </div>
              <!-- 装饰器 -->
              <div v-if="selectedEntity.decorators?.length" class="rel-section">
                <span class="label">装饰器</span>
                <div class="rel-list">
                  <el-tag v-for="d in selectedEntity.decorators" :key="d" size="small" type="danger" class="rel-tag">{{ d }}</el-tag>
                </div>
              </div>
              <!-- 外部依赖 -->
              <div v-if="entityExternalDeps.length" class="rel-section">
                <span class="label">外部依赖 ({{ entityExternalDeps.length }})</span>
                <div class="rel-list">
                  <el-tag v-for="dep in entityExternalDeps" :key="dep" size="small" type="info" class="rel-tag">{{ dep }}</el-tag>
                </div>
              </div>
              <div v-if="callsOut.length" class="rel-section">
                <span class="label">调用 ({{ callsOut.length }})</span>
                <div class="rel-list">
                  <el-tag
                    v-for="c in callsOut"
                    :key="c.id"
                    size="small"
                    class="rel-tag"
                    @click="selectEntityById(c.id)"
                  >{{ c.name }}</el-tag>
                </div>
              </div>
              <div v-if="callsIn.length" class="rel-section">
                <span class="label">被调用 ({{ callsIn.length }})</span>
                <div class="rel-list">
                  <el-tag
                    v-for="c in callsIn"
                    :key="c.id"
                    size="small"
                    type="info"
                    class="rel-tag"
                    @click="selectEntityById(c.id)"
                  >{{ c.name }}</el-tag>
                </div>
              </div>
              <div class="entity-actions">
                <el-button
                  size="small"
                  type="primary"
                  :disabled="selectedEntity.line_start == null"
                  @click="jumpToCode(selectedEntity)"
                >跳转源码</el-button>
                <!-- 不懂就问: 实体上下文预填 AI 助手 (可编辑后发送, 不自动发) -->
                <el-button
                  size="small"
                  type="primary"
                  plain
                  data-test="ask-ai"
                  @click="askAiAboutEntity"
                >让 AI 解释</el-button>
              </div>
            </div>
          </el-card>

          <el-card v-else shadow="never" class="panel-card">
            <template #header><span>实体详情</span></template>
            <el-empty description="点击图谱节点查看详情" :image-size="60" />
          </el-card>
        </div>

        <!-- 项目导读浮条 (手动逐站, 按层级从入口下探) -->
        <div v-if="tourActive && tourStop" class="tour-bar">
          <span class="tour-progress">第 {{ tourStop.layer }} 层 · 第 {{ tourIndex + 1 }}/{{ tourStops.length }} 站</span>
          <el-tag size="small" type="warning">{{ TOUR_ROLE_LABELS[tourStop.role] || tourStop.role }}</el-tag>
          <span class="tour-name">{{ tourStop.entity?.name || tourStop.id }}</span>
          <span class="tour-kind">({{ tourStop.entity?.kind || '?' }})</span>
          <span class="tour-why">{{ tourStop.why }}</span>
          <div class="tour-actions">
            <el-button size="small" :disabled="tourIndex === 0" @click="tourStep(-1)">‹ 上一步</el-button>
            <el-button size="small" type="primary" :disabled="tourIndex >= tourStops.length - 1" @click="tourStep(1)">下一步 ›</el-button>
            <el-button size="small" type="primary" plain @click="askAiAboutEntity">问 AI</el-button>
            <el-button size="small" text @click="exitTour">退出</el-button>
          </div>
        </div>
      </div>
    </template>

    <!-- 深度分析结果弹窗 (从侧栏移出, 800px 宽屏展示) -->
    <el-dialog
      v-model="analysisDialogVisible"
      title="项目深度分析"
      width="800px"
      append-to-body
      :close-on-click-modal="false"
      class="analysis-dialog"
    >
      <template v-if="pg.analysis">
        <p v-if="pg.analysis.summary" class="analysis-summary">{{ pg.analysis.summary }}</p>

        <div v-if="pg.analysis.architecture" class="analysis-section">
          <div class="analysis-label">架构模式</div>
          <el-tag size="small">{{ pg.analysis.architecture.pattern || '未知' }}</el-tag>
          <div v-if="pg.analysis.architecture.entry_points?.length" class="analysis-sub">
            <span class="analysis-label-sm">入口点</span>
            <el-tag v-for="ep in pg.analysis.architecture.entry_points" :key="ep" size="small" type="info" class="analysis-tag">{{ ep }}</el-tag>
          </div>
          <div v-if="pg.analysis.architecture.key_modules?.length" class="analysis-sub">
            <span class="analysis-label-sm">关键模块</span>
            <div v-for="m in pg.analysis.architecture.key_modules" :key="m" class="analysis-module">{{ m }}</div>
          </div>
        </div>

        <div v-if="pg.analysis.complexity" class="analysis-section">
          <div class="analysis-label">复杂度</div>
          <el-tag size="small" :type="pg.analysis.complexity.level === '高' ? 'danger' : pg.analysis.complexity.level === '中' ? 'warning' : 'success'">
            {{ pg.analysis.complexity.level || '未知' }}
          </el-tag>
          <p v-if="pg.analysis.complexity.note" class="analysis-note">{{ pg.analysis.complexity.note }}</p>
        </div>

        <div v-if="pg.analysis.recommendations?.length" class="analysis-section">
          <div class="analysis-label">学习建议</div>
          <ul class="analysis-recs">
            <li v-for="(r, i) in pg.analysis.recommendations" :key="i">{{ r }}</li>
          </ul>
        </div>

        <div v-if="pg.analysis.tech_stack?.length" class="analysis-section">
          <div class="analysis-label">检测到的技术栈</div>
          <el-tag v-for="t in pg.analysis.tech_stack" :key="t" size="small" type="info" class="analysis-tag">{{ t }}</el-tag>
        </div>
      </template>

      <template #footer>
        <div class="analysis-footer">
          <el-button @click="handleReanalyze" :loading="pg.analyzing">重新分析</el-button>
          <el-button
            v-if="pg.analysis?.web_resources?.length"
            type="primary"
            @click="goToWebResources"
          >查看联网资源 ({{ pg.analysis.web_resources.length }})</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 项目代码图谱视图 (阶段4b + 本次补全)
 *
 * 数据来源: useProjectGraphStore.graph (由 chat generate_project_graph 委派工具填充)
 *   - entities: [{ id, name, qualified_name, kind, line_start, line_end }]
 *   - relations: [{ source, target, type }]
 *
 * 本次补全 (对齐知识图谱页交互水准):
 *   - 搜索框 + 类型筛选 (前端本地过滤)
 *   - 自适应节点宽度 (按 qualified_name 长度, 不再固定 140 截断)
 *   - 浮层详情面板 (调用/被调用关系 + 跳源码, 可折叠, 画布避让)
 *   - 图例 + 过期提示 + 关系统计
 */
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { Search, RefreshRight, ArrowDown, ArrowUp, Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { Graph } from '@antv/g6'
import { useProjectGraphStore } from '@/stores/projectGraph'
import { useSidebarStore } from '@/stores/sidebar'
import { useWorkspaceStore } from '@/stores/workspace'
import { useChatStore } from '@/stores/chat'
import { buildEntityQuestion } from '@/utils/askAi'
import { detectTechStack } from '@/utils/techStack'
import { buildTourStops, TOUR_ROLE_LABELS } from '@/utils/projectTour'
import http from '@/api'
import { useLearningResourcesStore } from '@/stores/learningResources'
import { useAiSettingsStore } from '@/stores/aiSettings'

const pg = useProjectGraphStore()
const sidebar = useSidebarStore()
const ws = useWorkspaceStore()
const chat = useChatStore()
const lr = useLearningResourcesStore()
const aiSettings = useAiSettingsStore()
const containerRef = ref(null)
let g6 = null

const KIND_COLORS = {
  function: '#5b8ff9',
  class: '#5ad8a6',
  method: '#f6bd16',
  module: '#6dc8ec',
  default: '#c8c6c4',
}
const KINDS = ['function', 'class', 'method', 'module']

// 视图模式: layered 分层 dagre (调用层级) / grouped 模块分组 combo (架构视角,
// 借鉴 Understand-Anything 按架构层级自动分组带颜色编码)
const VIEW_MODES = [
  { id: 'layered', label: '分层', desc: '按调用依赖自顶向下分层 (默认)' },
  { id: 'grouped', label: '模块分组', desc: '同模块实体收进一个带底色容器, 一眼看懂项目结构' },
]
const viewMode = ref('layered')

function setViewMode(id) {
  if (viewMode.value === id) return
  viewMode.value = id
}

// combo 容器配色 (浅色系循环, 与节点 KIND_COLORS 错开饱和度: 容器当"底色"不当主角)
const MODULE_COLORS = ['#8f9bb3', '#79a5b2', '#b2a179', '#a189b2', '#88b28d', '#b28787', '#7f8fb2', '#a3b287']

// ---------------------------------------------------------------
// 搜索 & 筛选状态
// ---------------------------------------------------------------
const searchQuery = ref('')
const kindFilter = ref('')
const selectedEntity = ref(null)
const panelCollapsed = ref(false)
const docstringExpanded = ref(false)

// 实体详情: 参数列表 (从 params 数组格式化)
const entityParams = computed(() => {
  const e = selectedEntity.value
  if (!e?.params) return []
  return e.params.filter((p) => p && p.name).slice(0, 12)
})

// 实体详情: 外部依赖 (external_calls 去重, 取 top-level 模块名)
const entityExternalDeps = computed(() => {
  const e = selectedEntity.value
  if (!e?.external_calls) return []
  const mods = new Set()
  for (const c of e.external_calls) {
    const name = typeof c === 'string' ? c : c?.name
    if (!name) continue
    mods.add(name.split('.')[0])
  }
  return [...mods].sort().slice(0, 15)
})

// 技术栈自动检测 (扫描所有实体 external_calls, 零 LLM)
const techStack = computed(() => {
  const g = pg.graph
  if (!g?.entities) return []
  return detectTechStack(g.entities)
})

// 搜索中标志 (技术栈 badge 点击触发联网搜索)
const searchingTech = ref(false)

// 技术栈 badge 点击 -> 联网搜该技术的学习资源 -> 跳转学习视图查看
async function searchTechResource(techName) {
  if (searchingTech.value) return
  searchingTech.value = true
  try {
    const data = await http.post('/api/search/web', {
      query: `${techName} Python 教程 入门`,
      max_results: 5,
      tavily_key: aiSettings.tavilyKey || undefined,
    })
    lr.addWebResources(techName, data?.results || [])
    ElMessage.success(`已搜索 ${techName} 学习资源`)
    sidebar.setView('learning')
  } catch (e) {
    ElMessage.warning('联网搜索失败, 请检查 Tavily Key 配置')
  } finally {
    searchingTech.value = false
  }
}

// 过滤后的实体 (按 kind + 名称子串)
const filteredEntities = computed(() => {
  const g = pg.graph
  if (!g) return []
  const q = searchQuery.value.trim().toLowerCase()
  return (g.entities || []).filter((e) => {
    if (kindFilter.value && e.kind !== kindFilter.value) return false
    if (q) {
      const name = (e.qualified_name || e.name || '').toLowerCase()
      if (!name.includes(q)) return false
    }
    return true
  })
})

// 过滤后的关系 (两端实体都在过滤集合中才保留)
const filteredEdges = computed(() => {
  const g = pg.graph
  if (!g) return []
  const ids = new Set(filteredEntities.value.map((e) => String(e.id)))
  return (g.relations || []).filter(
    (r) => ids.has(String(r.source)) && ids.has(String(r.target)),
  )
})

const entityById = (id) =>
  (pg.graph?.entities || []).find((e) => String(e.id) === String(id))

// 选中实体的调用 / 被调用关系
const callsOut = computed(() => {
  if (!selectedEntity.value || !pg.graph) return []
  const id = String(selectedEntity.value.id)
  return (pg.graph.relations || [])
    .filter((r) => String(r.source) === id)
    .map((r) => entityById(r.target))
    .filter(Boolean)
})
const callsIn = computed(() => {
  if (!selectedEntity.value || !pg.graph) return []
  const id = String(selectedEntity.value.id)
  return (pg.graph.relations || [])
    .filter((r) => String(r.target) === id)
    .map((r) => entityById(r.source))
    .filter(Boolean)
})

// ---------------------------------------------------------------
// 节点宽度自适应: 按 label 字符数估宽, 限 [120, 220]
// ---------------------------------------------------------------
function nodeWidth(label) {
  return Math.min(220, Math.max(120, (label || '').length * 8 + 24))
}

function buildData() {
  // 导读模式用全量实体 (忽略搜索/类型过滤), 保证导读上下文完整
  const source = tourActive.value ? (pg.graph?.entities || []) : filteredEntities.value
  const edgeSource = tourActive.value ? (pg.graph?.relations || []) : filteredEdges.value
  const stop = tourActive.value ? tourStop.value : null

  // grouped 模式: 按 module_name 建 combo 容器, 同模块实体收进一个容器 (架构视角)
  const grouped = viewMode.value === 'grouped'
  const combos = []
  if (grouped) {
    const modCount = new Map()
    for (const e of source) {
      if (!e.module_name) continue
      modCount.set(e.module_name, (modCount.get(e.module_name) || 0) + 1)
    }
    let i = 0
    for (const [mod, count] of modCount) {
      combos.push({
        id: `combo:${mod}`,
        data: { label: `${mod} · ${count}`, color: MODULE_COLORS[i++ % MODULE_COLORS.length] },
      })
    }
  }

  const nodes = source.map((e) => {
    const label = e.qualified_name || e.name || String(e.id)
    const data = { label, w: nodeWidth(label), kind: e.kind, entity: e }
    if (stop) {
      data.tourCurrent = String(e.id) === stop.id
      data.tourNeighbor = !data.tourCurrent && stop.neighborIds.has(String(e.id))
      data.dimmed = !data.tourCurrent && !data.tourNeighbor
    }
    const node = { id: String(e.id), data }
    if (grouped && e.module_name) node.combo = `combo:${e.module_name}`
    return node
  })
  const edges = edgeSource.map((r, i) => {
    const data = { type: r.type || 'call' }
    if (stop) {
      const sid = String(stop.id)
      data.tourEdge = String(r.source) === sid || String(r.target) === sid
    }
    return {
      id: `e${i}`,
      source: String(r.source),
      target: String(r.target),
      data,
    }
  })
  return grouped ? { nodes, edges, combos } : { nodes, edges }
}

function initGraph() {
  if (!containerRef.value) return
  const { nodes, edges, combos } = buildData()
  const grouped = viewMode.value === 'grouped' && combos?.length > 0

  // 详情面板改底部抽屉, 画布拿满全宽 (不避让)
  const w = containerRef.value.offsetWidth || 800
  const h = containerRef.value.offsetHeight || 600

  g6 = new Graph({
    container: containerRef.value,
    width: w,
    height: h,
    // grouped: combo-combined (combo 间力导向 + combo 内 grid 整齐排), combos 为空自动回落 dagre
    // layered: dagre 分层, nodeSize 用最大可能宽度 220 保守估防宽节点重叠
    layout: grouped
      ? { type: 'combo-combined', comboPadding: 30, comboSpacing: 90, layout: { type: 'grid' } }
      : { type: 'dagre', rankdir: 'TB', nodesep: 40, ranksep: 80, nodeSize: [220, 44] },
    data: { nodes, edges, ...(grouped ? { combos } : {}) },
    node: {
      type: 'rect',
      style: {
        fill: (d) => KIND_COLORS[d.data?.kind] || KIND_COLORS.default,
        size: (d) => [d.data?.w || 160, 34],
        labelText: (d) => d.data?.label || d.id,
        labelPlacement: 'center',
        labelFontSize: 11,
        labelFill: '#ffffff',
        labelMaxWidth: 200,
        // 导读模式: 当前站 primary 强调 / 邻居细描边 / 其余淡化; 平时浅灰描边
        stroke: (d) => (d.data?.tourCurrent || d.data?.tourNeighbor) ? '#6c7ce0' : '#e4e3e1',
        lineWidth: (d) => d.data?.tourCurrent ? 3 : d.data?.tourNeighbor ? 1.5 : 1,
        shadowBlur: (d) => (d.data?.tourCurrent ? 14 : 0),
        shadowColor: '#6c7ce0',
        opacity: (d) => (d.data?.dimmed ? 0.25 : 1),
        radius: 6,
      },
      state: { hover: { lineWidth: 2, shadowBlur: 10, shadowColor: KIND_COLORS.function } },
    },
    // 模块分组容器: 浅底色 + 同色虚线描边 + 顶部模块名, 做"底色"不做主角
    ...(grouped ? {
      combo: {
        type: 'rect',
        style: {
          fill: (d) => d.data?.color || '#8f9bb3',
          fillOpacity: 0.06,
          stroke: (d) => d.data?.color || '#8f9bb3',
          strokeOpacity: 0.45,
          lineWidth: 1.5,
          lineDash: [6, 4],
          radius: 10,
          labelText: (d) => d.data?.label || '',
          labelPlacement: 'top',
          labelFontSize: 11,
          labelFontWeight: 600,
          labelFill: (d) => d.data?.color || '#8f9bb3',
          labelOffsetY: 4,
        },
      },
    } : {}),
    edge: {
      style: {
        // 导读模式: 当前站关联边高亮, 其余淡化
        stroke: (d) => (d.data?.tourEdge ? '#6c7ce0' : '#c8c6c4'),
        lineWidth: (d) => (d.data?.tourEdge ? 2 : 1),
        endArrow: true,
        opacity: (d) => (tourActive.value && tourStop.value && !d.data?.tourEdge ? 0.15 : 1),
      },
    },
    behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element', { type: 'hover-activate', degree: 1, direction: 'both' }],
  })

  g6.on('node:click', (evt) => {
    const id = evt.target?.id
    const node = nodes.find((n) => n.id === id)
    if (node?.data?.entity) {
      selectedEntity.value = node.data.entity
      // 点击节点自动展开底部详情抽屉
      panelCollapsed.value = false
      // 保留原有跳转联动 (点击即跳源码)
      pg.requestReveal(node.data.entity.line_start, node.data.entity.line_end, node.data.entity.name)
    }
  })

  g6.render()
}

function destroyGraph() {
  if (g6) { try { g6.destroy() } catch { /* ignore */ }; g6 = null }
}

function rebuildGraph() {
  destroyGraph()
  if (pg.graph) initGraph()
}

function resetGraph() {
  searchQuery.value = ''
  kindFilter.value = ''
  selectedEntity.value = null
  rebuildGraph()
}

function selectEntityById(id) {
  const e = entityById(id)
  if (!e) return
  selectedEntity.value = e
  if (e.line_start != null) pg.requestReveal(e.line_start, e.line_end, e.name)
}

function jumpToCode(e) {
  if (e?.line_start != null) pg.requestReveal(e.line_start, e.line_end, e.name)
}

// 不懂就问: 实体上下文预填 AI 助手并切 chat 视图 (用户可编辑后发送)
function askAiAboutEntity() {
  const e = selectedEntity.value
  if (!e) return
  chat.setDraft(buildEntityQuestion(e, {
    sourcePath: pg.graph?.sourcePath,
    callsOut: (callsOut.value || []).map((c) => c.name),
    callsIn: (callsIn.value || []).map((c) => c.name),
  }))
  sidebar.setView('chat')
}

onMounted(async () => {
  await nextTick()
  // P2: 无图谱时尝试从后端恢复上次解析结果 (localStorage 记 projectId)
  if (!pg.graph) pg.restorePersisted()
  if (pg.graph) initGraph()
})

watch(() => pg.graph, async () => {
  destroyGraph()
  await nextTick()
  if (pg.graph) initGraph()
})

// 视图模式切换 (分层 <-> 模块分组) -> 重建图谱
watch(viewMode, () => { rebuildGraph() })

onBeforeUnmount(destroyGraph)

function goCode() { sidebar.setView('code') }

// P2: 手动触发项目解析 (空态大按钮 / 工具栏"重新解析")
function handleParse() {
  pg.parseCurrentProject()
}

// C2: 重置+重新解析合并 — 先复位视图 (搜索/筛选/选中), 再拉取最新源码解析
function handleReparse() {
  resetGraph()
  nextTick(() => { handleParse() })
}

// 深度分析弹窗可见性
const analysisDialogVisible = ref(false)

// 已有分析结果 -> 直接弹窗; 无 -> 调 LLM 分析, watch 自动弹窗
function handleAnalyze() {
  if (pg.analysis) {
    analysisDialogVisible.value = true
  } else {
    pg.analyze()
  }
}

// 弹窗内"重新分析"按钮: 关弹窗 -> 重新调 LLM -> watch 自动重开
function handleReanalyze() {
  analysisDialogVisible.value = false
  pg.analyze()
}

// 跳转学习视图查看联网资源
function goToWebResources() {
  analysisDialogVisible.value = false
  sidebar.setView('learning')
}

// 分析完成后自动弹窗 (pg.analysis 从 null 变非 null)
watch(() => pg.analysis, (val) => {
  if (val) analysisDialogVisible.value = true
})

// ---------------------------------------------------------------
// 项目导读 (场景二 Step 4: 分层项目解读, 手动逐站按层级下探)
// ---------------------------------------------------------------
const tourActive = ref(false)
const tourStops = ref([])
const tourIndex = ref(0)
const tourStop = computed(() => tourStops.value[tourIndex.value] || null)

function startTour() {
  const g = pg.graph
  if (!g?.entities?.length) {
    ElMessage.warning('请先解析项目图谱')
    return
  }
  const stops = buildTourStops(g.entities, g.relations)
  if (!stops.length) {
    ElMessage.warning('项目图谱缺少实体或调用关系，无法生成导读')
    return
  }
  tourStops.value = stops
  tourIndex.value = 0
  tourActive.value = true
  applyTourStop()
  ElMessage.success(`导读路径已生成: ${stops.length} 站，按层级从入口开始`)
}

function tourStep(delta) {
  const next = tourIndex.value + delta
  if (next < 0 || next >= tourStops.value.length) return
  tourIndex.value = next
  applyTourStop()
}

function applyTourStop() {
  const stop = tourStop.value
  if (!stop) return
  selectedEntity.value = stop.entity // 侧栏详情同步跟随
  rebuildGraph()                     // 重建带导读高亮
  nextTick(() => {
    try {
      const p = g6?.focusElement(String(stop.id))
      if (p && typeof p.catch === 'function') p.catch(() => { /* 聚焦失败仅高亮 */ })
    } catch { /* G6 版本差异兜底 */ }
  })
}

function exitTour() {
  tourActive.value = false
  tourStops.value = []
  tourIndex.value = 0
  rebuildGraph()
}

// Esc: 退出导读 / 收起底部详情抽屉
function _onKeydown(e) {
  if (e.key !== 'Escape') return
  if (tourActive.value) { exitTour(); return }
  if (!panelCollapsed.value && selectedEntity.value) panelCollapsed.value = true
}
window.addEventListener('keydown', _onKeydown)
onBeforeUnmount(() => window.removeEventListener('keydown', _onKeydown))

// 重新解析得到新图谱时自动退出导读 (旧站点失效)
watch(() => pg.graph, () => {
  if (tourActive.value) exitTour()
})
</script>

<style scoped>
.project-graph-page { height: 100%; display: flex; flex-direction: column; min-height: 0; padding: 0; }

/* ---- 标题栏已去除 (导航已标识视图, 统计在工具栏右侧) ---- */
.pg-stats { display: flex; gap: 12px; font-size: 12px; color: var(--km-gray-500); font-family: var(--km-font-mono); white-space: nowrap; flex-shrink: 0; margin-left: auto; }
.pg-stats span { white-space: nowrap; }
.pg-stale { margin-bottom: 12px; }
.pg-hint { font-size: 12px; color: var(--km-gray-500); margin: 0 0 8px; }

/* ---- 技术栈 badges ---- */
.pg-tech-bar { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.pg-tech-label { font-size: 12px; color: var(--km-gray-500); flex-shrink: 0; }
.pg-tech-tag { cursor: pointer; transition: opacity 0.15s; }
.pg-tech-tag:hover { opacity: 0.8; }
.pg-tech-cat { font-size: 10px; opacity: 0.7; margin-left: 2px; }
.pg-empty-wrap { flex: 1; display: flex; align-items: center; justify-content: center; }
.pg-empty-state { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.pg-empty-state .pg-spin { color: var(--km-primary, #6c7ce0); }
.pg-empty-title { font-size: 14px; color: var(--km-gray-700); margin: 4px 0 0; }
.pg-empty-actions { display: flex; gap: 8px; justify-content: center; }

/* ---- 工具栏 ---- */
.toolbar-card { margin-bottom: 12px; }
.toolbar-card :deep(.el-card) {
  --el-card-bg-color: var(--km-bg-layer-2);
  --el-card-border-color: var(--km-border-light);
}
.toolbar-card :deep(.el-card__body) { padding: 10px 14px; }
.toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.search-input { width: 220px; }
.filter-select { width: 140px; }
/* 视图模式切换 (分层/模块分组), 视觉对齐 KnowledgeGraph 的 persona-selector */
.view-mode-selector { display: inline-flex; gap: 2px; background: var(--km-bg-layer-2); border: 1px solid var(--km-border-light); border-radius: var(--km-radius-sm); padding: 2px; }
.vm-btn { border: 0; background: transparent; color: var(--km-gray-500); font-size: 12px; padding: 3px 10px; border-radius: var(--km-radius-xs); cursor: pointer; transition: color 0.15s, background 0.15s; }
.vm-btn:hover { color: var(--km-gray-700); }
.vm-btn.active { background: var(--km-primary); color: #fff; }

/* ---- 更多 popover (图例 + AI 分析 收纳, C2) ---- */
.more-pop { display: flex; flex-direction: column; gap: 6px; }
.more-section { display: flex; flex-direction: column; gap: 6px; }
.more-section + .more-section {
  margin-top: 6px; padding-top: 8px; border-top: 1px solid var(--km-border-light);
}
.more-section-title {
  font-size: 11px; font-weight: 600; color: var(--km-gray-500);
  text-transform: uppercase; letter-spacing: 0.3px;
}
.legend-item { display: flex; align-items: center; gap: 8px; }
.dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }

/* ---- 主区 ---- */
.main-area { display: flex; flex: 1; min-height: 0; position: relative; }
.canvas-area { flex: 1; min-width: 0; min-height: 0; }
.pg-canvas {
  width: 100%; height: 100%;
  border: 1px solid var(--km-border);
  border-radius: var(--km-radius-sm);
  background: var(--km-bg-layer-3);
}

/* ---- 详情面板 (底部抽屉, 画布全宽不避让; 可折叠) ---- */
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
.panel-card :deep(.el-card__header) {
  padding: 10px 16px; font-weight: 600; font-size: 14px;
  color: var(--km-gray-800);
  border-bottom: 1px solid var(--km-border-light);
}
.panel-card :deep(.el-card__body) { padding: 12px 16px; }

/* ---- 实体详情 ---- */
.entity-detail h4 {
  margin: 0 0 10px; font-size: 14px; color: var(--km-gray-800);
  word-break: break-all;
}
.detail-row {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 8px; font-size: 13px; color: var(--km-gray-700);
}
.detail-row .label { color: var(--km-gray-500); width: 48px; flex-shrink: 0; }
.detail-row code {
  background: var(--km-bg-layer-1); padding: 1px 6px;
  border-radius: var(--km-radius-xs); font-size: 12px; color: var(--km-gray-800);
  word-break: break-all;
}
.rel-section { margin-top: 10px; }
.entity-actions { display: flex; gap: 8px; margin-top: 12px; }
.entity-docstring {
  margin: 4px 0 0; padding: 8px 10px; border-radius: var(--km-radius-sm);
  background: var(--km-bg-layer-2); border: 1px solid var(--km-border-light);
  font-size: 12px; line-height: 1.6; color: var(--km-gray-600);
  white-space: pre-wrap; word-break: break-word; cursor: pointer; max-height: 200px; overflow-y: auto;
}
.param-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.param-item {
  font-size: 11px; padding: 2px 8px; border-radius: var(--km-radius-xs);
  background: var(--km-bg-layer-2); border: 1px solid var(--km-border-light);
}
.param-type { color: var(--km-gray-500); }
.rel-section > .label {
  display: block; color: var(--km-gray-500); font-size: 13px; margin-bottom: 6px;
}
.rel-list { display: flex; flex-wrap: wrap; gap: 4px; }
.rel-tag { cursor: pointer; }
.rel-tag:hover { opacity: 0.8; }

/* ---- 项目导读浮条 (画布底部居中悬浮) ---- */
.tour-bar {
  position: absolute; left: 50%; top: 16px; transform: translateX(-50%);
  z-index: 6; max-width: calc(100% - 48px);
  display: flex; align-items: center; flex-wrap: wrap; gap: 8px;
  padding: 10px 14px;
  background: var(--km-bg-layer-2, #fff);
  border: 1px solid var(--km-border-light, #e4e3e1);
  border-radius: var(--km-radius-sm, 8px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.14);
}
.tour-progress { font-size: 12px; color: var(--km-gray-500); white-space: nowrap; font-family: var(--km-font-mono, monospace); }
.tour-name { font-size: 14px; font-weight: 600; color: var(--km-gray-800); white-space: nowrap; }
.tour-kind { font-size: 12px; color: var(--km-gray-500); white-space: nowrap; }
.tour-why { font-size: 13px; color: var(--km-gray-600); flex: 1; min-width: 160px; }
.tour-actions { display: flex; gap: 6px; margin-left: auto; }
</style>

<!-- 深度分析弹窗样式 (非 scoped: append-to-body 移到 body 外, scoped data-v 不生效) -->
<style>
.analysis-dialog .analysis-summary { margin: 0 0 16px; line-height: 1.7; font-size: 14px; color: var(--km-gray-700); }
.analysis-dialog .analysis-section { margin-bottom: 16px; }
.analysis-dialog .analysis-label { font-size: 13px; color: var(--km-gray-500); margin-bottom: 6px; font-weight: 500; }
.analysis-dialog .analysis-label-sm { font-size: 12px; color: var(--km-gray-500); margin-right: 6px; }
.analysis-dialog .analysis-sub { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.analysis-dialog .analysis-tag { margin: 2px 0; }
.analysis-dialog .analysis-module { font-size: 13px; color: var(--km-gray-600); padding: 3px 0; }
.analysis-dialog .analysis-note { font-size: 13px; color: var(--km-gray-500); margin: 6px 0 0; }
.analysis-dialog .analysis-recs { margin: 0; padding-left: 18px; font-size: 13px; color: var(--km-gray-600); line-height: 2; }
.analysis-dialog .analysis-footer { display: flex; justify-content: flex-end; gap: 10px; }
</style>
