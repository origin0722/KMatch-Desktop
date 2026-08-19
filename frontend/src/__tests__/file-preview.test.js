/** FilePreview — 文件内联预览 (图片/Markdown 安全渲染/HTML sandbox/PDF) 单测。 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// mock mermaid 动态 import → render 抛错 (测试失败降级路径; 成功渲染由浏览器真机覆盖)
vi.mock('mermaid', () => ({ default: {
  initialize() {},
  render: async () => { throw new Error('no-dom') },
} }))

function installApi({ readBase64 = null, readFile = null }) {
  globalThis.window = globalThis.window || {}
  window.api = {
    fs: {
      readBase64: readBase64 || vi.fn(async () => 'QUJD'), // 'ABC'
      readFile: readFile || vi.fn(async () => 'plain'),
    },
  }
  return window.api.fs
}

const FilePreview = (await import('@/ide/FilePreview.vue')).default

describe('FilePreview', () => {
  beforeEach(() => { installApi({}) })

  it('图片: base64 → <img data:image/png>', async () => {
    const w = mount(FilePreview, { props: { relPath: 'assets/logo.png', kind: 'image' } })
    await flushPromises()
    const img = w.find('img.pv-image')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toBe('data:image/png;base64,QUJD')
    expect(window.api.fs.readBase64).toHaveBeenCalledWith('assets/logo.png')
  })

  it('Markdown: marked+DOMPurify 安全渲染 (script 被清掉)', async () => {
    installApi({ readFile: vi.fn(async () => '# 标题\n\n<script>alert(1)</script>') })
    const w = mount(FilePreview, { props: { relPath: 'doc.md', kind: 'markdown' } })
    await flushPromises()
    const md = w.find('.pv-markdown')
    expect(md.html()).toContain('<h1>标题</h1>')
    expect(md.html()).not.toContain('<script')
  })

  it('HTML: sandbox iframe + srcdoc', async () => {
    installApi({ readFile: vi.fn(async () => '<h1>hi</h1>') })
    const w = mount(FilePreview, { props: { relPath: 'page.html', kind: 'html' } })
    await flushPromises()
    const frame = w.find('iframe.pv-frame')
    expect(frame.exists()).toBe(true)
    expect(frame.attributes('sandbox')).toBe('allow-same-origin')
    expect(frame.attributes('srcdoc')).toContain('<h1>hi</h1>')
  })

  it('PDF: base64 data-url iframe', async () => {
    const w = mount(FilePreview, { props: { relPath: 'doc.pdf', kind: 'pdf' } })
    await flushPromises()
    const frame = w.find('iframe.pv-frame')
    expect(frame.attributes('src')).toBe('data:application/pdf;base64,QUJD')
  })

  it('读取失败 → 错误占位, 不崩溃', async () => {
    installApi({ readBase64: vi.fn(async () => { throw new Error('ENOENT') }) })
    const w = mount(FilePreview, { props: { relPath: 'x.png', kind: 'image' } })
    await flushPromises()
    expect(w.find('.pv-error').text()).toContain('ENOENT')
  })

  it('Markdown 含 mermaid 代码块: 渲染失败 → 降级源码块 + 提示 (不崩)', async () => {
    installApi({ readFile: vi.fn(async () => '```mermaid\ngraph TD\nA-->B\n```\n') })
    const w = mount(FilePreview, { props: { relPath: 'd.md', kind: 'markdown' } })
    await flushPromises()
    expect(w.find('.mmd-fallback').exists()).toBe(true)
    expect(w.text()).toContain('Mermaid 渲染失败')
    expect(w.text()).toContain('graph TD')
  })
})
