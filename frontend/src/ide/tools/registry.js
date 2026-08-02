/**
 * 工具注册中心 — C1.2 单一源
 *
 * 工具定义（TOOLS）与权限默认（DEFAULT_TOOL_PERMISSIONS）此前分散在 chat.js 与 aiSettings.js，
 * 同名 6 工具硬编码两处。本模块收为单一源：增删/重命名工具只改这里。
 *
 * 术语对齐 CONTEXT.md "AI 助手工具集"。权限枚举 TOOL_PERMISSION 与 aiSettings 共用。
 */

export const TOOL_PERMISSION = Object.freeze({
  ALLOW: 'allow',
  ASK: 'ask',
  DENY: 'deny',
})

/** 可用工具定义（name/description/parameters），驱动系统提示词与权限默认。 */
export const TOOLS = Object.freeze([
  {
    name: 'read_file',
    description: '读取项目中的文件内容。参数: path (相对路径)。',
    parameters: { path: 'string (相对项目根目录的文件路径)' },
  },
  {
    name: 'list_directory',
    description: '列出目录内容。参数: path (相对路径，默认根目录)。',
    parameters: { path: 'string (可选，默认为项目根目录)' },
  },
  {
    name: 'write_file',
    description: '写入/创建项目文件 (需用户审批)。参数: path (相对路径), content (文件内容)。',
    parameters: {
      path: 'string (相对项目根目录的文件路径)',
      content: 'string (完整文件内容)',
    },
  },
  {
    name: 'generate_project_graph',
    description: '解析 Python 代码生成项目代码图谱 (函数/类/方法/调用关系)。参数: path (工作区文件相对路径, 优先) 或 code+filename。',
    parameters: {
      path: 'string (工作区文件相对路径, 优先于 code)',
      code: 'string (源码, path 缺省时用)',
      filename: 'string (默认 main.py)',
      write_to_neo4j: 'boolean (默认 false, 仅解析返回不落库)',
    },
  },
  {
    name: 'code_review',
    description: '代码审查 (四维度评分: 逻辑/安全/规范/领域合规, 需 Neo4j+LLM 在线)。参数: path 或 code; target_direction (开发目标方向)。',
    parameters: {
      path: 'string (工作区文件相对路径, 优先)',
      code: 'string (源码)',
      target_direction: 'string (开发目标方向, 必填)',
      knowledge_node_ids: 'string[] (可选, 指定对照知识点 ID)',
    },
  },
  {
    name: 'code_test',
    description: '代码测试 (LLM 生成 pytest 用例并沙箱执行, 需 Neo4j+LLM 在线)。参数: path 或 code+filename; target_direction; mode (默认 generate)。',
    parameters: {
      path: 'string (工作区文件相对路径, 优先)',
      code: 'string (源码)',
      filename: 'string (默认 main.py)',
      target_direction: 'string (开发目标方向, 必填)',
      mode: 'string (generate|baseline, 默认 generate)',
      knowledge_node_ids: 'string[] (可选)',
    },
  },
  {
    name: 'web_search',
    description: '联网搜索 (Tavily) 查领域知识/教程/文档, 减少幻觉; 结果自动落学习资源模块。参数: query (搜索词)。',
    parameters: {
      query: 'string (搜索词, 必填)',
      max_results: 'number (默认3, 1-8)',
    },
  },
  {
    name: 'get_knowledge_node',
    description: '按知识点编号查详情 (name/summary/difficulty/category)。不知道 PY-xxx 编号对应什么主题时调它, 不要反问用户。',
    parameters: { node_id: 'string (知识点编号, 如 PY-002)' },
  },
  {
    name: 'generate_learning_resources',
    description: '基于学情画像薄弱知识点, 调后端 content_generator 生成结构化学习资源 (讲义/实操/测试题), 结果自动落「学习资源」模块。用户说"生成学习资源/讲义"时调它, 不要自己手写讲义。需先完成学情测评。',
    parameters: { strategy: 'string (scaffold补基础|remediate降维|advance进阶, 默认 scaffold)' },
  },
])

/** 工具名清单（派生自 TOOLS，单一源）。 */
export const TOOL_NAMES = Object.freeze(TOOLS.map((t) => t.name))

/** 各工具权限默认值（与 TOOLS 同源）。 */
export const DEFAULT_TOOL_PERMISSIONS = Object.freeze({
  read_file: TOOL_PERMISSION.ALLOW,
  list_directory: TOOL_PERMISSION.ALLOW,
  write_file: TOOL_PERMISSION.ASK,
  generate_project_graph: TOOL_PERMISSION.ALLOW,
  code_review: TOOL_PERMISSION.ALLOW,
  code_test: TOOL_PERMISSION.ALLOW,
  web_search: TOOL_PERMISSION.ALLOW,
  get_knowledge_node: TOOL_PERMISSION.ALLOW,
  generate_learning_resources: TOOL_PERMISSION.ALLOW,
})

const TOOL_CALL_EXAMPLES = {
  read_file: '{"tool": "read_file", "path": "相对路径"}',
  list_directory: '{"tool": "list_directory", "path": "相对路径(可选)"}',
  write_file: '{"tool": "write_file", "path": "相对路径", "content": "完整文件内容"}',
  generate_project_graph: '{"tool": "generate_project_graph", "path": "相对路径", "write_to_neo4j": false}',
  code_review: '{"tool": "code_review", "path": "相对路径", "target_direction": "开发目标方向"}',
  code_test: '{"tool": "code_test", "path": "相对路径", "target_direction": "开发目标方向", "mode": "generate"}',
  web_search: '{"tool": "web_search", "query": "Python 装饰器原理与用法"}',
  get_knowledge_node: '{"tool": "get_knowledge_node", "node_id": "PY-002"}',
  generate_learning_resources: '{"tool": "generate_learning_resources", "strategy": "scaffold"}',
}

export function toolCallExample(tool) {
  return TOOL_CALL_EXAMPLES[tool]
}

/** 是否对外广告某工具：allow 恒广告；write_file 在 ask 下也广告（触发审批门）。 */
export function shouldAdvertiseTool(tool, permission) {
  return permission === TOOL_PERMISSION.ALLOW || (tool === 'write_file' && permission === TOOL_PERMISSION.ASK)
}

/** 按权限决策返回对外广告的工具名清单。permissionFor: (tool) => mode。 */
export function buildAdvertisedToolNames(permissionFor) {
  return TOOLS
    .map((t) => t.name)
    .filter((name) => shouldAdvertiseTool(name, permissionFor?.(name) || TOOL_PERMISSION.DENY))
}

/** 权限门错误信息：deny 报禁用；非 write_file 的 ask 报需确认；其余放行返回 null。 */
export function toolPermissionError(tool, permission) {
  if (permission === TOOL_PERMISSION.DENY) return `工具 ${tool} 已在 AI 设置中禁用`
  if (permission === TOOL_PERMISSION.ASK && tool !== 'write_file') {
    return `工具 ${tool} 需要用户确认，请先在 AI 设置中改为允许，或等待工具审批功能启用`
  }
  return null
}

/** 构建系统提示词中的"可用工具"块（示例 + 各工具注意事项）。 */
export function buildToolBlock(allowedTools) {
  const allow = new Set(Array.isArray(allowedTools) ? allowedTools : [])
  const examples = TOOLS
    .filter((t) => allow.has(t.name))
    .map((t) => `\`\`\`tool_call\n${toolCallExample(t.name)}\n\`\`\``)
    .join('\n')
  const notes = []
  const readTools = ['read_file', 'list_directory'].filter((name) => allow.has(name))
  if (readTools.length) notes.push(`- ${readTools.join('/')} 调用后返回结果, 你再继续回答。`)
  if (allow.has('write_file')) {
    notes.push(`- write_file 会触发用户审批门 (Python 文件先经 AST 安全预检), 用户可能批准或拒绝;
  批准后返回写入成功, 拒绝则返回"用户拒绝写入", 你应据此调整后续回答。
  write_file 的 content 必须是完整可用的文件内容, 不要写占位符。`)
  }
  if (allow.has('generate_project_graph')) {
    notes.push(`- generate_project_graph: 解析 Python 代码生成项目代码图谱 (函数/类/方法/调用关系),
  返回实体清单与统计; 不依赖 Neo4j (离线可用)。审查/测试工作区文件前可先调它了解结构。`)
  }
  if (allow.has('code_review')) {
    notes.push(`- code_review: 四维度代码审查 (逻辑/安全/规范/领域合规), 需 Neo4j+LLM 在线;
  target_direction 必填 (开发目标方向, 从用户上下文推断, 缺失时先问用户)。`)
  }
  if (allow.has('code_test')) {
    notes.push('- code_test: LLM 生成 pytest 用例并沙箱执行, 返回通过率/覆盖率/失败用例; 需 Neo4j+LLM 在线。')
  }
  if (allow.has('web_search')) {
    notes.push('- web_search: 联网搜索 (Tavily) 查领域知识/教程/文档, 返回 web_link 资源并自动落入学习资源模块; 遇不确定的领域概念或需要最新文档时主动调, 减少幻觉。')
  }
  if (allow.has('get_knowledge_node')) {
    notes.push('- get_knowledge_node: 按知识点编号 (如 PY-002) 查详情 (名称/摘要/难度/分类); 遇到不认识的 PY-xxx 编号 (如学情画像薄弱点) 时主动调, 查清主题后再生成资源, 不要反问用户。')
  }
  if (allow.has('generate_learning_resources')) {
    notes.push('- generate_learning_resources: 用户要"生成学习资源/讲义/实操/测试题"时调它, 调后端 content_generator 图谱驱动生成结构化资源并自动落「学习资源」模块; 【不要自己手写讲义】。需用户已完成学情测评 (有 session+画像), 无则引导先去学习会话测评。strategy: scaffold(补基础,默认)/remediate(降维)/advance(进阶)。')
  }
  if (allow.has('generate_project_graph') || allow.has('code_review') || allow.has('code_test')) {
    notes.push('- 审查/测试/解析工作区文件时优先传 path (而非贴 code), 便于编辑器符号联动。')
  }
  notes.push('- 后端返回 503 时表示 Neo4j 图谱引擎未就绪, 你应转告用户启动 Neo4j。')

  return `
## 可用工具
调用工具时【必须严格用 ` + '```tool_call' + ` fence 格式】, 否则工具不会执行:
- 格式: ` + '```tool_call' + ` 换行 + JSON 对象 + 换行 + ` + '```' + `
- JSON 必须含 "tool" 字段 (工具名, 见下方示例), 缺失会报格式错误
- 每个 fence 放一个工具调用; 不要在正文里裸写 JSON 当作工具调用
示例:
${examples || '(当前没有可用工具)'}
${notes.join('\n')}`
}
