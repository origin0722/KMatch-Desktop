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
})

const TOOL_CALL_EXAMPLES = {
  read_file: '{"tool": "read_file", "path": "相对路径"}',
  list_directory: '{"tool": "list_directory", "path": "相对路径(可选)"}',
  write_file: '{"tool": "write_file", "path": "相对路径", "content": "完整文件内容"}',
  generate_project_graph: '{"tool": "generate_project_graph", "path": "相对路径", "write_to_neo4j": false}',
  code_review: '{"tool": "code_review", "path": "相对路径", "target_direction": "开发目标方向"}',
  code_test: '{"tool": "code_test", "path": "相对路径", "target_direction": "开发目标方向", "mode": "generate"}',
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
  if (allow.has('generate_project_graph') || allow.has('code_review') || allow.has('code_test')) {
    notes.push('- 审查/测试/解析工作区文件时优先传 path (而非贴 code), 便于编辑器符号联动。')
  }
  notes.push('- 后端返回 503 时表示 Neo4j 图谱引擎未就绪, 你应转告用户启动 Neo4j。')

  return `
## 可用工具
你可以通过以下格式调用工具来读写项目文件、委派后端多 Agent 能力:
${examples || '(当前没有可用工具)'}
${notes.join('\n')}`
}
