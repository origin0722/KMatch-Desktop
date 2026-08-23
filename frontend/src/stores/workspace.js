/**
 * 工作区 store — IDE 状态: 项目根 / 文件树 / 打开标签 / 激活文件
 * 阶段1: 文件浏览 + 多标签编辑 + 保存。Monaco model 由 MonacoEditor 组件管理。
 * 阶段8: 文件监听 — 订阅主进程 watcher 事件, 自动刷新文件树 + 标记外部改动 (供 Monaco 失效)。
 */
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useReactiveMap, useReactiveSet } from '@/ide/useReactiveCollection'
import { isPreviewFile } from '@/utils/fileKind'

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

  // 项目打开订阅者 (P2: projectGraph 订阅 -> 后台自动解析成图谱, workspace 不直接依赖 projectGraph)
  const _projectOpenListeners = new Set()
  function onProjectOpened(cb) {
    _projectOpenListeners.add(cb)
    return () => _projectOpenListeners.delete(cb)
  }

  const hasProject = computed(() => !!root.value)
  const openCount = computed(() => openFiles.value.length)

  async function openProject() {
    const res = await window.api.workspace.openProject()
    if (!res) return false
    root.value = res.root
    rootName.value = res.name
    _resetTreeCache()
    await refreshTree()
    await loadRecent()
    openFiles.value = []
    activeFile.value = null
    startWatching() // 主进程 openProject 已 start watcher, 渲染层订阅事件
    // P2: 通知订阅者 (projectGraph 后台自动解析), 不阻塞文件树交互
    for (const cb of _projectOpenListeners) {
      try { cb(res) } catch { /* 单个订阅者异常不影响其他 */ }
    }
    return true
  }

  async function setRoot(dir) {
    const res = await window.api.workspace.setRoot(dir)
    if (!res) return
    root.value = res.root
    rootName.value = res.name
    _resetTreeCache()
    await refreshTree()
    await loadRecent()
    if (dir) startWatching()
    else stopWatching()
    // issue: 最近项目点击/关闭项目同样通知订阅者 (projectGraph: 换项目先清旧图谱再自动解析)
    for (const cb of _projectOpenListeners) {
      try { cb(res) } catch { /* 单个订阅者异常不影响其他 */ }
    }
  }

  // ---- 懒加载目录树 (借鉴 DSH-better-sidebar 资源管理器) ----
  // 顶层列表 + 展开时逐层拉取子项, 避免大项目全量深遍历卡顿。
  const expandedDirs = useReactiveSet()      // 已展开的目录(相对路径)
  const loadingDirs = useReactiveSet()       // 正在拉取的目录
  const dirChildren = useReactiveMap()       // 目录(相对路径) → 子项 [] (缓存; '' => 根)
  const expandedDirsRef = expandedDirs.ref
  const loadingDirsRef = loadingDirs.ref
  const dirChildrenRef = dirChildren.ref

  function _resetTreeCache() {
    expandedDirs.clear()
    dirChildren.clear()
    loadingDirs.clear()
  }

  async function refreshTree() {
    if (!root.value) return
    // 只取顶层, 子目录惰性展开
    tree.value = await window.api.fs.listDirectory(null)
  }

  /** 展开/收起目录 (首次展开才拉取子项, 之后折叠/再展开命中缓存) */
  async function toggleDir(dirPath) {
    if (expandedDirs.has(dirPath)) {
      expandedDirs.delete(dirPath)
      return
    }
    if (!dirChildren.has(dirPath) && !loadingDirs.has(dirPath)) {
      loadingDirs.add(dirPath)
      try {
        const children = await window.api.fs.listDirectory(dirPath)
        dirChildren.set(dirPath, children || [])
      } catch { /* 读取失败: 视为空, 仍允许展开 */}
      finally {
        loadingDirs.delete(dirPath)
      }
    }
    expandedDirs.add(dirPath)
  }

  async function loadRecent() {
    recent.value = await window.api.workspace.listRecent()
  }

  // issue-90: 从最近打开中删除单条 (主进程持久化写回)
  async function removeRecent(dir) {
    try {
      if (window.api?.workspace?.removeRecent) {
        recent.value = await window.api.workspace.removeRecent(dir)
      } else {
        recent.value = recent.value.filter((p) => p !== dir)
      }
    } catch {
      recent.value = recent.value.filter((p) => p !== dir)
    }
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
    // 预览类文件 (图片/PDF/Markdown/HTML) 不走文本预读 (避免把大二进制当 utf-8 读),
    // 由 FilePreview 按 kind 走 readBase64/readFile。
    if (!isPreviewFile(relPath)) await window.api.fs.readFile(relPath)
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
    // 懒加载目录树状态
    expandedDirs: expandedDirsRef,
    loadingDirs: loadingDirsRef,
    dirChildren: dirChildrenRef,
    toggleDir,
    hasProject, openCount,
    openProject, setRoot, refreshTree, loadRecent, removeRecent,
    openFile, closeFile, setActive, markDirty, saveFile,
    startWatching, stopWatching, clearExternalChange, onExternalChange,
    onProjectOpened,
  }
})
