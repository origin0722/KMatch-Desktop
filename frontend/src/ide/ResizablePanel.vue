<template>
  <div class="resizable-panel" :style="{ width: `${width}px` }">
    <div class="panel-body"><slot /></div>
    <div
      class="resize-divider"
      :class="{ dragging, 'side-left': side === 'left' }"
      @pointerdown.prevent="onDown"
    />
  </div>
</template>

<script setup>
/**
 * ResizablePanel — 可拖拽宽度面板 (#25)
 * 包裹任意侧栏/面板: 边缘 4px 拖拽条, 拖动实时更新宽度, 松手落 localStorage 持久化.
 * side: 'right' 拖右缘 (NavSidebar/FileExplorer), 'left' 拖左缘 (AssistantPanel).
 * 拖动中临时禁用文本选中 + 全局 col-resize 光标; 松手派发 resize 通知 Monaco/G6 重算.
 */
import { ref, onUnmounted } from 'vue'

const props = defineProps({
  panelKey: { type: String, required: true }, // localStorage 键 (刷新保持)
  min: { type: Number, default: 160 },
  max: { type: Number, default: 480 },
  side: { type: String, default: 'right' },
  initial: { type: Number, default: 240 },
})

function clamp(v) { return Math.min(props.max, Math.max(props.min, v)) }

const width = ref(clamp(Number(localStorage.getItem(props.panelKey)) || props.initial))
const dragging = ref(false)
let startX = 0
let startW = 0
let rafId = 0

function onDown(e) {
  dragging.value = true
  startX = e.clientX
  startW = width.value
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}
// 性能(F): pointermove 高频 → rAF 合并, 一帧只写一次宽度 (少布局抖动)
function onMove(e) {
  if (rafId) return
  const d = props.side === 'right' ? e.clientX - startX : startX - e.clientX
  rafId = requestAnimationFrame(() => {
    rafId = 0
    width.value = clamp(startW + d)
  })
}
function onUp() {
  if (rafId) { cancelAnimationFrame(rafId); rafId = 0 }
  dragging.value = false
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', onUp)
  localStorage.setItem(props.panelKey, String(width.value))
  // 通知依赖容器尺寸的组件 (Monaco / G6) 重算布局
  window.dispatchEvent(new Event('resize'))
}
onUnmounted(onUp)
</script>

<style scoped>
.resizable-panel {
  position: relative;
  will-change: width; /* 性能(F): 拖动时提示合成器独立层, 减少重排范围 */
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  min-width: 0;
  min-height: 0;
}
.panel-body {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
}
.resize-divider {
  position: absolute;
  top: 0; bottom: 0;
  width: 4px;
  z-index: 20;
  cursor: col-resize;
  transition: background-color 0.15s var(--km-ease);
}
.resize-divider.side-left { left: -2px; }
.resize-divider:not(.side-left) { right: -2px; }
.resize-divider:hover,
.resize-divider.dragging {
  background: var(--km-primary);
  opacity: 0.4;
}
</style>
