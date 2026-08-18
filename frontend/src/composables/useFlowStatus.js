/**
 * useFlowStatus — 把 useAgentStatus 的 Agent 状态流整理成"流程进度 DAG"输入
 *
 * Phase 3a (只读): 以协同面板现有 Agent 流水 (AGENT_DEFS 序) 为线性流程,
 * 计算每阶段 status + current(当前运行步), 供 FlowDiagram 渲染。
 * Phase 3b 将改为由 workflow 定义 (workflow_def) 驱动真实阶段拓扑。
 *
 * 纯派生, 无 G6 依赖 → 可单测。
 */
import { computed } from 'vue'
import { useAgentStatus } from './useAgentStatus'

export function useFlowStatus() {
  const agent = useAgentStatus()

  const stages = computed(() => {
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
  })

  /** 当前正在执行/下一步的阶段文案 (无运行中时 null) */
  const currentLabel = computed(() => stages.value.find((s) => s.current)?.label || null)
  const doneCount = computed(() => agent.completedCount.value)
  const pendingCount = computed(() => agent.pendingCount.value)
  const running = computed(() => agent.pipelineRunning.value)

  return { stages, currentLabel, doneCount, pendingCount, running }
}
