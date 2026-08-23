<template>
  <!-- Codex 风格左侧导航栏: 208px 带 label, 可折叠为 48px 图标轨 (issue-61) -->
  <div class="nav-sidebar" :class="{ collapsed: sidebar.navCollapsed }">
    <!-- 顶部: 仅折叠/展开按钮 (issue-72: 移除 项目/工具/帮助 菜单, 命令已下沉导航底栏/文件树) -->
    <div class="nav-head">
      <button
        class="nav-collapse-btn"
        :title="sidebar.navCollapsed ? '展开导航栏' : '折叠导航栏 (节约空间)'"
        data-test="nav-collapse"
        @click="sidebar.toggleNavCollapsed()"
      >
        <el-icon :size="14"><Expand v-if="sidebar.navCollapsed" /><Fold v-else /></el-icon>
      </button>
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
      <!-- T4 双形态后此开关只控制右侧并排侧栏 (主区 chat 视图才是 AI 助手本体) -->
      <div
        class="nav-item"
        :class="{ on: sidebar.aiPanelVisible }"
        title="并排显示 AI 助手侧栏 (在其他视图边学边问)"
        data-test="ai-toggle-button"
        @click="sidebar.toggleAiPanel()"
      >
        <el-icon :size="18"><ChatDotRound /></el-icon>
        <span class="nav-item-label">AI 分屏</span>
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
import { Fold, Expand } from '@element-plus/icons-vue'
import { ACTIVITY_ITEMS, useSidebarStore } from '@/stores/sidebar'
import { useThemeStore } from '@/stores/theme'

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
  width: 100%; /* #25 宽度由外层 ResizablePanel 控制 */
  /* issue-71 深度玻璃透: 背景 ~0.38 透明 + 强模糊/饱和, 主区内容可透出; 悬停态局部加深保可读 */
  background: color-mix(in srgb, var(--km-bg-layer-0) 36%, transparent);
  backdrop-filter: blur(22px) saturate(1.5);
  -webkit-backdrop-filter: blur(22px) saturate(1.5);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  border-right: 1px solid transparent;
  /* issue-85: 顶部 16px 出让给全局拖拽区 (无边框窗口), 折叠按钮不遮挡 */
  padding: 16px 8px 10px;
}
/* ---- 顶部: 折叠/展开按钮行 (issue-72: 无菜单, 右对齐) ---- */
.nav-head {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0 2px 8px;
  margin-bottom: 2px;
}
/* issue-61: 折叠/展开切换按钮 */
.nav-collapse-btn {
  flex-shrink: 0;
  width: 26px; height: 26px;
  display: inline-flex; align-items: center; justify-content: center;
  border: 1px solid transparent; border-radius: var(--km-radius-xs);
  background: transparent; color: var(--km-gray-500);
  cursor: pointer; transition: all 0.15s var(--km-ease);
  -webkit-app-region: no-drag;
}
.nav-collapse-btn:hover { color: var(--km-primary-active); background: var(--km-gray-100); border-color: var(--km-border-light); }
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
  /* #27 激活态用品牌色软底 + 图标/文字着色, 视觉更明显 (底层透明时加深一档保可读) */
  background: color-mix(in srgb, var(--km-primary-light) 88%, transparent);
}
.nav-item.active .nav-item-label {
  font-weight: 600;
}
.nav-item.active::before {
  content: '';
  position: absolute;
  left: 0; top: 8px; bottom: 8px;
  width: 4px;
  border-radius: 2px;
  /* issue-82: 撞色 — 主色 → 强调色渐变指示条 */
  background: linear-gradient(180deg, var(--km-activity-active), var(--km-accent, #f0a040));
  /* #27 点击动画: 指示条 scaleY 回弹入场 */
  transform: scaleY(0);
  transform-origin: center top;
  animation: nav-indicator-in 0.32s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}
@keyframes nav-indicator-in {
  from { transform: scaleY(0); }
  to { transform: scaleY(1); }
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
/* ---- issue-61: 折叠态 (图标轨) ---- */
.nav-sidebar.collapsed .nav-item {
  justify-content: center;
  padding: 0;
}
.nav-sidebar.collapsed .nav-item-label { display: none; }
.nav-sidebar.collapsed .nav-head { justify-content: flex-end; }
.nav-sidebar.collapsed .nav-foot .nav-item { justify-content: center; }
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
