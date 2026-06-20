<template>
  <div class="status-bar">
    <div class="status-left">
      <span class="status-item" v-if="ws.hasProject">
        <el-icon :size="13"><FolderOpened /></el-icon>{{ ws.rootName }}
      </span>
      <span class="status-item" v-if="ws.activeFile">{{ ws.activeFile }}</span>
      <span class="status-item muted" v-if="ws.activeFile && dirty">未保存</span>
    </div>
    <div class="status-right">
      <span class="status-item" :class="backendClass" :title="backendTitle">
        <span class="dot"></span>{{ backendLabel }}
      </span>
      <span class="status-item clickable" @click="toggleTheme">
        {{ theme.mode === 'dark' ? '🌙 暗色' : '☀️ 亮色' }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useThemeStore } from '@/stores/theme'

const ws = useWorkspaceStore()
const theme = useThemeStore()
const toggleTheme = () => theme.toggle()

const backendOk = ref(null) // null=未知, true, false
const dirty = computed(() => ws.activeFile && ws.dirtyFiles.has(ws.activeFile))

const backendLabel = computed(() => {
  if (backendOk.value === null) return '后端检测中'
  return backendOk.value ? '后端就绪' : '后端未起'
})
const backendClass = computed(() => ({
  ok: backendOk.value === true,
  bad: backendOk.value === false,
}))
const backendTitle = computed(() => backendOk.value ? 'localhost:8000' : '后端未运行, 测评/图谱等功能不可用 (见 scripts/start_all.py)')

async function checkBackend() {
  try {
    const res = await window.api.http.request('GET', '/api/health')
    backendOk.value = res.ok
  } catch {
    backendOk.value = false
  }
}

onMounted(() => {
  checkBackend()
  setInterval(checkBackend, 8000)
})
</script>

<style scoped>
.status-bar {
  height: 24px;
  background: var(--kbg-statusbar);
  color: var(--ktext-on-statusbar);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px;
  font-size: 12px;
  flex-shrink: 0;
}
.status-left, .status-right { display: flex; align-items: center; gap: 14px; }
.status-item { display: flex; align-items: center; gap: 4px; }
.status-item.muted { opacity: 0.7; }
.status-item.clickable { cursor: pointer; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #999; }
.status-item.ok .dot { background: var(--ksuccess); }
.status-item.bad .dot { background: var(--kdanger); }
</style>
