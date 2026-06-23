/**
 * 场景：响应式 Map/Set helper (F11)。
 *
 * Vue ref(Map/Set) 的 mutation 不触发响应式; 旧代码手写 new Map(...) 重赋易漏。
 * helper 封装 mutation 后自动 trigger (重新赋值)。验证: mutation 后 ref 引用变化 + 业务方法正确。
 */
import { describe, it, expect } from 'vitest'
import { useReactiveMap, useReactiveSet } from '@/ide/useReactiveCollection'

describe('useReactiveCollection (F11)', () => {
  it('useReactiveMap: set/delete/clear 改变 ref 引用 (触发响应式) + 业务正确', () => {
    const m = useReactiveMap()
    const ref0 = m.ref.value
    m.set('a', 1)
    expect(m.get('a')).toBe(1)
    expect(m.has('a')).toBe(true)
    expect(m.size).toBe(1)
    expect(m.ref.value).not.toBe(ref0) // 引用变 → 响应式可触发

    const ref1 = m.ref.value
    m.set('b', 2)
    expect(m.ref.value).not.toBe(ref1)

    m.delete('a')
    expect(m.has('a')).toBe(false)
    expect(m.size).toBe(1)

    m.clear()
    expect(m.size).toBe(0)
  })

  it('useReactiveMap: delete 不存在的 key 不改变引用 (无谓 trigger)', () => {
    const m = useReactiveMap()
    const ref0 = m.ref.value
    m.delete('absent')
    expect(m.ref.value).toBe(ref0) // 未触发
  })

  it('useReactiveSet: add/delete/clear 改变 ref 引用 + 业务正确', () => {
    const s = useReactiveSet()
    const ref0 = s.ref.value
    s.add('a.py')
    expect(s.has('a.py')).toBe(true)
    expect(s.size).toBe(1)
    expect(s.ref.value).not.toBe(ref0)

    s.add('b.py')
    expect(s.size).toBe(2)

    s.delete('a.py')
    expect(s.has('a.py')).toBe(false)
    expect(s.size).toBe(1)

    s.clear()
    expect(s.size).toBe(0)
  })

  it('useReactiveSet: delete 不存在的 key 不改变引用', () => {
    const s = useReactiveSet()
    const ref0 = s.ref.value
    s.delete('absent')
    expect(s.ref.value).toBe(ref0)
  })

  it('初始值支持', () => {
    const m = useReactiveMap([['k', 'v']])
    const s = useReactiveSet(['x'])
    expect(m.get('k')).toBe('v')
    expect(s.has('x')).toBe(true)
  })
})
