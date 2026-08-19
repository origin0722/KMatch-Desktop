/**
 * workspace 懒加载目录树 store 单测
 *
 * 修复目标 (借鉴 DSH-better-sidebar): 打开/刷新项目不再全量深遍历(listDirectory deep),
 * 改为顶层加载 + 展开目录时逐层拉取; 大项目不再卡顿。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

let listCalls = []
const fsTree = {
  null: [
    { name: 'src', path: 'src', isDirectory: true },
    { name: 'README.md', path: 'README.md', isDirectory: false },
  ],
  'src': [
    { name: 'main.py', path: 'src/main.py', isDirectory: false },
    { name: 'lib', path: 'src/lib', isDirectory: true },
  ],
  'src/lib': [{ name: 'util.py', path: 'src/lib/util.py', isDirectory: false }],
}

function installWindowApi() {
  listCalls = []
  globalThis.window = globalThis.window || {}
  window.api = {
    fs: {
      listDirectory: vi.fn(async (dir) => { listCalls.push([dir, null]); return fsTree[dir] || [] }),
      readFile: vi.fn(async () => 'x'),
      stat: vi.fn(async () => ({})),
      writeFile: vi.fn(async () => {}),
      onChange: vi.fn(() => () => {}),
    },
    workspace: {
      openProject: vi.fn(async () => ({ root: '/proj', name: 'proj' })),
      setRoot: vi.fn(async (dir) => ({ root: dir, name: dir })),
      listRecent: vi.fn(async () => []),
    },
  }
}

const { useWorkspaceStore } = await import('@/stores/workspace')

describe('workspace 懒加载目录树', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    installWindowApi()
    vi.clearAllMocks()
  })

  it('refreshTree 只取顶层 (不再 deep 全量遍历)', async () => {
    const ws = useWorkspaceStore()
    await ws.openProject()
    expect(ws.tree.map((n) => n.name)).toEqual(['src', 'README.md'])
    expect(listCalls).toEqual([[null, null]]) // 仅一次顶级调用, 无 deep
  })

  it('toggleDir 惰性拉取子项 + 缓存复用 + 折叠', async () => {
    const ws = useWorkspaceStore()
    await ws.openProject()
    await ws.toggleDir('src')
    expect(ws.expandedDirs.has('src')).toBe(true)
    expect(ws.dirChildren.get('src').map((n) => n.name)).toEqual(['main.py', 'lib'])
    expect(listCalls).toContainEqual(['src', null])

    // 折叠
    await ws.toggleDir('src')
    expect(ws.expandedDirs.has('src')).toBe(false)

    // 再展开 → 命中缓存, 不再请求
    const before = listCalls.length
    await ws.toggleDir('src')
    expect(ws.dirChildren.get('src')).toHaveLength(2)
    expect(listCalls.length).toBe(before)
  })

  it('加载中标记 loadingDirs; 展开子目录递归可用', async () => {
    const ws = useWorkspaceStore()
    await ws.openProject()
    let resolvePending
    window.api.fs.listDirectory.mockImplementationOnce(async (dir) => { listCalls.push([dir]); return new Promise((r) => { resolvePending = r }) })
    const p = ws.toggleDir('src/lib') // 挂起
    expect(ws.loadingDirs.has('src/lib')).toBe(true)
    resolvePending(fsTree['src/lib'])
    await p
    expect(ws.loadingDirs.has('src/lib')).toBe(false)
    expect(ws.dirChildren.get('src/lib')).toHaveLength(1)
  })

  it('setRoot 清空展开/子项缓存 (切换项目不留旧树)', async () => {
    const ws = useWorkspaceStore()
    await ws.openProject()
    await ws.toggleDir('src')
    expect(ws.dirChildren.get('src')).toBeTruthy()
    await ws.setRoot('/other')
    expect(ws.expandedDirs.has('src')).toBe(false)
    expect(ws.dirChildren.get('src')).toBeUndefined()
  })

  it('openFile: 预览类文件跳过文本预读, 普通文件预读', async () => {
    const ws = useWorkspaceStore()
    await ws.openFile('assets/x.png')
    expect(window.api.fs.readFile).not.toHaveBeenCalled() // 二进制不 utf-8 预读
    expect(ws.openFiles).toContain('assets/x.png')
    await ws.openFile('main.py')
    expect(window.api.fs.readFile).toHaveBeenCalledWith('main.py')
  })
})
