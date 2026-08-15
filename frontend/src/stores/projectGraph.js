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
import { readProjectPyFiles, parseProjectFiles, getProjectGraph, normalizeGraphResponse, analyzeProject } from '@/api/project'

const LS_KEY = 'kmatch-last-project-id'

export const useProjectGraphStore = defineStore('projectGraph', () => {
  // 最近一次 generate_project_graph 产出
  // { projectId, stats, entities, relations, sourcePath, written }
  const graph = ref(null)

  // P2: 自动解析状态机
  const parsing = ref(false)
  const parseError = ref(null)

  // 阶段8: 图谱是否已过期 (源文件被外部改动, 行号可能漂移, 跳转会指错行)
  const stale = ref(false)

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

  function setGraph(result, sourcePath) {
    graph.value = {
      projectId: result.projectId,
      stats: result.stats || {},
      entities: result.entities || [],
      relations: result.relations || [],
      sourcePath: sourcePath || result.sourcePath,
      written: !!result.written,
    }
    activeLine.value = null
    revealTarget.value = null
    stale.value = false // 新图谱生成, 清过期标记
    // C2: 订阅 workspace 文件变动, 源文件被改时自行 markStale (workspace 不再硬调 projectGraph)。
    // 只订阅一次; 失败忽略 (workspace 未就绪则无失效通知, 非致命)。
    if (!_unsubscribeWsChange) {
      try {
        _unsubscribeWsChange = useWorkspaceStore().onExternalChange((event) => markStale(event.path))
      } catch { /* workspace 未就绪, 忽略 */ }
    }
  }

  let _unsubscribeWsChange = null

  /** 阶段8: 源文件被外部改动 → 标记图谱过期 (AssistantPanel 提示, 禁用实体跳转) */
  function markStale(path) {
    const g = graph.value
    if (!g || !path) return
    if (g.sourcePath === path) {
      stale.value = true
    }
  }

  function clearStale() {
    stale.value = false
  }

  // ---- P2: 项目自动解析 ----
  /** 后台解析当前工作区项目 -> 落 Neo4j + 填充 graph (不阻塞文件树交互) */
  async function parseCurrentProject() {
    const ws = useWorkspaceStore()
    if (!ws.root) return // 无项目, 跳过
    parsing.value = true
    parseError.value = null
    try {
      const sources = await readProjectPyFiles('')
      if (!Object.keys(sources).length) {
        parseError.value = '项目中没有可解析的 .py 文件'
        return
      }
      const data = await parseProjectFiles(sources)
      const result = normalizeGraphResponse(data, ws.root)
      setGraph(result, ws.root)
      try { localStorage.setItem(LS_KEY, result.projectId) } catch { /* ignore */ }
      ElMessage.success(`项目图谱已生成: ${result.entities.length} 个实体, ${result.relations.length} 条关系`)
    } catch (e) {
      parseError.value = e?.message || '项目解析失败'
      ElMessage.error(`项目解析失败: ${parseError.value}`)
    } finally {
      parsing.value = false
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
      const { data } = await analyzeProject(g.projectId, aiSettings.tavilyKey)
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

  // P2: 订阅 workspace 项目打开事件 -> 后台自动解析 (只订阅一次)
  let _unsubscribeProjectOpen = null
  function _ensureProjectOpenSubscription() {
    if (_unsubscribeProjectOpen) return
    try {
      _unsubscribeProjectOpen = useWorkspaceStore().onProjectOpened(() => {
        parseCurrentProject()
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
    analyzing, analysis,
    setGraph, clear, clearStale, markStale,
    parseCurrentProject, restorePersisted, analyze,
    requestReveal, setActiveLine, consumeReveal,
  }
})
