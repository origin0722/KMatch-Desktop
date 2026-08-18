/**
 * flowEditing — 流程定义编辑状态 (Phase 3b)
 *
 * 把"可编辑流程拓扑"的增删改查抽成纯状态机 (reactive, 无 G6/API 依赖 → 可单测):
 *  - 阶段 CRUD + 排序 + label/agents/dependencies 编辑
 *  - 依赖只允许指向更早阶段 (顺序即拓扑, 与后端 validate 一致)
 *  - 提供轻量本地校验 (权威校验在后端 commit 时执行)
 *
 * 工作流: 编辑态 → saveWorkflowDraft(草稿) / commitWorkflow(提交发布, revision 化)。
 */
import { reactive } from 'vue'

export const KNOWN_AGENTS = ['orchestrator', 'diagnostics', 'reviewer', 'graph_controller', 'content_generator']
export const WF_FORMAT = 'kmatch.workflow'
export const WF_VERSION = 1

function stageFactory(key) {
  return { id: key, label: key, agents: ['diagnostics'], dependencies: [] }
}

export function createFlowEditor(definition = null) {
  const state = reactive({
    id: definition?.id || '',
    name: definition?.name || '',
    description: definition?.description || '',
    stages: (definition?.stages || []).map((s) => ({
      id: s.id, label: s.label || s.id, agents: [...(s.agents || [])], dependencies: [...(s.dependencies || [])],
    })),
    decisions: definition?.decisions ? JSON.parse(JSON.stringify(definition.decisions)) : [],
  })

  const _nextKey = () => `stage-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`

  /** 依赖只能指向更早阶段 (返回是否成功) */
  function addDependency(idx, depId) {
    const s = state.stages[idx]
    if (!s) return false
    const orderIdx = state.stages.findIndex((x) => x.id === depId)
    if (orderIdx < 0 || orderIdx >= idx || depId === s.id) return false
    if (!s.dependencies.includes(depId)) s.dependencies.push(depId)
    return true
  }

  function removeDependency(idx, depId) {
    const s = state.stages[idx]
    if (!s) return
    const i = s.dependencies.indexOf(depId)
    if (i >= 0) s.dependencies.splice(i, 1)
  }

  function addStage(key) {
    state.stages.push(stageFactory(key || _nextKey()))
  }

  function removeStage(idx) {
    const removed = state.stages[idx]
    if (!removed) return
    for (const s of state.stages) {
      const i = s.dependencies.indexOf(removed.id)
      if (i >= 0) s.dependencies.splice(i, 1)
    }
    state.stages.splice(idx, 1)
  }

  function moveStage(from, to) {
    if (from === to || from < 0 || to < 0 || from >= state.stages.length || to >= state.stages.length) return
    const [item] = state.stages.splice(from, 1)
    state.stages.splice(to, 0, item)
    // 移动后重新校验依赖序: 指向自己后面的阶段视为悬垂, 清除
    for (const s of state.stages) {
      const orderIdx = state.stages.findIndex((x) => x.id === s.id)
      s.dependencies = s.dependencies.filter((d) => {
        const di = state.stages.findIndex((x) => x.id === d)
        return di >= 0 && di < orderIdx && d !== s.id
      })
    }
  }

  function setStageLabel(idx, label) {
    if (state.stages[idx]) state.stages[idx].label = label
  }

  function setStageAgents(idx, agents) {
    if (state.stages[idx]) state.stages[idx].agents = agents
  }

  function setName(v) { state.name = v }
  function setDescription(v) { state.description = v }
  function setId(v) { state.id = v }

  function reset(definition) {
    state.id = definition?.id || ''
    state.name = definition?.name || ''
    state.description = definition?.description || ''
    state.stages = (definition?.stages || []).map((s) => ({
      id: s.id, label: s.label || s.id, agents: [...(s.agents || [])], dependencies: [...(s.dependencies || [])],
    }))
    state.decisions = definition?.decisions ? JSON.parse(JSON.stringify(definition.decisions)) : []
  }

  function buildDefinition() {
    return {
      format: WF_FORMAT,
      version: WF_VERSION,
      id: state.id,
      name: state.name,
      description: state.description,
      stages: state.stages.map((s) => ({ id: s.id, label: s.label, agents: [...s.agents], dependencies: [...s.dependencies] })),
      decisions: JSON.parse(JSON.stringify(state.decisions)),
    }
  }

  /** 轻量本地校验 (权威在后端) */
  function localIssues() {
    const issues = []
    if (!state.id) issues.push('缺流程 id')
    if (!state.name) issues.push('缺名称')
    const seen = new Set()
    for (const s of state.stages) {
      if (!s.id) { issues.push('存在无 id 的阶段'); continue }
      if (seen.has(s.id)) issues.push(`阶段 id 重复: ${s.id}`)
      seen.add(s.id)
      if (!s.agents || !s.agents.length) issues.push(`阶段「${s.label}」缺 Agents`)
      for (const a of s.agents || []) {
        if (!KNOWN_AGENTS.includes(a)) issues.push(`阶段「${s.label}」未知 Agent: ${a}`)
      }
    }
    return issues
  }

  /** 预览边 (依赖拓扑; 后端返回顺序即拓扑, 编辑器按此连线) */
  function previewEdges() {
    return state.stages.flatMap((s, i) =>
      (s.dependencies || []).map((d) => ({ source: d, target: s.id })),
    )
  }

  return {
    state,
    addStage, removeStage, moveStage,
    setStageLabel, setStageAgents, addDependency, removeDependency,
    setName, setDescription, setId,
    reset, buildDefinition, localIssues, previewEdges,
  }
}
