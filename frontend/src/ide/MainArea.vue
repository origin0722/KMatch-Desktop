<template>
  <div class="main-area">
    <!-- 代码视图: 文件树 + 编辑器标签 + Monaco -->
    <template v-if="sidebar.activeView === 'code'">
      <div class="code-layout">
        <FileExplorer v-show="sidebar.sidebarVisible" />
        <div class="editor-area">
          <EditorTabs />
          <div class="editor-host">
            <MonacoEditor />
          </div>
        </div>
      </div>
    </template>

    <!-- 其他视图: 全宽装载 (导航由左侧活动栏统一, 无顶部 Tab)
         套浅色卡片: 赛题视图原为浅色设计, 暗色主题下作为嵌入式浅色面板 -->
    <div v-else class="view-host">
      <div class="view-card">
        <KnowledgeGraph v-if="sidebar.activeView === 'graph'" />
        <Assessment v-else-if="sidebar.activeView === 'assessment'" />
        <Learning v-else-if="sidebar.activeView === 'learning'" />
        <AgentView v-else-if="sidebar.activeView === 'agents'" />
        <Dashboard v-else-if="sidebar.activeView === 'dashboard'" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, watch } from 'vue'
import { useSidebarStore } from '@/stores/sidebar'
import FileExplorer from './FileExplorer.vue'
import EditorTabs from './EditorTabs.vue'
import MonacoEditor from './MonacoEditor.vue'
import KnowledgeGraph from '@/views/KnowledgeGraph.vue'
import Assessment from '@/views/Assessment.vue'
import Learning from '@/views/Learning.vue'
import AgentView from '@/views/AgentView.vue'
import Dashboard from '@/views/Dashboard.vue'

const sidebar = useSidebarStore()

// 视图切换后, 触发 resize 让 G6/雷达图等依赖容器尺寸的组件重算
watch(() => sidebar.activeView, async () => {
  await nextTick()
  // 延迟一帧, 确保 DOM 已挂载 + 尺寸就绪
  requestAnimationFrame(() => window.dispatchEvent(new Event('resize')))
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
.code-layout {
  display: flex;
  flex: 1;
  min-height: 0;
}
.editor-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
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
  display: flex;
}
/* 赛题视图容器: 使用 KMatch 语义 token, 保持亮暗主题一致 */
.view-card {
  background: var(--km-bg-layer-1);
  color: var(--km-gray-700);
  border: 1px solid var(--km-border-light);
  border-radius: var(--km-radius-lg);
  flex: 1;
  min-width: 0;
  padding: 20px 24px;
  box-shadow: var(--km-shadow-sm);
}
.view-card :deep(.el-card) {
  --el-card-bg-color: var(--km-bg-layer-2);
  --el-text-color-primary: var(--km-gray-800);
  --el-fill-color-blank: var(--km-bg-layer-2);
}
</style>
