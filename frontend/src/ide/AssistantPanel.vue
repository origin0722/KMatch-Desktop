<template>
  <div class="assistant-panel">
    <div class="assistant-header">
      <span class="assistant-title">
        <el-icon :size="15"><ChatDotRound /></el-icon>&nbsp;AI 助手
      </span>
      <el-icon class="icon-btn" title="收起" @click="sidebar.toggleAiPanel()"><Close /></el-icon>
    </div>

    <div class="assistant-body">
      <!-- 阶段2 起: 消息流 + 工具卡。当前占位 -->
      <div class="placeholder">
        <el-icon :size="40" color="var(--ktext-muted)"><ChatLineSquare /></el-icon>
        <p class="ph-title">AI 助手</p>
        <p class="ph-hint">阶段2 接入:多模型对话 + 工具调用 + 权限审批</p>
        <div class="ph-features">
          <div class="feat">💬 多模型对话 (DeepSeek/OpenAI/千问)</div>
          <div class="feat">🔧 工具: 读写文件 / 跑命令</div>
          <div class="feat">🕸 委派: 代码审查 / 测试 / 项目图谱</div>
          <div class="feat">🔒 敏感操作需审批</div>
        </div>
      </div>
    </div>

    <!-- 输入框 (占位, 阶段2 接通) -->
    <div class="assistant-input">
      <el-input
        placeholder="阶段2 接入后可对话…"
        disabled
        :prefix-icon="Promotion"
      />
    </div>
  </div>
</template>

<script setup>
import { Promotion } from '@element-plus/icons-vue'
import { useSidebarStore } from '@/stores/sidebar'
const sidebar = useSidebarStore()
</script>

<style scoped>
.assistant-panel {
  width: 340px;
  background: var(--kbg-sidebar);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  height: 100%;
  border-left: 1px solid var(--kborder);
}
.assistant-header {
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  border-bottom: 1px solid var(--kborder);
  flex-shrink: 0;
}
.assistant-title {
  display: flex; align-items: center;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--ktext-secondary);
  font-weight: 600;
}
.icon-btn { cursor: pointer; color: var(--ktext-secondary); }
.icon-btn:hover { color: var(--ktext); }

.assistant-body {
  flex: 1;
  overflow-y: auto;
  display: flex;
}
.placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 24px;
  text-align: center;
}
.ph-title { font-size: 15px; font-weight: 600; color: var(--ktext); margin-top: 6px; }
.ph-hint { font-size: 12px; color: var(--ktext-muted); margin-bottom: 14px; }
.ph-features {
  display: flex; flex-direction: column; gap: 8px;
  width: 100%;
}
.feat {
  font-size: 12px;
  color: var(--ktext-secondary);
  background: var(--kbg-hover);
  padding: 8px 12px;
  border-radius: 6px;
  text-align: left;
}

.assistant-input {
  padding: 10px 12px;
  border-top: 1px solid var(--kborder);
  flex-shrink: 0;
}
</style>
