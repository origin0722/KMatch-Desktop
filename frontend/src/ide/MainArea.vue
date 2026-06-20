<template>
  <div class="main-area">
    <!-- 顶部视图切换 Tab -->
    <div class="view-tabs">
      <div
        v-for="v in MAIN_VIEWS"
        :key="v.id"
        class="view-tab"
        :class="{ active: sidebar.activeView === v.id }"
        @click="sidebar.setView(v.id)"
      >
        {{ v.label }}
      </div>
    </div>

    <!-- 视图内容 -->
    <div class="view-content">
      <!-- 代码视图: 编辑器标签 + Monaco -->
      <template v-if="sidebar.activeView === 'code'">
        <EditorTabs />
        <MonacoEditor />
      </template>

      <!-- 知识图谱 / 答题测评 / Agent协同: 全宽装载原视图 -->
      <div v-else class="full-view-wrap">
        <component :is="viewComponent" v-if="viewComponent" />
        <div v-else class="empty-view">选择一个视图</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { MAIN_VIEWS, useSidebarStore } from '@/stores/sidebar'
import EditorTabs from './EditorTabs.vue'
import MonacoEditor from './MonacoEditor.vue'
import KnowledgeGraph from '@/views/KnowledgeGraph.vue'
import Assessment from '@/views/Assessment.vue'
import AgentView from '@/views/AgentView.vue'

const sidebar = useSidebarStore()

const VIEW_MAP = {
  graph: KnowledgeGraph,
  assessment: Assessment,
  agents: AgentView,
}

const viewComponent = computed(() => VIEW_MAP[sidebar.activeView] || null)
</script>

<style scoped>
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--kbg);
  height: 100%;
}
.view-tabs {
  display: flex;
  height: 36px;
  background: var(--kbg-elevated);
  border-bottom: 1px solid var(--kborder);
  flex-shrink: 0;
}
.view-tab {
  display: flex;
  align-items: center;
  padding: 0 16px;
  height: 36px;
  cursor: pointer;
  font-size: 13px;
  color: var(--ktext-secondary);
  position: relative;
  border-right: 1px solid var(--kborder);
}
.view-tab:hover { color: var(--ktext); background: var(--kbg-hover); }
.view-tab.active {
  color: var(--ktext);
  background: var(--kbg);
}
.view-tab.active::after {
  content: '';
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: 2px;
  background: var(--kaccent);
}
.view-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.full-view-wrap {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: var(--kbg);
}
.empty-view {
  display: flex; align-items: center; justify-content: center;
  height: 100%; color: var(--ktext-muted);
}
</style>
