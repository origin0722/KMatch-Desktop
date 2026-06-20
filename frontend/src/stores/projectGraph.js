/**
 * 项目代码图谱 + Monaco 符号联动状态 (阶段4b)
 *
 * 由 chat 的 generate_project_graph 委派工具成功后填充 (setGraph)。
 * 双向联动:
 *   - chat 实体列表点击 → requestReveal → MonacoEditor watch revealTarget 跳转+高亮
 *   - Monaco 光标移动 → setActiveLine → chat 实体列表反查高亮对应实体
 */
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export const useProjectGraphStore = defineStore('projectGraph', () => {
  // 最近一次 generate_project_graph 产出
  // { projectId, stats, entities, relations, sourcePath, written }
  const graph = ref(null)

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
  }

  function clear() {
    graph.value = null
    activeLine.value = null
    revealTarget.value = null
  }

  /** chat 实体点击 → 触发 Monaco 跳转 */
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

  return {
    graph, revealTarget, activeLine, activeEntityId,
    setGraph, clear, requestReveal, setActiveLine, consumeReveal,
  }
})
