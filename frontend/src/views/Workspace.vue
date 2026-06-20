<template>
  <div class="ide-shell">
    <!-- 顶部标题栏 -->
    <div class="ide-titlebar">
      <div class="title-left">
        <span class="title-brand">KMatch·知链</span>
        <span class="title-sep">—</span>
        <span class="title-scene">工作区 · 二次开发</span>
      </div>
      <div class="title-center" v-if="ws.hasProject">
        <el-icon :size="13"><FolderOpened /></el-icon>
        <span>{{ ws.rootName }}</span>
      </div>
      <div class="title-right">
        <span class="title-hint">IDE 工作区 · 二次开发 + 个性化学习</span>
      </div>
    </div>

    <!-- IDE 主体 -->
    <div class="ide-body">
      <ActivityBar />
      <SidePanel />
      <div class="editor-area">
        <EditorTabs />
        <MonacoEditor />
      </div>
      <!-- 阶段2: 右侧 AI 助手面板 <AssistantPanel /> -->
    </div>

    <StatusBar />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import ActivityBar from '@/ide/ActivityBar.vue'
import SidePanel from '@/ide/SidePanel.vue'
import EditorTabs from '@/ide/EditorTabs.vue'
import MonacoEditor from '@/ide/MonacoEditor.vue'
import StatusBar from '@/ide/StatusBar.vue'

const ws = useWorkspaceStore()
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
.editor-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--kbg);
}
</style>
