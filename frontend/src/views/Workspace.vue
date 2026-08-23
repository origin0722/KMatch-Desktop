<template>
  <!-- issue-62: 启动就绪门 — 后端就绪后才进入主界面 (避免 AI 一进来就报错); 超时可重试/跳过 -->
  <ReadyGate v-if="!gateReady" @ready="gateReady = true" @skip="gateReady = true" />
  <div v-else class="ide-shell">
    <!-- 顶部标题栏: 精简为拖拽条 + 工作区名 (品牌/菜单/工具入口已移至 NavSidebar) -->
    <div class="ide-titlebar">
      <div class="title-left">
        <span v-if="ws.hasProject" class="title-workspace">
          <el-icon :size="12"><FolderOpened /></el-icon>
          <span>{{ ws.rootName }}</span>
        </span>
      </div>
    </div>

    <!-- IDE 主体: 左导航栏(可拖宽/可折叠图标轨) | 主区(文件树+编辑器/视图) | AI面板(可拖宽) -->
    <div class="ide-body">
      <!-- issue-61: 折叠态用独立 panel-key 重挂载 → 宽度自动收成 48px 图标轨 -->
      <ResizablePanel
        :key="sidebar.navCollapsed ? 'nav-mini' : 'nav-full'"
        :panel-key="sidebar.navCollapsed ? 'km.nav-w-mini' : 'km.nav-w'"
        :min="sidebar.navCollapsed ? 44 : 180"
        :max="sidebar.navCollapsed ? 60 : 280"
        :initial="sidebar.navCollapsed ? 48 : 208"
        side="right"
      >
        <NavSidebar />
      </ResizablePanel>
      <MainArea />
      <!-- T4 双形态: chat 视图本身就是 AI 对话, 侧栏不重复挂载 (chat store 共享, 切回即恢复) -->
      <ResizablePanel v-if="sidebar.aiPanelVisible && sidebar.activeView !== 'chat'" panel-key="km.ai-w" :min="280" :max="560" :initial="340" side="left">
        <AssistantPanel />
      </ResizablePanel>
    </div>

    <StatusBar />

    <!-- 首次引导 (脚本式多步, Codex 风格; 显隐收口 sidebar store, 设置页可重新触发) -->
    <OnboardingOverlay :visible="sidebar.onboardingActive" @done="onOnboardDone" />
  </div>
</template>

<script setup>
import { ref, onMounted, defineAsyncComponent } from 'vue'
import { FolderOpened } from '@element-plus/icons-vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useSidebarStore } from '@/stores/sidebar'
import NavSidebar from '@/ide/NavSidebar.vue'
import MainArea from '@/ide/MainArea.vue'
import ResizablePanel from '@/ide/ResizablePanel.vue'
import StatusBar from '@/ide/StatusBar.vue'
import OnboardingOverlay from '@/components/OnboardingOverlay.vue'
import ReadyGate from '@/ide/ReadyGate.vue'
// 右侧 AI 分栏懒加载: AssistantPanel 依赖 MarkdownViewer + 重组件, 默认视图是 code 首屏无需它
const AssistantPanel = defineAsyncComponent(() => import('@/ide/AssistantPanel.vue'))

const ws = useWorkspaceStore()
const sidebar = useSidebarStore()
// issue-62: 就绪门状态 (后端就绪/用户跳过后进入主界面)
const gateReady = ref(false)

// 首次使用 (无 onboarded 标记) 自动弹引导; 重新触发入口在设置页「通用」段
if (!localStorage.getItem('kmatch-onboarded')) sidebar.startOnboarding()

// 引导完成: 按场景落地 (学新技能 -> learning-session, 有项目 -> code; 跳过保持当前视图)
function onOnboardDone(skipped, scene) {
  sidebar.finishOnboarding()
  if (skipped) return
  if (scene === 'project') sidebar.setView('code')
  else sidebar.setView('learning-session')
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
