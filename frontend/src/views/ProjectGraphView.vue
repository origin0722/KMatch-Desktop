<template>
  <div class="project-graph-page km-workbench">
    <!-- 页面标题栏 -->
    <div class="pg-header">
      <div>
        <p class="pg-kicker">project graph</p>
        <h3 class="pg-title">项目代码图谱</h3>
      </div>
      <div v-if="pg.graph" class="pg-stats">
        <span>函数 {{ pg.graph.stats?.function || 0 }}</span>
        <span>类 {{ pg.graph.stats?.class || 0 }}</span>
        <span>方法 {{ pg.graph.stats?.method || 0 }}</span>
        <span>关系 {{ pg.graph.relations?.length || 0 }}</span>
      </div>
    </div>

    <!-- 过期提示 (源文件被外部改动, 行号漂移) -->
    <el-alert v-if="pg.stale" type="warning" :closable="false" show-icon class="pg-stale">
      项目图谱已过期 (源文件被外部改动, 行号可能漂移), 建议在 AI 助手中重新解析
    </el-alert>

    <!-- 空状态 -->
    <el-empty v-if="!pg.graph" description="尚未生成项目图谱" :image-size="120">
      <p class="pg-hint">在 AI 助手中发送"解析这个项目", 或打开 .py 文件后让 AI 解析</p>
      <el-button type="primary" @click="goCode">前往代码视图</el-button>
    </el-empty>

    <template v-else>
      <!-- 工具栏 -->
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
          <el-button :icon="RefreshRight" @click="resetGraph">重置</el-button>

          <el-popover placement="bottom" :width="180" trigger="click">
            <template #reference>
              <el-button>图例</el-button>
            </template>
            <div class="legend-popover">
              <div v-for="k in KINDS" :key="k" class="legend-item">
                <span class="dot" :style="{ background: KIND_COLORS[k] }"></span> {{ k }}
              </div>
            </div>
          </el-popover>

          <span class="graph-stats">
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
            <el-icon><ArrowRight v-if="panelCollapsed" /><ArrowLeft v-else /></el-icon>
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
              <div class="detail-row" v-if="selectedEntity.line_start != null">
                <span class="label">行范围</span>
                <code>{{ selectedEntity.line_start }}-{{ selectedEntity.line_end }}</code>
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
              <el-button
                size="small"
                type="primary"
                :disabled="selectedEntity.line_start == null"
                @click="jumpToCode(selectedEntity)"
                style="margin-top: 10px"
              >跳转源码</el-button>
            </div>
          </el-card>

          <el-card v-else shadow="never" class="panel-card">
            <template #header><span>实体详情</span></template>
            <el-empty description="点击图谱节点查看详情" :image-size="60" />
          </el-card>
        </div>
      </div>
    </template>
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
import { Search, RefreshRight, ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { Graph } from '@antv/g6'
import { useProjectGraphStore } from '@/stores/projectGraph'
import { useSidebarStore } from '@/stores/sidebar'

const pg = useProjectGraphStore()
const sidebar = useSidebarStore()
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

// ---------------------------------------------------------------
// 搜索 & 筛选状态
// ---------------------------------------------------------------
const searchQuery = ref('')
const kindFilter = ref('')
const selectedEntity = ref(null)
const panelCollapsed = ref(false)

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
  const nodes = filteredEntities.value.map((e) => {
    const label = e.qualified_name || e.name || String(e.id)
    return {
      id: String(e.id),
      data: { label, w: nodeWidth(label), kind: e.kind, entity: e },
    }
  })
  const edges = filteredEdges.value.map((r, i) => ({
    id: `e${i}`,
    source: String(r.source),
    target: String(r.target),
    data: { type: r.type || 'call' },
  }))
  return { nodes, edges }
}

function initGraph() {
  if (!containerRef.value) return
  const { nodes, edges } = buildData()

  // 侧栏展开时画布逻辑宽度避让右侧 300px, dagre 在剩余区布局
  const panelGap = panelCollapsed.value ? 0 : 300
  const w = (containerRef.value.offsetWidth || 800) - panelGap
  const h = containerRef.value.offsetHeight || 600

  g6 = new Graph({
    container: containerRef.value,
    width: w,
    height: h,
    data: { nodes, edges },
    // nodeSize 用最大可能宽度 220 保守估, 防宽节点重叠; 实际节点 size 自适应
    layout: { type: 'dagre', rankdir: 'TB', nodesep: 40, ranksep: 80, nodeSize: [220, 44] },
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
        stroke: '#e4e3e1',
        lineWidth: 1,
        radius: 6,
      },
      state: { hover: { lineWidth: 2, shadowBlur: 10, shadowColor: KIND_COLORS.function } },
    },
    edge: { style: { stroke: '#c8c6c4', lineWidth: 1, endArrow: true } },
    behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element', { type: 'hover-activate', degree: 1, direction: 'both' }],
  })

  g6.on('node:click', (evt) => {
    const id = evt.target?.id
    const node = nodes.find((n) => n.id === id)
    if (node?.data?.entity) {
      selectedEntity.value = node.data.entity
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

onMounted(async () => {
  await nextTick()
  if (pg.graph) initGraph()
})

watch(() => pg.graph, async () => {
  destroyGraph()
  await nextTick()
  if (pg.graph) initGraph()
})

// 侧栏折叠 -> 重建图谱 (画布避让宽度变化)
watch(panelCollapsed, () => { rebuildGraph() })

onBeforeUnmount(destroyGraph)

function goCode() { sidebar.setView('code') }
</script>

<style scoped>
.project-graph-page { height: 100%; display: flex; flex-direction: column; min-height: 0; padding: 0; }

/* ---- 标题栏 ---- */
.pg-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 12px; gap: 16px; }
.pg-kicker { margin: 0; font-size: 11px; color: var(--km-gray-500); text-transform: uppercase; letter-spacing: 0.5px; }
.pg-title { margin: 2px 0 4px; font-size: 16px; color: var(--km-gray-800); }
.pg-desc { margin: 0; font-size: 12px; color: var(--km-gray-500); }
.pg-stats { display: flex; gap: 14px; font-size: 12px; color: var(--km-gray-500); font-family: var(--km-font-mono); white-space: nowrap; flex-shrink: 0; }
.pg-stats span { white-space: nowrap; }
.pg-stale { margin-bottom: 12px; }
.pg-hint { font-size: 12px; color: var(--km-gray-500); margin: 0 0 8px; }

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
.graph-stats {
  margin-left: auto; color: var(--km-gray-500); font-size: 12px;
  white-space: nowrap; font-family: var(--km-font-mono);
}

/* ---- 图例 ---- */
.legend-popover { display: flex; flex-direction: column; gap: 8px; font-size: 13px; }
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

/* ---- 浮层详情面板 (可折叠, 不挤占画布) ---- */
.side-panel {
  position: absolute; top: 12px; right: 12px;
  width: 280px; max-height: calc(100% - 24px);
  overflow-y: auto;
  display: flex; flex-direction: column; gap: 10px;
  z-index: 5;
  transition: width 0.2s ease;
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
  border-radius: 3px; font-size: 12px; color: var(--km-gray-800);
  word-break: break-all;
}
.rel-section { margin-top: 10px; }
.rel-section > .label {
  display: block; color: var(--km-gray-500); font-size: 13px; margin-bottom: 6px;
}
.rel-list { display: flex; flex-wrap: wrap; gap: 4px; }
.rel-tag { cursor: pointer; }
.rel-tag:hover { opacity: 0.8; }
</style>
