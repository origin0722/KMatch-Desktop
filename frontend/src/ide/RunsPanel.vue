<template>
  <div class="runs-panel">
    <div class="rp-head">
      <span class="rp-title">🕘 运行历史</span>
      <div class="rp-actions">
        <el-button size="small" :loading="loading" @click="refresh">刷新</el-button>
      </div>
    </div>

    <div v-if="error" class="rp-error">{{ error }}</div>
    <div v-else-if="!runs.length && !loading" class="rp-empty">
      暂无运行记录 — 跑一次测评 / 答题提交后这里会留痕（run.json + events.jsonl）
    </div>

    <div class="rp-list">
      <div v-for="r in runs" :key="r.session_id" class="rp-row" @click="toggle(r.session_id)">
        <div class="rp-row-head">
          <span class="rp-mode" :class="r.mode">{{ modeLabel(r.mode) }}</span>
          <span class="rp-target">{{ targetOf(r) }}</span>
          <span class="rp-time">{{ fmt(r.created_at) }}</span>
        </div>
        <div class="rp-meta">
          <span v-for="(c, i) in chips(r)" :key="i" class="rp-chip">{{ c }}</span>
          <span v-if="r.summary?.profile_diff" class="rp-chip diff" title="该次提交包含画像版本变化">📈 画像变化</span>
        </div>

        <div v-if="expanding === r.session_id" class="rp-detail">
          <div v-if="detailLoading" class="rp-note">加载事件…</div>
          <template v-else-if="detail">
            <div class="rp-note rp-summary">{{ summaryLine(detail) }}</div>
            <div v-if="detail.orchestration_events?.length" class="rp-events">
              <div v-for="(ev, j) in shownEvents" :key="j" class="rp-event">
                <span class="ev-st" :class="ev.status || ''">{{ (ev.status || 'run').padEnd(9) }}</span>
                <span class="ev-agent">{{ ev.agent || '' }}</span>
                <span class="ev-msg">{{ ev.message || '' }}</span>
              </div>
              <div v-if="detail.orchestration_events.length > 40" class="rp-note">…仅显示前 40 条</div>
            </div>
            <div class="rp-run-actions">
              <el-button v-if="r.mode === 'demo'" size="small" @click.stop="rerun(detail)">按此重跑</el-button>
              <el-button size="small" type="primary" @click.stop="retake(detail)">重新测评该目标</el-button>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * RunsPanel — 后台任务页 (复用 P1 耐久 run + 协同事件):
 * 历史运行列表 → 展开事件时间线(Agent 状态/拓扑) → 按此重跑(续跑) / 重新测评该目标。
 */
import { ref, computed, onMounted } from 'vue'
import { fetchRuns, fetchRun } from '@/api/diagnostics'
import { useAssessmentStore } from '@/stores/assessment'
import { useSidebarStore } from '@/stores/sidebar'

const store = useAssessmentStore()
const sidebar = useSidebarStore()

const runs = ref([])
const loading = ref(false)
const error = ref('')
const expanding = ref(null)
const detail = ref(null)
const detailLoading = ref(false)

const shownEvents = computed(() => (detail.value?.orchestration_events || []).slice(0, 40))

const modeLabel = (m) => ({ demo: '演示测评', interactive: '自定义测评' }[m] || m || 'run')
const targetOf = (r) => r?.request?.target_direction || r?.summary?.target_direction || r?.request?.direction || '—'
function fmt(ts) {
  if (!ts) return ''
  try { return new Date(ts).toLocaleString('zh-CN', { hour12: false }) } catch { return ts }
}
function chips(r) {
  const s = r?.summary || {}
  const out = []
  if (s.correct_count != null && s.total_count) out.push(`${s.correct_count}/${s.total_count} 正确`)
  if (s.strategy) out.push(`策略 ${s.strategy}`)
  if (s.theory_level != null) out.push(`Lv.${s.theory_level}`)
  if (s.path_nodes != null) out.push(`${s.path_nodes} 节点`)
  if (!out.length) out.push('—')
  return out
}
function summaryLine(d) {
  const s = d?.summary || {}
  const parts = []
  if (s.review_passed != null) parts.push(s.review_passed ? '审核通过' : '审核打回')
  if (s.review_rounds != null) parts.push(`打回 ${s.review_rounds} 轮`)
  if (s.pacing?.weeks) parts.push(`约 ${s.pacing.weeks} 周节奏`)
  return parts.join(' · ') || '（无摘要）'
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchRuns(30)
    runs.value = (data?.runs || []).slice().sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
  } catch (e) {
    error.value = e?.message || '加载运行历史失败'
    runs.value = []
  } finally {
    loading.value = false
  }
}

async function toggle(sid) {
  if (expanding.value === sid) { expanding.value = null; return }
  expanding.value = sid
  detail.value = null
  detailLoading.value = true
  try {
    detail.value = await fetchRun(sid)
  } catch {
    detail.value = { error: '加载详情失败' }
  } finally {
    detailLoading.value = false
  }
}

async function rerun(run) {
  // demo run: loadRun 填充 lastRun → resumeRunDemo 按上次请求一键续跑
  await store.loadRun(run.session_id)
  const resumed = await store.resumeRunDemo()
  if (resumed) sidebar.setView('learning-session')
}

function retake(run) {
  const target = run?.request?.target_direction || targetOf(run)
  if (run?.mode === 'demo') {
    store.startDemoStream({ targetDirection: target, scene: run.request?.scene || 'no_project' })
  } else {
    store.startAssessment({ targetDirection: target })
  }
  sidebar.setView('learning-session')
}

onMounted(refresh)
</script>

<style scoped>
.runs-panel { height: 100%; overflow-y: auto; padding: 14px 18px; }
.rp-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.rp-title { font-size: 15px; font-weight: 650; }
.rp-error { color: var(--km-danger); font-size: 13px; padding: 8px 0; }
.rp-empty { color: var(--km-gray-500); font-size: 13px; padding: 20px 0; }
.rp-list { display: flex; flex-direction: column; gap: 8px; }
.rp-row {
  border: 1px solid var(--km-border-light); border-radius: var(--km-radius);
  padding: 8px 12px; cursor: pointer; transition: border-color 0.15s var(--km-ease);
}
.rp-row:hover { border-color: var(--km-primary); }
.rp-row-head { display: flex; align-items: center; gap: 10px; }
.rp-mode { font-size: 11px; padding: 1px 8px; border-radius: 8px; flex-shrink: 0; }
.rp-mode.demo { background: rgba(240,160,64,0.14); color: #b9680d; }
.rp-mode.interactive { background: rgba(24,144,255,0.12); color: var(--km-primary); }
.rp-target { font-weight: 550; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rp-time { margin-left: auto; font-size: 11px; color: var(--km-gray-400); flex-shrink: 0; }
.rp-meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.rp-chip { font-size: 11px; color: var(--km-gray-600); background: var(--km-gray-200); padding: 1px 8px; border-radius: 8px; }
.rp-chip.diff { background: rgba(52,179,126,0.12); color: var(--km-success); }
.rp-detail { margin-top: 8px; border-top: 1px dashed var(--km-border-light); padding-top: 8px; }
.rp-note { font-size: 12px; color: var(--km-gray-500); margin: 2px 0; }
.rp-summary { color: var(--km-gray-600); }
.rp-events { max-height: 260px; overflow: auto; display: flex; flex-direction: column; gap: 2px; margin: 6px 0; }
.rp-event {
  display: flex; gap: 6px; font-size: 12px; font-family: var(--km-font-mono, monospace);
  line-height: 1.6; color: var(--km-gray-700);
}
.ev-st { flex-shrink: 0; color: var(--km-gray-400); }
.ev-st.done { color: var(--km-success); } .ev-st.failed { color: var(--km-danger); }
.ev-st.degraded { color: #b9680d; } .ev-st.running { color: var(--km-warning); }
.ev-agent { flex-shrink: 0; color: var(--km-gray-500); width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ev-msg { color: var(--km-gray-700); }
.rp-run-actions { display: flex; gap: 8px; margin-top: 6px; }
</style>
