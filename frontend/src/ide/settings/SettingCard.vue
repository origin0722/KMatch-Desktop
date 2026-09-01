<template>
  <div class="setting-card">
    <div class="setting-head" :class="{ clickable: collapsible }" @click="toggle">
      <div class="setting-title-row">
        <div class="setting-title">{{ title }}</div>
        <slot name="badge" />
        <span v-if="collapsible" class="setting-caret">{{ open ? '▾' : '▸' }}</span>
      </div>
      <div v-if="info" class="setting-info">{{ info }}</div>
    </div>
    <!-- v-show 保持内容挂载 (状态查询不因折叠丢失), 仅视觉收起 -->
    <div v-show="!collapsible || open" class="setting-control"><slot /></div>
  </div>
</template>

<script setup>
const props = defineProps({
  title: { type: String, required: true },
  info: { type: String, default: '' },
  // collapsible + open (受控): 折叠能力为可选增强, 既有调用方零改动
  collapsible: { type: Boolean, default: false },
  open: { type: Boolean, default: true },
})
const emit = defineEmits(['update:open'])

function toggle() {
  if (props.collapsible) emit('update:open', !props.open)
}
</script>

<style scoped>
.setting-card {
  background: var(--km-bg-layer-2);
  border: 1px solid var(--km-border-light);
  border-radius: var(--km-radius-lg);
  padding: 14px 16px;
  margin-bottom: 12px;
  transition: box-shadow 0.18s var(--km-ease), border-color 0.18s var(--km-ease);
}
.setting-card:hover {
  box-shadow: var(--km-shadow-sm);
  border-color: var(--km-primary-light);
}
.setting-head { margin-bottom: 10px; }
.setting-head.clickable { cursor: pointer; user-select: none; }
.setting-title-row { display: flex; align-items: center; gap: 8px; }
.setting-title { font-size: 13.5px; font-weight: 600; color: var(--km-gray-800); }
.setting-caret { font-size: 11px; color: var(--km-gray-400); margin-left: auto; }
.setting-info { font-size: 12px; color: var(--km-gray-500); margin-top: 2px; line-height: 1.5; }
.setting-control { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
</style>
