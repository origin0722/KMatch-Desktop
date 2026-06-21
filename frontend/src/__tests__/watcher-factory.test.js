/**
 * 阶段8: 文件监听控制器纯工厂单测
 *
 * 测 createWatcherController 的逻辑 (不依赖真实 electron/worker_threads/chokidar):
 *   - Worker 注入: 收到 worker 'change' 消息 → 推送到主窗口 webContents
 *   - isDestroyed 守卫: 窗口已销毁时不崩
 *   - start/stop 生命周期: stop 后 worker 被 terminate
 *   - 同根重复 start 不重启
 *
 * 照 window-ipc.test.js 的纯工厂 + 依赖注入测法。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

// mock electron / worker_threads / ./fs.js (watcher.js 顶层 import 它们, vitest 里不可用)
vi.mock('electron', () => ({ ipcMain: { handle: vi.fn() } }))
vi.mock('worker_threads', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, Worker: vi.fn() }
})
vi.mock('../../../electron/main/ipc/fs.js', () => ({ IGNORE_NAMES: new Set(['node_modules', '.git']) }))

const { createWatcherController } = await import('../../../electron/main/ipc/watcher.js')

/** 造一个 fake Worker 构造器: new 时返回带 on/postMessage/terminate 的实例 */
function makeFakeWorkerCtor() {
  const handlers = {}
  const instance = {
    on: vi.fn((event, cb) => { handlers[event] = cb }),
    postMessage: vi.fn(),
    terminate: vi.fn().mockResolvedValue(undefined),
    _emit: (event, payload) => handlers[event]?.(payload),
  }
  // 普通函数 (非箭头) 才能被 new; 返回 instance 覆盖默认 this
  function Ctor() { return instance }
  Ctor.instance = instance
  return Ctor
}

describe('createWatcherController', () => {
  let sent
  let win
  let getMainWindow

  beforeEach(() => {
    sent = []
    win = {
      isDestroyed: () => false,
      webContents: { send: (channel, event) => sent.push({ channel, event }) },
    }
    getMainWindow = () => win
  })

  it('转发 worker change 事件到主窗口 webContents (fs:watch:change)', async () => {
    const Ctor = makeFakeWorkerCtor()
    const controller = createWatcherController({
      Worker: Ctor,
      workerPath: '/fake/worker.js',
      getMainWindow,
    })
    await controller.start('/proj/root')

    Ctor.instance._emit('message', { type: 'change', event: { kind: 'change', path: 'src/a.py', absPath: '/proj/root/src/a.py' } })

    expect(sent).toHaveLength(1)
    expect(sent[0].channel).toBe('fs:watch:change')
    expect(sent[0].event).toEqual({ kind: 'change', path: 'src/a.py', absPath: '/proj/root/src/a.py' })
  })

  it('窗口已销毁时不抛 (isDestroyed 守卫)', async () => {
    const Ctor = makeFakeWorkerCtor()
    const controller = createWatcherController({
      Worker: Ctor,
      workerPath: '/fake/worker.js',
      getMainWindow: () => ({ isDestroyed: () => true, webContents: { send: () => { throw new Error('不应到达') } } }),
    })
    await controller.start('/proj/root')

    expect(() => {
      Ctor.instance._emit('message', { type: 'change', event: { kind: 'add', path: 'x', absPath: '/x' } })
    }).not.toThrow()
  })

  it('stop 后 terminate worker 且 isActive=false', async () => {
    const Ctor = makeFakeWorkerCtor()
    const controller = createWatcherController({
      Worker: Ctor,
      workerPath: '/fake/worker.js',
      getMainWindow,
    })
    await controller.start('/proj/root')
    expect(controller.isActive()).toBe(true)

    await controller.stop()
    expect(Ctor.instance.terminate).toHaveBeenCalled()
    expect(controller.isActive()).toBe(false)
  })

  it('同根重复 start 不重启 worker', async () => {
    let created = 0
    const Ctor = makeFakeWorkerCtor()
    function CountingCtor() { created++; return Ctor.instance }
    const controller = createWatcherController({
      Worker: CountingCtor,
      workerPath: '/fake/worker.js',
      getMainWindow,
    })
    await controller.start('/proj/root')
    await controller.start('/proj/root') // 同根
    expect(created).toBe(1)
  })

  it('换根 start 先停旧 worker 再建新', async () => {
    const CtorA = makeFakeWorkerCtor()
    const CtorB = makeFakeWorkerCtor()
    const ctors = [CtorA, CtorB]
    let i = 0
    function PickCtor() { return ctors[i++].instance }
    const controller = createWatcherController({
      Worker: PickCtor,
      workerPath: '/fake/worker.js',
      getMainWindow,
    })
    await controller.start('/proj/a')
    await controller.start('/proj/b') // 换根
    expect(CtorA.instance.terminate).toHaveBeenCalled()
    expect(controller.isActive()).toBe(true)
  })

  it('start 时向 worker 发 start 指令带 ignoreNames', async () => {
    const Ctor = makeFakeWorkerCtor()
    const controller = createWatcherController({
      Worker: Ctor,
      workerPath: '/fake/worker.js',
      getMainWindow,
    })
    await controller.start('/proj/root')
    expect(Ctor.instance.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'start', root: '/proj/root' }),
    )
    const call = Ctor.instance.postMessage.mock.calls[0][0]
    expect(Array.isArray(call.ignoreNames)).toBe(true)
    expect(call.ignoreNames).toContain('node_modules')
  })

  it('worker error 消息不致命 (不推送到渲染层)', async () => {
    const Ctor = makeFakeWorkerCtor()
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const controller = createWatcherController({
      Worker: Ctor,
      workerPath: '/fake/worker.js',
      getMainWindow,
    })
    await controller.start('/proj/root')
    Ctor.instance._emit('message', { type: 'error', message: 'boom' })

    expect(sent).toHaveLength(0) // error 不推渲染层
    errSpy.mockRestore()
  })
})
