<template>
  <div class="monaco-wrap">
    <div ref="containerRef" class="monaco-container"></div>
    <div v-if="!ws.activeFile" class="monaco-empty">
      <el-icon :size="48" color="var(--ktext-muted)"><DocumentCopy /></el-icon>
      <p class="empty-title">KMatch·知链 工作区</p>
      <p class="empty-hint">从左侧资源管理器打开文件, 或点击活动栏 📁 打开项目</p>
      <p class="empty-hint dim">阶段1: 文件浏览 + Monaco 编辑 (Ctrl+S 保存) · 阶段2 起: AI 助手 + 图谱委派</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import { useWorkspaceStore } from '@/stores/workspace'
import { useThemeStore } from '@/stores/theme'

// Monaco worker (阶段1 仅 editor 通用 worker; ts/js 智能提示阶段4 按需加)
self.MonacoEnvironment = { getWorker: () => new editorWorker() }

const ws = useWorkspaceStore()
const theme = useThemeStore()

const containerRef = ref(null)
let editor = null
const models = new Map() // relPath -> ITextModel

const LANG_BY_EXT = {
  '.py': 'python', '.js': 'javascript', '.ts': 'typescript', '.jsx': 'javascript',
  '.vue': 'html', '.json': 'json', '.md': 'markdown', '.html': 'html',
  '.css': 'css', '.yml': 'yaml', '.yaml': 'yaml', '.txt': 'plaintext', '.sql': 'sql',
}

function langFor(path) {
  const ext = path.slice(path.lastIndexOf('.'))
  return LANG_BY_EXT[ext] || 'plaintext'
}

async function getOrCreateModel(relPath) {
  if (models.has(relPath)) return models.get(relPath)
  const content = await window.api.fs.readFile(relPath)
  const model = monaco.editor.createModel(content, langFor(relPath), monaco.Uri.parse('file:///' + relPath.replace(/\\/g, '/')))
  model.onDidChangeContent(() => ws.markDirty(relPath, true))
  models.set(relPath, model)
  return model
}

function applyTheme() {
  monaco.editor.setTheme(theme.mode === 'dark' ? 'vs-dark' : 'vs')
}

onMounted(async () => {
  await nextTick()
  editor = monaco.editor.create(containerRef.value, {
    automaticLayout: true,
    fontSize: 14,
    fontFamily: 'var(--kfont-mono)',
    minimap: { enabled: true },
    scrollBeyondLastLine: false,
    tabSize: 4,
    theme: theme.mode === 'dark' ? 'vs-dark' : 'vs',
  })
  applyTheme()

  // Ctrl+S 保存当前文件
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, async () => {
    if (!ws.activeFile) return
    const model = models.get(ws.activeFile)
    if (model) {
      await ws.saveFile(ws.activeFile, model.getValue())
    }
  })

  if (ws.activeFile) await switchTo(ws.activeFile)
})

watch(() => ws.activeFile, async (p) => {
  if (!editor) return
  if (!p) { editor.setModel(null); return }
  await switchTo(p)
})

async function switchTo(relPath) {
  const model = await getOrCreateModel(relPath)
  editor.setModel(model)
}

watch(() => theme.mode, applyTheme)

onBeforeUnmount(() => {
  models.forEach((m) => m.dispose())
  models.clear()
  editor?.dispose()
})
</script>

<style scoped>
.monaco-wrap { flex: 1; position: relative; min-width: 0; height: 100%; background: var(--kbg); }
.monaco-container { position: absolute; inset: 0; }
.monaco-empty {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 10px; color: var(--ktext-secondary); pointer-events: none;
}
.empty-title { font-size: 20px; font-weight: 600; color: var(--ktext); margin-top: 8px; }
.empty-hint { font-size: 13px; }
.empty-hint.dim { font-size: 11px; color: var(--ktext-muted); }
</style>
