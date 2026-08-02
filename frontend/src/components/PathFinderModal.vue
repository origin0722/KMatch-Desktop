<template>
  <el-dialog :model-value="modelValue" title="路径查找" width="600px"
             @update:model-value="$emit('update:modelValue', $event)">
    <div class="path-finder">
      <p class="pf-hint">选起点和目标, 查找学习路径 (按依赖顺序, BFS 最短路径)</p>
      <div class="pf-row">
        <el-select v-model="fromId" placeholder="起点" filterable size="small" style="flex:1">
          <el-option v-for="n in nodes" :key="n.id" :label="n.data?.label || n.id" :value="n.id" />
        </el-select>
        <span class="pf-arrow">→</span>
        <el-select v-model="toId" placeholder="目标" filterable size="small" style="flex:1">
          <el-option v-for="n in nodes" :key="n.id" :label="n.data?.label || n.id" :value="n.id" />
        </el-select>
      </div>
      <el-button type="primary" size="small" :disabled="!fromId || !toId" @click="findPath" style="margin-top:12px">
        查找路径
      </el-button>
      <div v-if="pathResult" class="pf-result">
        <div v-if="pathResult.length" class="pf-path">
          <template v-for="(id, i) in pathResult" :key="id">
            <span class="pf-node" :style="{ background: categoryColorOf(id) }">{{ nodeLabel(id) }}</span>
            <span v-if="i < pathResult.length - 1" class="pf-sep">→</span>
          </template>
        </div>
        <el-empty v-else description="无可达路径 (两节点间无依赖链)" :image-size="60" />
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  modelValue: Boolean,
  nodes: { type: Array, default: () => [] },
  prereqMap: { type: Object, default: () => ({}) },
})
defineEmits(['update:modelValue'])

const fromId = ref('')
const toId = ref('')
const pathResult = ref(null)

const COLORS = {
  '基础语法': '#5b8ff9', '数据结构与算法': '#5ad8a6', '面向对象编程': '#f6bd16',
  'Python进阶': '#6dc8ec', '常用库与工具': '#e86452', '项目实战': '#945fb9',
}

const nodeLabel = (id) => props.nodes.find((n) => n.id === id)?.data?.label || id
const categoryColorOf = (id) => {
  const cat = props.nodes.find((n) => n.id === id)?.data?.category
  return COLORS[cat] || '#c8c6c4'
}

function findPath() {
  if (!fromId.value || !toId.value || fromId.value === toId.value) {
    pathResult.value = []
    return
  }
  // 建邻接表: prereq -> node (正向学习顺序, 前置学完才能学后续)
  const adj = {}
  for (const [node, prereqs] of Object.entries(props.prereqMap)) {
    for (const p of (prereqs || [])) {
      if (!adj[p]) adj[p] = []
      adj[p].push(node)
    }
  }
  // BFS from -> to (最短路径)
  const queue = [[fromId.value]]
  const visited = new Set([fromId.value])
  let found = null
  while (queue.length) {
    const path = queue.shift()
    const last = path[path.length - 1]
    if (last === toId.value) { found = path; break }
    for (const next of (adj[last] || [])) {
      if (!visited.has(next)) {
        visited.add(next)
        queue.push([...path, next])
      }
    }
  }
  pathResult.value = found || []
}
</script>

<style scoped>
.path-finder { padding: 0 4px; }
.pf-hint { font-size: 12px; color: var(--km-gray-500); margin: 0 0 12px; }
.pf-row { display: flex; align-items: center; gap: 10px; }
.pf-arrow { color: var(--km-gray-400); font-size: 16px; }
.pf-result { margin-top: 16px; }
.pf-path { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.pf-node { padding: 4px 10px; border-radius: 6px; color: #fff; font-size: 12px; font-weight: 600; }
.pf-sep { color: var(--km-gray-400); font-size: 14px; }
</style>
