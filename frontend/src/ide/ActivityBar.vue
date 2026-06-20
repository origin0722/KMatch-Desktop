<template>
  <div class="activity-bar">
    <div
      v-for="item in ACTIVITY_ITEMS"
      :key="item.id"
      class="activity-item"
      :class="{ active: sidebar.activeView === item.id }"
      :title="item.title"
      @click="onViewClick(item.id)"
    >
      <el-icon :size="22"><component :is="item.icon" /></el-icon>
    </div>

    <div class="activity-spacer" />

    <!-- AI 面板开关 -->
    <div
      class="activity-item"
      :class="{ on: sidebar.aiPanelVisible }"
      title="AI 助手"
      @click="sidebar.toggleAiPanel()"
    >
      <el-icon :size="22"><ChatDotRound /></el-icon>
    </div>

    <!-- 主题切换 -->
    <div
      class="activity-item"
      :title="themeMode === 'dark' ? '切换到亮色' : '切换到暗色'"
      @click="toggleTheme"
    >
      <el-icon :size="22">
        <Sunny v-if="themeMode === 'dark'" />
        <Moon v-else />
      </el-icon>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ACTIVITY_ITEMS, useSidebarStore } from '@/stores/sidebar'
import { useThemeStore } from '@/stores/theme'

const sidebar = useSidebarStore()
const theme = useThemeStore()
const themeMode = computed(() => theme.mode)
const toggleTheme = () => theme.toggle()

// VS Code 风格: 点击已激活视图 → 折叠侧栏; 否则切换视图
function onViewClick(id) {
  if (sidebar.activeView === id) {
    sidebar.toggleSidebar()
  } else {
    sidebar.setView(id)
    // 切换到代码视图时, 默认展开文件树
    if (id === 'code' && !sidebar.sidebarVisible) {
      sidebar.toggleSidebar()
    }
  }
}
</script>

<style scoped>
.activity-bar {
  width: 48px;
  background: var(--km-activity-bg);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0;
  flex-shrink: 0;
  border-right: 1px solid rgba(255,255,255,0.04);
}
.activity-item {
  width: 40px;
  height: 40px;
  margin: 2px 4px;
  border-radius: var(--km-radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--km-activity-text);
  cursor: pointer;
  position: relative;
  opacity: 0.55;
  transition: all 0.2s var(--km-ease);
}
.activity-item:hover { opacity: 0.85; background: rgba(255,255,255,0.06); }
.activity-item:active { transform: scale(0.95); }
/* 主区视图激活 */
.activity-item.active {
  opacity: 1;
  background: rgba(255,255,255,0.08);
}
.activity-item.active::before {
  content: '';
  position: absolute;
  left: -8px; top: 8px; bottom: 8px;
  width: 2px;
  border-radius: 1px;
  background: var(--km-activity-active);
}
/* 工具按钮开启态 */
.activity-item.on { opacity: 0.8; }
.activity-spacer { flex: 1; }
</style>
