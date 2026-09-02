/**
 * 项目代码图谱 + Monaco 符号联动状态 (阶段4b)
 *
 * 由 chat 的 generate_project_graph 委派工具成功后填充 (setGraph);
 * P2: openProject 后后台自动解析 (parseCurrentProject), 重启可恢复 (restorePersisted)。
 * 双向联动:
 *   - chat 实体列表点击 -> requestReveal -> MonacoEditor watch revealTarget 跳转+高亮
 *   - Monaco 光标移动 -> setActiveLine -> chat 实体列表反查高亮对应实体
 */
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'
import { useWorkspaceStore } from '@/stores/workspace'
import { useLearningResourcesStore } from '@/stores/learningResources'
import { useAiSettingsStore } from '@/stores/aiSettings'
import { useGraphHistoryStore } from '@/stores/graphHistory'
import { readProjectPyFiles, parseProjectFiles, getProjectGraph, normalizeGraphResponse, analyzeProject } from '@/api/project'

const LS_KEY = 'kmatch-last-project-id'

export const useProjectGraphStore = defineStore('projectGraph', () => {
  // 最近一次 generate_project_graph 产出
  // { projectId, stats, entities, relations, sourcePath, written }
  const graph = ref(null)

  // ---- 历史项目图谱回看态 (issue: 此前 openFromHistory 直接覆盖当前项目图谱, 钻进去回不来) ----
  // 首次进入历史浏览时备份当前 graph, "返回当前项目图谱"一键还原; 链式浏览历史不覆盖备份。
  const historyViewing = ref(null) // null | { projectId, name }
  const historyBackup = ref(null) // { graph, stale }

  // P2: 自动解析状态机
  const parsing = ref(false)
  const parseError = ref(null)

  // 阶段8: 图谱是否已过期 (源文件被外部改动, 行号可能漂移, 跳转会指错行)
  const stale = ref(false)

  // v1.3.3: 图谱覆盖的模块集 (setGraph 时从 entities.module_name 构建), stale 判定依据
  const coveredModules = ref(new Set())

  /** 从当前 graph 重建覆盖模块集 (setGraph 与 backToCurrentProject 还原时都要重建 —
   *  终审修复: 回看历史会把覆盖集换成历史项目的, 还原时不重建则 stale 判定失效) */
  function _rebuildCoveredModules() {
    coveredModules.value = new Set(
      (graph.value?.entities || []).map((e) => e.module_name).filter(Boolean),
    )
  }

  // Monaco 跳转目标 (chat → Monaco): { path, lineStart, lineEnd, name }
  const revealTarget = ref(null)

  // Monaco 当前光标行 (Monaco → chat 反查高亮)
  const activeLine = ref(null)

  // 当前光标所在实体 id (由 activeLine + graph.entities 计算)
  const activeEntityId = computed(() => {
    const g = graph.value
    if (!g || activeLine.value == null) return null
    const ent = (g.entities || []).find(
      (e) => e.line_start != null && e.line_end != null
        && activeLine.value >= e.line_start && activeLine.value <= e.line_end,
    )
    return ent ? ent.id : null
  })

  function setGraph(result, sourcePath, { fromHistory = false } = {}) {
    const entities = result.entities || []
    graph.value = {
      projectId: result.projectId,
      stats: result.stats || {},
      entities,
      relations: result.relations || [],
      sourcePath: sourcePath || result.sourcePath,
      written: !!result.written,
    }
    // v1.3.3 stale 检测修复: 记录图谱覆盖的模块集 (module_name 由文件相对路径推导,
    // 与 watcher 事件 path 同源), markStale 按「改动文件 ∈ 覆盖集」判定。
    // 此前比较 g.sourcePath(项目根) === 事件 path(具体文件) 永假 → 过期横幅从不出现。
    _rebuildCoveredModules()
    activeLine.value = null
    revealTarget.value = null
    stale.value = false // 新图谱生成, 清过期标记
    // 真实解析/重启恢复产生新图谱 → 历史回看态失效 (重新解析即"返回当前")
    if (!fromHistory) {
      historyViewing.value = null
      historyBackup.value = null
    }
    // C2: 订阅 workspace 文件变动, 源文件被改时自行 markStale (workspace 不再硬调 projectGraph)。
    // 只订阅一次; 失败忽略 (workspace 未就绪则无失效通知, 非致命)。
    if (!_unsubscribeWsChange) {
      try {
        _unsubscribeWsChange = useWorkspaceStore().onExternalChange((event) => markStale(event.path))
      } catch { /* workspace 未就绪, 忽略 */ }
    }
  }

  let _unsubscribeWsChange = null

  /** 从历史打开已解析过的项目图谱 (无需打开项目文件; 只读回看, 源码跳转不可用)。
   *  不覆盖当前项目图谱: 首次进入时备份当前 graph, 可 backToCurrentProject 一键还原。 */
  async function openFromHistory(pid, name) {
    try {
      const data = await getProjectGraph(pid)
      const result = normalizeGraphResponse(data, '')
      if (!historyViewing.value && graph.value) {
        historyBackup.value = { graph: graph.value, stale: stale.value }
      }
      setGraph(result, '', { fromHistory: true })
      historyViewing.value = { projectId: pid, name: name || '项目' }
      useGraphHistoryStore().addProject({ projectId: pid, name })
      return true
    } catch (e) {
      const st = e?.response?.status
      if (st === 404) {
        useGraphHistoryStore().remove(`project:${pid}`)
        ElMessage.warning('该历史图谱在后端已不存在（可能被清理），已从列表移除')
      } else {
        ElMessage.error(`历史图谱加载失败: ${e?.response?.data?.detail || e?.message || '未知错误'}`)
      }
      return false
    }
  }

  /** 返回当前项目图谱 (退出历史回看, 还原进入前的 graph/stale)。 */
  function backToCurrentProject() {
    historyViewing.value = null
    activeLine.value = null
    revealTarget.value = null
    if (historyBackup.value) {
      graph.value = historyBackup.value.graph
      stale.value = historyBackup.value.stale
      _rebuildCoveredModules() // 终审修复: 覆盖集随当前图谱还原 (回看期间被换成了历史项目的)
      historyBackup.value = null
    } else {
      // 进入历史前没有当前图谱 (如未打开项目直接看历史) → "返回"即清空回空态 (此前 early return 无任何效果)
      graph.value = null
      stale.value = false
    }
  }

  /** 阶段8: 源文件被外部改动 → 标记图谱过期 (AssistantPanel 提示, 禁用实体跳转)
   *  v1.3.3 修复: 原实现比较 sourcePath(项目根) === path(具体文件) 永假, 过期横幅从不出现,
   *  用户会按旧行号跳错位置。现按「改动文件推导的模块 ∈ 图谱覆盖模块集」判定;
   *  兼容旧调用方直接传项目根路径 (与 sourcePath 全等) 的语义。
   *  终审补充: 历史回看态忽略 — 覆盖集此时属于历史项目, 误标会在"返回当前图谱"
   *  还原备份 stale 时冲掉当前项目的真实过期标记。 */
  function markStale(path) {
    if (historyViewing.value) return
    const g = graph.value
    if (!g || !path) return
    if (g.sourcePath === path) {
      stale.value = true
      return
    }
    if (!coveredModules.value.size) return
    // watcher 事件 path 为工作区相对路径 (watcher-worker path.relative), 与
    // readProjectPyFiles 推导 module_name 的路径同源 → 同一归一化即可精确匹配
    const mod = String(path).replace(/\.py$/i, '').replace(/[\\/]/g, '.')
    if (coveredModules.value.has(mod)) stale.value = true
  }

  function clearStale() {
    stale.value = false
  }

  // ---- W5 三维测评: 最近一次代码测试摘要 (practical_level 证据源) ----
  // AI 助手 code_test 成功后写入; 学情 submit 时读取上送 practical_evidence
  const lastTestReport = ref(null) // { passed, total, at }

  function setLastTestReport({ passed, total }) {
    if (!Number.isFinite(passed) || !Number.isFinite(total) || total <= 0) return
    lastTestReport.value = { passed, total, at: Date.now() }
  }

  // ---- P2: 项目自动解析 ----
  // 性能(D): 大项目解析(读文件+Neo4j+大 JSON 回填)可能秒级 — 先让"解析中"状态渲染出来
  // (setTimeout 让出主线程), 并带 token 丢弃过期调用, 避免旧结果覆盖新项目/UI 冻结。
  let _parseToken = { n: 0 }
  /** 后台解析当前工作区项目 -> 落 Neo4j + 填充 graph (不阻塞文件树交互) */
  async function parseCurrentProject() {
    const ws = useWorkspaceStore()
    if (!ws.root) return // 无项目, 跳过
    const token = ++_parseToken.n
    parsing.value = true
    parseError.value = null
    await new Promise((r) => setTimeout(r, 0)) // 先渲染"解析中", 再进 CPU 密集段
    try {
      const sources = await readProjectPyFiles('')
      if (token !== _parseToken.n) return // 已被更新的解析取代 → 丢弃
      if (!Object.keys(sources).length) {
        parseError.value = '项目中没有可解析的 .py 文件'
        return
      }
      const data = await parseProjectFiles(sources)
      if (token !== _parseToken.n) return // 过期结果不覆盖
      const result = normalizeGraphResponse(data, ws.root)
      setGraph(result, ws.root)
      useGraphHistoryStore().addProject({ projectId: result.projectId, name: ws.rootName || ws.root })
      try { localStorage.setItem(LS_KEY, result.projectId) } catch { /* ignore */ }
      ElMessage.success(`项目图谱已生成: ${result.entities.length} 个实体, ${result.relations.length} 条关系`)
    } catch (e) {
      if (token !== _parseToken.n) return
      parseError.value = e?.message || '项目解析失败'
      ElMessage.error(`项目解析失败: ${parseError.value}`)
    } finally {
      if (token === _parseToken.n) parsing.value = false
    }
  }

  /** 重启恢复: store 空 + localStorage 有上次 projectId -> 从后端拉回 (失败静默) */
  async function restorePersisted() {
    if (graph.value) return // 已有图谱, 不覆盖
    let pid
    try { pid = localStorage.getItem(LS_KEY) } catch { return }
    if (!pid) return
    try {
      const data = await getProjectGraph(pid)
      const result = normalizeGraphResponse(data, '')
      setGraph(result, '')
    } catch {
      // 404 = 后端重启/图谱已清, 清掉过期 id
      try { localStorage.removeItem(LS_KEY) } catch { /* ignore */ }
    }
  }

  // ---- P3: LLM 深度分析 + 联网搜索 (按需) ----
  const analyzing = ref(false)
  const analysis = ref(null) // {summary, architecture, complexity, recommendations, tech_stack, web_resources}

  /** 按需深度分析: LLM 分析架构 + 联网搜技术栈教程, 结果流入 learningResources */
  async function analyze() {
    const g = graph.value
    if (!g?.projectId) {
      ElMessage.warning('请先解析项目图谱')
      return
    }
    analyzing.value = true
    try {
      const aiSettings = useAiSettingsStore()
      const data = await analyzeProject(g.projectId, aiSettings.tavilyKey)
      analysis.value = data
      // web_resources 流入 learningResources store (学习视图可查看)
      const lr = useLearningResourcesStore()
      if (data.web_resources?.length) {
        lr.addWebResources('项目深度分析', data.web_resources.map((r) => ({
          title: r.title, url: r.url, snippet: r.snippet,
        })))
      }
      ElMessage.success('项目深度分析完成')
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || '深度分析失败'
      ElMessage.error(msg)
    } finally {
      analyzing.value = false
    }
  }

  // P2: 订阅 workspace 项目打开/关闭事件 -> 打开即自动解析; 关闭/切换先清旧图谱
  let _unsubscribeProjectOpen = null
  function _ensureProjectOpenSubscription() {
    if (_unsubscribeProjectOpen) return
    try {
      _unsubscribeProjectOpen = useWorkspaceStore().onProjectOpened((res) => {
        // issue: 关项目/换项目 → 旧图谱立即移除 (不再"留在那里"), 并清"上次项目"缓存
        clear()
        if (res?.root) parseCurrentProject()
      })
    } catch { /* workspace 未就绪, 忽略 */ }
  }

  function clear() {
    graph.value = null
    activeLine.value = null
    revealTarget.value = null
    stale.value = false
    parsing.value = false
    parseError.value = null
    analyzing.value = false
    analysis.value = null
    // 关项目后不再恢复旧图谱 (历史缓存仍保留, 可从历史打开)
    try { localStorage.removeItem(LS_KEY) } catch { /* ignore */ }
  }

  /** chat 实体点击 -> 触发 Monaco 跳转 */
  function requestReveal(lineStart, lineEnd, name) {
    const g = graph.value
    if (!g || lineStart == null) return
    revealTarget.value = {
      path: g.sourcePath,
      lineStart,
      lineEnd: lineEnd || lineStart,
      name: name || '',
    }
  }

  /** Monaco 光标变化回传 */
  function setActiveLine(line) {
    activeLine.value = line
  }

  /** Monaco 跳转完成后清空 (防重复触发) */
  function consumeReveal() {
    revealTarget.value = null
  }

  // store 首次使用时订阅项目打开事件 (后台自动解析)
  _ensureProjectOpenSubscription()

  return {
    graph, stale, parsing, parseError, revealTarget, activeLine, activeEntityId,
    analyzing, analysis, lastTestReport,
    setGraph, clear, clearStale, markStale, setLastTestReport,
    parseCurrentProject, restorePersisted, analyze, openFromHistory, backToCurrentProject, historyViewing,
    requestReveal, setActiveLine, consumeReveal,
  }
})
