<template>
  <div ref="containerRef" class="flow-canvas" :style="{ height: `${height}px` }"></div>
</template>

<script setup>
/**
 * FlowDiagram — 只读流程进度 DAG (Phase 3a)
 *
 * 用 AntV G6 v5 把协作 Agent 流水渲染成"节点+边"的流程进度图:
 *  - 节点 = 阶段 (status 着色: idle 灰 / deferred 蓝底待启动 / running 琥珀+当前步高亮 /
 *    done 绿 / degraded 淡琥珀 / failed 红)
 *  - 边 = 相邻阶段的前驱关系 (线性链近似; Phase 3b 由 workflow 定义驱动真实拓扑)
 *  - 交互 = 平移/缩放 (只读, 无节点编辑)
 *
 * 测试/无 canvas 环境安全: G6 延迟 import; 容器无 2d context (jsdom) 时静默跳过。
 * 配色镜像 styles/theme.css 的 --km-* token (G6 canvas 不能读 CSS 变量)。
 */
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  /** 阶段数组 (有序): {key,label,icon,status,current} */
  stages: { type: Array, default: () => [] },
  /** 可选边 [{source,target}] (按阶段 id); 缺省按阶段顺序成线性前驱链 */
  edges: { type: Array, default: () => [] },
  height: { type: Number, default: 150 },
})

const containerRef = ref(null)
let graph = null
let resizeObs = null

// 镜像 --km-* 主题 token (hex, G6 canvas 用)
const C = {
  primary: '#4f46e5',
  success: '#34b37e',
  danger: '#e05555',
  warning: '#f0a040',
  gray300: '#d2d6e3',
  gray500: '#8b93a7',
  white: '#ffffff',
}

const NODE_FILL = { idle: '#f3f4f8', deferred: '#eef2ff', running: '#fff4e6', done: '#e8f6f0', degraded: '#fdf3e7', failed: '#fdeeee' }
const NODE_STROKE = { idle: C.gray300, deferred: '#a5b4fc', running: C.warning, done: C.success, degraded: '#d98b3c', failed: C.danger }
const NODE_LABEL_FILL = { idle: C.gray500, deferred: '#4f46e5', running: '#c7771a', done: '#207a55', degraded: '#b9680d', failed: C.danger }

function buildData() {
  const nodes = (props.stages || []).map((s, i) => ({
    id: s.key || `s${i}`,
    data: { label: s.icon ? `${s.icon} ${s.label}` : s.label, status: s.status, current: !!s.current },
  }))
  const ids = new Set(nodes.map((n) => n.id))
  let edges
  if (props.edges && props.edges.length) {
    // 显式边 (依赖拓扑): 只保留两端都属于当前阶段的边
    edges = props.edges
      .filter((e) => e && ids.has(e.source) && ids.has(e.target))
      .map((e, i) => ({ id: `e${i}`, source: e.source, target: e.target }))
  } else {
    edges = nodes.slice(1).map((n, i) => ({ id: `e${i}`, source: nodes[i].id, target: n.id }))
  }
  return { nodes, edges }
}

function canRender() {
  const el = containerRef.value
  if (!el) return false
  let ctx
  try { ctx = el.getContext('2d') } catch { ctx = null }
  return !!(ctx && typeof ctx.fillRect === 'function')
}

async function init() {
  if (!props.stages || !props.stages.length) return
  if (!canRender()) return // jsdom / 无 canvas → 静默跳过
  try {
    const { Graph } = await import('@antv/g6') // 延迟加载: 减小初始包体 + 测试安全
    if (!containerRef.value) return
    const el = containerRef.value
    graph = new Graph({
      container: el,
      width: el.offsetWidth || 320,
      height: props.height,
      data: buildData(),
      layout: { type: 'dagre', rankdir: 'LR', nodesep: 24, ranksep: 46 },
      node: {
        type: 'rect',
        style: {
          size: [118, 40],
          radius: 8,
          fill: (d) => NODE_FILL[d.data.status] || NODE_FILL.idle,
          stroke: (d) => (d.data.current ? C.primary : NODE_STROKE[d.data.status] || C.gray300),
          lineWidth: (d) => (d.data.current ? 2.5 : 1.2),
          labelText: (d) => d.data.label,
          labelPlacement: 'center',
          labelFontSize: 12,
          labelFill: (d) => NODE_LABEL_FILL[d.data.status] || C.gray500,
          labelMaxWidth: 104,
        },
      },
      edge: {
        type: 'polyline',
        style: { stroke: C.gray300, lineWidth: 1.5, endArrow: true },
      },
      behaviors: ['drag-canvas', 'zoom-canvas'],
      autoResize: true,
    })
    await graph.render()
    observeResize()
  } catch (e) {
    // BUG-049 防御模式: G6 版本差异 / headless 环境兜底
    console.error('[FlowDiagram] G6 初始化失败:', e)
    graph = null
  }
}

function observeResize() {
  if (resizeObs || typeof ResizeObserver === 'undefined') return
  const el = containerRef.value
  if (!el) return
  resizeObs = new ResizeObserver(() => {
    if (graph) { try { graph.resize() } catch { /* ignore */ } }
  })
  resizeObs.observe(el)
}

function destroy() {
  if (graph) { try { graph.destroy() } catch { /* ignore */ } graph = null }
  if (resizeObs) { try { resizeObs.disconnect() } catch { /* ignore */ } resizeObs = null }
}

// 状态/拓扑变化 → setData + 重绘 (不改节点位置语义, 只读)
// 性能(C): SSE 阶段推进频繁触发 — rAF 合并, 一帧内多次变化只重排一次, 防卡顿。
let _raf = 0
function scheduleRefresh() {
  if (_raf || !graph) return
  _raf = requestAnimationFrame(() => {
    _raf = 0
    try { graph.setData(buildData()); graph.render() } catch { /* ignore */ }
  })
}
watch(
  () => props.stages,
  () => scheduleRefresh(),
  { deep: true },
)

onMounted(() => { init() })
onBeforeUnmount(() => { destroy() })
</script>

<style scoped>
.flow-canvas { width: 100%; overflow: hidden; }
</style>
