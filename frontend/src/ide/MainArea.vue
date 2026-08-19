<template>
  <div class="main-area">
    <!-- 代码视图: 文件树 + 编辑器标签 + Monaco
         阶段8: v-show 常驻 (治 S6 — 切视图不销毁 Monaco, models/未保存编辑保留) -->
    <div class="code-layout" v-show="sidebar.activeView === 'code'">
      <ResizablePanel v-show="sidebar.sidebarVisible" panel-key="km.explorer-w" :min="180" :max="420" :initial="240" side="right">
        <FileExplorer />
      </ResizablePanel>
      <div class="editor-area">
        <EditorTabs />
        <div class="editor-host">
          <MonacoEditor />
        </div>
      </div>
    </div>

    <!-- 其他视图: 全宽装载 (导航由左侧活动栏统一, 无顶部 Tab)
         套浅色卡片: 赛题视图原为浅色设计, 暗色主题下作为嵌入式浅色面板 -->
    <div v-if="sidebar.activeView !== 'code'" class="view-host">
      <div class="view-card" :class="{ 'no-pad': ['learning-session', 'settings', 'project-graph', 'chat', 'workflow-studio', 'runs'].includes(sidebar.activeView) }">
        <SettingsView v-if="sidebar.activeView === 'settings'" />
        <LearningSession v-else-if="sidebar.activeView === 'learning-session'" />
        <RunsPanel v-else-if="sidebar.activeView === 'runs'" />
        <!-- T4 双形态: chat 视图 = 居中大留白对话 (chat store 与右侧侧栏共享) -->
        <AssistantPanel v-else-if="sidebar.activeView === 'chat'" variant="wide" />
        <KnowledgeGraph v-else-if="sidebar.activeView === 'graph'" />
        <ProjectGraphView v-else-if="sidebar.activeView === 'project-graph'" />
        <WorkflowStudio v-else-if="sidebar.activeView === 'workflow-studio'" />
        <Learning v-else-if="sidebar.activeView === 'learning'" />
        <Dashboard v-else-if="sidebar.activeView === 'dashboard'" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, watch, defineAsyncComponent } from 'vue'
import { useSidebarStore } from '@/stores/sidebar'
import FileExplorer from './FileExplorer.vue'
import ResizablePanel from './ResizablePanel.vue'
import EditorTabs from './EditorTabs.vue'
import MonacoEditor from './MonacoEditor.vue'
// 非当前视图懒加载: KnowledgeGraph(@antv/g6)、Learning(echarts)、Dashboard(echarts)、
// LearningSession、ProjectGraphView、SettingsView 都是重组件, 静态 import 会全打进首屏 chunk。
// 改 defineAsyncComponent 按 tab 切换才下载, code 视图(默认)首屏只载 Monaco。
const AssistantPanel = defineAsyncComponent(() => import('./AssistantPanel.vue'))
const SettingsView = defineAsyncComponent(() => import('@/ide/settings/SettingsView.vue'))
const KnowledgeGraph = defineAsyncComponent(() => import('@/views/KnowledgeGraph.vue'))
const ProjectGraphView = defineAsyncComponent(() => import('@/views/ProjectGraphView.vue'))
const LearningSession = defineAsyncComponent(() => import('@/views/LearningSession.vue'))
const Learning = defineAsyncComponent(() => import('@/views/Learning.vue'))
const Dashboard = defineAsyncComponent(() => import('@/views/Dashboard.vue'))
const WorkflowStudio = defineAsyncComponent(() => import('@/ide/workflow/WorkflowStudioView.vue'))
const RunsPanel = defineAsyncComponent(() => import('@/ide/RunsPanel.vue')) // 后台任务页

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
  padding: 20px;
  display: flex;
}
/* 赛题视图容器: 使用 KMatch 语义 token, 保持亮暗主题一致 */
.view-card {
  background: var(--km-bg-layer-1);
  color: var(--km-gray-700);
  border: 1px solid var(--km-border-light);
  border-radius: var(--km-radius-panel);
  flex: 1;
  min-width: 0;
  padding: 22px 26px;
  box-shadow: var(--km-shadow-sm);
  font-size: 14px; /* #29 各功能页统一继承字号 (原各自 12-13.5px 不同步) */
}
.view-card :deep(.el-card) {
  --el-card-bg-color: var(--km-bg-layer-2);
  --el-text-color-primary: var(--km-gray-800);
  --el-fill-color-blank: var(--km-bg-layer-2);
}
/* learning-session 自带内边距与滚动, view-card 不再二次包裹 */
.view-card.no-pad { padding: 16px 0 0 0; background: transparent; border: 0; box-shadow: none; }
</style>
