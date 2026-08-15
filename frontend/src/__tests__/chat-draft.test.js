/**
 * 图谱"问 AI"预填通路单测 (P1)
 *
 * chat.draft: 图谱/项目图谱详情面板 setDraft 预填 → AssistantPanel 绑定带出,
 * 用户可编辑后发送 (sendMessage 后清空)。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

import { useChatStore } from '@/stores/chat'

describe('chat.draft 预填通路', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('初始为空串', () => {
    const chat = useChatStore()
    expect(chat.draft).toBe('')
  })

  it('setDraft 预填 / 传 null 归零', () => {
    const chat = useChatStore()
    chat.setDraft('我在学习图谱里遇到了知识点「列表」…')
    expect(chat.draft).toBe('我在学习图谱里遇到了知识点「列表」…')
    chat.setDraft(null)
    expect(chat.draft).toBe('')
  })

  it('跨组件共享: 同一 pinia 实例两处读写一致 (图谱视图预填 → chat 视图带出)', () => {
    const writer = useChatStore()   // 模拟 KnowledgeGraph 视图
    const reader = useChatStore()   // 模拟 AssistantPanel
    writer.setDraft('请解释这个实体')
    expect(reader.draft).toBe('请解释这个实体')
    reader.draft = '改一下再发'      // AssistantPanel 输入框可编辑
    expect(writer.draft).toBe('改一下再发')
  })
})
