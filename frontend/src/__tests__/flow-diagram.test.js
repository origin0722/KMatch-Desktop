/**
 * FlowDiagram — 挂载冒烟测试 (Phase 3a)
 *
 * jsdom 无 canvas 2d context → G6 延迟 import 且不初始化; 验证容器渲染、props 传递、
 * 状态变化 watch 不抛错、stages 为空安全。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'

import FlowDiagram from '@/ide/workflow/FlowDiagram.vue'

const STAGES = [
  { key: 'orchestrator', label: '主控调度', icon: '🎯', status: 'done', current: false },
  { key: 'diagnostics', label: '学情检测', icon: '🔍', status: 'running', current: true },
  { key: 'reviewer', label: '内容审核', icon: '⚖️', status: 'idle', current: false },
]

describe('FlowDiagram (只读流程进度)', () => {
  it('jsdom 无 canvas 时安全挂载并渲染容器', () => {
    const w = mount(FlowDiagram, { props: { stages: STAGES } })
    expect(w.find('.flow-canvas').exists()).toBe(true)
    expect(w.vm).toBeTruthy()
    // G6 未初始化 (无 graph), 不抛错
  })

  it('stages 为空时不报错', () => {
    const w = mount(FlowDiagram, { props: { stages: [] } })
    expect(w.find('.flow-canvas').exists()).toBe(true)
  })

  it('stages 变化触发 watch 更新不抛错 (无 canvas 降级路径)', async () => {
    const w = mount(FlowDiagram, { props: { stages: STAGES } })
    await w.setProps({ stages: [...STAGES, { key: 'content_generator', label: '内容生成', icon: '📝', status: 'idle', current: false }] })
    expect(w.find('.flow-canvas').exists()).toBe(true)
  })

  it('自定义高度生效', () => {
    const w = mount(FlowDiagram, { props: { stages: STAGES, height: 120 } })
    expect(w.find('.flow-canvas').attributes('style')).toContain('height: 120px')
  })
})
