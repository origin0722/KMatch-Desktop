/** fileKind — 文件类型判定 (文件内联预览分发) 纯函数单测。 */
import { describe, it, expect } from 'vitest'
import { fileKind, isPreviewKind, isPreviewFile } from '@/utils/fileKind'

describe('fileKind', () => {
  it('按扩展名分发', () => {
    expect(fileKind('a.png')).toBe('image')
    expect(fileKind('a.PNG')).toBe('image')
    expect(fileKind('a.svg')).toBe('image')
    expect(fileKind('README.markdown')).toBe('markdown')
    expect(fileKind('doc.md')).toBe('markdown')
    expect(fileKind('page.html')).toBe('html')
    expect(fileKind('x.htm')).toBe('html')
    expect(fileKind('paper.pdf')).toBe('pdf')
  })

  it('文本/代码 → text (进 Monaco)', () => {
    expect(fileKind('main.py')).toBe('text')
    expect(fileKind('a.js')).toBe('text')
    expect(fileKind('noext')).toBe('text')
    expect(fileKind('')).toBe('text')
  })

  it('isPreviewKind / isPreviewFile 一致', () => {
    expect(isPreviewKind('image')).toBe(true)
    expect(isPreviewKind('markdown')).toBe(true)
    expect(isPreviewKind('html')).toBe(true)
    expect(isPreviewKind('pdf')).toBe(true)
    expect(isPreviewKind('text')).toBe(false)
    expect(isPreviewFile('x.png')).toBe(true)
    expect(isPreviewFile('x.md')).toBe(true)
    expect(isPreviewFile('x.pdf')).toBe(true)
    expect(isPreviewFile('x.py')).toBe(false)
  })
})
