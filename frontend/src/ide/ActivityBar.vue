<template>
  <div class="activity-bar">
    <div
      v-for="item in ACTIVITY_ITEMS"
      :key="item.id"
      class="activity-item"
      :class="{ active: sidebar.activeView === item.id }"
      :title="item.title"
      @click="sidebar.setView(item.id)"
    >
      <el-icon :size="22"><component :is="item.icon" /></el-icon>
    </div>

    <div class="activity-spacer" />

    <!-- 资源管理器侧栏开关 (工具按钮, 不参与主区指示竞争) -->
    <div
      class="activity-item"
      :class="{ on: sidebar.sidebarVisible }"
      title="资源管理器"
      @click="sidebar.toggleSidebar()"
    >
      <el-icon :size="22"><Files /></el-icon>
    </div>

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
import { Files } from '@element-plus/icons-vue'
import { ACTIVITY_ITEMS, useSidebarStore } from '@/stores/sidebar'
import { useThemeStore } from '@/stores/theme'

const sidebar = useSidebarStore()
const theme = useThemeStore()
const themeMode = computed(() => theme.mode)
const toggleTheme = () => theme.toggle()
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
  opacity: 0.6;
  transition: opacity 0.15s;
}
.activity-item:hover { opacity: 0.9; }
/* 主区视图激活: 实心高亮 + 左侧指示条 */
.activity-item.active { opacity: 1; }
.activity-item.active::before {
  content: '';
  position: absolute;
  left: 0; top: 8px; bottom: 8px;
  width: 2px;
  background: var(--kaccent);
}
/* 工具按钮 (侧栏/AI) 开启态: 轻微高亮, 无指示条 (区别于主区视图) */
.activity-item.on { opacity: 0.85; }
.activity-spacer { flex: 1; }
</style>
