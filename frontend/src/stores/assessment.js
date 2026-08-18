/**
 * 学情测评 Pinia Store
 *
 * 管理测评全流程状态：输入提交 → loading → 结果展示 / 错误处理。
 * 第5周 Dashboard 页会复用此 store 的 profile / assessment 数据。
 *
 * W7③ 更新：
 *   - demo 模式改用 SSE 流式 (startAssessmentStream)，防 2-4min 超前端 60s 超时
 *   - interactive 模式保留原阻塞 /assess
 *   - 去掉 knownTopics/maxRetries 输入（内部参数不应暴露给用户）
 *   - 新增 currentStep 用于 SSE 进度展示
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { submitAssessment, startAssessmentStream, submitAnswers, requestFeedback, fetchRun } from '@/api/diagnostics'
import { fetchLearningReport } from '@/api/learning'

export const useAssessmentStore = defineStore('assessment', () => {
  // ============================================================
  // 状态
  // ============================================================

  /** 会话 ID — 非空表示已完成或正在进行测评 */
  const sessionId = ref(null)

  /** 是否正在请求后端（LLM 调用可能 15~30 秒 / demo 2-4 分钟） */
  const loading = ref(false)

  /** 错误信息（null 表示无错误） */
  const error = ref(null)

  /**
   * SSE 流式进度 — demo 模式专用
   * { node: 'diagnostics'|'reviewer'|'graph_controller'|'content_generator'|'finish',
   *   message: '学情检测中…', log_tail: [...] }
   */
  const currentStep = ref(null)

  /**
   * 用户能力画像 v3
   * 结构对齐 data/user_profiles/profile_schema.json
   */
  const profile = ref(null)

  /**
   * 测评明细
   * 结构: { questions, answers, per_node, correct_count, total_count }
   */
  const assessment = ref(null)

  /**
   * 内容审核报告
   * 结构: { passed, overall_score, dimensions, verdict, retry_hint, reviewed_at }
   */
  const reviewResults = ref(null)

  /**
   * Agent 执行日志
   * 字符串数组，每条格式: "[时间戳] 🔧/📖/📝/✅/❌ 消息"
   */
  const orchestrationLog = ref([])

  /**
   * 结构化 Agent 执行事件 (Phase 0)
   * 对象数组，由后端 to_log_event 规范化: { type, agent, status, message, log }
   * 驱动 useAgentStatus 做确定性状态推导 (正则仅作降级兜底)。
   */
  const orchestrationEvents = ref([])

  /**
   * Phase 1: 最近一次持久化 run 的续跑信息
   * 结构: { sessionId, mode, request: {target_direction, scene, max_retries}, summary }
   * 由 loadRun / submit / demo done 填入, 供"按此流程重跑"与复盘。
   */
  const lastRun = ref(null)

  /**
   * 学习路径图谱 (graph_controller 产出, BUG-030)
   */
  const knowledgeGraph = ref(null)

  /**
   * 生成的学习资源 (content_generator 产出, BUG-030)
   */
  const generatedContent = ref(null)

  /**
   * 可视化报告数据契约 (三类可视化预计算 + M5 真实质量指标)
   * demo 模式由 assess/assess_stream 内联返回; interactive 由 /learning/report 补跑
   * 结构: { blind_spots, difficulty_match, learning_path, review_status, quality_metrics, generated_at }
   *   (契约对齐 backend/app/agents/report_builder.build_learning_report)
   */
  const learningReport = ref(null)
  /** 报告补跑中 (interactive /learning/report) */
  const reportLoading = ref(false)
  /** 报告已取 (含会话失效降级), 幂等防重复补跑 */
  const reportLoaded = ref(false)

  // ============================================================
  // interactive 三阶段状态 (S9 修复: 接通答题闭环)
  // ============================================================
  /** 阶段: 'idle' | 'answering' | 'feedback' (demo 模式直接走 hasResults) */
  const phase = ref('idle')
  /** interactive 出题阶段缓存的题目 (answer/explanation 已剥离) */
  const pendingQuestions = ref([])
  /** 用户作答数组 (按 question_index 对齐) */
  const userAnswers = ref([])
  /** 动态反馈策略 (submit 返回): 'advance'|'remediate'|'scaffold' */
  const feedbackStrategy = ref(null)
  /** 动态反馈再生资源 (feedback 接口返回) */
  const feedbackContent = ref(null)

  /** 请求取消控制器 */
  const abortController = ref(null)

  // ============================================================
  // 计算属性
  // ============================================================

  /** 测评是否已完成（画像有实际内容，非空对象——BUG-017） */
  const hasResults = computed(() => {
    const p = profile.value
    if (!p || typeof p !== 'object') return false
    return Object.keys(p).length > 0
  })

  /** 审核是否通过 */
  const reviewPassed = computed(() => reviewResults.value?.passed ?? false)

  /** 答题正确率 0-1 */
  const accuracy = computed(() => {
    const a = assessment.value
    if (!a || !a.total_count) return 0
    return a.correct_count / a.total_count
  })

  /** 已知节点 ID 列表（快捷取用） */
  const knownNodeIds = computed(() =>
    profile.value?.known_topics?.map((t) => t.node_id) ?? [],
  )

  /** 薄弱节点 ID 列表（快捷取用） */
  const weakNodeIds = computed(() =>
    profile.value?.weak_topics?.map((t) => t.node_id) ?? [],
  )

  // ============================================================
  // 内部：重置结果相关状态 (demo/interactive/reset 共用)
  // ============================================================
  function _resetResult() {
    profile.value = null
    assessment.value = null
    reviewResults.value = null
    orchestrationLog.value = []
    orchestrationEvents.value = []
    lastRun.value = null
    knowledgeGraph.value = null
    generatedContent.value = null
    learningReport.value = null
    reportLoading.value = false
    reportLoaded.value = false
  }

  // ============================================================
  // 内部：应用 demo/完整结果到 store (含 learning_report, S8)
  // ============================================================
  function _applyResult(data) {
    sessionId.value = data.session_id
    profile.value = data.profile
    assessment.value = data.assessment
    reviewResults.value = data.review_results
    orchestrationLog.value = data.orchestration_log || []
    orchestrationEvents.value = data.orchestration_events || []
    knowledgeGraph.value = data.knowledge_graph || null
    generatedContent.value = data.generated_content || null
    learningReport.value = data.learning_report || null

    // BUG-028: demo 模式空画像 → 错误提示
    // (interactive 模式空画像是正常的出题阶段, 由 startAssessment 单独处理, 不会走到这)
    if (!data.profile || Object.keys(data.profile).length === 0) {
      error.value = data.review_results?.retry_hint
        || '学情检测未产出有效画像（后端 LLM 可能未配置），请检查后端配置后重试'
      profile.value = null
    }
  }

  // ============================================================
  // Actions
  // ============================================================

  /**
   * interactive 模式 — 出题阶段 (S9 修复: 不再把空 profile 当错误, 而是进入答题)
   *
   * 流程: assess(interactive) → 拿到 questions → phase='answering'
   *       → 用户答题 → submitAnswers() → submitAssessmentAnswers()
   *       → phase='feedback' → requestFeedback()
   *
   * @param {Object} opts
   * @param {string} opts.targetDirection
   * @param {'no_project'|'with_project'} [opts.scene='no_project']
   */
  async function startAssessment({
    targetDirection,
    scene = 'no_project',
  }) {
    abortController.value?.abort()
    abortController.value = new AbortController()

    // 重置
    loading.value = true
    error.value = null
    _resetResult()
    currentStep.value = null
    phase.value = 'idle'
    pendingQuestions.value = []
    userAnswers.value = []
    feedbackStrategy.value = null
    feedbackContent.value = null

    try {
      // 动态建域 (阶段16): 新领域联网检索资料用, 与 feedback 阶段同源 (aiSettings, 懒加载避循环依赖)
      const { useAiSettingsStore } = await import('@/stores/aiSettings')
      const data = await submitAssessment({
        targetDirection,
        mode: 'interactive',
        scene,
        tavilyKey: useAiSettingsStore().tavilyKey,
      }, abortController.value.signal)

      // interactive 出题阶段: 拿到 questions 进入答题, 不调 _applyResult (它会因空 profile 误报)
      sessionId.value = data.session_id
      const questions = data.assessment?.questions || []
      if (questions.length === 0) {
        error.value = '出题失败：未获得测评题目（后端 LLM/题库可能未配置）'
        phase.value = 'idle'
        return
      }
      pendingQuestions.value = questions
      userAnswers.value = new Array(questions.length).fill('')
      assessment.value = data.assessment
      phase.value = 'answering'
    } catch (e) {
      if (e.name === 'CanceledError') return
      error.value = e.response?.data?.detail || e.message || '测评请求失败'
      phase.value = 'idle'
    } finally {
      loading.value = false
    }
  }

  /**
   * interactive 第二步 — 提交答题 (S9)
   * 调 POST /submit → 判分 + 画像 + feedback.strategy, 进入反馈阶段
   */
  async function submitAssessmentAnswers() {
    if (!sessionId.value || phase.value !== 'answering') return
    loading.value = true
    error.value = null
    try {
      const data = await submitAnswers({ sessionId: sessionId.value, answers: userAnswers.value })
      // submit 返回: { session_id, profile, assessment, review_results, feedback:{strategy,...} }
      profile.value = data.profile
      assessment.value = data.assessment
      reviewResults.value = data.review_results
      feedbackStrategy.value = data.feedback?.strategy || null
      knowledgeGraph.value = data.knowledge_graph || null
      orchestrationLog.value = data.orchestration_log || []
      orchestrationEvents.value = data.orchestration_events || []
      phase.value = 'feedback'
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '提交答题失败'
    } finally {
      loading.value = false
    }
  }

  /**
   * interactive 第三步 — 动态反馈再生 (S9)
   * 按 feedbackStrategy 调 POST /feedback → 针对性再生资源
   *   advance: 进阶题 / remediate: 降维讲义 / scaffold: 补前置基础
   */
  async function fetchFeedback() {
    if (!sessionId.value || !feedbackStrategy.value) return
    loading.value = true
    error.value = null
    try {
      const { useAiSettingsStore } = await import('@/stores/aiSettings')
      const tavilyKey = useAiSettingsStore().tavilyKey
      const data = await requestFeedback({ sessionId: sessionId.value, strategy: feedbackStrategy.value, profile: profile.value, tavilyKey })
      feedbackContent.value = data
      // #30 后续: 反馈产物落入「学习资源」页 (Learning.vue 读取)——
      //   再生知识点 (lecture/practice_guide/test) → generatedContent (讲义/实操/测试 tab)
      //   web_link 相关网址 → learningResources (联网资源 tab); 有产物时自动打开右侧学习资源分屏
      const resources = data.resources || []
      const links = resources.filter((r) => r.content_type === 'web_link')
      const content = resources.filter((r) => r.content_type !== 'web_link')
      if (links.length) {
        const { useLearningResourcesStore } = await import('@/stores/learningResources')
        useLearningResourcesStore().addFeedbackLinks(links)
      }
      if (content.length) {
        const existing = generatedContent.value || { resources: [] }
        generatedContent.value = {
          ...existing,
          resources: [...(existing.resources || []), ...content],
          node_count: data.node_count ?? existing.node_count,
        }
      }
      if (resources.length) {
        const { useSessionStore } = await import('@/stores/session')
        useSessionStore().setSplitView('learning')
      }
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '动态反馈再生失败'
    } finally {
      loading.value = false
    }
  }

  /**
   * interactive 可视化报告 (issue-42): 按 session_id 调 /learning/report 补跑,
   * 填充 learningReport (M5 真实质量指标 + 三类可视化预计算) 供 Dashboard 使用。
   *
   * 幂等: reportLoaded 防止重复补跑 (后端同一 session 也会缓存);
   * 会话失效 (404/409) 标记已取, 不给死磕。补跑失败不弹错, Dashboard 走客户端派生兜底。
   */
  async function loadLearningReport() {
    if (!sessionId.value || !profile.value || reportLoading.value || reportLoaded.value) return
    reportLoading.value = true
    try {
      const data = await fetchLearningReport({ sessionId: sessionId.value })
      learningReport.value = data.learning_report || null
      // 补跑产出的路径/内容/审核在 interactive 下可能缺失, 合并回 store 供看板/学习资源消费
      // (已有值不覆盖 —— 反馈再生的针对性内容优先保留)
      if (!knowledgeGraph.value && data.knowledge_graph) knowledgeGraph.value = data.knowledge_graph
      if (!generatedContent.value && data.generated_content) generatedContent.value = data.generated_content
      if (!reviewResults.value && data.review_results) reviewResults.value = data.review_results
      reportLoaded.value = true
    } catch (e) {
      const st = e?.response?.status
      if (st === 404 || st === 409) reportLoaded.value = true // 会话失效 → 不再补跑
      if (import.meta.env.DEV) console.debug('[assessment] 学习报告补跑失败', e?.message)
    } finally {
      reportLoading.value = false
    }
  }

  /** interactive 阶段回退到输入 (重新测评) */
  function backToInput() {
    phase.value = 'idle'
    pendingQuestions.value = []
    userAnswers.value = []
    feedbackStrategy.value = null
    feedbackContent.value = null
  }

  /**
   * demo 模式 — SSE 流式测评（全流程 2-4 分钟，流式推送防超时）
   *
   * @param {Object} opts
   * @param {string} opts.targetDirection
   * @param {'no_project'|'with_project'} [opts.scene='no_project']
   */
  async function startDemoStream({
    targetDirection,
    scene = 'no_project',
  }) {
    // 重置
    loading.value = true
    error.value = null
    sessionId.value = null
    _resetResult()
    currentStep.value = null
    phase.value = 'idle'
    pendingQuestions.value = []
    userAnswers.value = []
    feedbackStrategy.value = null
    feedbackContent.value = null

    // Phase 1: 记录本次 demo 的请求 meta, 供"按此流程重跑" (续跑)
    lastRun.value = {
      sessionId: null,
      mode: 'demo',
      request: { target_direction: targetDirection, scene, max_retries: 3 },
      summary: lastRun.value?.summary || null,
    }

    await startAssessmentStream(
      { targetDirection, scene, maxRetries: 3 },
      {
        onProgress: (p) => {
          currentStep.value = {
            node: p.node,
            message: p.message,
            logTail: p.log_tail || [],
          }
          // Phase 0: demo 流式期间实时累加事件与日志 (原有行为只在 done 后填充;
          // 修复 2-4 分钟流式期间 Agent 协同卡片空白), 去重后 at done 由终态整体替换
          const lt = Array.isArray(p.log_tail) ? p.log_tail : []
          for (const line of lt) {
            if (!orchestrationLog.value.includes(line)) orchestrationLog.value.push(line)
          }
          const evs = Array.isArray(p.log_events) ? p.log_events : []
          for (const ev of evs) {
            if (ev && !orchestrationEvents.value.some((e) => e.log === ev.log)) {
              orchestrationEvents.value.push(ev)
            }
          }
        },
        onDone: (data) => {
          _applyResult(data)
          if (lastRun.value) lastRun.value.sessionId = data.session_id
          loading.value = false
          currentStep.value = null
        },
        onError: (detail) => {
          error.value = detail || 'SSE 流式测评失败'
          loading.value = false
          currentStep.value = null
        },
      },
    )
  }

  /**
   * Phase 1: 读取已持久化的 run 记录并回灌 (复盘), 填充 lastRun 供续跑。
   * @param {string} sid 已落盘的 session_id
   * @returns {Promise<Object|null>} run 记录; 无运行记录返回 null。
   */
  async function loadRun(sid) {
    if (!sid) return null
    let data
    try {
      data = await fetchRun(sid)
    } catch (e) {
      if (e?.response?.status === 404) return null // 无持久 run 记录
      throw e
    }
    if (!data) return null
    orchestrationLog.value = data.orchestration_log || []
    orchestrationEvents.value = data.orchestration_events || []
    sessionId.value = data.session_id || sid
    lastRun.value = {
      sessionId: data.session_id || sid,
      mode: data.mode || 'demo',
      request: data.request || {},
      summary: data.summary || {},
    }
    return data
  }

  /**
   * Phase 1: 按上次 demo 的请求参数一键重跑 (续跑)。
   * @returns {Promise<void>|null} 无 demo run 记录时返回 null。
   */
  async function resumeRunDemo() {
    const r = lastRun.value
    if (!r || r.mode !== 'demo' || !r.request?.target_direction) return null
    return startDemoStream({
      targetDirection: r.request.target_direction,
      scene: r.request.scene || 'no_project',
    })
  }

  /** 清空所有状态，回到输入页 */
  function reset() {
    abortController.value?.abort()
    sessionId.value = null
    loading.value = false
    error.value = null
    _resetResult()
    currentStep.value = null
    phase.value = 'idle'
    pendingQuestions.value = []
    userAnswers.value = []
    feedbackStrategy.value = null
    feedbackContent.value = null
  }

  return {
    // state
    sessionId,
    loading,
    error,
    currentStep,
    profile,
    assessment,
    reviewResults,
    orchestrationLog,
    orchestrationEvents,
    knowledgeGraph,
    generatedContent,
    learningReport,
    reportLoading,
    reportLoaded,
    // interactive 三阶段状态 (S9)
    phase,
    pendingQuestions,
    userAnswers,
    feedbackStrategy,
    feedbackContent,
    // Phase 1: 持久 run (复盘/续跑)
    lastRun,
    // computed
    hasResults,
    reviewPassed,
    accuracy,
    knownNodeIds,
    weakNodeIds,
    // actions
    startAssessment,
    startDemoStream,
    submitAssessmentAnswers,
    fetchFeedback,
    loadLearningReport,
    loadRun,
    resumeRunDemo,
    backToInput,
    reset,
  }
})
