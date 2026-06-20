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
import { submitAssessment, startAssessmentStream } from '@/api/diagnostics'

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
   * 学习路径图谱 (graph_controller 产出, BUG-030)
   */
  const knowledgeGraph = ref(null)

  /**
   * 生成的学习资源 (content_generator 产出, BUG-030)
   */
  const generatedContent = ref(null)

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
  // 内部：应用测评结果到 store
  // ============================================================
  function _applyResult(data) {
    sessionId.value = data.session_id
    profile.value = data.profile
    assessment.value = data.assessment
    reviewResults.value = data.review_results
    orchestrationLog.value = data.orchestration_log || []
    knowledgeGraph.value = data.knowledge_graph || null
    generatedContent.value = data.generated_content || null

    // BUG-028: 空画像 → 错误提示
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
   * interactive 模式 — 阻塞式测评（出题快，10 秒内返回，无需 SSE）
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
    sessionId.value = null
    profile.value = null
    assessment.value = null
    reviewResults.value = null
    orchestrationLog.value = []
    knowledgeGraph.value = null
    generatedContent.value = null
    currentStep.value = null

    try {
      const data = await submitAssessment({
        targetDirection,
        mode: 'interactive',
        scene,
      }, abortController.value.signal)

      _applyResult(data)
    } catch (e) {
      if (e.name === 'CanceledError') return
      error.value = e.response?.data?.detail || e.message || '测评请求失败'
    } finally {
      loading.value = false
    }
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
    profile.value = null
    assessment.value = null
    reviewResults.value = null
    orchestrationLog.value = []
    knowledgeGraph.value = null
    generatedContent.value = null
    currentStep.value = null

    await startAssessmentStream(
      { targetDirection, scene, maxRetries: 3 },
      {
        onProgress: (p) => {
          currentStep.value = {
            node: p.node,
            message: p.message,
            logTail: p.log_tail || [],
          }
        },
        onDone: (data) => {
          _applyResult(data)
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

  /** 清空所有状态，回到输入页 */
  function reset() {
    abortController.value?.abort()
    sessionId.value = null
    loading.value = false
    error.value = null
    profile.value = null
    assessment.value = null
    reviewResults.value = null
    orchestrationLog.value = []
    knowledgeGraph.value = null
    generatedContent.value = null
    currentStep.value = null
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
    knowledgeGraph,
    generatedContent,
    // computed
    hasResults,
    reviewPassed,
    accuracy,
    knownNodeIds,
    weakNodeIds,
    // actions
    startAssessment,
    startDemoStream,
    reset,
  }
})
