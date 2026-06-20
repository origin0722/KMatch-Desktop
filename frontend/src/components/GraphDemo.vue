<template>
  <div>
    <div ref="graphContainer" class="g6-container"></div>
    <div class="graph-controls">
      <el-button size="small" @click="toggleLayout">切换布局</el-button>
      <el-button size="small" @click="resetGraph">重置</el-button>
      <span class="node-count">节点: {{ nodeCount }} | 边: {{ edgeCount }}</span>
    </div>
  </div>
</template>

<script setup>
/**
 * KMatch 第1周技术验证 Demo — AntV G6 基础图谱渲染
 *
 * 验证点:
 *   1. G6 库正常加载与初始化
 *   2. 节点 + 边 + 力导向布局渲染
 *   3. 节点颜色映射（模拟掌握状态）
 *   4. 节点点击交互
 *   5. 布局切换（力导向 ↔ 层次）
 */
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { Graph } from '@antv/g6'

const graphContainer = ref(null)
const nodeCount = ref(0)
const edgeCount = ref(0)
let graph = null

// 模拟知识图谱数据 — 第1周 Demo 用静态数据
const mockData = {
  nodes: [
    { id: 'PY-001', label: '变量与数据类型', category: '基础语法', mastery: 0.90 },
    { id: 'PY-003', label: '条件判断', category: '基础语法', mastery: 0.85 },
    { id: 'PY-005', label: '循环结构', category: '基础语法', mastery: 0.60 },
    { id: 'PY-012', label: '列表与元组', category: '数据结构与算法', mastery: 0.35 },
    { id: 'PY-015', label: '函数定义', category: '数据结构与算法', mastery: 0.40 },
    { id: 'PY-020', label: '字典与集合', category: '数据结构与算法', mastery: 0.20 },
    { id: 'PY-035', label: '文件操作', category: '常用库与工具', mastery: 0.10 },
    { id: 'PY-050', label: '装饰器', category: 'Python进阶', mastery: 0.05 },
    { id: 'PY-055', label: '面向对象基础', category: '面向对象编程', mastery: 0.15 },
    { id: 'PY-060', label: '异步编程', category: 'Python进阶', mastery: 0.00 },
  ],
  edges: [
    { source: 'PY-001', target: 'PY-003' },
    { source: 'PY-001', target: 'PY-005' },
    { source: 'PY-003', target: 'PY-015' },
    { source: 'PY-005', target: 'PY-015' },
    { source: 'PY-012', target: 'PY-035' },
    { source: 'PY-015', target: 'PY-050' },
    { source: 'PY-015', target: 'PY-055' },
    { source: 'PY-050', target: 'PY-060' },
    { source: 'PY-020', target: 'PY-035' },
  ],
}

function getNodeColor(mastery) {
  if (mastery >= 0.8) return '#52c41a'   // 已掌握 — 绿色
  if (mastery >= 0.5) return '#faad14'   // 学习中 — 橙色
  if (mastery > 0)    return '#ff7a45'   // 未掌握 — 红色
  return '#d9d9d9'                       // 未学习 — 灰色
}

function getNodeSize(mastery) {
  return mastery >= 0.8 ? 40 : 30
}

let useDagre = false

function initGraph(layoutType = 'force') {
  if (!graphContainer.value) return

  nodeCount.value = mockData.nodes.length
  edgeCount.value = mockData.edges.length

  const layoutConfig = layoutType === 'force'
    ? {
        type: 'force',
        preventOverlap: true,
        nodeStrength: -200,
        linkDistance: 150,
      }
    : {
        type: 'dagre',
        rankdir: 'TB',
        nodesep: 40,
        ranksep: 80,
      }

  graph = new Graph({
    container: graphContainer.value,
    width: graphContainer.value.offsetWidth || 800,
    height: 450,
    data: {
      nodes: mockData.nodes.map((n) => ({
        id: n.id,
        data: {
          label: n.label,
          mastery: n.mastery,
          nodeColor: getNodeColor(n.mastery),
          nodeSize: getNodeSize(n.mastery),
        },
      })),
      edges: mockData.edges.map((e, i) => ({
        id: `edge-${i}`,
        source: e.source,
        target: e.target,
        data: {},
      })),
    },
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
      },
      state: {
        hover: {
          lineWidth: 3,
          shadowBlur: 10,
          shadowColor: '#1890ff',
        },
      },
    },
    edge: {
      style: {
        stroke: '#c2c8d5',
        lineWidth: 1.5,
        endArrow: true,
      },
    },
    behaviors: [
      'drag-canvas',
      'zoom-canvas',
      'drag-element',
      {
        type: 'hover-activate',
        degree: 1,
        direction: 'both',
      },
    ],
  })

  graph.on('node:click', (evt) => {
    const nodeData = evt.target?.id
    const node = mockData.nodes.find((n) => n.id === nodeData)
    if (node) {
      // 使用 Element Plus 消息提示（简化版，后续改为弹窗）
      console.log(`🔍 节点详情: ${node.id} ${node.label}`, {
        分类: node.category,
        掌握程度: `${(node.mastery * 100).toFixed(0)}%`,
        状态: node.mastery >= 0.8 ? '已掌握' : node.mastery >= 0.5 ? '学习中' : '未掌握',
      })
    }
  })

  graph.render()
}

function toggleLayout() {
  useDagre = !useDagre
  if (graph) {
    graph.destroy()
    graph = null
  }
  initGraph(useDagre ? 'dagre' : 'force')
}

function resetGraph() {
  if (graph) {
    graph.destroy()
    graph = null
  }
  useDagre = false
  initGraph('force')
}

onMounted(() => {
  initGraph('force')
})

onBeforeUnmount(() => {
  if (graph) {
    graph.destroy()
  }
})
</script>

<style scoped>
.g6-container {
  width: 100%;
  height: 450px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  background: #fff;
}

.graph-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}

.node-count {
  margin-left: auto;
  color: #909399;
  font-size: 13px;
}
</style>
