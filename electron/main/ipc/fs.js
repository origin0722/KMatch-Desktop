/**
 * 文件系统 IPC (阶段1)
 * 所有 fs 操作只在 main 做, 渲染层无 Node fs 权限。
 * 路径安全: 限定在当前 workspace 根内 (阶段3 权限门会加审批)。
 *
 * 阶段1 暂不接审批门 — 读写均在 workspace 内, 阶段3 引入 permissionGate。
 */
import { ipcMain, dialog } from 'electron'
import fs from 'fs/promises'
import fsSync from 'fs'
import path from 'path'

let workspaceRoot = null

export function setWorkspaceRoot(p) {
  workspaceRoot = p
}

export function getWorkspaceRoot() {
  return workspaceRoot
}

/** 文件监听与目录列举共用: 排除这些目录名 (阶段8 watcher 复用) */
const IGNORE_NAMES = new Set([
  'node_modules', '.git', '__pycache__', '.pytest_cache', 'dist', 'out',
  '.venv', 'venv', '.idea', '.vscode', 'build',
])

export { IGNORE_NAMES }

/** 规范化并校验路径在 workspace 内, 防越界 */
function resolveSafe(relPath) {
  if (!workspaceRoot) throw new Error('未打开工作区')
  const abs = path.isAbsolute(relPath)
    ? relPath
    : path.resolve(workspaceRoot, relPath)
  const rel = path.relative(workspaceRoot, abs)
  if (rel.startsWith('..') || path.isAbsolute(rel)) {
    throw new Error(`路径越界工作区: ${relPath}`)
  }
  return abs
}

export function registerFsIpc() {
  ipcMain.handle('fs:readFile', async (_e, filePath) => {
    const abs = resolveSafe(filePath)
    return fs.readFile(abs, 'utf-8')
  })

  ipcMain.handle('fs:stat', async (_e, filePath) => {
    const abs = resolveSafe(filePath)
    const st = await fs.stat(abs)
    return {
      name: path.basename(abs),
      path: path.relative(workspaceRoot, abs),
      isDirectory: st.isDirectory(),
      size: st.size,
      mtime: st.mtimeMs,
    }
  })

  /**
   * 列目录 (一层), 返回直接子项 (含文件/目录, 排除常见忽略项)
   * deep=true 时递归返回扁平文件列表 (供文件树一次性构建)
   */
  ipcMain.handle('fs:listDirectory', async (_e, dirPath, { deep = false } = {}) => {
    const abs = dirPath ? resolveSafe(dirPath) : workspaceRoot
    if (deep) return listDeep(abs)
    return listOne(abs)
  })

  // 阶段1 写操作暂直接执行 (限 workspace 内); 阶段3 接审批门 + safety-check
  ipcMain.handle('fs:writeFile', async (_e, filePath, content) => {
    const abs = resolveSafe(filePath)
    await fs.mkdir(path.dirname(abs), { recursive: true })
    await fs.writeFile(abs, content, 'utf-8')
    return { ok: true, path: path.relative(workspaceRoot, abs) }
  })

  ipcMain.handle('fs:createFile', async (_e, filePath) => {
    const abs = resolveSafe(filePath)
    if (fsSync.existsSync(abs)) throw new Error('文件已存在')
    await fs.mkdir(path.dirname(abs), { recursive: true })
    await fs.writeFile(abs, '', 'utf-8')
    return { ok: true }
  })

  ipcMain.handle('fs:deleteFile', async (_e, filePath) => {
    const abs = resolveSafe(filePath)
    await fs.rm(abs, { recursive: true, force: true })
    return { ok: true }
  })

  ipcMain.handle('fs:rename', async (_e, oldPath, newPath) => {
    const absOld = resolveSafe(oldPath)
    const absNew = resolveSafe(newPath)
    await fs.rename(absOld, absNew)
    return { ok: true }
  })
}

async function listOne(absDir) {
  const entries = await fs.readdir(absDir, { withFileTypes: true })
  return entries
    .filter((e) => !IGNORE_NAMES.has(e.name))
    .map((e) => ({
      name: e.name,
      path: path.relative(workspaceRoot, path.join(absDir, e.name)),
      isDirectory: e.isDirectory(),
    }))
    .sort((a, b) => (a.isDirectory === b.isDirectory ? a.name.localeCompare(b.name) : a.isDirectory ? -1 : 1))
}

async function listDeep(absDir) {
  const out = []
  async function walk(dir) {
    let entries = []
    try { entries = await fs.readdir(dir, { withFileTypes: true }) } catch { return }
    for (const e of entries) {
      if (IGNORE_NAMES.has(e.name)) continue
      const full = path.join(dir, e.name)
      const rel = path.relative(workspaceRoot, full)
      if (e.isDirectory()) {
        out.push({ name: e.name, path: rel, isDirectory: true })
        await walk(full)
      } else {
        out.push({ name: e.name, path: rel, isDirectory: false })
      }
    }
  }
  await walk(absDir)
  return out
}
