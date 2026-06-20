<template>
  <div class="file-explorer">
    <div class="explorer-header">
      <span class="explorer-title">{{ ws.rootName || '资源管理器' }}</span>
      <div class="explorer-actions">
        <el-icon class="icon-btn" title="刷新" @click="ws.refreshTree()"><Refresh /></el-icon>
        <el-icon class="icon-btn" title="打开项目" @click="ws.openProject()"><FolderOpened /></el-icon>
        <el-icon class="icon-btn" title="收起侧栏" @click="sidebar.toggleSidebar()"><Fold /></el-icon>
      </div>
    </div>

    <!-- 无项目: 打开/最近 -->
    <div v-if="!ws.hasProject" class="explorer-empty">
      <el-button type="primary" plain @click="ws.openProject()">
        <el-icon><FolderOpened /></el-icon>&nbsp;打开项目文件夹
      </el-button>
      <div v-if="ws.recent.length" class="recent-list">
        <div class="recent-title">最近打开</div>
        <div
          v-for="p in ws.recent"
          :key="p"
          class="recent-item"
          @click="ws.setRoot(p)"
        >
          <el-icon><Folder /></el-icon>
          <span>{{ basename(p) }}</span>
        </div>
      </div>
      <div class="hint">提示: 可打开仓库内 <code>data/example_projects/simple_crawler</code> 体验</div>
    </div>

    <!-- 文件树 (扁平列表按目录层级缩进) -->
    <div v-else class="tree">
      <div
        v-for="node in treeNodes"
        :key="node.path"
        class="tree-node"
        :class="{
          directory: node.isDirectory,
          file: !node.isDirectory,
          active: ws.activeFile === node.path,
        }"
        :style="{ paddingLeft: 8 + node.depth * 14 + 'px' }"
        :title="node.path"
        @click="onNodeClick(node)"
      >
        <el-icon class="node-icon" :size="14">
          <Folder v-if="node.isDirectory" />
          <Document v-else />
        </el-icon>
        <span class="node-name">{{ node.name }}</span>
        <span v-if="!node.isDirectory && ws.dirtyFiles.has(node.path)" class="dirty-dot">●</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Fold } from '@element-plus/icons-vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useSidebarStore } from '@/stores/sidebar'

const ws = useWorkspaceStore()
const sidebar = useSidebarStore()

function basename(p) {
  const parts = p.replace(/\\/g, '/').split('/')
  return parts[parts.length - 1] || p
}

// 扁平 tree → 带深度缩进的可见列表 (跳过空目录折叠, 阶段1 全展开)
const treeNodes = computed(() => {
  return (ws.tree || []).map((n) => ({
    ...n,
    depth: n.path.replace(/\\/g, '/').split('/').length - 1,
  }))
})

function onNodeClick(node) {
  if (!node.isDirectory) ws.openFile(node.path)
}
</script>

<style scoped>
.file-explorer {
  width: 240px;
  background: var(--km-bg-layer-0);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  height: 100%;
  border-right: 1px solid var(--km-border-light);
  font-size: 13px;
}
.explorer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  height: 40px;
  flex-shrink: 0;
}
.explorer-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--km-gray-600);
  font-weight: 600;
}
.explorer-actions { display: flex; gap: 4px; }
.icon-btn {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 6px;
  cursor: pointer; color: var(--km-gray-500);
  transition: all 0.15s var(--km-ease);
}
.icon-btn:hover { color: var(--km-gray-700); background: var(--km-gray-200); }

.explorer-empty {
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  color: var(--km-gray-600);
}
.recent-title { font-size: 11px; color: var(--km-gray-500); margin-top: 8px; }
.recent-item {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 8px; border-radius: var(--km-radius-sm); cursor: pointer;
  font-size: 13px;
  transition: background 0.15s var(--km-ease);
}
.recent-item:hover { background: var(--km-gray-200); }
.hint { font-size: 11px; color: var(--km-gray-500); margin-top: 8px; line-height: 1.5; }
.hint code { background: var(--km-gray-200); padding: 1px 4px; border-radius: 3px; }

.tree { flex: 1; overflow-y: auto; padding: 4px 0; }
.tree-node {
  display: flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding-right: 8px;
  cursor: pointer;
  color: var(--km-gray-700);
  user-select: none;
  transition: background 0.1s var(--km-ease);
}
.tree-node:hover { background: var(--km-gray-200); }
.tree-node.active { background: var(--km-primary-light); color: var(--km-primary-active); }
.tree-node.directory { color: var(--km-gray-600); font-weight: 500; }
.node-icon { flex-shrink: 0; opacity: 0.8; }
.node-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dirty-dot { color: var(--km-primary); font-size: 10px; margin-left: auto; }
</style>
