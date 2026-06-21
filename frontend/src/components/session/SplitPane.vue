<template>
  <div class="split-pane" :class="{ open: !!view }">
    <div class="split-header">
      <span class="split-title">{{ label }}</span>
      <button class="split-close" title="关闭分屏" @click="session.closeSplit()">×</button>
    </div>
    <div class="split-content">
      <!-- v-show 常驻, 不 v-if 重建 (与 S6 治理一致, G6/Monaco 状态保留) -->
      <KnowledgeGraph v-show="view === 'graph'" />
      <Learning v-show="view === 'learning'" />
      <Dashboard v-show="view === 'dashboard'" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSessionStore } from '@/stores/session'
import KnowledgeGraph from '@/views/KnowledgeGraph.vue'
import Learning from '@/views/Learning.vue'
import Dashboard from '@/views/Dashboard.vue'

const session = useSessionStore()
const view = computed(() => session.splitView)
const labels = { graph: '知识图谱', learning: '学习资源', dashboard: '数据看板' }
const label = computed(() => labels[view.value] || '')
</script>

<style scoped>
.split-pane {
  display: flex; flex-direction: column;
  width: 0; min-width: 0; overflow: hidden;
  border-left: 1px solid var(--km-border-light);
  background: var(--km-bg-layer-1);
  transition: width 0.35s var(--km-ease), min-width 0.35s var(--km-ease), opacity 0.2s var(--km-ease);
  opacity: 0;
}
.split-pane.open { width: 50%; min-width: 360px; opacity: 1; }
.split-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; border-bottom: 1px solid var(--km-border-light);
  font-size: 13px; font-weight: 650; color: var(--km-gray-800);
}
.split-close {
  border: 0; background: transparent; color: var(--km-gray-500);
  font-size: 18px; cursor: pointer; line-height: 1;
}
.split-close:hover { color: var(--km-gray-800); }
.split-content { flex: 1; min-height: 0; overflow: auto; padding: 12px; }
@media (prefers-reduced-motion: reduce) {
  .split-pane { transition: none; }
}
</style>
