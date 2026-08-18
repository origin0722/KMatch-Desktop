/**
 * useAgentStatus — 从结构化事件 / orchestrationLog 推导各 Agent 实时状态
 *
 * 输入：store.orchestrationEvents[]（结构化, Phase 0 优先, 后端 to_log_event 产出）
 *       store.orchestrationLog[]（字符串, 正则降级兜底）
 * 输出：agentNodes（含 status/retryCount）+ pipelineRunning
 *
 * Phase 0 推导规则（结构化事件优先，事件缺失时回退正则）：
 *   - 事件 {type, agent, status} → 确定性状态映射 (running/done/failed)
 *   - run-end degraded → orchestrator failed (降级结束)
 *   - retryCount 始终来自日志 "(第N轮)"（事件不带轮数）
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
// 结构化事件 → 状态 (Phase 0, 优先; 事件缺失时回退下方正则推导)
// ---------------------------------------------------------------
function statesFromEvents(events) {
  const states = {}
  for (const def of AGENT_DEFS) {
    states[def.key] = { status: 'idle', retryCount: 0 }
  }
  for (const ev of events) {
    if (!ev || !ev.agent) continue
    if (ev.type === 'run-end') {
      // 降级结束 → orchestrator 显示「降级」(区别于失败): 超重试/降级待人工
      states.orchestrator.status = ev.status === 'degraded' ? 'degraded' : 'done'
      continue
    }
    const st = states[ev.agent]
    if (!st) continue
    if (ev.status === 'running') st.status = 'running'
    else if (ev.status === 'failed') st.status = 'failed'
    else if (ev.status === 'degraded') st.status = 'degraded'
    else if (ev.status === 'done') st.status = 'done'
  }
  return states
}

// ---------------------------------------------------------------
// 状态推导 (正则)
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
    // 降级提示 (⚠️ 含"流程结束"= orchestrator 降级结束; 其余为某阶段降级, 如 LLM 未配置)
    else if (/⚠️/.test(line)) {
      state.status = 'degraded'
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
  const events = computed(() => store.orchestrationEvents || [])

  // ---------------------------------------------------------------
  // 每 Agent 产出概览 (store 实数据, ground truth) - 先于 agentNodes, 供 done 判定
  // interactive 模式 submit 仅跑 学情检测+画像+图谱管控; 内容生成/审核按需触发。
  // 故产出自适应: 有数据则展示具体产出, 无则 undefined (组件回落到 role 描述)。
  // ---------------------------------------------------------------
  const productions = computed(() => {
    const out = {}
    // 主控调度: 有结果即编排完成
    if (store.hasResults) out.orchestrator = '流程编排完成 · 各 Agent 产出已就绪'
    // 学情检测: 判分 + 画像维度
    const asm = store.assessment
    const p = store.profile
    if (asm && p) {
      out.diagnostics = `判分 ${asm.correct_count}/${asm.total_count} · 理论 L${p.theory_level ?? '?'}/实操 L${p.practical_level ?? '?'} · 薄弱 ${p.weak_topics?.length ?? 0} 点`
    }
    // 图谱管控: 学习路径节点数 + 预估时长
    const kg = store.knowledgeGraph
    if (kg) {
      const n = kg.learning_path?.length ?? kg.path_node_ids?.length ?? 0
      const h = kg.estimated_total_hours
      out.graph_controller = `${n} 节点学习路径` + (h ? ` · 预估 ${h}h` : '')
    }
    // 内容生成: 优先 generatedContent, 回落 针对性反馈 feedbackContent
    const gc = store.generatedContent
    const fc = store.feedbackContent
    if (gc?.resources?.length) {
      out.content_generator = `已生成 ${gc.resources.length} 段资源` + (gc.node_count ? ` · 覆盖 ${gc.node_count} 节点` : '')
    } else if (fc?.resources?.length) {
      out.content_generator = `针对性反馈 · ${fc.strategy ?? ''} 策略 · ${fc.resources.length} 段`
    }
    // 内容审核: 通过/打回 + 评分 + 轮次
    const rr = store.reviewResults
    if (rr) {
      const parts = [rr.passed ? '通过' : '打回']
      if (rr.overall_score != null) parts.push(`评分 ${rr.overall_score}`)
      out.reviewer = parts.join(' · ')
    }
    return out
  })

  // ---------------------------------------------------------------
  // agentNodes: 优先结构化事件(events)推导; 无事件回退日志正则。
  // 产出覆盖仍为 ground truth (有产出即 done)。retryCount 始终取日志 "(第N轮)"。
  // ---------------------------------------------------------------
  const agentNodes = computed(() => {
    const logStates = deriveAgentStates(logs.value)
    const states = events.value.length ? statesFromEvents(events.value) : logStates
    const prod = productions.value
    return AGENT_DEFS.map((def) => {
      let status = states[def.key]?.status || 'idle'
      // retryCount 来自日志推导 (事件不带轮数)
      const retryCount = logStates[def.key]?.retryCount || 0
      if (prod[def.key]) status = 'done'
      return { ...def, status, retryCount }
    })
  })

  // 运行中: 仅在请求 in flight (loading) 且有日志/事件时为真。
  // Phase 0: 结构化事件与日志任一存在即视为流进行中 (旧逻辑只看日志长度)。
  // 旧逻辑看最后一条日志是否含"流程结束"--interactive submit 无此标记, 会误判为一直运行中。
  const pipelineRunning = computed(
    () => !!store.loading && (logs.value.length > 0 || events.value.length > 0),
  )

  // 实时动作: pipelineRunning 时取最后一条事件/日志的 agent + 去时间戳/emoji 的消息
  const currentAction = computed(() => {
    if (!pipelineRunning.value) return null
    // 结构化事件优先: 最后一条事件的 message 已清洗
    const evs = events.value
    if (evs.length) {
      const lastEv = evs[evs.length - 1]
      const key = lastEv.agent && AGENT_DEFS.some((d) => d.key === lastEv.agent) ? lastEv.agent : null
      const label = AGENT_DEFS.find((d) => d.key === key)?.label || '协同'
      const action = lastEv.message || lastEv.status || '执行中'
      if (action && action !== 'idle') return { label, action }
    }
    const all = logs.value
    if (!all.length) return null
    const last = all[all.length - 1]
    const key = resolveAgentKey(last)
    const label = AGENT_DEFS.find((d) => d.key === key)?.label || '协同'
    // 去时间戳 [..] + 去行首 emoji/符号 (剥到首个中文/字母)。
    // emoji 是代理对, 不能用枚举字符类 (无 u flag 会只剥高位代理 -> 乱码)。
    const msg = String(last)
      .replace(/^\[[^\]]*\]\s*/, '')
      .replace(/^[^一-龥a-zA-Z]+/, '')
    return { label, action: msg || '执行中' }
  })

  const completedCount = computed(() => agentNodes.value.filter((n) => n.status === 'done').length)
  const pendingCount = computed(() => agentNodes.value.filter((n) => n.status === 'idle').length)

  return { agentNodes, pipelineRunning, productions, currentAction, completedCount, pendingCount }
}
