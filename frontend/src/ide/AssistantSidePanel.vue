<template>
  <!-- issue-81: AI 助手右侧多面板 — 任务 / 文件 / 日志 (场景类似参考工具) -->
  <div class="assistant-side" data-test="assistant-side">
    <div class="side-tabs">
      <button
        v-for="t in TABS"
        :key="t.id"
        class="side-tab"
        :class="{ active: activeTab === t.id }"
        @click="activeTab = t.id"
      >{{ t.label }}</button>
    </div>

    <!-- 任务: 最近运行历史 -->
    <div v-if="activeTab === 'tasks'" class="side-body">
      <div v-if="runsLoading" class="side-note">加载中…</div>
      <div v-else-if="!runs.length" class="side-note">暂无运行记录</div>
      <div v-else class="side-list">
        <div v-for="r in runs" :key="r.session_id" class="side-item" @click="goRuns">
          <span class="si-mode" :class="r.mode">{{ r.mode === 'demo' ? '演示' : '自定义' }}</span>
          <span class="si-text">{{ r.request?.target_direction || '—' }}</span>
          <span class="si-time">{{ shortTime(r.created_at) }}</span>
        </div>
      </div>
    </div>

    <!-- 文件: 当前项目文件树精简版 -->
    <div v-else-if="activeTab === 'files'" class="side-body">
      <div v-if="!ws.hasProject" class="side-note">尚未打开项目</div>
      <div v-else-if="!files.length" class="side-note">项目为空或文件树未加载</div>
      <div v-else class="side-list">
        <div
          v-for="f in files"
          :key="f.path"
          class="side-item"
          :class="{ active: ws.activeFile === f.path }"
          @click="openFile(f.path)"
        >
          <span class="si-file">{{ f.path }}</span>
        </div>
      </div>
    </div>

    <!-- 日志: 最近一次运行的结构化事件 -->
    <div v-else class="side-body">
      <div v-if="!events.length" class="side-note">暂无协同日志</div>
      <div v-else class="side-list mono">
        <div v-for="(ev, i) in events" :key="i" class="side-event">
          <span class="ev-st" :class="ev.status || ''">{{ ev.status || 'run' }}</span>
          <span class="ev-msg">{{ ev.message || '' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * AssistantSidePanel — AI 助手右侧多面板 (issue-81)
 * 任务=运行历史 / 文件=项目文件树 / 日志=协同事件; 无数据给引导, 点击可跳转对应视图。
 */
import { ref, computed, onMounted } from 'vue'
import { fetchRuns } from '@/api/diagnostics'
import { useAssessmentStore } from '@/stores/assessment'
import { useWorkspaceStore } from '@/stores/workspace'
import { useSidebarStore } from '@/stores/sidebar'

const TABS = [
  { id: 'tasks', label: '任务' },
  { id: 'files', label: '文件' },
  { id: 'logs', label: '日志' },
]

const activeTab = ref('tasks')
const runs = ref([])
const runsLoading = ref(false)

const store = useAssessmentStore()
const ws = useWorkspaceStore()
const sidebar = useSidebarStore()

const events = computed(() => (store.orchestrationEvents || []).slice(-30).reverse())

const files = computed(() => (ws.tree || []).slice(0, 60))

function shortTime(ts) {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch { return '' }
}

function goRuns() { sidebar.setView('runs') }
function openFile(path) {
  ws.openFile(path)
  sidebar.setView('code')
}

onMounted(async () => {
  runsLoading.value = true
  try {
    const data = await fetchRuns(10)
    runs.value = (data?.runs || []).sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
  } catch { runs.value = [] } finally { runsLoading.value = false }
})
</script>

<style scoped>
.assistant-side {
  width: 300px;
  display: flex; flex-direction: column;
  min-height: 0;
  border-left: 1px solid var(--km-border-light);
  background: color-mix(in srgb, var(--km-bg-layer-1) 70%, transparent);
  backdrop-filter: blur(12px);
}
.side-tabs { display: flex; gap: 2px; padding: 10px 10px 6px; }
.side-tab {
  flex: 1; height: 30px;
  border: 0; border-radius: var(--km-radius-sm);
  background: transparent; color: var(--km-gray-500);
  font-size: 12.5px; font-weight: 550; cursor: pointer;
  transition: all 0.15s var(--km-ease);
}
.side-tab:hover { color: var(--km-gray-700); background: var(--km-gray-200); }
.side-tab.active { color: #fff; background: var(--km-primary); }
.side-body { flex: 1; overflow-y: auto; padding: 6px 10px 12px; }
.side-note { font-size: 12px; color: var(--km-gray-500); padding: 12px 4px; line-height: 1.7; }
.side-list { display: flex; flex-direction: column; gap: 4px; }
.side-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-radius: var(--km-radius-sm);
  cursor: pointer; transition: background-color 0.14s var(--km-ease);
}
.side-item:hover { background: var(--km-gray-200); }
.side-item.active { background: var(--km-primary-light); }
.si-mode { font-size: 10.5px; padding: 1px 7px; border-radius: 8px; flex-shrink: 0; }
.si-mode.demo { background: rgba(240,160,64,0.16); color: #b9680d; }
.si-mode.interactive { background: rgba(24,144,255,0.12); color: var(--km-primary); }
.si-text {
  flex: 1; min-width: 0; font-size: 12.5px; color: var(--km-gray-700);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.si-file { flex: 1; min-width: 0; font-size: 12px; color: var(--km-gray-600); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.si-time { font-size: 11px; color: var(--km-gray-400); flex-shrink: 0; }
.side-list.mono { font-family: var(--km-font-mono); }
.side-event { display: flex; gap: 6px; font-size: 11.5px; line-height: 1.6; color: var(--km-gray-600); padding: 3px 2px; }
.ev-st { flex-shrink: 0; color: var(--km-gray-400); }
.ev-st.done { color: var(--km-success); }
.ev-st.failed { color: var(--km-danger); }
.ev-st.degraded { color: #b9680d; }
.ev-st.running { color: var(--km-warning); }
.ev-msg { color: var(--km-gray-600); word-break: break-word; }
</style>
