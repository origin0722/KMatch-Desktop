<template>
  <div class="ide-shell">
    <!-- 顶部标题栏 -->
    <div class="ide-titlebar">
      <div class="title-left">
        <span class="title-brand">KMatch·知链</span>
        <span class="title-sep">—</span>
        <span class="title-scene">工作区</span>
      </div>
      <div class="title-center" v-if="ws.hasProject">
        <el-icon :size="13"><FolderOpened /></el-icon>
        <span>{{ ws.rootName }}</span>
      </div>
      <div class="title-right">
        <span class="title-hint">IDE · 二次开发 + 个性化学习</span>
      </div>
    </div>

    <!-- IDE 主体: 活动栏 | 主区(文件树+编辑器/视图) | AI面板 -->
    <div class="ide-body">
      <ActivityBar />
      <MainArea />
      <AssistantPanel v-if="sidebar.aiPanelVisible" />
    </div>

    <StatusBar />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useSidebarStore } from '@/stores/sidebar'
import ActivityBar from '@/ide/ActivityBar.vue'
import MainArea from '@/ide/MainArea.vue'
import AssistantPanel from '@/ide/AssistantPanel.vue'
import StatusBar from '@/ide/StatusBar.vue'

const ws = useWorkspaceStore()
const sidebar = useSidebarStore()
onMounted(() => ws.loadRecent())
</script>

<style scoped>
.ide-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--kbg);
  color: var(--ktext);
  font-family: var(--kfont-ui);
}
.ide-titlebar {
  height: 36px;
  background: var(--kbg-elevated);
  border-bottom: 1px solid var(--kborder);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  flex-shrink: 0;
  -webkit-app-region: drag;
}
.title-left { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.title-brand { font-weight: 600; color: var(--ktext); }
.title-sep { color: var(--ktext-muted); }
.title-scene { color: var(--ktext-secondary); font-size: 12px; }
.title-center {
  display: flex; align-items: center; gap: 5px;
  font-size: 12px; color: var(--ktext-secondary);
  -webkit-app-region: no-drag;
}
.title-right { -webkit-app-region: no-drag; }
.title-hint { font-size: 11px; color: var(--ktext-muted); }

.ide-body {
  flex: 1;
  display: flex;
  min-height: 0;
}
</style>
