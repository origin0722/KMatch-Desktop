import { describe, it, expect } from 'vitest'
import { capabilityOf, formatContext } from '@/services/llm/modelCapabilities'

describe('capabilityOf', () => {
  it.each([
    ['openai',    'o1',                  'native',      128_000],
    ['openai',    'o3-mini',             'native',      128_000],
    ['openai',    'gpt-4.1',             'prompt-only', 1_000_000],
    ['openai',    'gpt-4o',              'prompt-only', 128_000],
    ['deepseek',  'deepseek-v4-pro',     'native',      128_000],
    ['deepseek',  'deepseek-reasoner',   'native',      64_000],
    ['deepseek',  'deepseek-v3',         'prompt-only', null],
    ['anthropic', 'claude-fable-5',      'native',      200_000],
    ['anthropic', 'claude-opus-4-8',     'native',      200_000],
    ['qwen',      'qwen-max',            'prompt-only', 128_000],
    ['gemini',    'gemini-2.5-pro',      'native',      1_000_000],
  ])('%s/%s -> reasoning=%s context=%s', (provider, model, reasoning, context) => {
    const cap = capabilityOf(provider, model)
    expect(cap.reasoning).toBe(reasoning)
    expect(cap.context).toBe(context)
  })

  it('falls back to prompt-only/null for unknown provider+model', () => {
    expect(capabilityOf('unknown', 'foo-bar')).toEqual({ reasoning: 'prompt-only', context: null })
  })

  it('custom:<uuid> falls back to prompt-only', () => {
    expect(capabilityOf('custom:default', 'whatever-7b').reasoning).toBe('prompt-only')
  })

  it('formatContext renders 1M / 128K / null', () => {
    expect(formatContext(1_000_000)).toBe('1M')
    expect(formatContext(128_000)).toBe('128K')
    expect(formatContext(null)).toBe('')
  })
})
