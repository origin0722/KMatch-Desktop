/**
 * flowEditing — 流程定义编辑状态 (Phase 3b) 纯逻辑单测
 */
import { describe, it, expect } from 'vitest'
import { createFlowEditor } from '@/composables/flowEditing'

const BASE = {
  format: 'kmatch.workflow',
  version: 1,
  id: 'my-flow',
  name: '我的流程',
  description: 'd',
  stages: [
    { id: 'a', label: 'A', agents: ['diagnostics'], dependencies: [] },
    { id: 'b', label: 'B', agents: ['reviewer'], dependencies: ['a'] },
    { id: 'c', label: 'C', agents: ['graph_controller'], dependencies: ['b'] },
  ],
  decisions: [{ id: 'strategy', label: '反馈策略', on: 'x', rules: [{ else: 'scaffold' }] }],
}

describe('flowEditing', () => {
  it('从定义初始化并深拷贝状态', () => {
    const ed = createFlowEditor(BASE)
    expect(ed.state.stages).toHaveLength(3)
    expect(ed.state.stages[1].dependencies).toEqual(['a'])
    // 深拷贝: 改编辑态不影响原定义
    ed.state.stages[0].label = 'A2'
    expect(BASE.stages[0].label).toBe('A')
  })

  it('addStage/removeStage, remove 会清理他人依赖', () => {
    const ed = createFlowEditor(BASE)
    ed.addStage('z')
    expect(ed.state.stages).toHaveLength(4)
    ed.removeStage(0) // 移除 a (b 依赖 a → 清理; c 依赖 b → 保留)
    expect(ed.state.stages.find((s) => s.id === 'b').dependencies).toEqual([])
    expect(ed.state.stages.find((s) => s.id === 'c').dependencies).toEqual(['b'])
  })

  it('addDependency 只允许更早阶段, 拒绝自身/乱序', () => {
    const ed = createFlowEditor(BASE)
    // c(下标2) 依赖 a(下标0) → 成功
    expect(ed.addDependency(2, 'a')).toBe(true)
    // c 依赖自身 → 拒绝
    expect(ed.addDependency(2, 'c')).toBe(false)
    // a(下标0) 依赖 b(下标1, 更晚) → 拒绝
    expect(ed.addDependency(0, 'b')).toBe(false)
    // 重复添加幂等
    ed.addDependency(2, 'a')
    expect(ed.state.stages[2].dependencies.filter((x) => x === 'a')).toHaveLength(1)
  })

  it('moveStage 后清理悬垂依赖', () => {
    const ed = createFlowEditor(BASE)
    ed.moveStage(2, 0) // c 移到最前, c 依赖 b(现在更晚) → 悬垂被清
    expect(ed.state.stages[0].id).toBe('c')
    expect(ed.state.stages[0].dependencies).toEqual([])
  })

  it('setStageLabel / setStageAgents', () => {
    const ed = createFlowEditor(BASE)
    ed.setStageLabel(1, 'B-新')
    ed.setStageAgents(1, ['content_generator'])
    expect(ed.state.stages[1].label).toBe('B-新')
    expect(ed.state.stages[1].agents).toEqual(['content_generator'])
  })

  it('localIssues: 重复 id / 未知 Agent / 缺 id', () => {
    const ed = createFlowEditor({ ...BASE, stages: [
      { id: 'a', label: 'A', agents: ['ghost'], dependencies: [] },
      { id: 'a', label: 'A2', agents: [], dependencies: [] },
    ] })
    const issues = ed.localIssues()
    expect(issues.some((i) => i.includes('重复'))).toBe(true)
    expect(issues.some((i) => i.includes('未知 Agent: ghost'))).toBe(true)
    expect(issues.some((i) => i.includes('缺 Agents'))).toBe(true)
  })

  it('buildDefinition 输出 command 可用 shape 且 decisions 深拷贝', () => {
    const ed = createFlowEditor(BASE)
    const built = ed.buildDefinition()
    expect(built.format).toBe('kmatch.workflow')
    expect(built.id).toBe('my-flow')
    expect(built.stages[1].dependencies).toEqual(['a'])
    expect(built.decisions).toHaveLength(1)
    // 改 built 不影响 state / 改 state 不影响 built (已序列化副本)
    built.decisions[0].id = 'x2'
    expect(ed.state.decisions[0].id).toBe('strategy')
  })

  it('previewEdges 由依赖生成 source→target', () => {
    const ed = createFlowEditor(BASE)
    expect(ed.previewEdges()).toEqual([{ source: 'a', target: 'b' }, { source: 'b', target: 'c' }])
  })

  it('reset 回到新定义', () => {
    const ed = createFlowEditor(BASE)
    ed.addStage('extra')
    ed.reset({ id: 'other', name: '另一个', stages: [{ id: 'x', label: 'X', agents: ['reviewer'], dependencies: [] }] })
    expect(ed.state.id).toBe('other')
    expect(ed.state.stages).toHaveLength(1)
  })
})
