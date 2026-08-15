/**
 * 技术栈自动检测 - 扫描实体 external_calls 推断项目依赖技术分类
 * 纯 AST 数据驱动, 零 LLM 成本
 */

// 常见 Python 包 -> 技术分类映射 (top-level import name -> 分类)
const TECH_MAP = {
  // Web 框架
  flask: { name: 'Flask', category: 'Web 框架' },
  fastapi: { name: 'FastAPI', category: 'Web 框架' },
  django: { name: 'Django', category: 'Web 框架' },
  starlette: { name: 'Starlette', category: 'Web 框架' },
  tornado: { name: 'Tornado', category: 'Web 框架' },
  bottle: { name: 'Bottle', category: 'Web 框架' },
  aiohttp: { name: 'AIOHTTP', category: 'Web 框架' },
  // HTTP 客户端
  requests: { name: 'Requests', category: 'HTTP 客户端' },
  httpx: { name: 'HTTPX', category: 'HTTP 客户端' },
  urllib3: { name: 'urllib3', category: 'HTTP 客户端' },
  aiohttp_client: { name: 'AIOHTTP', category: 'HTTP 客户端' },
  // 数据科学
  pandas: { name: 'Pandas', category: '数据分析' },
  numpy: { name: 'NumPy', category: '数值计算' },
  scipy: { name: 'SciPy', category: '科学计算' },
  matplotlib: { name: 'Matplotlib', category: '数据可视化' },
  seaborn: { name: 'Seaborn', category: '数据可视化' },
  plotly: { name: 'Plotly', category: '数据可视化' },
  // 机器学习
  sklearn: { name: 'scikit-learn', category: '机器学习' },
  tensorflow: { name: 'TensorFlow', category: '机器学习' },
  torch: { name: 'PyTorch', category: '机器学习' },
  keras: { name: 'Keras', category: '机器学习' },
  transformers: { name: 'Transformers', category: '机器学习' },
  xgboost: { name: 'XGBoost', category: '机器学习' },
  // 数据库
  sqlalchemy: { name: 'SQLAlchemy', category: 'ORM/数据库' },
  pymysql: { name: 'PyMySQL', category: '数据库驱动' },
  psycopg2: { name: 'psycopg2', category: '数据库驱动' },
  sqlite3: { name: 'SQLite', category: '数据库驱动' },
  redis: { name: 'Redis', category: '缓存/NoSQL' },
  pymongo: { name: 'PyMongo', category: '数据库驱动' },
  neo4j: { name: 'Neo4j', category: '图数据库' },
  // 测试
  pytest: { name: 'pytest', category: '测试' },
  unittest: { name: 'unittest', category: '测试' },
  mock: { name: 'mock', category: '测试' },
  // 工具
  click: { name: 'Click', category: 'CLI 工具' },
  typer: { name: 'Typer', category: 'CLI 工具' },
  celery: { name: 'Celery', category: '任务队列' },
  // LangChain 生态
  langchain: { name: 'LangChain', category: 'LLM 框架' },
  langgraph: { name: 'LangGraph', category: 'LLM 框架' },
  openai: { name: 'OpenAI SDK', category: 'LLM 客户端' },
  anthropic: { name: 'Anthropic SDK', category: 'LLM 客户端' },
  // 日志/配置
  logging: { name: 'logging', category: '日志' },
  pydantic: { name: 'Pydantic', category: '数据校验' },
  pyyaml: { name: 'PyYAML', category: '配置' },
  yaml: { name: 'PyYAML', category: '配置' },
}

/**
 * 从实体的 external_calls 提取 top-level 模块名
 * @param {Array|string} calls - external_calls 数组或单元素
 * @returns {string[]} top-level 模块名列表
 */
function extractModules(calls) {
  if (!Array.isArray(calls)) calls = [calls]
  const mods = []
  for (const c of calls) {
    const name = typeof c === 'string' ? c : c?.name
    if (!name || typeof name !== 'string') continue
    const top = name.split('.')[0].trim()
    if (top) mods.push(top)
  }
  return mods
}

/**
 * 检测项目技术栈
 * @param {Array} entities - 项目图谱实体列表 (含 external_calls 字段)
 * @returns {Array<{name, category, count}>} 按引用次数降序
 */
export function detectTechStack(entities) {
  if (!Array.isArray(entities) || entities.length === 0) return []

  // 聚合 top-level 模块引用次数
  const counts = new Map() // module -> count
  for (const e of entities) {
    if (!e.external_calls) continue
    for (const mod of extractModules(e.external_calls)) {
      counts.set(mod, (counts.get(mod) || 0) + 1)
    }
  }

  // 映射到已知技术 + 去重合并 (多个 import 名可能映射到同一技术, 如 yaml/pyyaml)
  const techCounts = new Map() // techKey -> {name, category, count}
  for (const [mod, count] of counts) {
    const meta = TECH_MAP[mod]
    if (!meta) continue
    const key = meta.name
    const existing = techCounts.get(key)
    if (existing) {
      existing.count += count
    } else {
      techCounts.set(key, { name: meta.name, category: meta.category, count })
    }
  }

  return [...techCounts.values()].sort((a, b) => b.count - a.count)
}
