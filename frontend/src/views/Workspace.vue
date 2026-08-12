<template>
  <div class="ide-shell">
    <!-- 顶部标题栏: 精简为拖拽条 + 工作区名 (品牌/菜单/工具入口已移至 NavSidebar) -->
    <div class="ide-titlebar">
      <div class="title-left">
        <span v-if="ws.hasProject" class="title-workspace">
          <el-icon :size="12"><FolderOpened /></el-icon>
          <span>{{ ws.rootName }}</span>
        </span>
      </div>
    </div>

    <!-- IDE 主体: 左导航栏 | 主区(文件树+编辑器/视图) | AI面板 -->
    <div class="ide-body">
      <NavSidebar />
      <MainArea />
      <AssistantPanel v-if="sidebar.aiPanelVisible" />
    </div>

    <StatusBar />

    <!-- 首次引导 (脚本式多步, Codex 风格) -->
    <OnboardingOverlay :visible="onboardingVisible" @done="finishOnboarding" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { FolderOpened } from '@element-plus/icons-vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useSidebarStore } from '@/stores/sidebar'
import NavSidebar from '@/ide/NavSidebar.vue'
import MainArea from '@/ide/MainArea.vue'
import AssistantPanel from '@/ide/AssistantPanel.vue'
import StatusBar from '@/ide/StatusBar.vue'
import OnboardingOverlay from '@/components/OnboardingOverlay.vue'

const ws = useWorkspaceStore()
const sidebar = useSidebarStore()

// 首次引导 (借鉴 Understand-Anything OnboardingOverlay): 首次打开显示功能介绍
const onboardingVisible = ref(!localStorage.getItem('kmatch-onboarded'))
function finishOnboarding() {
  localStorage.setItem('kmatch-onboarded', '1')
  onboardingVisible.value = false
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
  height: 32px;
  background: var(--kbg-elevated);
  border-bottom: 1px solid var(--kborder);
  display: flex;
  align-items: center;
  padding: 0 14px;
  flex-shrink: 0;
  -webkit-app-region: drag;
}
.title-left {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
}
.title-workspace {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 280px;
  padding: 0 8px;
  height: 22px;
  border-radius: 6px;
  font-size: 11.5px;
  color: var(--km-gray-600);
  background: var(--km-gray-200);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  -webkit-app-region: no-drag;
}
.title-workspace span {
  overflow: hidden;
  text-overflow: ellipsis;
}

.ide-body {
  flex: 1;
  display: flex;
  min-height: 0;
}
</style>
