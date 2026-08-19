/**
 * 文件系统 IPC (阶段1)
 * 所有 fs 操作只在 main 做, 渲染层无 Node fs 权限。
 * 路径安全: 限定在当前 workspace 根内 (resolveSafe 守卫)。
 *
 * F12 防御纵深: 写操作 (write/create/delete/rename) 除渲染层审批门外, main 侧
 *  - 审计日志: 记录操作/路径/字节数, 便于追溯异常写入 (renderer 被攻破或调用方绕过 gate 时可发现)
 *  - 危险删除守卫: 拒绝删除 workspace 根本身 (避免 rm -rf 整个项目)
 *  - 符号链接穿越检查: 拒绝写/删指向 workspace 外的符号链接
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

/** F12: 写操作审计日志 (main 侧防御纵深, 追溯异常写入) */
function auditWrite(op, relPath, extra = {}) {
  const meta = Object.entries(extra).map(([k, v]) => `${k}=${v}`).join(' ')
  console.log(`[fs-audit] ${op} ${relPath}${meta ? ' ' + meta : ''}`)
}

/** 规范化并校验路径在 workspace 内, 防越界 */
export function resolveSafe(relPath) {
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

/**
 * F12: 写/删操作的强化守卫。
 *  - 拒绝操作 workspace 根本身 (防止 rm 根目录或覆盖根)
 *  - 符号链接穿越检查 (目标指向 workspace 外 → 拒绝)
 *    issue-47: 目标文件不存在(新建)时, 旧实现 realpath 抛 ENOENT 直接放行,
 *    若其父目录是"指向工作区外的符号链接"会被 mkdir/write 沿着写穿工作区。
 *    现改为: 目标存在 → realpath 校验; 不存在 → 逐级上溯到最近存在的祖先并
 *    realpath 校验 (覆盖多级符号链接目录)。
 * 抛错则 IPC 返回异常, 渲染层 http/fs 错误路径处理。
 */
export function assertSafeForWrite(abs, op) {
  if (!workspaceRoot || path.resolve(abs) === path.resolve(workspaceRoot)) {
    throw new Error(`禁止${op}工作区根目录`)
  }
  // 符号链接穿越检查 (不存在的路径 realpath 返回 null)
  const probe = (p) => { try { return fsSync.realpathSync(p) } catch { return null } }

  const real = probe(abs)
  if (real) {
    const rel = path.relative(workspaceRoot, real)
    if (rel.startsWith('..') || path.isAbsolute(rel)) {
      throw new Error(`符号链接穿越工作区: ${abs} → ${real}`)
    }
    return
  }
  // 目标不存在 (createFile 新建 / writeFile 到新文件): 对最近存在的祖先目录做校验
  let cur = path.dirname(abs)
  let guard = 0
  while (guard++ < 64) {
    const r = probe(cur)
    if (r) {
      const rel = path.relative(workspaceRoot, r)
      if (rel.startsWith('..') || path.isAbsolute(rel)) {
        throw new Error(`符号链接穿越工作区(目录): ${abs} → ${r}`)
      }
      return
    }
    const parent = path.dirname(cur)
    if (parent === cur) return // 顶到盘符根
    cur = parent
  }
}

export function registerFsIpc() {
  ipcMain.handle('fs:readFile', async (_e, filePath) => {
    const abs = resolveSafe(filePath)
    return fs.readFile(abs, 'utf-8')
  })

  // 文件内联预览: 二进制 (图片/PDF) 以 base64 读 (预览用, 不落 Monaco)
  ipcMain.handle('fs:readBase64', async (_e, filePath) => {
    const abs = resolveSafe(filePath)
    return fs.readFile(abs).toString('base64')
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

  // F12: 写操作经 assertSafeForWrite + 审计日志 (renderer 审批门之外的防御纵深)
  ipcMain.handle('fs:writeFile', async (_e, filePath, content) => {
    const abs = resolveSafe(filePath)
    assertSafeForWrite(abs, '写入')
    const bytes = typeof content === 'string' ? Buffer.byteLength(content, 'utf-8') : 0
    auditWrite('write', filePath, { bytes })
    await fs.mkdir(path.dirname(abs), { recursive: true })
    await fs.writeFile(abs, content, 'utf-8')
    return { ok: true, path: path.relative(workspaceRoot, abs) }
  })

  ipcMain.handle('fs:createFile', async (_e, filePath) => {
    const abs = resolveSafe(filePath)
    assertSafeForWrite(abs, '创建')
    if (fsSync.existsSync(abs)) throw new Error('文件已存在')
    auditWrite('create', filePath)
    await fs.mkdir(path.dirname(abs), { recursive: true })
    await fs.writeFile(abs, '', 'utf-8')
    return { ok: true }
  })

  ipcMain.handle('fs:deleteFile', async (_e, filePath) => {
    const abs = resolveSafe(filePath)
    assertSafeForWrite(abs, '删除')
    auditWrite('delete', filePath)
    await fs.rm(abs, { recursive: true, force: true })
    return { ok: true }
  })

  ipcMain.handle('fs:rename', async (_e, oldPath, newPath) => {
    const absOld = resolveSafe(oldPath)
    const absNew = resolveSafe(newPath)
    assertSafeForWrite(absOld, '重命名(源)')
    assertSafeForWrite(absNew, '重命名(目标)')
    auditWrite('rename', oldPath, { to: newPath })
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
