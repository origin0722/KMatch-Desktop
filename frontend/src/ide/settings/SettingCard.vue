<template>
  <div class="setting-card">
    <div class="setting-head">
      <div class="setting-title">{{ title }}</div>
      <div v-if="info" class="setting-info">{{ info }}</div>
    </div>
    <div class="setting-control"><slot /></div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  info: { type: String, default: '' },
})
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
.setting-title { font-size: 13.5px; font-weight: 600; color: var(--km-gray-800); }
.setting-info { font-size: 12px; color: var(--km-gray-500); margin-top: 2px; line-height: 1.5; }
.setting-control { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
</style>
