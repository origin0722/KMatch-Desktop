/**
 * fileKind — 文件类型判定 (文件内联预览分发, 纯函数)
 *
 * text   → Monaco 编辑 (代码/文本)
 * image  → <img> base64 预览
 * markdown → marked+DOMPurify 安全渲染
 * html   → 沙箱 iframe srcdoc
 * pdf    → base64 data-url iframe
 */
const IMAGE_EXTS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico']
const PREVIEW_KINDS = ['image', 'markdown', 'html', 'pdf']
const PREVIEW_EXTS = new Set([
  ...IMAGE_EXTS,
  'md', 'markdown',
  'html', 'htm',
  'pdf',
])

export function fileKind(relPath) {
  const name = String(relPath || '')
  const dot = name.lastIndexOf('.')
  const ext = dot >= 0 ? name.slice(dot + 1).toLowerCase() : ''
  if (IMAGE_EXTS.includes(ext)) return 'image'
  if (ext === 'md' || ext === 'markdown') return 'markdown'
  if (ext === 'html' || ext === 'htm') return 'html'
  if (ext === 'pdf') return 'pdf'
  return 'text'
}

export function isPreviewKind(kind) {
  return PREVIEW_KINDS.includes(kind)
}

export function isPreviewFile(relPath) {
  const name = String(relPath || '').toLowerCase()
  const dot = name.lastIndexOf('.')
  const ext = dot >= 0 ? name.slice(dot + 1) : ''
  return PREVIEW_EXTS.has(ext)
}
