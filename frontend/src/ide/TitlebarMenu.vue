<template>
  <div class="titlebar-menu">
    <el-dropdown
      v-for="group in menuGroups"
      :key="group.id"
      class="menu-dropdown"
      trigger="hover"
      popper-class="km-titlebar-menu"
      @command="runCommand"
    >
      <button class="menu-trigger">
        <span class="menu-label">{{ group.label }}</span>
        <svg class="menu-chevron" width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-for="item in group.items"
            :key="item.command"
            :command="item.command"
            :divided="item.divided"
          >
            <span class="item-label">{{ item.label }}</span>
            <span v-if="item.hint" class="item-hint">{{ item.hint }}</span>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useWorkspaceStore } from '@/stores/workspace'
import { useSidebarStore } from '@/stores/sidebar'
import { useThemeStore } from '@/stores/theme'

const ws = useWorkspaceStore()
const sidebar = useSidebarStore()
const theme = useThemeStore()

const menuGroups = computed(() => [
  {
    id: 'project',
    label: '项目',
    items: [
      { command: 'project.open', label: '打开项目文件夹' },
      { command: 'project.refresh', label: '刷新文件树', hint: ws.hasProject ? ws.rootName : '' },
      { command: 'view.code', label: '回到代码视图', divided: true },
    ],
  },
  {
    id: 'tools',
    label: '工具',
    items: [
      { command: 'assistant.toggle', label: sidebar.aiPanelVisible ? '隐藏 AI 助手' : '显示 AI 助手' },
      { command: 'theme.toggle', label: theme.mode === 'dark' ? '切换到亮色' : '切换到暗色' },
      { command: 'view.settings', label: '设置', divided: true },
      { command: 'window.devtools', label: '打开开发者工具', divided: true },
    ],
  },
  {
    id: 'help',
    label: '帮助',
    items: [
      { command: 'help.backend', label: '后端与 Neo4j 启动提示' },
      { command: 'help.about', label: '关于 KMatch·知链' },
    ],
  },
])

async function runCommand(command) {
  if (command.startsWith('view.')) {
    const id = command.replace('view.', '').split('.')[0]
    sidebar.setView(id)
    return
  }
  if (command === 'project.open') {
    await ws.openProject()
    return
  }
  if (command === 'project.refresh') {
    if (!ws.hasProject) {
      ElMessage.info('请先打开项目文件夹')
      return
    }
    await ws.refreshTree()
    ElMessage.success('文件树已刷新')
    return
  }
  if (command === 'assistant.toggle') {
    sidebar.toggleAiPanel()
    return
  }
  if (command === 'theme.toggle') {
    theme.toggle()
    return
  }
  if (command === 'window.devtools') {
    const opened = await window.api?.window?.openDevTools?.()
    if (!opened) ElMessage.warning('当前环境无法打开开发者工具')
    return
  }
  if (command === 'help.backend') {
    await ElMessageBox.alert(
      '后端需要 FastAPI sidecar 或本地 uvicorn；Neo4j 需通过 docker-compose 启动，默认密码 kmatch2026。',
      '后端与 Neo4j 启动提示',
    )
    return
  }
  if (command === 'help.about') {
    await ElMessageBox.alert(
      'KMatch·知链：知识图谱驱动的多智能体协同个性化学习桌面 IDE。',
      '关于 KMatch·知链',
    )
  }
}
</script>

<style scoped>
.titlebar-menu {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
}
.menu-dropdown,
.menu-trigger {
  -webkit-app-region: no-drag;
}
.menu-trigger {
  height: 26px;
  padding: 0 10px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--km-gray-600);
  font-size: 12.5px;
  font-weight: 550;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: background-color 0.16s var(--km-ease), color 0.16s var(--km-ease), transform 0.12s var(--km-ease);
}
.menu-trigger:hover {
  background: var(--km-gray-200);
  color: var(--km-gray-800);
}
.menu-trigger:active {
  transform: scale(0.97);
}
.menu-label {
  letter-spacing: 0.2px;
}
.menu-chevron {
  color: var(--km-gray-500);
  transition: transform 0.18s var(--km-ease), color 0.16s var(--km-ease);
}
.menu-trigger:hover .menu-chevron {
  color: var(--km-primary-active);
  transform: translateY(1px);
}
.item-label {
  min-width: 96px;
}
.item-hint {
  margin-left: 16px;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--km-gray-500);
  font-size: 11px;
}
</style>

<!-- 非 scoped: el-dropdown 面板 teleport 到 body, 需全局样式 -->
<style>
.km-titlebar-menu.el-dropdown-menu {
  padding: 5px;
  border-radius: 11px !important;
  border: 1px solid var(--km-border-light);
  background: var(--km-bg-layer-3);
  box-shadow: var(--km-shadow-lg);
  animation: kmMenuIn 0.18s var(--km-ease-out);
}
@keyframes kmMenuIn {
  from { opacity: 0; transform: translateY(-4px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.km-titlebar-menu .el-dropdown-menu__item {
  border-radius: 7px;
  margin: 1px 0;
  padding: 6px 10px;
  font-size: 12.5px;
  color: var(--km-gray-700);
  transition: background-color 0.14s var(--km-ease), color 0.14s var(--km-ease);
}
.km-titlebar-menu .el-dropdown-menu__item:hover,
.km-titlebar-menu .el-dropdown-menu__item:focus {
  background: var(--km-primary-light);
  color: var(--km-primary-active);
}
.km-titlebar-menu .el-dropdown-menu__item.is-divided::before {
  background-color: var(--km-border-light);
  margin: 4px 6px;
}
</style>
