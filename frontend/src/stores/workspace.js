/**
 * 工作区 store — IDE 状态: 项目根 / 文件树 / 打开标签 / 激活文件
 * 阶段1: 文件浏览 + 多标签编辑 + 保存。Monaco model 由 MonacoEditor 组件管理。
 * 阶段8: 文件监听 — 订阅主进程 watcher 事件, 自动刷新文件树 + 标记外部改动 (供 Monaco 失效)。
 */
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export const useWorkspaceStore = defineStore('workspace', () => {
  const root = ref(null) // 项目根绝对路径
  const rootName = ref('')
  const tree = ref([]) // 扁平文件列表 [{name, path, isDirectory}]
  const openFiles = ref([]) // 打开文件路径数组
  const activeFile = ref(null) // 当前激活文件相对路径
  const dirtyFiles = ref(new Set()) // 未保存文件
  const recent = ref([])

  // 阶段8: 外部文件变动 (主进程 watcher 推送)。
  // externalChanges: Map<relPath, { kind, ts }> — MonacoEditor watch 此表, 对打开的非脏文件失效 model,
  //                  对脏文件标 conflict 弹确认。projectGraph 也据此标 stale。
  const externalChanges = ref(new Map())
  let _unsubscribeWatch = null
  let _refreshTimer = null

  const hasProject = computed(() => !!root.value)
  const openCount = computed(() => openFiles.value.length)

  async function openProject() {
    const res = await window.api.workspace.openProject()
    if (!res) return false
    root.value = res.root
    rootName.value = res.name
    await refreshTree()
    await loadRecent()
    openFiles.value = []
    activeFile.value = null
    startWatching() // 主进程 openProject 已 start watcher, 渲染层订阅事件
    return true
  }

  async function setRoot(dir) {
    const res = await window.api.workspace.setRoot(dir)
    if (!res) return
    root.value = res.root
    rootName.value = res.name
    await refreshTree()
    await loadRecent()
    if (dir) startWatching()
    else stopWatching()
  }

  async function refreshTree() {
    if (!root.value) return
    tree.value = await window.api.fs.listDirectory(null, { deep: true })
  }

  async function loadRecent() {
    recent.value = await window.api.workspace.listRecent()
  }

  // ---- 阶段8: 文件监听订阅 ----
  /** 订阅 fs:watch:change; 批量变动去抖合并一次 refreshTree + 标记 externalChanges */
  function startWatching() {
    if (_unsubscribeWatch) return // 已订阅
    if (typeof window === 'undefined' || !window.api?.fs?.onChange) return
    _unsubscribeWatch = window.api.fs.onChange(async (event) => {
      if (!event || !event.path) return
      // 记录外部改动 (MonacoEditor / projectGraph 据此响应)
      externalChanges.value.set(event.path, { kind: event.kind, ts: Date.now() })
      // 触发响应式 (Map mutation 需手动触发)
      externalChanges.value = new Map(externalChanges.value)

      // 阶段8: 若变动文件是项目图谱源文件, 标记图谱过期 (行号可能漂移, 跳转会指错)
      try {
        const { useProjectGraphStore } = await import('@/stores/projectGraph')
        useProjectGraphStore().markStale(event.path)
      } catch { /* projectGraph store 未就绪, 忽略 */ }

      // 去抖刷新文件树 (150ms 内多次变动合并一次)
      if (_refreshTimer) clearTimeout(_refreshTimer)
      _refreshTimer = setTimeout(() => {
        _refreshTimer = null
        refreshTree().catch(() => { /* ignore */ })
      }, 150)
    })
  }

  function stopWatching() {
    if (_unsubscribeWatch) {
      try { _unsubscribeWatch() } catch { /* ignore */ }
      _unsubscribeWatch = null
    }
    if (_refreshTimer) {
      clearTimeout(_refreshTimer)
      _refreshTimer = null
    }
    externalChanges.value = new Map()
  }

  /** MonacoEditor 处理完一个外部改动后清除标记 */
  function clearExternalChange(relPath) {
    if (externalChanges.value.has(relPath)) {
      externalChanges.value.delete(relPath)
      externalChanges.value = new Map(externalChanges.value)
    }
  }

  async function openFile(relPath) {
    if (openFiles.value.includes(relPath)) {
      activeFile.value = relPath
      return
    }
    // 预读一次确认可读 (MonacoEditor 会再读, 此处仅校验)
    await window.api.fs.readFile(relPath)
    openFiles.value.push(relPath)
    activeFile.value = relPath
  }

  function closeFile(relPath) {
    const idx = openFiles.value.indexOf(relPath)
    if (idx < 0) return
    openFiles.value.splice(idx, 1)
    dirtyFiles.value.delete(relPath)
    if (activeFile.value === relPath) {
      activeFile.value = openFiles.value[idx] || openFiles.value[idx - 1] || null
    }
  }

  function setActive(relPath) {
    activeFile.value = relPath
  }

  function markDirty(relPath, dirty = true) {
    if (dirty) dirtyFiles.value.add(relPath)
    else dirtyFiles.value.delete(relPath)
  }

  async function saveFile(relPath, content) {
    await window.api.fs.writeFile(relPath, content)
    dirtyFiles.value.delete(relPath)
    // 自己保存的改动会触发 watcher 回推, 清掉 externalChange 标记避免误判冲突
    clearExternalChange(relPath)
  }

  return {
    root, rootName, tree, openFiles, activeFile, dirtyFiles, recent,
    externalChanges,
    hasProject, openCount,
    openProject, setRoot, refreshTree, loadRecent,
    openFile, closeFile, setActive, markDirty, saveFile,
    startWatching, stopWatching, clearExternalChange,
  }
})
