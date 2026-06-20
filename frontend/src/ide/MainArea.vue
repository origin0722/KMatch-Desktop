<template>
  <div class="main-area">
    <!-- 代码视图: 编辑器标签 + Monaco -->
    <template v-if="sidebar.activeView === 'code'">
      <EditorTabs />
      <div class="editor-host">
        <MonacoEditor />
      </div>
    </template>

    <!-- 其他视图: 全宽装载 (导航由左侧活动栏统一, 无顶部 Tab)
         套浅色卡片 wrapper: 赛题视图原为浅色设计, 不强行套暗色避免样式冲突/看不见 -->
    <div v-else class="view-host">
      <div class="view-card">
        <component :is="viewComponent" v-if="viewComponent" :key="sidebar.activeView" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, watch } from 'vue'
import { useSidebarStore } from '@/stores/sidebar'
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

// 视图切换后, 触发 resize 让 G6/雷达图等依赖容器尺寸的组件重算
watch(() => sidebar.activeView, async () => {
  await nextTick()
  window.dispatchEvent(new Event('resize'))
})
</script>

<style scoped>
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: var(--kbg);
  height: 100%;
  overflow: hidden;
}
.editor-host {
  flex: 1;
  min-height: 0;
  display: flex;
}
.view-host {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background: var(--kbg);
  padding: 12px;
}
/* 浅色卡片: 包裹赛题视图 (它们按浅色页面设计), 暗色主题下作为嵌入式浅色面板 */
.view-card {
  background: #ffffff;
  color: #303133;
  border-radius: 8px;
  min-height: calc(100% - 0px);
  padding: 20px 24px;
  box-shadow: var(--kshadow);
}
.view-card :deep(.el-card) {
  --el-card-bg-color: #ffffff;
  --el-text-color-primary: #303133;
}
/* 让被装载的视图根撑满 */
.view-card > :deep(*) {
  width: 100%;
}
</style>
