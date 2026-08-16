/**
 * 项目代码图谱 API
 *
 * 对齐 backend/app/api/project.py:
 *   POST /api/project/parse       解析 Python 代码 -> 项目代码图谱 (可选落 Neo4j)
 *   GET  /api/project/graph/{id}  查询已落库的项目图谱
 *
 * readProjectPyFiles: 读工作区所有 .py 文件 (IPC fs), 供 parse 与 chat 工具复用。
 */
import http from './index'

const hasIpc = typeof window !== 'undefined' && !!window.api?.fs

/**
 * 读工作区目录所有 .py 文件 -> {module_name: source}
 * @param {string} dirPath 工作区相对路径 (空串 = 根)
 * @returns {Promise<Record<string, string>>}
 */
export async function readProjectPyFiles(dirPath = '') {
  if (!hasIpc) return {}
  const entries = await window.api.fs.listDirectory(dirPath, { deep: true })
  const pyFiles = (entries || []).filter((e) => !e.isDirectory && e.path.endsWith('.py'))
  const sources = {}
  for (const f of pyFiles) {
    try {
      const content = await window.api.fs.readFile(f.path)
      const module = (f.path || '').replace(/\.py$/, '').replace(/[\/\\]/g, '.')
      sources[module] = content
    } catch { /* skip unreadable */ }
  }
  return sources
}

/**
 * 解析项目代码 -> 项目代码图谱 (落 Neo4j, 供后续查询/跳转)
 * @param {Record<string, string>} sources {module_name: source_code}
 * @returns {Promise<Object>} {project_id, nodes, edges, stats, written_to_neo4j}
 */
export function parseProjectFiles(sources) {
  return http.post('/api/project/parse', {
    source_type: 'files',
    sources,
    write_to_neo4j: true,
  })
}

/**
 * 查询已落库的项目图谱 (重启恢复 / 助手查询)
 * @param {string} projectId
 * @returns {Promise<Object>} G6 结构 {project_id, nodes, edges, stats, parsed_at}
 */
export function getProjectGraph(projectId) {
  return http.get(`/api/project/graph/${projectId}`)
}

/**
 * LLM 深度分析项目图谱 + 联网搜索技术栈学习资源 (按需)
 * @param {string} projectId
 * @param {string} [tavilyKey] Tavily API Key (空时后端用 settings)
 * @returns {Promise<Object>} {summary, architecture, complexity, recommendations, tech_stack, web_resources}
 */
export function analyzeProject(projectId, tavilyKey) {
  return http.post('/api/project/analyze', {
    project_id: projectId,
    tavily_key: tavilyKey || undefined,
  }, { timeout: 180000 }) // 3 min: LLM 分析 + 多技术栈联网搜索
}

/**
 * 后端 ProjectGraphResponse -> projectGraph store setGraph 入参格式
 * (nodes G6 -> entities 扁平, 字段名驼峰化; chat 工具与 store 自动解析共用)
 * @param {Object} data 后端响应 {project_id, nodes, edges, stats, written_to_neo4j}
 * @param {string} sourcePath 工作区根路径 (GET 恢复时可能为空)
 * @returns {Object} {projectId, stats, entities, relations, sourcePath, written}
 */
export function normalizeGraphResponse(data, sourcePath = '') {
  const d = data || {}
  const entities = (d.nodes || []).map((n) => {
    const p = n.properties || {}
    return {
      id: n.id,
      name: n.label,
      kind: n.group,
      qualified_name: p.qualified_name || n.label,
      line_start: p.line_start,
      line_end: p.line_end,
      module_name: p.module_name,
      docstring: p.docstring || '',
      params: _parseJsonField(p.params, []),
      return_type: p.return_type || '',
      bases: _parseJsonField(p.bases, []),
      decorators: _parseJsonField(p.decorators, []),
      external_calls: _parseJsonField(p.external_calls, []),
      source_code: p.source_code || '',
      is_method: !!p.is_method,
    }
  })
  return {
    projectId: d.project_id,
    stats: _mapStats(d.stats),
    entities,
    relations: d.edges || [],
    sourcePath,
    written: !!d.written_to_neo4j,
  }
}

/** Neo4j 存 JSON 字符串的列表字段安全解析 */
function _parseJsonField(v, fallback) {
  if (Array.isArray(v)) return v
  if (typeof v === 'string') { try { return JSON.parse(v) } catch { return fallback } }
  return fallback
}

/** 后端 stats key (function_count) -> 前端期望的短 key (function) */
function _mapStats(stats) {
  if (!stats || typeof stats !== 'object') return {}
  const map = {
    module_count: 'module', class_count: 'class',
    function_count: 'function', method_count: 'method',
    contains_count: 'contains', call_count: 'call',
    inheritance_count: 'inheritance', external_call_count: 'external_call',
    relation_count: 'relation',
  }
  const out = {}
  for (const [k, v] of Object.entries(stats)) out[map[k] || k] = v
  return out
}
