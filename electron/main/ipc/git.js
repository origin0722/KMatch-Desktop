/**
 * Git IPC (方案A) — 主进程调系统 git CLI, 供 Git 视图做 克隆/状态/拉取/提交/推送/历史。
 *
 * 安全: 一律 execFile(git, argsArray, {cwd}) — 无 shell 拼接/注入面。
 * 每条返回 { ok: true, ... } 或 { ok: false, error }。
 * 凭据: HTTPS 依赖用户 git 配置/凭据管理器/token (应用不存储密钥)。
 */
import { ipcMain, dialog } from 'electron'
import { execFile } from 'child_process'
import path from 'path'

/** execFile promisify (git 可能超时/需凭据 → 失败快速上浮)。 */
function runGit(args, cwd, timeoutMs = 60_000) {
  return new Promise((resolve) => {
    execFile('git', args, { cwd, timeout: timeoutMs, maxBuffer: 8 * 1024 * 1024, windowsHide: true },
      (err, stdout, stderr) => {
        if (err) {
          // git 报错时 stdout/stderr 都可能是可读信息 (如 "Not a git repository")
          const msg = (stderr || err.message || '').trim()
          resolve({ ok: false, error: msg || 'git 命令失败' })
          return
        }
        resolve({ ok: true, output: (stdout || '').trim() })
      })
  })
}

/** git 是否可用 */
async function checkGit() {
  const r = await runGit(['--version'], process.cwd(), 10_000)
  return { ok: r.ok, version: r.ok ? r.output : '', error: r.error }
}

/** 工作区状态: git status --porcelain=v1 -b → { isRepo, branch, files:[{path,status}] } */
async function status(cwd) {
  if (!cwd) return { ok: false, error: '未打开项目（无工作目录）' }
  const r = await runGit(['status', '--porcelain=v1', '-b'], cwd)
  if (!r.ok) {
    const txt = r.error || ''
    if (/not a git repository/i.test(txt)) return { ok: true, isRepo: false, branch: '', files: [], error: '' }
    return { ok: false, error: txt }
  }
  const lines = r.output.split(/\r?\n/).filter(Boolean)
  let branch = ''
  const files = []
  for (const line of lines) {
    if (line.startsWith('## ')) {
      branch = line.slice(3).split('...')[0].split(' ')[0]
      continue
    }
    // porcelain v1: XY path (重命名取原路径 R 两段)
    files.push({ status: line.slice(0, 2), path: line.slice(3).trim() })
  }
  return { ok: true, isRepo: true, branch, files }
}

/** 克隆远程: 主进程弹系统目录选择器 → 目录名取 URL 末尾 → git clone → 返回新仓库根 (渲染层 setRoot 自动解析)。 */
async function pickCloneParent() {
  const res = await dialog.showOpenDialog({
    properties: ['openDirectory', 'createDirectory'],
    title: '选择克隆到哪个文件夹（将在其中创建同名子目录）',
  })
  if (res.canceled || !res.filePaths.length) return null
  return res.filePaths[0]
}

export function registerGitIpc() {
  ipcMain.handle('git:check', () => checkGit())

  ipcMain.handle('git:status', (_e, cwd) => status(cwd))

  ipcMain.handle('git:init', async (_e, cwd) => {
    const r = await runGit(['init'], cwd)
    if (!r.ok) return r
    return { ok: true, output: r.output }
  })

  ipcMain.handle('git:clone', async (_e, { url }) => {
    if (!url) return { ok: false, error: '缺少远程地址' }
    const parent = await pickCloneParent()
    if (!parent) return { ok: false, canceled: true, error: '已取消选择文件夹' }
    const name = url.replace(/\.git$/, '').split('/').pop() || 'repo'
    const target = path.join(parent, name)
    const r = await runGit(['clone', url, target], parent, 300_000)
    if (!r.ok) return { ...r, target }
    return { ok: true, root: target, name, output: r.output }
  })

  ipcMain.handle('git:pull', (_e, cwd) => runGit(['pull'], cwd, 180_000))

  ipcMain.handle('git:commit', async (_e, { cwd, message, stageAll }) => {
    if (!message || !message.trim()) return { ok: false, error: '提交消息不能为空' }
    if (stageAll) {
      const add = await runGit(['add', '-A'], cwd)
      if (!add.ok) return add
    }
    return runGit(['commit', '-m', message.trim()], cwd, 60_000)
  })

  ipcMain.handle('git:push', (_e, cwd) => runGit(['push'], cwd, 180_000))

  ipcMain.handle('git:log', async (_e, { cwd, max = 10 }) => {
    const r = await runGit(['log', `--max-count=${Math.min(50, Math.max(1, max))}`, '--oneline', '--decorate'], cwd)
    return r
  })
}
