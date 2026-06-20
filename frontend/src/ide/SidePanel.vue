<template>
  <div class="side-panel">
    <FileExplorer />
  </div>
</template>

<script setup>
import FileExplorer from './FileExplorer.vue'
</script>

<style scoped>
.side-panel {
  width: 240px;
  background: var(--kbg-sidebar);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  height: 100%;
  border-right: 1px solid var(--kborder);
}
</style>
