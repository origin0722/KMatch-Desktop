// Vite: 动态 import.meta.glob 把目录扫成 url 映射
const ICONS = import.meta.glob('@/assets/icons/llm_providers/*.svg', { eager: true, query: '?url', import: 'default' })

const MAP = Object.fromEntries(
  Object.entries(ICONS).map(([path, url]) => {
    const key = path.split('/').pop().replace('.svg', '') // 'claude' 等
    return [key, url]
  }),
)

export function iconUrlOf(iconKey) {
  return MAP[iconKey] || MAP.custom
}
