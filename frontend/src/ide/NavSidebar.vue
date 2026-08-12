<template>
  <!-- Codex 风格左侧导航栏: 240px 带 label (替代 48px 图标活动栏) -->
  <div class="nav-sidebar">
    <!-- 顶部: 品牌 + 菜单 (原标题栏内容下移) -->
    <div class="nav-head">
      <div class="nav-brand">
        <span class="nav-logo">知</span>
        <span class="nav-brand-name">KMatch·知链</span>
      </div>
      <TitlebarMenu class="nav-menu" />
    </div>

    <!-- 中部: 视图导航 (icon + label, 复用 ACTIVITY_ITEMS) -->
    <nav class="nav-items">
      <div
        v-for="item in ACTIVITY_ITEMS"
        :key="item.id"
        class="nav-item"
        :class="{ active: sidebar.activeView === item.id }"
        :title="item.title"
        @click="onViewClick(item.id)"
      >
        <el-icon :size="18"><component :is="item.icon" /></el-icon>
        <span class="nav-item-label">{{ item.title }}</span>
      </div>
    </nav>

    <div class="nav-spacer" />

    <!-- 底部: AI 面板开关 + 主题切换 + 设置 (聚拢, 去重状态栏) -->
    <div class="nav-foot">
      <div
        class="nav-item"
        :class="{ on: sidebar.aiPanelVisible }"
        title="AI 助手"
        data-test="ai-toggle-button"
        @click="sidebar.toggleAiPanel()"
      >
        <el-icon :size="18"><ChatDotRound /></el-icon>
        <span class="nav-item-label">AI 助手</span>
      </div>
      <div
        class="nav-item"
        :title="themeMode === 'dark' ? '切换到亮色' : '切换到暗色'"
        @click="toggleTheme"
      >
        <el-icon :size="18">
          <Sunny v-if="themeMode === 'dark'" />
          <Moon v-else />
        </el-icon>
        <span class="nav-item-label">{{ themeMode === 'dark' ? '亮色模式' : '暗色模式' }}</span>
      </div>
      <div
        class="nav-item"
        :class="{ active: sidebar.activeView === 'settings' }"
        title="设置"
        data-test="ai-settings-gear"
        @click="sidebar.setView('settings')"
      >
        <el-icon :size="18"><Setting /></el-icon>
        <span class="nav-item-label">设置</span>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * Codex 风格左侧导航栏 (阶段A 布局骨架)
 * 替代原 48px 图标活动栏: 240px 带 label, 顶部品牌+菜单, 底部聚拢工具入口.
 * 复用 ACTIVITY_ITEMS + 单一指示模型 (activeView); 图标走 main.js 全局注册 (字符串 :is).
 */
import { computed } from 'vue'
import { ACTIVITY_ITEMS, useSidebarStore } from '@/stores/sidebar'
import { useThemeStore } from '@/stores/theme'
import TitlebarMenu from '@/ide/TitlebarMenu.vue'

const sidebar = useSidebarStore()
const theme = useThemeStore()
const themeMode = computed(() => theme.mode)
const toggleTheme = () => theme.toggle()

// VS Code 风格: 点击已激活视图 -> 折叠文件树; 否则切换视图
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
.nav-sidebar {
  width: 208px;
  background: var(--km-bg-layer-0);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  border-right: 1px solid var(--km-border-light);
  padding: 10px 8px;
}
/* ---- 顶部品牌 + 菜单 ---- */
.nav-head {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 2px 6px 10px;
  border-bottom: 1px solid var(--km-border-light);
  margin-bottom: 8px;
}
.nav-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  -webkit-app-region: drag;
}
.nav-logo {
  width: 26px; height: 26px;
  border-radius: 7px;
  background: var(--km-primary);
  color: var(--km-primary-text);
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 700;
  flex-shrink: 0;
}
.nav-brand-name {
  font-size: 13px; font-weight: 650; letter-spacing: 0.3px;
  color: var(--km-gray-800);
  white-space: nowrap;
}
.nav-menu {
  -webkit-app-region: no-drag;
}
/* ---- 视图导航项 ---- */
.nav-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 9px;
  height: 34px;
  padding: 0 10px;
  border-radius: var(--km-radius-sm);
  color: var(--km-activity-text);
  cursor: pointer;
  position: relative;
  transition: color 0.18s var(--km-ease), background-color 0.18s var(--km-ease), transform 0.12s var(--km-ease);
}
.nav-item:hover {
  color: var(--km-activity-active-text);
  background: var(--km-activity-hover);
}
.nav-item:active { transform: scale(0.98); }
.nav-item.active {
  color: var(--km-activity-active-text);
  background: var(--km-activity-active-bg);
}
.nav-item.active::before {
  content: '';
  position: absolute;
  left: 0; top: 8px; bottom: 8px;
  width: 3px;
  border-radius: 2px;
  background: var(--km-activity-active);
}
.nav-item.on {
  color: var(--km-activity-active-text);
  background: var(--km-activity-active-bg);
}
.nav-item-label {
  font-size: 12.5px;
  font-weight: 500;
  white-space: nowrap;
}
.nav-spacer { flex: 1; }
/* ---- 底部工具入口 ---- */
.nav-foot {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: 8px;
  border-top: 1px solid var(--km-border-light);
}
</style>
