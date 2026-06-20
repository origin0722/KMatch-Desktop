/**
 * 工作区 store — IDE 状态: 项目根 / 文件树 / 打开标签 / 激活文件
 * 阶段1: 文件浏览 + 多标签编辑 + 保存。Monaco model 由 MonacoEditor 组件管理。
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
    return true
  }

  async function setRoot(dir) {
    const res = await window.api.workspace.setRoot(dir)
    if (!res) return
    root.value = res.root
    rootName.value = res.name
    await refreshTree()
    await loadRecent()
  }

  async function refreshTree() {
    if (!root.value) return
    tree.value = await window.api.fs.listDirectory(null, { deep: true })
  }

  async function loadRecent() {
    recent.value = await window.api.workspace.listRecent()
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
  }

  return {
    root, rootName, tree, openFiles, activeFile, dirtyFiles, recent,
    hasProject, openCount,
    openProject, setRoot, refreshTree, loadRecent,
    openFile, closeFile, setActive, markDirty, saveFile,
  }
})
