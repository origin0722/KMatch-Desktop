/**
 * 场景：工作台样式加载顺序与 token 完整性守卫。
 *
 * 1) main.js 必须在 theme.css（设计 token 基底）之后才 import workbench.css，
 *    保证工作台样式能覆盖主题变量、CSS 变量级联顺序不被颠倒。
 * 2) workbench.css 须声明一组可复用工作台类（.km-workbench / .km-surface / .km-mono-number 等），
 *    防止漏定义导致阶段7 主题收编后的视图样式回退失效。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

describe('workbench style primitives', () => {
  it('main imports workbench.css after theme.css', () => {
    const main = fs.readFileSync(path.resolve(__dirname, '../main.js'), 'utf8')
    const themeImport = "import './styles/theme.css'"
    const workbenchImport = "import './styles/workbench.css'"

    expect(main).toContain(workbenchImport)
    expect(main.indexOf(workbenchImport)).toBeGreaterThan(main.indexOf(themeImport))
  })

  it('defines reusable workbench classes', () => {
    const css = fs.readFileSync(path.resolve(__dirname, '../styles/workbench.css'), 'utf8')

    expect(css).toContain('.km-workbench')
    expect(css).toContain('.km-workbench-header')
    expect(css).toContain('.km-workbench-kicker')
    expect(css).toContain('.km-workbench-title')
    expect(css).toContain('.km-workbench-desc')
    expect(css).toContain('.km-surface')
    expect(css).toContain('.km-surface-quiet')
    expect(css).toContain('.km-empty-state')
    expect(css).toContain('.km-evidence-list')
    expect(css).toContain('.km-evidence-row')
    expect(css).toContain('.km-mono-number')
  })
})
