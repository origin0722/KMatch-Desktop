/**
 * 场景：main 侧 fs 写操作守卫 (F12 防御纵深)。
 *
 * resolveSafe 限定 workspace 内; assertSafeForWrite 额外拒绝写/删 workspace 根 +
 * 符号链接穿越。这是 renderer write_file 审批门之外的 main 侧防线
 * (renderer 被攻破或调用方绕过 gate 时仍守得住)。
 *
 * 注: 这些函数在 electron/main 下 (Node), 用相对路径 import; jsdom 环境下 path/fsSync 可用。
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import os from 'node:os'
import fs from 'node:fs'
import path from 'node:path'
import { setWorkspaceRoot, resolveSafe, assertSafeForWrite } from '../../../electron/main/ipc/fs'

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'kmatch-fs-guard-'))

beforeEach(() => setWorkspaceRoot(TMP))
afterEach(() => {
  setWorkspaceRoot(null)
  try { fs.rmSync(TMP, { recursive: true, force: true }) } catch { /* ignore */ }
})

describe('fs 写操作守卫 (F12)', () => {
  it('resolveSafe: workspace 内相对路径解析为绝对路径', () => {
    const abs = resolveSafe('src/a.py')
    expect(abs).toBe(path.resolve(TMP, 'src/a.py'))
  })

  it('resolveSafe: 拒绝越界路径 (..)', () => {
    expect(() => resolveSafe('../escape.py')).toThrow('路径越界')
    expect(() => resolveSafe('/etc/passwd')).toThrow('路径越界')
  })

  it('assertSafeForWrite: 拒绝写/删 workspace 根本身', () => {
    expect(() => assertSafeForWrite(TMP, '写入')).toThrow('工作区根目录')
    expect(() => assertSafeForWrite(path.resolve(TMP), '删除')).toThrow('工作区根目录')
  })

  it('assertSafeForWrite: workspace 内文件放行', () => {
    const abs = path.resolve(TMP, 'a.py')
    expect(() => assertSafeForWrite(abs, '写入')).not.toThrow()
  })

  it('assertSafeForWrite: 拒绝符号链接穿越到 workspace 外 (F12 核心防御)', () => {
    // 在 workspace 内建一个符号链接指向 workspace 外的临时文件
    const outsideTarget = path.join(os.tmpdir(), 'kmatch-outside-target.txt')
    fs.writeFileSync(outsideTarget, 'secret', 'utf-8')
    const linkAbs = path.resolve(TMP, 'evil-link.py')
    try { fs.symlinkSync(outsideTarget, linkAbs) } catch { /* 某些环境无权限建链接, 跳过 */ }
    if (fs.existsSync(linkAbs) && fs.lstatSync(linkAbs).isSymbolicLink()) {
      expect(() => assertSafeForWrite(linkAbs, '写入')).toThrow('符号链接穿越')
    }
    fs.rmSync(outsideTarget, { force: true })
  })

  it('issue-47: 拒绝写入"父目录为指向工作区外的符号链接"的新文件', () => {
    // 目标文件不存在 (新建场景), 但其父目录是指向外部目录的符号链接 → 旧实现 realpath 抛
    // ENOENT 放行, 会沿链接写穿工作区; 修复后应拒绝。
    const outsideDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kmatch-outside-dir-'))
    const linkDir = path.resolve(TMP, 'linked-dir')
    try { fs.symlinkSync(outsideDir, linkDir) } catch { /* 无权限建链接则跳过 */ }
    if (fs.existsSync(linkDir) && fs.lstatSync(linkDir).isSymbolicLink()) {
      expect(() => assertSafeForWrite(path.join(linkDir, 'new.py'), '写入')).toThrow('符号链接穿越')
      expect(() => assertSafeForWrite(path.join(linkDir, 'nested', 'new.py'), '写入')).toThrow('符号链接穿越')
    }
    fs.rmSync(outsideDir, { recursive: true, force: true })
  })
})
