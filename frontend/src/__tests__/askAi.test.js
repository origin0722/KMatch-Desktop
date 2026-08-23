/**
 * utils/askAi 问题构造单测 (P1)
 *
 * buildNodeQuestion / buildEntityQuestion 为纯函数: 图谱视图/项目图谱视图
 * 收集上下文后调它生成预填文本, 经 chat.setDraft 带入助手输入框。
 * 断言关键字段进入文本 (节点名/难度/掌握度/关键点/实体名/调用关系)。
 */
import { describe, it, expect } from 'vitest'
import { buildNodeQuestion, buildEntityQuestion, GRAPH_GUIDE_PROMPT, graphGuidePrompt } from '@/utils/askAi'

describe('graphGuidePrompt (issue-70: 知识图谱导读对话化)', () => {
  it('导读预填含对话式导航 + 查证要求', () => {
    expect(GRAPH_GUIDE_PROMPT).toContain('导读')
    expect(GRAPH_GUIDE_PROMPT).toContain('对话')
    expect(GRAPH_GUIDE_PROMPT).toContain('查证')
    expect(graphGuidePrompt()).toBe(GRAPH_GUIDE_PROMPT)
  })
})

describe('buildNodeQuestion', () => {
  const node = {
    node_id: 'PY-014',
    name: '列表推导式',
    difficulty: 3,
    mastery: 0.4,
    summary: '用一行生成列表的简洁语法。',
    key_points: ['[表达式 for 变量 in 可迭代]', '可带 if 过滤', '可嵌套', '可加 else', '第五个不展示'],
  }

  it('包含节点名、难度星、掌握度百分比', () => {
    const q = buildNodeQuestion(node)
    expect(q).toContain('列表推导式')
    expect(q).toContain('⭐⭐⭐')
    expect(q).toContain('40%')
  })

  it('key_points 至多展示 4 条', () => {
    const q = buildNodeQuestion(node)
    expect(q).toContain('可嵌套')
    expect(q).toContain('可加 else')
    expect(q).not.toContain('第五个不展示')
  })

  it('前置依赖名至多 6 个', () => {
    const prereqs = Array.from({ length: 8 }, (_, i) => `前置${i}`)
    const q = buildNodeQuestion(node, prereqs)
    expect(q).toContain('前置0')
    expect(q).toContain('前置5')
    expect(q).not.toContain('前置6')
  })

  it('含苏格拉底式引导语 (先问卡在哪, 不直接给答案)', () => {
    const q = buildNodeQuestion(node)
    expect(q).toContain('先问我目前卡在哪')
    expect(q).toContain('不要直接灌输答案')
  })

  it('空节点不抛错, 回退到"未知知识点"', () => {
    const q = buildNodeQuestion(null)
    expect(q).toContain('未知知识点')
    expect(q).toContain('0%')
  })
})

describe('buildEntityQuestion', () => {
  const entity = {
    name: 'parse_config',
    kind: 'function',
    qualified_name: 'app.utils.parse_config',
    line_start: 42,
    line_end: 60,
  }

  it('包含实体全名、类型、行范围', () => {
    const q = buildEntityQuestion(entity, { sourcePath: 'app/utils.py' })
    expect(q).toContain('app.utils.parse_config')
    expect(q).toContain('function')
    expect(q).toContain('app/utils.py')
    expect(q).toContain('第 42-60 行')
  })

  it('展示调用 / 被调用关系 (至多 8)', () => {
    const out = Array.from({ length: 10 }, (_, i) => `out_${i}`)
    const inn = ['main']
    const q = buildEntityQuestion(entity, { callsOut: out, callsIn: inn })
    expect(q).toContain('out_0')
    expect(q).toContain('out_7')
    expect(q).not.toContain('out_8')
    expect(q).toContain('main')
  })

  it('无 sourcePath 时回退"当前项目"', () => {
    const q = buildEntityQuestion(entity, {})
    expect(q).toContain('当前项目')
  })

  it('空实体不抛错', () => {
    const q = buildEntityQuestion(null)
    expect(q).toContain('未知')
    expect(q).toContain('当前项目')
  })
})
