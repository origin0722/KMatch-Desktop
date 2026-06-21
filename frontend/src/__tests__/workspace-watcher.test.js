/**
 * 阶段8: workspace store 文件监听订阅行为单测
 *
 * 建立仓库首个 window.api mock 模式 (workspace store 直连 window.api, 无 @/api/ wrapper)。
 * 测:
 *   - openProject 后 startWatching 订阅 onChange
 *   - 外部变动触发 refreshTree (去抖)
 *   - externalChanges 记录 + dirty 文件不直接清除标记 (留给 Monaco 处理)
 *   - clearExternalChange 清除标记
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// ---- window.api mock (仓库首个, 供后续 store 测试复用) ----
// workspace store 用 window.api.workspace / window.api.fs, 这里全 mock
let _onChangeCb = null
const fsMock = {
  readFile: vi.fn().mockResolvedValue('content'),
  stat: vi.fn().mockResolvedValue({}),
  listDirectory: vi.fn().mockResolvedValue([{ name: 'a.py', path: 'a.py', isDirectory: false }]),
  writeFile: vi.fn().mockResolvedValue(undefined),
  createFile: vi.fn().mockResolvedValue(undefined),
  deleteFile: vi.fn().mockResolvedValue(undefined),
  rename: vi.fn().mockResolvedValue(undefined),
  onChange: vi.fn((cb) => { _onChangeCb = cb; return () => { _onChangeCb = null } }),
}
const workspaceMock = {
  openProject: vi.fn().mockResolvedValue({ root: '/proj', name: 'proj' }),
  setRoot: vi.fn().mockResolvedValue({ root: '/proj', name: 'proj' }),
  getRoot: vi.fn().mockResolvedValue('/proj'),
  listRecent: vi.fn().mockResolvedValue([]),
}

function installWindowApi() {
  globalThis.window = globalThis.window || {}
  globalThis.window.api = { fs: fsMock, workspace: workspaceMock }
  _onChangeCb = null
  fsMock.onChange.mockClear()
}

describe('workspace store 文件监听', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    installWindowApi()
    vi.clearAllMocks()
  })

  it('openProject 后订阅 fs.onChange', async () => {
    const { useWorkspaceStore } = await import('@/stores/workspace')
    const ws = useWorkspaceStore()
    await ws.openProject()
    expect(fsMock.onChange).toHaveBeenCalled()
  })

  it('外部变动事件记录到 externalChanges', async () => {
    const { useWorkspaceStore } = await import('@/stores/workspace')
    const ws = useWorkspaceStore()
    await ws.openProject()

    expect(_onChangeCb).toBeTruthy()
    _onChangeCb({ kind: 'change', path: 'src/a.py', absPath: '/proj/src/a.py' })

    expect(ws.externalChanges.has('src/a.py')).toBe(true)
    expect(ws.externalChanges.get('src/a.py').kind).toBe('change')
  })

  it('clearExternalChange 清除单条标记', async () => {
    const { useWorkspaceStore } = await import('@/stores/workspace')
    const ws = useWorkspaceStore()
    await ws.openProject()
    _onChangeCb({ kind: 'change', path: 'src/a.py', absPath: '/proj/src/a.py' })

    ws.clearExternalChange('src/a.py')
    expect(ws.externalChanges.has('src/a.py')).toBe(false)
  })

  it('外部变动触发去抖 refreshTree (真实短定时器)', async () => {
    const { useWorkspaceStore } = await import('@/stores/workspace')
    const ws = useWorkspaceStore()
    await ws.openProject()
    fsMock.listDirectory.mockClear() // openProject 已调一次

    _onChangeCb({ kind: 'add', path: 'new.py', absPath: '/proj/new.py' })
    // 未到去抖窗口, 不应刷新
    expect(fsMock.listDirectory).not.toHaveBeenCalled()

    // 等去抖窗口 (150ms) + microtask flush (onChange async + refreshTree async)
    await new Promise((r) => setTimeout(r, 220))
    await new Promise((r) => setTimeout(r, 10))
    // 变动后去抖触发了 refreshTree (listDirectory 至少被调一次)
    expect(fsMock.listDirectory).toHaveBeenCalled()
  })

  it('stopWatching 取消订阅 + 清 externalChanges', async () => {
    const { useWorkspaceStore } = await import('@/stores/workspace')
    const ws = useWorkspaceStore()
    await ws.openProject()
    _onChangeCb({ kind: 'change', path: 'a.py', absPath: '/proj/a.py' })
    expect(ws.externalChanges.size).toBe(1)

    ws.stopWatching()
    expect(_onChangeCb).toBeNull()
    expect(ws.externalChanges.size).toBe(0)
  })

  it('saveFile 后清自身文件的 externalChange (避免 watcher 回推误判冲突)', async () => {
    const { useWorkspaceStore } = await import('@/stores/workspace')
    const ws = useWorkspaceStore()
    await ws.openProject()
    _onChangeCb({ kind: 'change', path: 'a.py', absPath: '/proj/a.py' })

    await ws.saveFile('a.py', 'new content')
    expect(ws.externalChanges.has('a.py')).toBe(false)
    expect(fsMock.writeFile).toHaveBeenCalledWith('a.py', 'new content')
  })
})
