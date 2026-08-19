<template>
  <div class="file-preview">
    <div class="pv-head">
      <span class="pv-name">{{ basename }}</span>
      <span class="pv-kind">{{ kindLabel }}</span>
    </div>
    <div class="pv-body">
      <div v-if="loading" class="pv-loading">正在加载预览…</div>
      <div v-else-if="error" class="pv-error">无法预览该文件：{{ error }}</div>
      <template v-else>
        <img v-if="kind === 'image'" class="pv-image" :src="imageSrc" alt="" />
        <div v-else-if="kind === 'markdown'" ref="mdBox" class="pv-markdown" v-html="markdownHtml"></div>
        <iframe v-else-if="kind === 'html'" class="pv-frame" sandbox="allow-same-origin" :srcdoc="text"></iframe>
        <iframe v-else-if="kind === 'pdf'" class="pv-frame" :src="pdfSrc"></iframe>
      </template>
    </div>
  </div>
</template>

<script setup>
/**
 * FilePreview — 文件内联预览 (用户体验优先):
 * 图片 base64 / Markdown(marked+DOMPurify 安全) / HTML(sandbox iframe) / PDF(base64 data-url)。
 * 二进制走 window.api.fs.readBase64 (electron 新增 IPC), 文本走 readFile。
 */
import { ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps({
  relPath: { type: String, required: true },
  kind: { type: String, default: 'text' },
})

const MIME = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp', svg: 'image/svg+xml', bmp: 'image/bmp', ico: 'image/x-icon' }

const loading = ref(false)
const error = ref('')
const text = ref('')
const base64 = ref('')
const imageSrc = ref('')
const pdfSrc = ref('')
const markdownHtml = ref('')
const mdBox = ref(null)

function basename() {
  const parts = props.relPath.replace(/\\/g, '/').split('/')
  return parts[parts.length - 1] || props.relPath
}
const kindLabel = { image: '图片预览', markdown: 'Markdown 预览', html: 'HTML 预览', pdf: 'PDF 预览' }[props.kind] || '预览'

const _esc = (s) => String(s || '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))

// Mermaid 代码块 → 占位 div, 渲染完成后再替换为 SVG (惰性 import, 失败降级为代码块)
function renderMermaidBlock(text) {
  return `<div class="mmd-block" data-mmd="${encodeURIComponent(text)}"></div>`
}

const _markdownRenderer = new marked.Renderer()
_markdownRenderer.code = (token) => {
  if (token && token.lang === 'mermaid') return renderMermaidBlock(token.text)
  const cls = token?.lang ? ` class="lang-${token.lang}"` : ''
  return `<pre><code${cls}>${_esc(token?.text || '')}</code></pre>`
}

/** 渲染 .mmd-block (动态 import mermaid; 任一环节失败 → 显示源码+提示, 不崩) */
async function renderMermaidBlocks(root) {
  const blocks = root?.querySelectorAll?.('.mmd-block') || []
  if (!blocks.length) return
  let mermaid = null
  try {
    mermaid = (await import('mermaid')).default
    if (mermaid?.initialize) mermaid.initialize({ startOnLoad: false })
  } catch { /* 未安装/加载失败 → 走降级 */ }
  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i]
    const src = decodeURIComponent(block.getAttribute('data-mmd') || '')
    if (!mermaid) {
      block.outerHTML = `<pre class="mmd-fallback">${_esc(src)}</pre><div class="pv-note">⚠️ Mermaid 渲染器未加载</div>`
      continue
    }
    try {
      const id = `mmd-${Math.random().toString(36).slice(2, 8)}`
      const { svg } = await mermaid.render(id, src)
      block.innerHTML = svg
    } catch (e) {
      block.outerHTML = `<pre class="mmd-fallback">${_esc(src)}</pre><div class="pv-note">⚠️ Mermaid 渲染失败: ${_esc(String(e?.message || e))}</div>`
    }
  }
}

async function load() {
  loading.value = true
  error.value = ''
  text.value = ''
  base64.value = ''
  imageSrc.value = ''
  pdfSrc.value = ''
  markdownHtml.value = ''
  try {
    if (props.kind === 'image' || props.kind === 'pdf') {
      const b64 = await window.api.fs.readBase64(props.relPath)
      base64.value = b64
      if (props.kind === 'image') {
        const ext = props.relPath.split('.').pop().toLowerCase()
        imageSrc.value = `data:${MIME[ext] || 'image/png'};base64,${b64}`
      } else {
        pdfSrc.value = `data:application/pdf;base64,${b64}`
      }
    } else {
      const content = await window.api.fs.readFile(props.relPath)
      text.value = content
      if (props.kind === 'markdown') {
        const html = String(marked.parse(content, { renderer: _markdownRenderer }) || '')
        markdownHtml.value = DOMPurify.sanitize(html, {
          FORBID_TAGS: ['iframe', 'object', 'embed', 'form', 'input', 'style'],
        })
      }
    }
  } catch (e) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
  // 内容渲染完成 (loading=false, mdBox 已挂载) 后再处理 mermaid 占位 → svg (失败降级源码块)
  if (props.kind === 'markdown' && !error.value) {
    await nextTick()
    await renderMermaidBlocks(mdBox.value)
  }
}

watch(() => [props.relPath, props.kind], load, { immediate: true })
onBeforeUnmount(() => { /* 仅清理; base64 字符串由 GC 回收 */ })
</script>

<style scoped>
.file-preview {
  height: 100%; display: flex; flex-direction: column; background: var(--kbg, #fff);
}
.pv-head {
  display: flex; align-items: center; gap: 8px; padding: 6px 12px;
  border-bottom: 1px solid var(--km-border-light); flex-shrink: 0;
  font-size: 12px; color: var(--km-gray-600);
}
.pv-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pv-kind { margin-left: auto; font-size: 11px; color: var(--km-gray-400); }
.pv-body { flex: 1; overflow: auto; padding: 12px; }
.pv-loading, .pv-error { color: var(--km-gray-500); font-size: 13px; }
.pv-image { max-width: 100%; max-height: 100%; object-fit: contain; display: block; }
.pv-frame { width: 100%; height: 100%; border: none; }
.pv-markdown { line-height: 1.7; color: var(--km-gray-800); font-size: 14px; }
.pv-markdown :deep(h1), .pv-markdown :deep(h2), .pv-markdown :deep(h3) { margin: 0.6em 0 0.3em; }
.pv-markdown :deep(code) { background: var(--km-gray-200); padding: 1px 4px; border-radius: 3px; font-family: var(--kfont-mono, monospace); }
.pv-markdown :deep(pre) { background: var(--km-gray-100); padding: 8px; border-radius: 6px; overflow: auto; }
.pv-markdown :deep(img) { max-width: 100%; }
.pv-markdown :deep(svg) { max-width: 100%; height: auto; } /* mermaid 图表 */
.pv-markdown :deep(table) { border-collapse: collapse; }
.pv-markdown :deep(td), .pv-markdown :deep(th) { border: 1px solid var(--km-border-light); padding: 4px 8px; }
.mmd-fallback { background: var(--km-gray-100); padding: 8px; border-radius: 6px; overflow: auto; white-space: pre; font-family: var(--kfont-mono, monospace); font-size: 12px; }
.pv-note { font-size: 12px; color: var(--km-gray-500); margin: 4px 0; }
</style>
