/**
 * 模型能力静态表 — 按 provider × modelPattern 匹配。
 * 字段:
 *   reasoning: 'native' = 支持原生 thinking/reasoning_effort 参数
 *              'prompt-only' = 仅靠提示词代偿
 *   context: 上下文窗口 token 数; null = 未知
 *
 * vision 不在此表 — 走运行时探测 (modelVision store)。
 */
const CAPABILITY_TABLE = [
  // OpenAI
  { provider: 'openai', modelPattern: /^o(1|3)/,       reasoning: 'native',      context: 128_000 },
  { provider: 'openai', modelPattern: /^gpt-4\.1/,     reasoning: 'prompt-only', context: 1_000_000 },
  { provider: 'openai', modelPattern: /^gpt-4o/,       reasoning: 'prompt-only', context: 128_000 },

  // DeepSeek
  { provider: 'deepseek', modelPattern: /^deepseek-v4/,       reasoning: 'native', context: 128_000 },
  { provider: 'deepseek', modelPattern: /^deepseek-reasoner/, reasoning: 'native', context:  64_000 },

  // Anthropic
  { provider: 'anthropic', modelPattern: /^claude-(opus|sonnet|haiku|fable|mythos)-(4|5)/,
    reasoning: 'native', context: 200_000 },

  // Qwen
  { provider: 'qwen', modelPattern: /^qwen-/, reasoning: 'prompt-only', context: 128_000 },

  // Gemini
  { provider: 'gemini', modelPattern: /^gemini-2\.5/, reasoning: 'native', context: 1_000_000 },
]

const DEFAULT_CAP = Object.freeze({ reasoning: 'prompt-only', context: null })

export function capabilityOf(provider, model) {
  const p = (provider || '').toLowerCase()
  // custom:<uuid> 走兜底
  const pid = p.startsWith('custom') ? 'custom' : p
  const m = model || ''
  for (const row of CAPABILITY_TABLE) {
    if (row.provider !== pid) continue
    if (row.modelPattern.test(m)) {
      return { reasoning: row.reasoning, context: row.context }
    }
  }
  return { ...DEFAULT_CAP }
}

export function formatContext(n) {
  if (!n) return ''
  if (n >= 1_000_000) return `${Math.round(n / 1_000_000)}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`
  return String(n)
}
