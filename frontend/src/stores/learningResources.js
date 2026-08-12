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

  /**
   * #30 后续: 针对性反馈返回的 web_link 网址直入「学习资源」联网资源 tab。
   * 与 addWebResources 的区别: 接受后端 feedback 接口直出形态 (content/target_node_id,
   * 非 {snippet, query} 搜索形态), 保留 target_node_id 供溯源, 仍按 url 去重置顶。
   */
  function addFeedbackLinks(links) {
    const existing = new Set(webResources.value.map((r) => r.url))
    const fresh = (links || [])
      .filter((r) => r.url && !existing.has(r.url))
      .map((r) => ({
        content_type: 'web_link',
        title: r.title || r.url,
        url: r.url,
        content: r.content || r.snippet || '',
        target_node_id: r.target_node_id,
        added_at: Date.now(),
      }))
    webResources.value = [...fresh, ...webResources.value]
  }

  function clear() {
    webResources.value = []
  }

  return { webResources, addWebResources, addFeedbackLinks, clear }
})
