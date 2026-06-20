<template>
  <div class="activity-bar">
    <div
      v-for="item in ACTIVITY_ITEMS"
      :key="item.id"
      class="activity-item"
      :class="{ active: isActive(item) }"
      :title="item.title"
      @click="onItemClick(item)"
    >
      <el-icon :size="22"><component :is="item.icon" /></el-icon>
    </div>

    <div class="activity-spacer" />

    <!-- AI 面板开关 -->
    <div
      class="activity-item"
      :class="{ active: sidebar.aiPanelVisible }"
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

function isActive(item) {
  if (item.kind === 'sidebar') return sidebar.sidebarVisible
  return sidebar.activeView === item.id
}

function onItemClick(item) {
  sidebar.handleActivityClick(item)
}
</script>

<style scoped>
.activity-bar {
  width: 48px;
  background: var(--kbg-activity);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0;
  flex-shrink: 0;
  border-right: 1px solid #00000033;
}
.activity-item {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ktext-on-dark);
  cursor: pointer;
  position: relative;
  opacity: 0.7;
  transition: opacity 0.15s;
}
.activity-item:hover { opacity: 1; }
.activity-item.active { opacity: 1; }
.activity-item.active::before {
  content: '';
  position: absolute;
  left: 0; top: 8px; bottom: 8px;
  width: 2px;
  background: var(--kaccent);
}
.activity-spacer { flex: 1; }
</style>
