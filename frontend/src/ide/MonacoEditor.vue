<template>
  <div class="monaco-wrap">
    <!-- 文件内联预览 (图片/Markdown/HTML/PDF) → 不再进 Monaco 看乱码 -->
    <FilePreview v-if="showPreview && ws.activeFile" :rel-path="ws.activeFile" :kind="currentKind" />
    <!-- issue-79: 二进制/容器格式 → 友好提示, 不再按文本读乱码 -->
    <div v-else-if="binaryPath && binaryPath === ws.activeFile" class="binary-note">
      <el-icon :size="40"><WarningFilled /></el-icon>
      <p class="bn-title">该文件为二进制/压缩格式，暂不支持在 IDE 内预览</p>
      <p class="bn-hint">请在系统默认应用中打开；文本类文件可直接在编辑器查看（更多格式见文件类型支持）。</p>
    </div>
    <template v-else>
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
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import { WarningFilled, DocumentCopy } from '@element-plus/icons-vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useThemeStore } from '@/stores/theme'
import { useProjectGraphStore } from '@/stores/projectGraph'
import FilePreview from './FilePreview.vue'
import { fileKind, isPreviewKind, isPreviewFile } from '@/utils/fileKind'

// Monaco worker (阶段1 仅 editor 通用 worker; ts/js 智能提示阶段4 按需加)
self.MonacoEnvironment = { getWorker: () => new editorWorker() }

const ws = useWorkspaceStore()
const theme = useThemeStore()
const projectGraph = useProjectGraphStore()

// 文件内联预览: 图片/Markdown/HTML/PDF → 预览视图, 其余进 Monaco
const currentKind = computed(() => (ws.activeFile ? fileKind(ws.activeFile) : 'text'))
const showPreview = computed(() => isPreviewKind(currentKind.value))

const containerRef = ref(null)
let editor = null
const models = new Map() // relPath -> ITextModel
let decorations = []     // 符号高亮装饰 (阶段4b)
const binaryPath = ref(null) // issue-79: 当前二进制文件 (显示提示不建 model)

// 阶段8: 外部改动冲突 — 已打开且脏的文件被外部修改时, 弹 banner 让用户选保留/加载
const conflictPath = ref(null)

// issue-79: 扩展常见文本/配置/语言; 其余回退 plaintext
const LANG_BY_EXT = {
  '.py': 'python', '.js': 'javascript', '.ts': 'typescript', '.jsx': 'javascript',
  '.vue': 'html', '.json': 'json', '.md': 'markdown', '.html': 'html', '.htm': 'html',
  '.css': 'css', '.yml': 'yaml', '.yaml': 'yaml', '.txt': 'plaintext', '.sql': 'sql',
  '.log': 'plaintext', '.ini': 'plaintext', '.cfg': 'plaintext', '.conf': 'plaintext',
  '.toml': 'plaintext', '.env': 'plaintext', '.csv': 'plaintext', '.tsv': 'plaintext',
  '.xml': 'xml', '.sh': 'shell', '.bash': 'shell', '.zsh': 'shell', '.bat': 'bat', '.cmd': 'bat',
  '.ps1': 'powershell',
  '.rs': 'rust', '.go': 'go', '.java': 'java', '.c': 'c', '.h': 'cpp',
  '.cpp': 'cpp', '.cc': 'cpp', '.hpp': 'cpp', '.cs': 'csharp',
  '.rb': 'ruby', '.php': 'php', '.swift': 'swift', '.kt': 'kotlin', '.kts': 'kotlin',
  '.dockerfile': 'plaintext',
}
// issue-79: 明确不支持的二进制/容器格式 (不按文本读, 避免乱码)
const BINARY_EXTS = new Set([
  'zip', 'jar', 'class', 'pyd', 'dll', 'exe', 'so', 'dylib', 'bin', 'dat',
  'docx', 'xlsx', 'pptx', 'doc', 'xls', 'ppt', '7z', 'gz', 'tar', 'rar',
])

function langFor(path) {
  const ext = path.slice(path.lastIndexOf('.'))
  return LANG_BY_EXT[ext] || 'plaintext'
}

async function getOrCreateModel(relPath, content = null) {
  if (models.has(relPath)) return models.get(relPath)
  const text = content ?? await window.api.fs.readFile(relPath)
  const model = monaco.editor.createModel(text, langFor(relPath), monaco.Uri.parse('file:///' + relPath.replace(/\\/g, '/')))
  model.onDidChangeContent(() => ws.markDirty(relPath, true))
  models.set(relPath, model)
  return model
}

/** issue-79: 扩展名推断 (小写, 无扩展返回 '')。 */
function extOf(path) {
  const dot = String(path || '').lastIndexOf('.')
  return dot >= 0 ? String(path).slice(dot + 1).toLowerCase() : ''
}

function applyTheme() {
  monaco.editor.setTheme(theme.mode === 'dark' ? 'vs-dark' : 'vs')
}

onMounted(async () => {
  await nextTick()
  if (showPreview.value) return // 预览文件不初始化 Monaco (避免把二进制当文本创建 model)
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
  if (!target) return
  // 预览类文件 (图片/MD/PDF...): 只打开预览视图, 不做编辑器跳转/高亮
  if (isPreviewFile(target.path)) {
    if (target.path !== ws.activeFile) await ws.openFile(target.path)
    projectGraph.consumeReveal()
    return
  }
  if (!editor) return
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
  if (showPreview.value) return // 预览文件 → 渲染 FilePreview, 不进 Monaco
  if (!editor) return
  if (!p) { editor.setModel(null); return }
  await switchTo(p)
})

async function switchTo(relPath) {
  // issue-79: 二进制/容器格式或内容含 NUL → 友好提示, 不建文本 model
  if (BINARY_EXTS.has(extOf(relPath))) {
    binaryPath.value = relPath
    editor.setModel(null)
    return
  }
  const content = await window.api.fs.readFile(relPath)
  if (content.includes('\u0000')) {
    binaryPath.value = relPath
    editor.setModel(null)
    return
  }
  binaryPath.value = null
  const model = await getOrCreateModel(relPath, content)
  editor.setModel(model)
}

watch(() => theme.mode, applyTheme)

// F9: 项目切换 (root 变) 时清空 model 缓存。models 按 relPath 缓存, 但 relPath 相对项目根;
// 新项目若含同 relPath 文件, 会复用旧 model (旧项目内容) 直到外部改动失效。切项目即全失效。
// 注意: openProject 先设 root 再 (await) 清 activeFile, 故此 watcher 触发时 activeFile 可能仍为旧值;
// 已 dispose 的 model 必须无条件从 editor 摘下, 否则编辑器挂在已 dispose 的 model 上。
watch(() => ws.root, () => {
  if (!editor) return
  models.forEach((m) => { try { m.dispose() } catch { /* ignore */ } })
  models.clear()
  conflictPath.value = null
  editor.setModel(null)
})

// 阶段8: 外部文件变动响应
// watch externalChanges: 对已打开的非脏文件失效 model (下次 getOrCreateModel 重读磁盘);
//                       对脏文件设 conflictPath 弹 banner。
// 性能(B): externalChanges 是响应式 Map(useReactiveMap, mutation 即触发),
// 去掉 deep 深度代理遍历 — 保存/外部同步时不再每次深度遍历整表。
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
})

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

/* issue-79: 二进制/容器格式提示 */
.binary-note {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; padding: 24px; text-align: center;
  color: var(--ktext-secondary);
}
.bn-title { margin: 6px 0 0; font-size: 15px; font-weight: 600; color: var(--ktext); }
.bn-hint { margin: 0; font-size: 12.5px; color: var(--ktext-muted); max-width: 420px; line-height: 1.6; }
</style>

<!-- 阶段4b: 符号高亮装饰 (全局, Monaco decoration className 不受 scoped 控制) -->
<style>
.monaco-editor .symbol-highlight {
  background: rgba(24, 144, 255, 0.18);
  border-left: 2px solid #1890ff;
}
</style>
