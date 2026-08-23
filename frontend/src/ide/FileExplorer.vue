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
      <!-- issue-90: 最近打开可删除单条 -->
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
          <button
            class="recent-del"
            title="从最近打开中移除"
            @click.stop="ws.removeRecent(p)"
          >✕</button>
        </div>
      </div>
    </div>

    <!-- 文件树 (懒加载目录树: 顶层 + 展开时逐层拉取, 大项目不卡) -->
    <div v-else class="tree">
      <FileTreeBranch
        v-for="node in ws.tree"
        :key="node.path"
        :entry="node"
        :depth="0"
      />
      <div v-if="!ws.tree.length" class="ftb-empty">（空项目）</div>
    </div>
  </div>
</template>

<script setup>
import { Fold } from '@element-plus/icons-vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useSidebarStore } from '@/stores/sidebar'
import FileTreeBranch from './FileTreeBranch.vue'

const ws = useWorkspaceStore()
const sidebar = useSidebarStore()

function basename(p) {
  const parts = p.replace(/\\/g, '/').split('/')
  return parts[parts.length - 1] || p
}
</script>

<style scoped>
.file-explorer {
  width: 100%; /* #25 宽度由外层 ResizablePanel 控制 */
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
.recent-del {
  margin-left: auto;
  width: 18px; height: 18px;
  display: flex; align-items: center; justify-content: center;
  border: 0; border-radius: var(--km-radius-xs);
  background: transparent; color: var(--km-gray-400);
  font-size: 10px; cursor: pointer;
  opacity: 0; transition: all 0.14s var(--km-ease);
}
.recent-item:hover .recent-del { opacity: 1; }
.recent-del:hover { color: var(--km-danger); background: var(--km-danger-light); }

.tree { flex: 1; overflow-y: auto; padding: 4px 0; }
.ftb-empty { padding: 10px 12px; font-size: 12px; color: var(--km-gray-500); }
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
