<template>
  <div class="side-panel">
    <!-- 面板标题 -->
    <div class="panel-header">
      <span class="panel-title">{{ currentTitle }}</span>
    </div>

    <!-- 面板内容: explorer 用 FileExplorer, 其余动态装载学习视图 -->
    <div class="panel-body">
      <FileExplorer v-if="sidebar.activePanel === 'explorer'" />
      <div v-else class="learn-view-wrap">
        <component :is="viewComponent" v-if="viewComponent" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSidebarStore, PANELS } from '@/stores/sidebar'
import FileExplorer from './FileExplorer.vue'
import Assessment from '@/views/Assessment.vue'
import KnowledgeGraph from '@/views/KnowledgeGraph.vue'
import Learning from '@/views/Learning.vue'
import AgentView from '@/views/AgentView.vue'
import Dashboard from '@/views/Dashboard.vue'

const sidebar = useSidebarStore()

const VIEW_MAP = {
  assessment: Assessment,
  graph: KnowledgeGraph,
  learning: Learning,
  agents: AgentView,
  dashboard: Dashboard,
}

const currentTitle = computed(() => {
  const p = PANELS.find((x) => x.id === sidebar.activePanel)
  return p ? p.title : ''
})

const viewComponent = computed(() => VIEW_MAP[sidebar.activePanel] || null)
</script>

<style scoped>
.side-panel {
  width: 340px;
  background: var(--kbg-sidebar);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  height: 100%;
  border-right: 1px solid var(--kborder);
}
.panel-header {
  height: 38px;
  display: flex;
  align-items: center;
  padding: 0 12px;
  border-bottom: 1px solid var(--kborder);
  flex-shrink: 0;
}
.panel-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--ktext-secondary);
  font-weight: 600;
}
.panel-body {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
/* 学习视图容器: 可滚动, 主题适配 */
.learn-view-wrap {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}
</style>
