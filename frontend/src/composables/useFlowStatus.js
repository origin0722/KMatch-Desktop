/**
 * useFlowStatus — 把 useAgentStatus 的 Agent 状态整理成"流程进度 DAG"输入
 *
 * 两种数据源:
 *  - 有流程定义 (workflow_def 快照, 如 run 落盘的 workflow): 按定义 stages 渲染真实
 *    拓扑 (阶段 label + agents 聚合状态 + 依赖连线), 与 Phase 3b 工作台/Phase 2 对齐;
 *  - 无定义: 回退到 AGENT_DEFS 线性链 (orchestrator→diagnostics→…), 保持实时直播可用。
 *
 * 纯派生, 无 G6 依赖 → 可单测。
 */
import { computed } from 'vue'
import { useAgentStatus } from './useAgentStatus'

function fallbackStages(agent) {
  const nodes = agent.agentNodes.value || []
  const firstRunning = nodes.findIndex((n) => n.status === 'running')
  return nodes.map((n, i) => ({
    key: n.key,
    label: n.label,
    icon: n.icon || '',
    status: n.status || 'idle',
    retryCount: n.retryCount || 0,
    current: i === firstRunning,
  }))
}

function definitionStages(agent, defStages) {
  const byAgent = Object.fromEntries((agent.agentNodes.value || []).map((n) => [n.key, n]))
  return defStages.map((s, i) => {
    const ags = (s.agents || []).map((a) => byAgent[a]).filter(Boolean)
    let status = 'idle'
    if (ags.some((a) => a.status === 'running')) status = 'running'
    else if (ags.some((a) => a.status === 'failed')) status = 'failed'
    else if (ags.some((a) => a.status === 'degraded')) status = 'degraded'
    else if (ags.length && ags.every((a) => a.status === 'done')) status = 'done'
    // 全员延后 (诊断+图谱就绪、资源未生成) → deferred, 不再落回 idle 灰色与列表文案打架
    else if (ags.length && ags.every((a) => a.status === 'deferred')) status = 'deferred'
    return {
      key: s.id || `s${i}`,
      label: s.label || s.id || `阶段 ${i + 1}`,
      icon: '',
      status,
      deps: Array.isArray(s.dependencies) ? s.dependencies : [],
    }
  })
}

export function useFlowStatus(definition = null) {
  const agent = useAgentStatus()

  const defStages = computed(() => {
    const d = definition && definition.stages
    return Array.isArray(d) && d.length ? d : null
  })

  const stages = computed(() => {
    const ds = defStages.value
    const arr = ds ? definitionStages(agent, ds) : fallbackStages(agent)
    const firstRunning = arr.findIndex((s) => s.status === 'running')
    return arr.map((s, i) => ({ ...s, current: i === firstRunning }))
  })

  /** 真实拓扑边 (仅定义模式; 回退线性链由 FlowDiagram 默认生成) */
  const edges = computed(() => {
    if (!defStages.value) return null
    return defStages.value.flatMap((s) =>
      (Array.isArray(s.dependencies) ? s.dependencies : []).map((d) => ({ source: d, target: s.id })),
    )
  })

  /** 当前正在执行/下一步的阶段文案 (无运行中时 null) */
  const currentLabel = computed(() => stages.value.find((s) => s.current)?.label || null)
  const doneCount = computed(() => stages.value.filter((s) => s.status === 'done').length)
  const pendingCount = computed(() => stages.value.filter((s) => s.status === 'idle').length)
  const running = computed(() => agent.pipelineRunning.value)

  return { stages, edges, currentLabel, doneCount, pendingCount, running }
}
