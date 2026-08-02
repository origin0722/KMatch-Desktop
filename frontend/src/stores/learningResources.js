/**
 * 学习资源 store - AI 联网搜索结果 (web_link 资源) 单一源
 *
 * AI 助手 web_search 工具调用后, 结果存入此 store, Learning.vue "联网资源" tab 读取展示。
 * 独立于 assessment.generatedContent.resources (学情生成的讲义/实操/测试), 两者在 Learning.vue 合并。
 *
 * 新结果置顶, 按 url 去重; clear 清空。
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'

export const useLearningResourcesStore = defineStore('learningResources', () => {
  const webResources = ref([])

  function addWebResources(query, results) {
    const existing = new Set(webResources.value.map((r) => r.url))
    const fresh = (results || [])
      .filter((r) => r.url && !existing.has(r.url))
      .map((r) => ({
        content_type: 'web_link',
        title: r.title || r.url,
        url: r.url,
        content: r.snippet || '',
        query: query || '',
        added_at: Date.now(),
      }))
    webResources.value = [...fresh, ...webResources.value]
  }

  function clear() {
    webResources.value = []
  }

  return { webResources, addWebResources, clear }
})
