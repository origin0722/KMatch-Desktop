/**
 * 工作区 store — IDE 状态: 项目根 / 文件树 / 打开标签 / 激活文件
 * 阶段1: 文件浏览 + 多标签编辑 + 保存。Monaco model 由 MonacoEditor 组件管理。
 * 阶段8: 文件监听 — 订阅主进程 watcher 事件, 自动刷新文件树 + 标记外部改动 (供 Monaco 失效)。
 */
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useReactiveMap, useReactiveSet } from '@/ide/useReactiveCollection'

export const useWorkspaceStore = defineStore('workspace', () => {
  const root = ref(null) // 项目根绝对路径
  const rootName = ref('')
  const tree = ref([]) // 扁平文件列表 [{name, path, isDirectory}]
  const openFiles = ref([]) // 打开文件路径数组
  const activeFile = ref(null) // 当前激活文件相对路径
  // F11: dirtyFiles/externalChanges 用响应式 helper (mutation 后自动 trigger),
  // 旧实现 Set/Map mutation 不触发响应式 → dirty 标记静默不更新 (EditorTabs/FileExplorer/StatusBar 看不到)
  const dirtySet = useReactiveSet()
  const dirtyFiles = dirtySet.ref // 暴露 ref 供组件 .has() 读 (契约不变)
  const recent = ref([])

  // 阶段8: 外部文件变动 (主进程 watcher 推送)。
  // externalChanges: Map<relPath, { kind, ts }> — MonacoEditor watch 此表, 对打开的非脏文件失效 model,
  //                  对脏文件标 conflict 弹确认。
  const extChanges = useReactiveMap()
  const externalChanges = extChanges.ref
  let _unsubscribeWatch = null
  let _refreshTimer = null

  // 文件变动订阅者 (C2 解耦: workspace 不再硬调 projectGraph.markStale, 改由订阅者自行响应)。
  // projectGraph 在 setGraph 时订阅, markStale 逻辑收回 projectGraph 自己。
  const _changeListeners = new Set()
  function onExternalChange(cb) {
    _changeListeners.add(cb)
    return () => _changeListeners.delete(cb)
  }

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
      // 记录外部改动 (MonacoEditor 据此响应; projectGraph 经 onExternalChange 订阅响应)
      extChanges.set(event.path, { kind: event.kind, ts: Date.now() })

      // 通知文件变动订阅者 (C2: projectGraph 自行订阅并 markStale, workspace 不再 import projectGraph)
      for (const cb of _changeListeners) {
        try { cb(event) } catch { /* 单个订阅者异常不影响其他 */ }
      }

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
    extChanges.clear()
  }

  /** MonacoEditor 处理完一个外部改动后清除标记 */
  function clearExternalChange(relPath) {
    extChanges.delete(relPath)
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
    dirtySet.delete(relPath)
    if (activeFile.value === relPath) {
      activeFile.value = openFiles.value[idx] || openFiles.value[idx - 1] || null
    }
  }

  function setActive(relPath) {
    activeFile.value = relPath
  }

  function markDirty(relPath, dirty = true) {
    if (dirty) dirtySet.add(relPath)
    else dirtySet.delete(relPath)
  }

  async function saveFile(relPath, content) {
    await window.api.fs.writeFile(relPath, content)
    dirtySet.delete(relPath)
    // 自己保存的改动会触发 watcher 回推, 清掉 externalChange 标记避免误判冲突
    clearExternalChange(relPath)
  }

  return {
    root, rootName, tree, openFiles, activeFile, dirtyFiles, recent,
    externalChanges,
    hasProject, openCount,
    openProject, setRoot, refreshTree, loadRecent,
    openFile, closeFile, setActive, markDirty, saveFile,
    startWatching, stopWatching, clearExternalChange, onExternalChange,
  }
})
