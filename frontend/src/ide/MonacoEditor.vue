<template>
  <div class="monaco-wrap">
    <div ref="containerRef" class="monaco-container"></div>
    <div v-if="!ws.activeFile" class="monaco-empty">
      <el-icon :size="48" color="var(--ktext-muted)"><DocumentCopy /></el-icon>
      <p class="empty-title">KMatch·知链 工作区</p>
      <p class="empty-hint">从左侧资源管理器打开文件, 或点击活动栏 📁 打开项目</p>
      <p class="empty-hint dim">阶段1: 文件浏览 + Monaco 编辑 (Ctrl+S 保存) · 阶段2 起: AI 助手 + 图谱委派</p>
    </div>
    <!-- 阶段8: 外部改动冲突确认 (已打开且脏的文件被外部修改) -->
    <div v-if="conflictPath" class="conflict-banner">
      <span class="conflict-text">
        <el-icon><WarningFilled /></el-icon>
        {{ conflictPath }} 已被外部修改
      </span>
      <div class="conflict-actions">
        <el-button size="small" @click="keepLocal">保留我的编辑</el-button>
        <el-button size="small" type="primary" @click="loadDisk">加载磁盘版本</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import { WarningFilled, DocumentCopy } from '@element-plus/icons-vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useThemeStore } from '@/stores/theme'
import { useProjectGraphStore } from '@/stores/projectGraph'

// Monaco worker (阶段1 仅 editor 通用 worker; ts/js 智能提示阶段4 按需加)
self.MonacoEnvironment = { getWorker: () => new editorWorker() }

const ws = useWorkspaceStore()
const theme = useThemeStore()
const projectGraph = useProjectGraphStore()

const containerRef = ref(null)
let editor = null
const models = new Map() // relPath -> ITextModel
let decorations = []     // 符号高亮装饰 (阶段4b)

// 阶段8: 外部改动冲突 — 已打开且脏的文件被外部修改时, 弹 banner 让用户选保留/加载
const conflictPath = ref(null)

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

  // 阶段4b: 光标移动 → 回传 activeLine (供 chat 实体列表反查高亮)
  editor.onDidChangeCursorPosition((e) => {
    if (projectGraph.graph && projectGraph.graph.sourcePath === ws.activeFile) {
      projectGraph.setActiveLine(e.position.lineNumber)
    }
  })

  if (ws.activeFile) await switchTo(ws.activeFile)
})

// 阶段4b: chat 实体点击 → 跳转 + 高亮符号区间
async function revealSymbol(target) {
  if (!editor || !target) return
  try {
    // 若目标文件非当前激活, 先打开并切 model (主动切, 不依赖 watcher 时序)
    if (target.path !== ws.activeFile) {
      await ws.openFile(target.path)
      const model = await getOrCreateModel(target.path)
      editor.setModel(model)
    }
    editor.revealLineInCenter(target.lineStart)
    editor.setPosition({ lineNumber: target.lineStart, column: 1 })
    editor.focus()
    // 高亮 [lineStart, lineEnd] 行区间
    decorations = editor.deltaDecorations(decorations, [{
      range: new monaco.Range(target.lineStart, 1, target.lineEnd, 1),
      options: {
        isWholeLine: true,
        className: 'symbol-highlight',
        overviewRuler: { color: '#1890ff', position: monaco.editor.OverviewRulerLane.Center },
      },
    }])
  } catch (e) { /* reveal 失败忽略 */ }
  projectGraph.consumeReveal()
}

watch(() => projectGraph.revealTarget, (t) => {
  if (t) revealSymbol(t)
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

// F9: 项目切换 (root 变) 时清空 model 缓存。models 按 relPath 缓存, 但 relPath 相对项目根;
// 新项目若含同 relPath 文件, 会复用旧 model (旧项目内容) 直到外部改动失效。切项目即全失效。
watch(() => ws.root, () => {
  if (!editor) return
  models.forEach((m) => { try { m.dispose() } catch { /* ignore */ } })
  models.clear()
  conflictPath.value = null
  if (!ws.activeFile) editor.setModel(null)
})

// ---- 阶段8: 外部文件变动响应 ----
// watch externalChanges: 对已打开的非脏文件失效 model (下次 getOrCreateModel 重读磁盘);
//                       对脏文件设 conflictPath 弹 banner。
watch(() => ws.externalChanges, (changes) => {
  if (!changes || changes.size === 0) return
  for (const [relPath, info] of changes) {
    if (!models.has(relPath)) continue // 未打开的文件不关心 (refreshTree 已刷树)
    if (info.kind === 'unlink') {
      // 文件被删除: 失效 model (不论脏否, 文件没了)
      disposeModel(relPath)
      ws.clearExternalChange(relPath)
      continue
    }
    if (ws.dirtyFiles.has(relPath)) {
      // 脏文件被外部改: 弹冲突 (不自动覆盖用户编辑)
      if (!conflictPath.value) conflictPath.value = relPath
    } else {
      // 非脏文件: 失效 model, 若当前激活则立即重读
      disposeModel(relPath)
      if (ws.activeFile === relPath) {
        switchTo(relPath).catch(() => { /* ignore */ })
      }
      ws.clearExternalChange(relPath)
    }
  }
}, { deep: true })

/** dispose 单个 model 并从缓存移除 (下次 getOrCreateModel 重读磁盘) */
function disposeModel(relPath) {
  const m = models.get(relPath)
  if (m) {
    try { m.dispose() } catch { /* ignore */ }
    models.delete(relPath)
  }
}

/** 冲突: 用户选保留编辑 — 清标记, 不动 model */
function keepLocal() {
  if (conflictPath.value) ws.clearExternalChange(conflictPath.value)
  conflictPath.value = null
}

/** 冲突: 用户选加载磁盘 — 失效 model 重读 */
async function loadDisk() {
  const p = conflictPath.value
  if (!p) return
  disposeModel(p)
  ws.clearExternalChange(p)
  conflictPath.value = null
  if (ws.activeFile === p) {
    await switchTo(p)
  }
}

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

/* 阶段8: 外部改动冲突 banner */
.conflict-banner {
  position: absolute; top: 8px; left: 50%; transform: translateX(-50%);
  z-index: 10;
  display: flex; align-items: center; gap: 12px;
  padding: 8px 14px;
  background: var(--km-warning-light);
  border: 1px solid var(--km-warning);
  border-radius: var(--km-radius-sm);
  box-shadow: var(--km-shadow-md);
  font-size: 13px; color: var(--km-gray-800);
}
.conflict-text { display: flex; align-items: center; gap: 6px; font-weight: 600; }
.conflict-actions { display: flex; gap: 6px; }
</style>

<!-- 阶段4b: 符号高亮装饰 (全局, Monaco decoration className 不受 scoped 控制) -->
<style>
.monaco-editor .symbol-highlight {
  background: rgba(24, 144, 255, 0.18);
  border-left: 2px solid #1890ff;
}
</style>
