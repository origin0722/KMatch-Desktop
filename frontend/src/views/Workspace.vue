<template>
  <div class="ide-shell">
    <!-- 顶部标题栏 -->
    <div class="ide-titlebar">
      <div class="title-left">
        <TitlebarMenu />
      </div>
      <div class="title-center" v-if="ws.hasProject">
        <el-icon :size="13"><FolderOpened /></el-icon>
        <span>{{ ws.rootName }}</span>
      </div>
      <div class="title-right">
        <button
          class="title-icon-button"
          :class="{ active: sidebar.aiPanelVisible }"
          title="显示或隐藏 AI 助手"
          data-test="ai-toggle-button"
          @click="sidebar.toggleAiPanel()"
        >
          AI
        </button>
        <button
          class="title-icon-button"
          title="AI 设置"
          data-test="ai-settings-gear"
          @click="openAiSettingsEntry"
        >
          ⚙
        </button>
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
import TitlebarMenu from '@/ide/TitlebarMenu.vue'

const ws = useWorkspaceStore()
const sidebar = useSidebarStore()

function openAiSettingsEntry() {
  if (!sidebar.aiPanelVisible) sidebar.toggleAiPanel()
}

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
.title-left { display: flex; align-items: center; min-width: 0; }
.title-center {
  display: flex; align-items: center; gap: 5px;
  font-size: 12px; color: var(--ktext-secondary);
  -webkit-app-region: no-drag;
}
.title-right {
  display: flex;
  align-items: center;
  gap: 6px;
  -webkit-app-region: no-drag;
}
.title-icon-button {
  height: 24px;
  min-width: 28px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: var(--km-gray-600);
  font-size: 11px;
  font-weight: 650;
  cursor: pointer;
  transition: all 0.16s var(--km-ease);
}
.title-icon-button:hover,
.title-icon-button.active {
  background: var(--km-primary-light);
  color: var(--km-primary-active);
  border-color: var(--km-border-light);
}

.ide-body {
  flex: 1;
  display: flex;
  min-height: 0;
}
</style>
