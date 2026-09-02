<template>
  <div ref="rootRef" class="markdown-viewer" v-html="renderedHtml" @click="onCodeCopyClick"></div>
</template>

<script setup>
/**
 * MarkdownViewer — 增强 Markdown 渲染组件
 *
 * - Monaco 代码语法高亮 (colorizeElement API, LSP 级)
 * - 代码块一键复制按钮
 * - DOMPurify XSS 消毒
 * - 支持亮/暗主题
 */
import { ref, computed, watch, nextTick } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import * as monaco from 'monaco-editor'
import { useThemeStore } from '@/stores/theme'

const props = defineProps({
  content: { type: String, default: '' },
})

const themeStore = useThemeStore()
const rootRef = ref(null)

// ---- 配置 marked ----
const renderer = new marked.Renderer()

// 覆写 code 渲染: 包装 .code-block 容器 + 语言标签 + 展开/收起按钮 + 复制按钮 + Monaco 标记
renderer.code = function ({ text, lang }) {
  const escaped = escapeHtml(text)
  const langAttr = lang ? ` data-lang="${lang}"` : ''
  const langLabel = (lang || '').toString().toLowerCase() || 'code'

  return `<div class="code-block">`
    + `<div class="code-block-head">`
    + `<span class="code-lang">${escapeHtml(langLabel)}</span>`
    + `<button class="code-expand-btn" type="button" title="展开/收起">`
    + `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>`
    + `<span class="code-expand-label">展开</span>`
    + `</button>`
    + `</div>`
    + `<button class="code-copy-btn" data-code="${escaped}" type="button" title="复制代码">`
    + `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`
    + `</button>`
    + `<pre><code class="monaco-code"${langAttr}>${escaped}</code></pre>`
    + `</div>`
}

// 覆写 codespan
renderer.codespan = function ({ text }) {
  return `<code>${escapeHtml(text)}</code>`
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// lang → Monaco mimeType 映射
const MIME_MAP = {
  py: 'text/x-python', python: 'text/x-python',
  js: 'text/javascript', javascript: 'text/javascript', jsx: 'text/javascript',
  ts: 'text/typescript', typescript: 'text/typescript', tsx: 'text/typescript',
  json: 'application/json', jsonc: 'application/json',
  html: 'text/html', htm: 'text/html', vue: 'text/html',
  css: 'text/css', scss: 'text/css', less: 'text/css',
  sql: 'text/x-sql',
  yaml: 'text/x-yaml', yml: 'text/x-yaml',
  xml: 'text/xml', svg: 'text/xml',
  md: 'text/markdown', markdown: 'text/markdown',
  sh: 'text/x-sh', bash: 'text/x-sh', shell: 'text/x-sh', zsh: 'text/x-sh',
  java: 'text/x-java',
  c: 'text/x-c', cpp: 'text/x-c++src', h: 'text/x-c',
  go: 'text/x-go',
  rs: 'text/x-rust', rust: 'text/x-rust',
  php: 'text/x-php',
  rb: 'text/x-ruby', ruby: 'text/x-ruby',
  txt: 'text/plain', plaintext: 'text/plain', text: 'text/plain',
}

function mimeFor(lang) {
  if (!lang) return 'text/plain'
  const key = lang.toLowerCase().trim()
  return MIME_MAP[key] || `text/x-${key}`
}

function monacoTheme() {
  return themeStore.mode === 'dark' ? 'vs-dark' : 'vs'
}

// ---- 渲染 ----
// v1.3.3 净化: 剥离泄漏到正文的机器标记 (提示词 v1.3.3 起已禁止产出, 此处兜底历史消息/旧资源):
//   [ref: PY-012.key_points[2]] 溯源标记 / [已心算验证] 验证标记 — 仅剥这两类精确模式,
//   不做标题 emoji 等宽泛清理 (本组件聊天与学习页共用, 防误伤用户内容)。
// 流式防跳变: 未闭合代码围栏在渲染时自动补闭合 (仅渲染层, 不改原始内容) —
// 流式输出跨围栏边界时排版不再整体塌一下。
function sanitizeMachineMarkers(md) {
  return String(md)
    .replace(/[ \t]*\[ref:[^\]]*\]/g, '')
    .replace(/[ \t]*\[已心算验证\]/g, '')
}

function closeUnclosedFence(md) {
  const fences = md.match(/^ {0,3}(```|~~~)/gm) || []
  return fences.length % 2 === 1 ? `${md}\n\`\`\`` : md
}

const renderedHtml = computed(() => {
  if (!props.content) return ''
  const cleaned = closeUnclosedFence(sanitizeMachineMarkers(props.content))
  const raw = marked.parse(cleaned, { breaks: true, gfm: true, renderer })
  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ['data-code', 'data-lang'],
  })
})

// ---- Monaco colorize (DOM 更新后) ----
let colorizeQueue = null

async function colorizeCodeBlocks() {
  if (!rootRef.value) return

  const nodes = rootRef.value.querySelectorAll('.monaco-code')
  if (nodes.length === 0) return

  const theme = monacoTheme()
  // 取消上一批 (如果用户快速切换)
  const batchId = Symbol()
  colorizeQueue = batchId

  const jobs = []
  for (const node of nodes) {
    if (node.dataset.colorized === theme) continue // 已是目标主题，跳过
    const lang = node.dataset.lang || ''
    const mimeType = mimeFor(lang)
    const el = /** @type {HTMLElement} */ (node)
    jobs.push(
      monaco.editor.colorizeElement(el, { theme, mimeType }).then(() => {
        el.dataset.colorized = theme
      })
    )
  }

  await Promise.allSettled(jobs)
  if (colorizeQueue !== batchId) return // 有更新的批次
}

// ---- 代码块展开/收起 (v-html 整段渲染, DOM 挂载后 querySelector 绑 click) ----
// 每次 content 变更 v-html 会重建 DOM (旧监听随之销毁), 故在渲染后重绑;
// 用 dataset.expandBound 防同一节点重复绑。展开时给 <pre> 加 .expanded,
// 由 AssistantPanel 的 :deep(pre.expanded) 规则放开 max-height。
function bindCodeExpandButtons() {
  if (!rootRef.value) return
  const blocks = rootRef.value.querySelectorAll('.code-block')
  for (const block of blocks) {
    const btn = block.querySelector('.code-expand-btn')
    const pre = block.querySelector('pre')
    if (!btn || !pre || btn.dataset.expandBound) continue
    btn.dataset.expandBound = '1'
    btn.addEventListener('click', () => {
      const expanded = pre.classList.toggle('expanded')
      const label = btn.querySelector('.code-expand-label')
      if (label) label.textContent = expanded ? '收起' : '展开'
      btn.classList.toggle('expanded', expanded)
    })
  }
}

// 监听 content 变化 → 等 DOM 更新后高亮
// v1.3.3 流式防卡: colorize 防抖 250ms — 流式期间每增量全量 colorize 所有代码块
// (Monaco colorizeElement 较重, 长回答多代码块时明显卡), 合并为一帧收尾; 展开按钮绑定不延迟。
let _colorizeTimer = null
watch(() => props.content, async () => {
  await nextTick()
  // 额外延迟一帧，确保 v-html 的 DOM 已被挂载
  requestAnimationFrame(() => {
    bindCodeExpandButtons()
    if (_colorizeTimer) clearTimeout(_colorizeTimer)
    _colorizeTimer = setTimeout(() => {
      _colorizeTimer = null
      colorizeCodeBlocks()
    }, 250)
  })
}, { immediate: true })

// 主题切换 → 重绘已有代码块
watch(() => themeStore.mode, async () => {
  await nextTick()
  // 清除已缓存的 colorized 标记，强制重新上色
  if (rootRef.value) {
    for (const node of rootRef.value.querySelectorAll('.monaco-code')) {
      delete node.dataset.colorized
    }
  }
  colorizeCodeBlocks()
})

// ---- 代码复制 ----
function onCodeCopyClick(e) {
  const btn = e.target.closest('.code-copy-btn')
  if (!btn) return

  const code = btn.getAttribute('data-code')
  if (!code) return

  navigator.clipboard.writeText(code).then(() => {
    btn.classList.add('copied')
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`
    setTimeout(() => {
      btn.classList.remove('copied')
      btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`
    }, 2000)
  }).catch(() => { /* 静默失败 */ })
}
</script>

<style scoped>
.markdown-viewer {
  font-size: 14px;
  line-height: 1.8;
  color: var(--km-gray-700);
}

/* ---- 标题 ---- */
.markdown-viewer :deep(h1) {
  font-size: 20px; margin: 0 0 12px; padding-bottom: 8px;
  border-bottom: 1px solid var(--km-border);
}
.markdown-viewer :deep(h2) { font-size: 17px; margin: 16px 0 8px; }
.markdown-viewer :deep(h3) { font-size: 15px; margin: 14px 0 6px; }

/* ---- 段落 / 列表 ---- */
.markdown-viewer :deep(p) { margin: 0 0 8px; }
.markdown-viewer :deep(ul),
.markdown-viewer :deep(ol) { margin: 0 0 8px; padding-left: 20px; }
.markdown-viewer :deep(li) { margin-bottom: 4px; }

/* ---- 行内代码 ---- */
.markdown-viewer :deep(code) {
  background: var(--km-gray-200);
  padding: 2px 6px; border-radius: 4px;
  font-family: var(--km-font-mono);
  font-size: 13px;
  color: var(--km-primary-active);
}

/* ---- 代码块容器 ---- */
.markdown-viewer :deep(.code-block) {
  position: relative; margin: 0 0 10px;
}
.markdown-viewer :deep(.code-block pre) {
  background: var(--km-bg-layer-2);
  border-radius: var(--km-radius-sm);
  padding: 12px 16px; overflow-x: auto; margin: 0;
}
.markdown-viewer :deep(.code-block pre code) {
  background: none; padding: 0;
  color: var(--km-gray-700); font-size: 13px;
}
.markdown-viewer :deep(.code-block pre code span) {
  font-family: inherit; font-size: inherit;
}

/* ---- 代码块头部 (语言标签 + 展开/收起) ---- */
.markdown-viewer :deep(.code-block-head) {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; padding: 3px 40px 3px 10px;
  background: var(--km-gray-200);
  border-radius: var(--km-radius-sm) var(--km-radius-sm) 0 0;
}
.markdown-viewer :deep(.code-lang) {
  font-family: var(--km-font-mono); font-size: 11px;
  color: var(--km-gray-500); text-transform: lowercase;
}
.markdown-viewer :deep(.code-expand-btn) {
  display: inline-flex; align-items: center; gap: 3px;
  border: none; background: transparent; cursor: pointer;
  color: var(--km-gray-500); font-size: 11px; padding: 2px 4px;
  border-radius: 4px;
}
.markdown-viewer :deep(.code-expand-btn:hover) {
  background: var(--km-gray-300); color: var(--km-gray-700);
}
.markdown-viewer :deep(.code-expand-btn svg) { transition: transform 0.15s var(--km-ease); }
.markdown-viewer :deep(.code-expand-btn.expanded svg) { transform: rotate(180deg); }

/* ---- 复制按钮 ---- */
.markdown-viewer :deep(.code-copy-btn) {
  position: absolute; top: 6px; right: 6px; z-index: 1;
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  background: var(--km-gray-200);
  border: none; border-radius: 6px;
  cursor: pointer; color: var(--km-gray-500);
  opacity: 0;
  transition: all 0.15s var(--km-ease);
}
.markdown-viewer :deep(.code-block:hover .code-copy-btn) { opacity: 1; }
.markdown-viewer :deep(.code-copy-btn:hover) {
  background: var(--km-gray-300);
  color: var(--km-gray-700);
}
.markdown-viewer :deep(.code-copy-btn.copied) { color: var(--km-success); }

/* ---- 表格 ---- */
.markdown-viewer :deep(table) {
  border-collapse: collapse; width: 100%;
  margin: 0 0 10px; font-size: 13px;
}
.markdown-viewer :deep(th),
.markdown-viewer :deep(td) {
  border: 1px solid var(--km-border); padding: 6px 10px; text-align: left;
}
.markdown-viewer :deep(th) { background: var(--km-gray-200); font-weight: 600; }

/* ---- 引用 ---- */
.markdown-viewer :deep(blockquote) {
  border-left: 3px solid var(--km-primary);
  margin: 0 0 8px; padding: 6px 14px;
  background: var(--km-primary-soft);
  color: var(--km-gray-600);
  border-radius: 0 var(--km-radius-sm) var(--km-radius-sm) 0;
}

/* ---- 分割线 / 图片 / 强调 ---- */
.markdown-viewer :deep(hr) {
  border: none; border-top: 1px solid var(--km-border); margin: 12px 0;
}
.markdown-viewer :deep(img) { max-width: 100%; border-radius: 4px; }
.markdown-viewer :deep(strong) { font-weight: 600; }
</style>
