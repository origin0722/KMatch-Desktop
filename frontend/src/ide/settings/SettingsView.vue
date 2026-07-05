<template>
  <div class="settings-view">
    <div ref="mainEl" class="settings-main" @scroll="onScroll">
      <div class="settings-content">
        <section id="sec-assistant" ref="secAssistant" class="settings-section">
          <h2 class="section-title">AI 助手</h2>
          <AssistantSettings />
        </section>
        <section id="sec-agent" ref="secAgent" class="settings-section">
          <h2 class="section-title">Agent 学习引擎</h2>
          <AgentSettings />
        </section>
        <section id="sec-providers" ref="secProviders" class="settings-section">
          <h2 class="section-title">供应商管理</h2>
          <ProvidersSettings />
        </section>
      </div>
    </div>
    <aside class="settings-anchors">
      <a
        v-for="a in anchors"
        :key="a.id"
        class="settings-anchor"
        :class="{ active: activeAnchor === a.id }"
        @click="scrollTo(a.id)"
      >{{ a.label }}</a>
    </aside>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import AssistantSettings from './AssistantSettings.vue'
import AgentSettings from './AgentSettings.vue'
import ProvidersSettings from './ProvidersSettings.vue'

const anchors = [
  { id: 'sec-assistant', label: 'AI 助手' },
  { id: 'sec-agent', label: 'Agent 学习引擎' },
  { id: 'sec-providers', label: '供应商管理' },
]

const mainEl = ref(null)
const activeAnchor = ref('sec-assistant')
let observer = null

function scrollTo(id) {
  activeAnchor.value = id
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function onScroll() {
  // 兜底: IntersectionObserver 在某些环境不触发时, 按滚动位置近似
  if (!mainEl.value) return
  const tops = anchors.map((a) => {
    const el = document.getElementById(a.id)
    return { id: a.id, top: el ? el.getBoundingClientRect().top : Infinity }
  })
  // 选 top 最接近 0 且 >= 负高度一半的段
  const visible = tops.filter((t) => t.top < 120)
  if (visible.length) activeAnchor.value = visible[visible.length - 1].id
}

onMounted(async () => {
  await nextTick()
  if (!('IntersectionObserver' in window) || !mainEl.value) return
  observer = new IntersectionObserver(
    (entries) => {
      const entering = entries.filter((e) => e.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (entering[0]) activeAnchor.value = entering[0].target.id
    },
    { root: mainEl.value, rootMargin: '-20% 0px -70% 0px', threshold: 0 },
  )
  anchors.forEach((a) => {
    const el = document.getElementById(a.id)
    if (el) observer.observe(el)
  })
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<style scoped>
.settings-view {
  display: flex;
  height: 100%;
  min-height: 0;
  background: var(--km-bg-layer-1);
}
.settings-main {
  flex: 1;
  overflow-y: auto;
  scroll-behavior: smooth;
}
.settings-content {
  max-width: 760px;
  margin: 0 auto;
  padding: 24px 28px 60px;
}
.settings-section { margin-bottom: 8px; scroll-margin-top: 16px; }
.section-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--km-gray-800);
  margin: 20px 0 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--km-border-light);
}
.settings-anchors {
  width: 160px;
  flex-shrink: 0;
  padding: 28px 16px;
  border-left: 1px solid var(--km-border-light);
  position: sticky;
  top: 0;
  align-self: flex-start;
}
.settings-anchor {
  display: block;
  padding: 6px 10px;
  margin-bottom: 4px;
  font-size: 12.5px;
  color: var(--km-gray-500);
  border-radius: var(--km-radius-sm);
  cursor: pointer;
  border-left: 2px solid transparent;
  transition: color 0.16s var(--km-ease), background 0.16s var(--km-ease), border-color 0.16s var(--km-ease);
}
.settings-anchor:hover { color: var(--km-gray-700); background: var(--km-gray-100); }
.settings-anchor.active {
  color: var(--km-primary-active);
  border-left-color: var(--km-primary-active);
  background: var(--km-primary-light);
}
</style>
