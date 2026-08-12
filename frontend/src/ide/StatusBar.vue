<template>
  <div class="status-bar">
    <div class="status-left">
      <span class="status-item" v-if="ws.hasProject">
        <el-icon :size="13"><FolderOpened /></el-icon>{{ ws.rootName }}
      </span>
      <span class="status-item" v-if="ws.activeFile">{{ ws.activeFile }}</span>
      <span class="status-item muted" v-if="ws.activeFile && dirty">未保存</span>
    </div>
    <div class="status-right">
      <span class="status-item" :class="backendClass" :title="backendTitle">
        <span class="dot"></span>{{ backend.label }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useBackendHealthStore } from '@/stores/backendHealth'

const ws = useWorkspaceStore()
const backend = useBackendHealthStore()

const dirty = computed(() => ws.activeFile && ws.dirtyFiles.has(ws.activeFile))

const backendClass = computed(() => ({
  ok: backend.backendUp,
  bad: backend.status === false,
}))
const backendTitle = computed(() => backend.backendUp ? 'localhost:8000' : '后端未运行, 测评/图谱等功能不可用 (见 scripts/start_all.py)')

// 健康检查轮询在 backendHealth store 内启动 (幂等); StatusBar 触发首次启动
onMounted(() => backend.start())
</script>

<style scoped>
.status-bar {
  height: 24px;
  background: var(--km-statusbar-bg);
  color: var(--km-gray-600);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  font-size: 12px;
  flex-shrink: 0;
  border-top: 1px solid var(--km-border-light);
}
.status-left, .status-right { display: flex; align-items: center; gap: 14px; }
.status-item { display: flex; align-items: center; gap: 4px; }
.status-item.muted { opacity: 0.6; }
.status-item.clickable { cursor: pointer; }
.dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--km-gray-400);
  transition: background 0.3s var(--km-ease);
}
.status-item.ok .dot { background: var(--km-success); box-shadow: 0 0 4px var(--km-success); }
.status-item.bad .dot { background: var(--km-danger); }
</style>
