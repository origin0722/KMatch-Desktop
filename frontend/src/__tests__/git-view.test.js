/**
 * GitView — Git 仓库面板 (issue-93, 方案A) 单测。
 * mock window.api.git (主进程 git CLI 桥), workspace store 用真实(pinia),
 * ElMessageBox.prompt mock 成可 resolve 以测克隆流程。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { useWorkspaceStore } from '@/stores/workspace'

const mocks = vi.hoisted(() => ({
  check: vi.fn(),
  status: vi.fn(),
  init: vi.fn(),
  clone: vi.fn(),
  pull: vi.fn(),
  commit: vi.fn(),
  push: vi.fn(),
  log: vi.fn(),
  wsSetRoot: vi.fn(),
  wsListRecent: vi.fn(),
  fsListDir: vi.fn(),
}))

vi.mock('element-plus', async (importOriginal) => {
  const orig = await importOriginal()
  return {
    ...orig,
    ElMessageBox: {
      ...orig.ElMessageBox,
      confirm: vi.fn(() => Promise.resolve()),
      prompt: vi.fn(() => Promise.resolve({ value: 'https://github.com/u/r.git' })),
    },
  }
})

const GitView = (await import('@/ide/GitView.vue')).default

describe('GitView Git 仓库面板', () => {
  let pinia
  const REPO = 'D:/demo-repo'

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    vi.clearAllMocks()
    // 默认: Git 可用 + 真仓库
    mocks.check.mockResolvedValue({ ok: true, version: 'git version 2.45.0' })
    mocks.status.mockResolvedValue({
      ok: true, isRepo: true, branch: 'main',
      files: [{ status: '??', path: 'a.py' }, { status: ' M', path: 'b.py' }],
    })
    mocks.log.mockResolvedValue({ ok: true, output: 'abc1234 feat: 新增查看\nabcd5678 fix: 修复问题' })
    mocks.init.mockResolvedValue({ ok: true, output: 'Initialized empty Git repository' })
    mocks.clone.mockResolvedValue({ ok: true, root: 'D:/cloned/r', output: 'Cloning into r...' })
    mocks.pull.mockResolvedValue({ ok: true, output: 'Already up to date.' })
    mocks.commit.mockResolvedValue({ ok: true, output: '[main abc1234] feat: 提交' })
    mocks.push.mockResolvedValue({ ok: true, output: 'Everything up-to-date' })
    mocks.wsSetRoot.mockResolvedValue({ root: 'D:/cloned/r', name: 'r' })
    mocks.wsListRecent.mockResolvedValue([])
    mocks.fsListDir.mockResolvedValue([])
    window.api = {
      git: {
        check: mocks.check, status: mocks.status, init: mocks.init, clone: mocks.clone,
        pull: mocks.pull, commit: mocks.commit, push: mocks.push, log: mocks.log,
      },
      workspace: { setRoot: mocks.wsSetRoot, listRecent: mocks.wsListRecent },
      fs: { listDirectory: mocks.fsListDir },
    }
  })

  it('未检测到 Git → 空态提示安装', async () => {
    mocks.check.mockResolvedValue({ ok: false, error: 'fatal: not found' })
    const w = mount(GitView, { global: { plugins: [pinia, ElementPlus] } })
    await flushPromises()
    expect(w.text()).toContain('未检测到 Git')
    expect(w.text()).toContain('Git for Windows')
    expect(mocks.status).not.toHaveBeenCalled()
  })

  it('未打开项目 → 克隆/打开项目入口', async () => {
    const w = mount(GitView, { global: { plugins: [pinia, ElementPlus] } })
    await flushPromises()
    expect(w.text()).toContain('克隆远程仓库')
    expect(w.text()).toContain('打开本地项目')
    expect(mocks.status).not.toHaveBeenCalled()
  })

  it('已打开项目但非仓库 → 初始化/克隆入口', async () => {
    const ws = useWorkspaceStore()
    ws.root = REPO
    mocks.status.mockResolvedValue({ ok: true, isRepo: false, branch: '', files: [] })
    const w = mount(GitView, { global: { plugins: [pinia, ElementPlus] } })
    await flushPromises()
    expect(w.text()).toContain('还不是 Git 仓库')
    expect(w.text()).toContain('初始化 Git 仓库')
  })

  it('仓库面板: 分支/更改文件(着色)/最近提交渲染', async () => {
    const ws = useWorkspaceStore()
    ws.root = REPO
    const w = mount(GitView, { global: { plugins: [pinia, ElementPlus] } })
    await flushPromises()
    expect(mocks.status).toHaveBeenCalledWith(REPO)
    expect(w.find('[data-test="git-branch"]').text()).toContain('main')
    const files = w.findAll('[data-test="git-file"]')
    expect(files).toHaveLength(2)
    expect(files[0].text()).toContain('未跟踪')
    expect(files[0].text()).toContain('a.py')
    expect(files[1].text()).toContain('修改')
    expect(files[1].text()).toContain('b.py')
    const commits = w.findAll('[data-test="git-commit-item"]')
    expect(commits).toHaveLength(2)
    expect(commits[0].text()).toContain('abc1234')
    expect(commits[0].text()).toContain('feat: 新增查看')
    expect(w.text()).toContain('更改（2）')
  })

  it('提交: 带消息调 commit(stageAll) 并清空输入', async () => {
    const ws = useWorkspaceStore()
    ws.root = REPO
    const w = mount(GitView, { global: { plugins: [pinia, ElementPlus] } })
    await flushPromises()
    await w.find('textarea').setValue('feat: 提交')
    await w.find('[data-test="git-commit"]').trigger('click')
    await flushPromises()
    expect(mocks.commit).toHaveBeenCalledWith({ cwd: REPO, message: 'feat: 提交', stageAll: true })
    expect(w.find('textarea').element.value).toBe('')
  })

  it('克隆: 先输 URL → git.clone → setRoot 切到克隆项目', async () => {
    const w = mount(GitView, { global: { plugins: [pinia, ElementPlus] } })
    await flushPromises()
    await w.find('[data-test="git-view"]').findAll('button').find((b) => b.text().includes('克隆远程仓库')).trigger('click')
    await flushPromises()
    const { ElMessageBox } = await import('element-plus')
    expect(ElMessageBox.prompt).toHaveBeenCalled()
    expect(mocks.clone).toHaveBeenCalledWith({ url: 'https://github.com/u/r.git' })
    expect(mocks.wsSetRoot).toHaveBeenCalledWith('D:/cloned/r')
  })

  it('拉取/推送调用主进程并刷新状态', async () => {
    const ws = useWorkspaceStore()
    ws.root = REPO
    const w = mount(GitView, { global: { plugins: [pinia, ElementPlus] } })
    await flushPromises()
    await w.find('[data-test="git-pull"]').trigger('click')
    await flushPromises()
    expect(mocks.pull).toHaveBeenCalledWith(REPO)
    await w.find('[data-test="git-push"]').trigger('click')
    await flushPromises()
    expect(mocks.push).toHaveBeenCalledWith(REPO)
    // pull 后刷新
    expect(mocks.status.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('初始化仓库: 调 init 并刷新', async () => {
    const ws = useWorkspaceStore()
    ws.root = REPO
    mocks.status.mockResolvedValue({ ok: true, isRepo: false, branch: '', files: [] })
    const w = mount(GitView, { global: { plugins: [pinia, ElementPlus] } })
    await flushPromises()
    const initBtn = w.findAll('button').find((b) => b.text().includes('初始化 Git 仓库'))
    await initBtn.trigger('click')
    await flushPromises()
    expect(mocks.init).toHaveBeenCalledWith(REPO)
  })
})
