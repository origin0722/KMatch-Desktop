<template>
  <div class="workspace-placeholder">
    <!-- 阶段0: 承载场景二入口(项目上传); 阶段1 将替换为完整 IDE 壳(Monaco + 文件树 + AI 助手面板) -->
    <ProjectUpload v-if="!ideReady" />
    <div v-else class="ide-shell">
      <!-- 阶段1: ActivityBar + FileExplorer + MonacoEditor + AssistantPanel -->
      <p>IDE 工作区(建设中)</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import ProjectUpload from './ProjectUpload.vue'

// 阶段0 先复用现有 ProjectUpload 视图; 阶段1 切换为完整 IDE 壳
const ideReady = ref(false)
</script>

<style scoped>
.workspace-placeholder {
  height: 100%;
  overflow: auto;
  padding: 20px;
  background-color: #f0f2f5;
}
</style>
