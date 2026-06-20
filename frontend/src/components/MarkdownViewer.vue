<template>
  <div class="markdown-viewer" v-html="renderedHtml"></div>
</template>

<script setup>
/**
 * MarkdownViewer — 基于 marked 的轻量 Markdown 渲染组件
 *
 * 接收 content prop（markdown 字符串），输出 styled HTML。
 * 第4周用于 Learning 页三类资源正文渲染。
 */
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps({
  content: { type: String, default: '' },
})

// per-call options (marked v5+ 推荐, BUG-053) + DOMPurify XSS 消毒 (BUG-046)
const renderedHtml = computed(() => {
  if (!props.content) return ''
  return DOMPurify.sanitize(marked.parse(props.content, { breaks: true, gfm: true }))
})
</script>

<style scoped>
.markdown-viewer {
  font-size: 14px;
  line-height: 1.8;
  color: #303133;
}

/* ---- 标题 ---- */
.markdown-viewer :deep(h1) {
  font-size: 20px;
  margin: 0 0 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e4e7ed;
}
.markdown-viewer :deep(h2) {
  font-size: 17px;
  margin: 16px 0 8px;
}
.markdown-viewer :deep(h3) {
  font-size: 15px;
  margin: 14px 0 6px;
}

/* ---- 段落 ---- */
.markdown-viewer :deep(p) {
  margin: 0 0 8px;
}

/* ---- 列表 ---- */
.markdown-viewer :deep(ul),
.markdown-viewer :deep(ol) {
  margin: 0 0 8px;
  padding-left: 20px;
}
.markdown-viewer :deep(li) {
  margin-bottom: 4px;
}

/* ---- 行内代码 ---- */
.markdown-viewer :deep(code) {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  color: #e6a23c;
}

/* ---- 代码块 ---- */
.markdown-viewer :deep(pre) {
  background: #f5f7fa;
  border-radius: 6px;
  padding: 12px 16px;
  overflow-x: auto;
  margin: 0 0 10px;
}
.markdown-viewer :deep(pre code) {
  background: none;
  padding: 0;
  color: #303133;
}

/* ---- 表格 ---- */
.markdown-viewer :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0 0 10px;
  font-size: 13px;
}
.markdown-viewer :deep(th),
.markdown-viewer :deep(td) {
  border: 1px solid #e4e7ed;
  padding: 6px 10px;
  text-align: left;
}
.markdown-viewer :deep(th) {
  background: #f5f7fa;
  font-weight: 600;
}

/* ---- 引用 ---- */
.markdown-viewer :deep(blockquote) {
  border-left: 3px solid #409eff;
  margin: 0 0 8px;
  padding: 6px 12px;
  background: #ecf5ff;
  color: #606266;
}

/* ---- 分割线 ---- */
.markdown-viewer :deep(hr) {
  border: none;
  border-top: 1px solid #e4e7ed;
  margin: 12px 0;
}

/* ---- 图片 ---- */
.markdown-viewer :deep(img) {
  max-width: 100%;
  border-radius: 4px;
}

/* ---- 强调 ---- */
.markdown-viewer :deep(strong) {
  font-weight: 600;
}
</style>
