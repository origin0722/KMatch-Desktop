<template>
  <div class="flow-studio">
    <!-- 左：流程选择 + 事务工具栏 + 版本回滚 + 校验提示 -->
    <aside class="studio-side">
      <div class="block">
        <label class="lbl">流程</label>
        <select class="sel" v-model="selectedId" @change="loadSelected">
          <option v-for="w in workflows" :key="w.id" :value="w.id">{{ w.name }}（{{ w.id }}）</option>
        </select>
        <div class="new-row">
          <input class="inp" v-model="newId" placeholder="新流程 id" :disabled="!!selectedId" />
          <button class="btn" :disabled="!newId || !!selectedId" @click="createNew">新建</button>
        </div>
      </div>

      <div class="block">
        <div class="row">
          <button class="btn" :disabled="busy" @click="saveDraft">存草稿</button>
          <button class="btn primary" :disabled="busy || !selectedId" @click="commit">提交发布</button>
        </div>
        <input class="inp" v-model="commitNote" placeholder="提交说明（审计）" />
        <div v-if="status" class="status" :class="{ err: statusErr }">{{ status }}</div>
      </div>

      <div class="block">
        <div class="lbl">版本（{{ revisions.length }}）</div>
        <div v-for="r in revisions" :key="r.revision" class="rev-row">
          <span class="rev-meta" :title="r.revision">{{ r._tx?.note || r.name || r.revision.slice(8, 20) }}</span>
          <button class="link" @click="restore(r.revision)">回滚</button>
        </div>
        <div v-if="!revisions.length" class="muted">暂无提交版本（仅内置时新建衍生副本后可见）</div>
      </div>

      <div v-if="issueText" class="block issues">{{ issueText }}</div>
    </aside>

    <!-- 右：定义编辑 + 实时预览 -->
    <main class="studio-main">
      <div class="meta">
        <input class="inp f-id" v-model="ed.state.id" placeholder="流程 id（改后按新 id 提交即衍生副本）" @blur="syncId" />
        <input class="inp" v-model="ed.state.name" placeholder="流程名称" />
        <input class="inp" v-model="ed.state.description" placeholder="流程描述" />
      </div>

      <div class="stages">
        <div v-for="(s, i) in ed.state.stages" :key="s.id" class="stage-row">
          <div class="order">
            <button class="mini" :disabled="i === 0" @click="ed.moveStage(i, i - 1)">↑</button>
            <button class="mini" :disabled="i === ed.state.stages.length - 1" @click="ed.moveStage(i, i + 1)">↓</button>
          </div>
          <input class="inp f-id" v-model="s.id" placeholder="id" />
          <input class="inp f-label" v-model="s.label" placeholder="名称" />
          <div class="chips" title="Agents">
            <label v-for="a in KNOWN_AGENTS" :key="a" class="chip">
              <input type="checkbox" :value="a" v-model="s.agents" />{{ a }}
            </label>
          </div>
          <div class="chips" title="依赖（仅更早阶段）">
            <label v-for="p in earlierStages(i)" :key="p.id" class="chip">
              <input type="checkbox" :value="p.id" v-model="s.dependencies" />{{ p.label }}
            </label>
          </div>
          <button class="mini danger" @click="removeStage(i)">✕</button>
        </div>
        <button class="btn" @click="addStage">＋ 阶段</button>
      </div>

      <div class="preview">
        <div class="preview-head">↻ 实时预览（{{ ed.state.stages.length }} 阶段）</div>
        <FlowDiagram :stages="previewStages" :edges="ed.previewEdges()" :height="180" />
      </div>
    </main>
  </div>
</template>

<script setup>
/**
 * WorkflowStudioView — 流程工作台 (Phase 3b)
 *
 * 编辑/预览流程定义并走"拓扑提交事务": 编辑 → 本地校验 → (可选说明) →
 * 服务端严格校验 → 原子 revision 发布; 支持草稿/回滚。内置流程不可覆盖,
 * 改 id 即以"衍生副本"提交。
 *
 * 依赖刻意保持轻量 (原生控件 + FlowDiagram), 便于 jsdom 单测。
 */
import { ref, computed, onMounted } from 'vue'
import {
  fetchWorkflows,
  fetchWorkflowRevisions,
  saveWorkflowDraft,
  commitWorkflow,
  restoreWorkflowRevision,
} from '@/api/diagnostics'
import { createFlowEditor, KNOWN_AGENTS } from '@/composables/flowEditing'
import FlowDiagram from './FlowDiagram.vue'

const workflows = ref([])
const selectedId = ref(null)
const newId = ref('')
const revisions = ref([])
const commitNote = ref('')
const busy = ref(false)
const status = ref('')
const statusErr = ref(false)
const ed = createFlowEditor()

const issueText = computed(() => ed.localIssues().join('；') || '')
const previewStages = computed(() =>
  ed.state.stages.map((s) => ({ key: s.id, label: s.label, icon: '', status: 'idle', current: false })),
)

function setStatus(msg, err = false) {
  status.value = msg || ''
  statusErr.value = err
}

function earlierStages(i) { return ed.state.stages.slice(0, i) }
function addStage() { ed.addStage() }
function removeStage(i) { ed.removeStage(i) }

async function loadWorkflows() {
  try {
    const d = await fetchWorkflows()
    workflows.value = d.workflows || []
    if (!selectedId.value && workflows.value.length) {
      selectedId.value = workflows.value[0].id
      loadSelected()
    }
  } catch (e) {
    setStatus(e?.message || '加载流程失败', true)
  }
}

function loadSelected() {
  const w = workflows.value.find((x) => x.id === selectedId.value)
  if (w) {
    ed.reset(w)
    setStatus(`已载入流程「${w.name}」`)
    loadRevisions()
  } else {
    setStatus('选择的流程不存在', true)
  }
}

async function loadRevisions() {
  try {
    const d = await fetchWorkflowRevisions(selectedId.value)
    revisions.value = d.revisions || []
  } catch {
    revisions.value = []
  }
}

function createNew() {
  const id = newId.value.trim()
  if (!id) return
  ed.reset({ id, name: id, description: '', stages: [] })
  selectedId.value = id
  revisions.value = []
  newId.value = ''
  setStatus(`新建流程草稿：${id}`)
}

function syncId() {
  const id = (ed.state.id || '').trim()
  if (!id || id === selectedId.value) return
  selectedId.value = id // 改 id → 提交为新(衍生)副本
  revisions.value = []
  setStatus(`流程 id 改为 ${id}，提交即以该 id 发布`)
}

async function saveDraft() {
  if (!selectedId.value) return
  busy.value = true
  try {
    const r = await saveWorkflowDraft(selectedId.value, ed.buildDefinition())
    setStatus(r.valid ? '草稿已保存（通过校验）' : `草稿已保存（警告 ${r.warnings?.length || 0} 条）`)
  } catch (e) {
    setStatus(e?.response?.data?.detail || e?.message || '保存草稿失败', true)
  } finally {
    busy.value = false
  }
}

async function commit() {
  if (!selectedId.value) return
  busy.value = true
  try {
    const r = await commitWorkflow(selectedId.value, ed.buildDefinition(), { note: commitNote.value })
    commitNote.value = ''
    setStatus(`已提交发布 rev ${r.revision}`)
    await loadRevisions()
    refreshList()
  } catch (e) {
    setStatus(e?.response?.data?.detail || e?.message || '提交失败', true)
  } finally {
    busy.value = false
  }
}

async function restore(rev) {
  try {
    await restoreWorkflowRevision(selectedId.value, rev)
    setStatus('已回滚')
    await loadRevisions()
    refreshList()
  } catch (e) {
    setStatus(e?.response?.data?.detail || '回滚失败', true)
  }
}

async function refreshList() {
  try {
    const d = await fetchWorkflows()
    workflows.value = d.workflows || []
  } catch { /* 列表刷新失败不影响当前编辑 */ }
}

onMounted(loadWorkflows)
</script>

<style scoped>
.flow-studio { display: flex; gap: 16px; height: 100%; padding: 16px; }
.studio-side { width: 260px; flex-shrink: 0; display: flex; flex-direction: column; gap: 14px; overflow-y: auto; }
.studio-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.block { display: flex; flex-direction: column; gap: 6px; }
.lbl { font-size: 12px; color: var(--km-gray-500); }
.sel, .inp { width: 100%; box-sizing: border-box; padding: 6px 8px; font-size: 12px; border: 1px solid var(--km-border-light); border-radius: var(--km-radius-sm); background: var(--km-bg-layer-2); color: var(--km-gray-800); }
.f-id { font-family: var(--km-font-mono); }
.new-row, .row { display: flex; gap: 6px; }
.new-row .inp { flex: 1; }
.btn { padding: 5px 10px; font-size: 12px; border: 1px solid var(--km-border-light); border-radius: var(--km-radius-sm); background: var(--km-bg-layer-2); color: var(--km-gray-800); cursor: pointer; }
.btn.primary { border-color: var(--km-primary); color: var(--km-primary); }
.btn:disabled { opacity: .45; cursor: default; }
.status { font-size: 12px; color: var(--km-success); }
.status.err { color: var(--km-danger); }
.issues { font-size: 11px; color: var(--km-danger); white-space: pre-wrap; }
.rev-row { display: flex; align-items: center; justify-content: space-between; padding: 3px 0; border-bottom: 1px dashed var(--km-border-light); }
.rev-meta { font-size: 11px; color: var(--km-gray-600); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.link { font-size: 11px; color: var(--km-primary); background: none; border: 0; cursor: pointer; }
.muted { font-size: 11px; color: var(--km-gray-500); }

.meta { display: flex; flex-direction: column; gap: 6px; }
.stages { display: flex; flex-direction: column; gap: 6px; }
.stage-row { display: flex; align-items: center; gap: 6px; padding: 6px; border: 1px solid var(--km-border-light); border-radius: var(--km-radius-sm); background: var(--km-bg-layer-2); }
.order { display: flex; flex-direction: column; gap: 2px; }
.mini { width: 18px; height: 18px; font-size: 10px; border: 0; border-radius: 4px; background: var(--km-bg-layer-3); color: var(--km-gray-600); cursor: pointer; }
.mini.danger { color: var(--km-danger); }
.f-id { max-width: 90px; }
.f-label { max-width: 110px; }
.chips { display: flex; flex-wrap: wrap; gap: 4px; }
.chip { display: inline-flex; align-items: center; gap: 2px; font-size: 11px; color: var(--km-gray-600); cursor: pointer; }
.chip input { margin: 0; }
.preview { border: 1px solid var(--km-border-light); border-radius: var(--km-radius-sm); background: var(--km-bg-layer-2); }
.preview-head { padding: 6px 10px; font-size: 12px; color: var(--km-gray-500); border-bottom: 1px solid var(--km-border-light); }
</style>
