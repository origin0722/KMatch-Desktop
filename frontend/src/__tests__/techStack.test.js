import { describe, it, expect } from 'vitest'
import { detectTechStack } from '@/utils/techStack'

describe('detectTechStack', () => {
  it('returns empty array for empty input', () => {
    expect(detectTechStack([])).toEqual([])
    expect(detectTechStack(null)).toEqual([])
    expect(detectTechStack(undefined)).toEqual([])
  })

  it('detects known tech from external_calls', () => {
    const entities = [
      { external_calls: ['requests.get', 'requests.post'] },
      { external_calls: ['pandas.DataFrame', 'numpy.array'] },
    ]
    const result = detectTechStack(entities)
    expect(result).toHaveLength(3)
    const names = result.map((t) => t.name)
    expect(names).toContain('Requests')
    expect(names).toContain('Pandas')
    expect(names).toContain('NumPy')
  })

  it('counts references across entities', () => {
    const entities = [
      { external_calls: ['flask.Flask', 'flask.request'] },
      { external_calls: ['flask.jsonify'] },
      { external_calls: ['requests.get'] },
    ]
    const result = detectTechStack(entities)
    const flask = result.find((t) => t.name === 'Flask')
    expect(flask.count).toBe(3)
    const requests = result.find((t) => t.name === 'Requests')
    expect(requests.count).toBe(1)
  })

  it('sorts by count descending', () => {
    const entities = [
      { external_calls: ['requests.get', 'pandas.read_csv', 'pandas.DataFrame'] },
      { external_calls: ['flask.Flask'] },
    ]
    const result = detectTechStack(entities)
    expect(result[0].count).toBeGreaterThanOrEqual(result[1].count)
    expect(result[0].name).toBe('Pandas') // 2 references
  })

  it('handles object-form external_calls', () => {
    const entities = [
      { external_calls: [{ name: 'django.conf' }, { name: 'django.http' }] },
    ]
    const result = detectTechStack(entities)
    expect(result).toHaveLength(1)
    expect(result[0].name).toBe('Django')
    expect(result[0].category).toBe('Web 框架')
  })

  it('ignores unknown modules', () => {
    const entities = [
      { external_calls: ['my_custom_module.do_stuff', 'requests.get'] },
    ]
    const result = detectTechStack(entities)
    expect(result).toHaveLength(1)
    expect(result[0].name).toBe('Requests')
  })

  it('handles entities without external_calls', () => {
    const entities = [
      { name: 'foo', kind: 'function' },
      { external_calls: ['pytest.fixture'] },
    ]
    const result = detectTechStack(entities)
    expect(result).toHaveLength(1)
    expect(result[0].name).toBe('pytest')
    expect(result[0].category).toBe('测试')
  })

  it('merges aliases mapping to same tech', () => {
    const entities = [
      { external_calls: ['yaml.safe_load', 'pyyaml.dump'] },
    ]
    const result = detectTechStack(entities)
    const yaml = result.find((t) => t.name === 'PyYAML')
    expect(yaml.count).toBe(2)
  })

  it('includes category field', () => {
    const entities = [{ external_calls: ['torch.nn', 'torch.optim'] }]
    const result = detectTechStack(entities)
    expect(result[0].name).toBe('PyTorch')
    expect(result[0].category).toBe('机器学习')
  })
})
