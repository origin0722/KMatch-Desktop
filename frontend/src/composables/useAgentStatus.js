/**
 * useAgentStatus — 从 orchestrationLog 推导各 Agent 实时状态
 *
 * 输入：store.orchestrationLog[]（字符串数组）
 * 输出：agentNodes（含 status/retryCount）+ pipelineRunning
 *
 * 推导规则：
 *   - 关键字映射 → agent key
 *   - 📚/🔍/📊 + "开始" → running
 *   - ✅ + "通过"|"完成" → done
 *   - ❌ + "不通过" → failed
 *   - reviewer 日志 "(第N轮)" → retryCount
 *   - pipelineRunning = 最后一条非 "✅ 流程结束"
 */
import { computed } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'

/** Agent 节点静态定义（不含状态，状态由日志动态推导） */
const AGENT_DEFS = [
  {
    key: 'orchestrator',
    label: '主控调度',
    icon: '🎯',
    role: '全局状态管理、流程编排、冲突裁决、循环控制',
  },
  {
    key: 'diagnostics',
    label: '学情检测',
    icon: '🔍',
    role: '理论+实操+学习风格三维测评，输出用户能力画像',
  },
  {
    key: 'reviewer',
    label: '内容审核',
    icon: '⚖️',
    role: '对照图谱事实校验生成内容与画像合理性，打回博弈',
  },
  {
    key: 'graph_controller',
    label: '图谱管控',
    icon: '🗺️',
    role: '组装学习路径图谱 / 项目图谱 + 节点状态标注',
  },
  {
    key: 'content_generator',
    label: '内容生成',
    icon: '📝',
    role: '基于图谱 + 画像生成讲义/实操指南/测试题，溯源到节点',
  },
]

// ---------------------------------------------------------------
// 关键字 → agent key 映射
// ---------------------------------------------------------------
const KEYWORD_MAP = [
  { pattern: /学情检测/, key: 'diagnostics' },
  { pattern: /内容审核|画像审核|内容模式|画像模式/, key: 'reviewer' },
  { pattern: /知识图谱|图谱组装/, key: 'graph_controller' },
  { pattern: /领域知识生成/, key: 'content_generator' },
  { pattern: /流程结束/, key: 'orchestrator' },
  { pattern: /主控调度/, key: 'orchestrator' },
]

function resolveAgentKey(line) {
  for (const { pattern, key } of KEYWORD_MAP) {
    if (pattern.test(line)) return key
  }
  return null
}

function extractRetryCount(line) {
  const m = line.match(/第(\d+)轮/)
  return m ? parseInt(m[1], 10) : null
}

// ---------------------------------------------------------------
// 状态推导
// ---------------------------------------------------------------
function deriveAgentStates(logs) {
  const states = {}
  for (const def of AGENT_DEFS) {
    states[def.key] = { status: 'idle', retryCount: 0 }
  }

  let maxRetry = 0

  for (const line of logs) {
    const key = resolveAgentKey(line)
    if (!key) continue

    const state = states[key]

    // 开始 → running (对齐后端日志 emoji: diagnostics=🔧, graph_controller=🗺️, content_generator=📚, reviewer=🔍)
    if (/📚|🔍|📊|🔧|🗺️/.test(line) && /开始/.test(line)) {
      state.status = 'running'
    }
    // 通过/完成 → done
    else if (/✅/.test(line) && /通过|完成/.test(line)) {
      state.status = 'done'
    }
    // 不通过 → failed
    else if (/❌/.test(line) && /不通过/.test(line)) {
      state.status = 'failed'
    }
    // orchestrator 降级结束 (⚠️ 流程结束 超过最大重试) 也判 done
    else if (/⚠️/.test(line) && /流程结束/.test(line)) {
      state.status = 'done'
    }

    // 提取重试轮数
    const round = extractRetryCount(line)
    if (round !== null && round > maxRetry) {
      maxRetry = round
    }
  }

  // retryCount 归给 reviewer（打回博弈的主体）
  if (states.reviewer) {
    states.reviewer.retryCount = Math.max(0, maxRetry - 1)
  }

  return states
}

// ---------------------------------------------------------------
// Composable
// ---------------------------------------------------------------
export function useAgentStatus() {
  const store = useAssessmentStore()

  const logs = computed(() => store.orchestrationLog || [])

  const agentNodes = computed(() => {
    const states = deriveAgentStates(logs.value)
    return AGENT_DEFS.map((def) => ({
      ...def,
      status: states[def.key]?.status || 'idle',
      retryCount: states[def.key]?.retryCount || 0,
    }))
  })

  const pipelineRunning = computed(() => {
    const all = logs.value
    if (all.length === 0) return false
    const last = all[all.length - 1]
    return !/✅.*流程结束/.test(last)
  })

  return { agentNodes, pipelineRunning }
}
