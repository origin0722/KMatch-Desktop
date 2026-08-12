<template>
  <div class="seg" role="group">
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      class="seg-item"
      :class="{
        active: modelValue === opt.value,
        disabled: opt.disabled,
        [`tone-${opt.tone || 'brand'}`]: modelValue === opt.value,
      }"
      :disabled="opt.disabled || disabled"
      :title="opt.title || opt.label"
      :data-test="opt.test"
      @click="$emit('update:modelValue', opt.value)"
    >{{ opt.label }}</button>
  </div>
</template>

<script setup>
/**
 * SegmentedControl — 分段式胶囊控件 (#28)
 * 替代 el-radio-button: 等宽圆角、激活态语义色填充 + 白字、未选灰字。
 * options: [{ label, value, tone?, disabled?, title?, test? }]
 *   tone: brand(默认) | success(允许) | warning(询问) | danger(禁用)
 */
defineProps({
  modelValue: { type: [String, Number], required: true },
  options: { type: Array, required: true },
  disabled: { type: Boolean, default: false }, // 整体禁用 (如流式传输中锁定)
})
defineEmits(['update:modelValue'])
</script>

<style scoped>
.seg {
  display: inline-flex;
  padding: 3px;
  gap: 3px;
  border-radius: 10px;
  background: var(--km-gray-200);
  border: 1px solid var(--km-border-light);
  flex-shrink: 0;
}
.seg-item {
  flex: 1;
  min-width: 46px;
  padding: 3px 12px;
  border: none;
  border-radius: 7px;
  background: transparent;
  font-size: 12px;
  font-weight: 500;
  color: var(--km-gray-500);
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.18s var(--km-ease), background-color 0.18s var(--km-ease),
    transform 0.12s var(--km-ease), box-shadow 0.18s var(--km-ease);
}
.seg-item:hover:not(.disabled):not(.active) {
  color: var(--km-gray-700);
  background: var(--km-gray-300);
}
.seg-item:active:not(.disabled) { transform: scale(0.96); }
.seg-item.active { color: #fff; }
.seg-item.tone-brand {
  background: var(--km-primary);
  box-shadow: 0 1px 3px rgba(108, 124, 224, 0.4);
}
.seg-item.tone-success {
  background: var(--km-success);
  box-shadow: 0 1px 3px rgba(52, 179, 126, 0.35);
}
.seg-item.tone-warning {
  background: var(--km-warning);
  box-shadow: 0 1px 3px rgba(240, 160, 64, 0.35);
}
.seg-item.tone-danger {
  background: var(--km-danger);
  box-shadow: 0 1px 3px rgba(224, 85, 85, 0.35);
}
.seg-item.disabled { opacity: 0.45; cursor: not-allowed; }
</style>
