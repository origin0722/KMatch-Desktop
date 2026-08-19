/**
 * FileExplorer 懒加载目录树挂载测试
 *
 * 验证: 顶层渲染 / 点目录惰性拉取子项并递归展示 / 空项目占位。jsdom 无真实 IPC,
 * window.api 由测试桩提供。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

const fsTree = {
  null: [
    { name: 'src', path: 'src', isDirectory: true },
    { name: 'README.md', path: 'README.md', isDirectory: false },
  ],
  'src': [{ name: 'main.py', path: 'src/main.py', isDirectory: false }],
}
let calls = []

function installWindowApi() {
  calls = []
  globalThis.window = globalThis.window || {}
  window.api = {
    fs: {
      listDirectory: vi.fn(async (dir) => { calls.push(dir); return fsTree[dir] || [] }),
      readFile: vi.fn(async () => 'x'),
      stat: vi.fn(async () => ({})),
      writeFile: vi.fn(async () => {}),
      onChange: vi.fn(() => () => {}),
    },
    workspace: {
      openProject: vi.fn(async () => ({ root: '/proj', name: 'proj' })),
      setRoot: vi.fn(async () => ({})),
      listRecent: vi.fn(async () => []),
    },
  }
}

const FileExplorer = (await import('@/ide/FileExplorer.vue')).default
const { useWorkspaceStore } = await import('@/stores/workspace')

describe('FileExplorer 懒加载目录树', () => {
  let pinia
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    installWindowApi()
    vi.clearAllMocks()
  })

  it('渲染顶层节点 (不再扁平全量)', async () => {
    const ws = useWorkspaceStore()
    await ws.openProject()
    await nextTick()
    const w = mount(FileExplorer, { global: { plugins: [pinia] } })
    const rows = w.findAll('.ftb-row')
    expect(rows.some((r) => r.text().includes('src'))).toBe(true)
    expect(rows.some((r) => r.text().includes('README'))).toBe(true)
    // 顶层只请求一次
    expect(calls.filter((c) => c === null)).toHaveLength(1)
  })

  it('点击目录 → 惰性拉取子项并递归展示', async () => {
    const ws = useWorkspaceStore()
    await ws.openProject()
    await nextTick()
    const w = mount(FileExplorer, { global: { plugins: [pinia] } })
    await w.findAll('.ftb-row').find((r) => r.text().includes('src')).trigger('click')
    await flushPromises()
    await nextTick()
    expect(calls).toContain('src') // 惰性拉取该目录
    const mainRows = w.findAll('.ftb-row').filter((r) => r.text().includes('main.py'))
    expect(mainRows.length).toBe(1)
  })

  it('空项目显示占位', async () => {
    const ws = useWorkspaceStore()
    window.api.fs.listDirectory.mockImplementation(async () => [])
    await ws.openProject()
    await nextTick()
    const w = mount(FileExplorer, { global: { plugins: [pinia] } })
    expect(w.text()).toContain('空项目')
  })
})
