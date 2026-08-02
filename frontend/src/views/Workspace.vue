<template>
  <div class="ide-shell">
    <!-- 顶部标题栏: 左菜单 | 居中品牌 | 右工作区+控制 -->
    <div class="ide-titlebar">
      <div class="title-left">
        <TitlebarMenu />
      </div>

      <div class="title-brand">KMatch·知链</div>

      <div class="title-right">
        <span v-if="ws.hasProject" class="title-workspace">
          <el-icon :size="12"><FolderOpened /></el-icon>
          <span>{{ ws.rootName }}</span>
        </span>
        <button
          class="title-icon-button"
          :class="{ active: sidebar.aiPanelVisible }"
          title="显示或隐藏 AI 助手"
          data-test="ai-toggle-button"
          @click="sidebar.toggleAiPanel()"
        >
          <el-icon :size="15"><ChatDotRound /></el-icon>
        </button>
        <button
          class="title-icon-button"
          title="AI 设置"
          data-test="ai-settings-gear"
          @click="openAiSettingsEntry"
        >
          <el-icon :size="16"><Setting /></el-icon>
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

    <!-- 首次引导 (借鉴 OnboardingOverlay) -->
    <el-dialog v-model="onboardingVisible" title="欢迎使用 KMatch·知链" width="520px"
               :close-on-click-modal="false" :show-close="false">
      <div class="onboard">
        <p>KMatch·知链 是知识图谱驱动的个性化 Python 学习平台。主要功能:</p>
        <ol>
          <li><b>学习会话</b>:选学习目标 → 答题 → 自动生成画像 + 专属知识图谱 + 讲义</li>
          <li><b>知识图谱</b>:可视化学习路径, 点击节点看详情, 路径查找, 角色切换详略</li>
          <li><b>AI 助手</b>:基于学情讲义答疑 (右侧面板)</li>
          <li><b>设置</b>:右上角齿轮, 配置 API Key / 联网搜索 / Agent</li>
        </ol>
        <p class="tip">提示:先在设置页配置 LLM API Key + Tavily 联网搜索 key, 再开始学习会话。</p>
      </div>
      <template #footer>
        <el-button type="primary" @click="finishOnboarding">开始使用</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { FolderOpened, ChatDotRound, Setting } from '@element-plus/icons-vue'
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
  sidebar.setView('settings')
}

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
  height: 38px;
  background: var(--kbg-elevated);
  border-bottom: 1px solid var(--kborder);
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 0 12px;
  flex-shrink: 0;
  -webkit-app-region: drag;
}
.title-left {
  display: flex;
  align-items: center;
  min-width: 0;
}
.title-brand {
  text-align: center;
  font-size: 13px;
  font-weight: 650;
  letter-spacing: 0.4px;
  color: var(--km-gray-800);
  white-space: nowrap;
  /* 居中品牌保持可拖拽, 不阻断拖动区域 */
}
.title-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  -webkit-app-region: no-drag;
}
.title-workspace {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 220px;
  padding: 0 8px;
  height: 24px;
  border-radius: 7px;
  font-size: 11.5px;
  color: var(--km-gray-600);
  background: var(--km-gray-200);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.title-workspace span {
  overflow: hidden;
  text-overflow: ellipsis;
}
.title-icon-button {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--km-gray-600);
  cursor: pointer;
  transition: background-color 0.16s var(--km-ease), color 0.16s var(--km-ease), transform 0.12s var(--km-ease), border-color 0.16s var(--km-ease);
}
.title-icon-button:hover,
.title-icon-button.active {
  background: var(--km-primary-light);
  color: var(--km-primary-active);
  border-color: var(--km-border-light);
}
.title-icon-button:active {
  transform: scale(0.94);
}

.ide-body {
  flex: 1;
  display: flex;
  min-height: 0;
}
</style>
