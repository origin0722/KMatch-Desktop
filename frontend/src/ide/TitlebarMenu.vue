<template>
  <div class="titlebar-menu">
    <div class="brand-block">
      <span class="brand-mark">知</span>
      <span class="brand-text">KMatch·知链</span>
    </div>

    <el-dropdown
      v-for="group in menuGroups"
      :key="group.id"
      class="menu-dropdown"
      trigger="click"
      @command="runCommand"
    >
      <button class="menu-trigger">
        {{ group.label }}
        <span class="chevron">⌄</span>
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
  if (command.startsWith('view.ai-settings')) {
    if (!sidebar.aiPanelVisible) sidebar.toggleAiPanel()
    ElMessage.info('AI 设置视图将在下一步启用；当前可在右侧 AI 助手底部设置模型/API Key。')
    return
  }
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
  gap: 4px;
  min-width: 0;
}
.brand-block {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-right: 8px;
}
.brand-mark {
  width: 22px;
  height: 22px;
  border-radius: 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--km-primary);
  color: var(--km-primary-text);
  font-size: 12px;
  font-weight: 700;
}
.brand-text {
  font-size: 13px;
  font-weight: 650;
  color: var(--km-gray-800);
  letter-spacing: 0.1px;
}
.menu-dropdown,
.menu-trigger {
  -webkit-app-region: no-drag;
}
.menu-trigger {
  height: 26px;
  padding: 0 9px;
  border: none;
  border-radius: var(--km-radius-sm);
  background: transparent;
  color: var(--km-gray-600);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.18s var(--km-ease);
}
.menu-trigger:hover {
  background: var(--km-gray-200);
  color: var(--km-gray-800);
}
.chevron {
  margin-left: 3px;
  color: var(--km-gray-500);
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
