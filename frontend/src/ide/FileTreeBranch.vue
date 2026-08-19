<template>
  <div class="ftb">
    <div
      class="ftb-row"
      :class="{ active: isActive, directory: entry.isDirectory }"
      :style="{ paddingLeft: 8 + depth * 14 + 'px' }"
      :title="entry.path"
      @click="onRow"
    >
      <span class="ftb-arrow" :class="{ leaf: !entry.isDirectory }">{{ entry.isDirectory ? (expanded ? '▾' : '▸') : '' }}</span>
      <el-icon class="node-icon" :size="14">
        <Folder v-if="entry.isDirectory" />
        <Document v-else />
      </el-icon>
      <span class="node-name">{{ entry.name }}</span>
      <span v-if="loading" class="ftb-loading">···</span>
      <span v-else-if="!entry.isDirectory && ws.dirtyFiles.has(entry.path)" class="dirty-dot">●</span>
    </div>

    <template v-if="entry.isDirectory && expanded">
      <FileTreeBranch
        v-for="child in children"
        :key="child.path"
        :entry="child"
        :depth="depth + 1"
      />
      <div v-if="!loading && children && !children.length" class="ftb-empty" :style="{ paddingLeft: 8 + (depth + 1) * 14 + 'px' }">（空目录）</div>
    </template>
  </div>
</template>

<script setup>
/**
 * FileTreeBranch — 懒加载目录树递归节点 (借鉴 DSH-better-sidebar 资源管理器)
 * 展开目录才拉取子项 (workspace.toggleDir), 避免大项目全量深遍历卡顿。
 */
import { computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'

defineOptions({ name: 'FileTreeBranch' })
const props = defineProps({
  entry: { type: Object, required: true },
  depth: { type: Number, default: 0 },
})

const ws = useWorkspaceStore()
const isActive = computed(() => ws.activeFile === props.entry.path)
const expanded = computed(() => ws.expandedDirs.has(props.entry.path))
const loading = computed(() => ws.loadingDirs.has(props.entry.path))
const children = computed(() => (ws.dirChildren ? ws.dirChildren.get(props.entry.path) : null))

function onRow() {
  if (props.entry.isDirectory) ws.toggleDir(props.entry.path)
  else ws.openFile(props.entry.path)
}
</script>

<style scoped>
.ftb-row {
  display: flex; align-items: center; gap: 4px; height: 26px; padding-right: 8px;
  cursor: pointer; color: var(--km-gray-700); user-select: none;
  transition: background 0.1s var(--km-ease);
}
.ftb-row:hover { background: var(--km-gray-200); }
.ftb-row.active { background: var(--km-primary-light); color: var(--km-primary-active); }
.ftb-row.directory { color: var(--km-gray-600); font-weight: 500; }
.ftb-arrow { width: 12px; flex-shrink: 0; font-size: 10px; color: var(--km-gray-400); }
.ftb-arrow.leaf { width: 12px; }
.node-icon { flex-shrink: 0; opacity: 0.8; }
.node-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ftb-loading { color: var(--km-gray-400); font-size: 11px; }
.dirty-dot { color: var(--km-primary); font-size: 10px; margin-left: auto; }
.ftb-empty { font-size: 11px; color: var(--km-gray-400); height: 22px; line-height: 22px; }
</style>
