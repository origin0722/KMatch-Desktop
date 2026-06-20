<template>
  <div class="editor-tabs">
    <div
      v-for="f in ws.openFiles"
      :key="f"
      class="tab"
      :class="{ active: ws.activeFile === f }"
      @click="ws.setActive(f)"
      @middle-click.stop="ws.closeFile(f)"
    >
      <el-icon :size="14" class="tab-icon"><Document /></el-icon>
      <span class="tab-name">{{ nameOf(f) }}</span>
      <span class="tab-close" @click.stop="ws.closeFile(f)">
        <span v-if="ws.dirtyFiles.has(f)" class="dirty">●</span>
        <el-icon v-else :size="14"><Close /></el-icon>
      </span>
    </div>
  </div>
</template>

<script setup>
import { useWorkspaceStore } from '@/stores/workspace'
const ws = useWorkspaceStore()
function nameOf(p) {
  const parts = p.replace(/\\/g, '/').split('/')
  return parts[parts.length - 1] || p
}
</script>

<style scoped>
.editor-tabs {
  display: flex;
  height: 36px;
  background: var(--kbg-elevated);
  border-bottom: 1px solid var(--kborder);
  overflow-x: auto;
  flex-shrink: 0;
}
.tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  height: 36px;
  min-width: 100px;
  max-width: 200px;
  cursor: pointer;
  border-right: 1px solid var(--kborder);
  color: var(--ktext-secondary);
  font-size: 13px;
  position: relative;
  flex-shrink: 0;
}
.tab.active {
  background: var(--kbg);
  color: var(--ktext);
}
.tab.active::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: var(--kaccent);
}
.tab-icon { opacity: 0.7; }
.tab-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.tab-close {
  display: flex; align-items: center;
  width: 18px; height: 18px;
  border-radius: 4px;
  justify-content: center;
}
.tab-close:hover { background: var(--km-gray-300); }
.dirty { color: var(--km-primary); font-size: 10px; }
</style>
