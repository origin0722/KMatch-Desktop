<template>
  <!-- issue-63: 联网搜索配置段 — Tavily key + 网络代理 (原散在 ProvidersSettings 里) -->
  <div class="web-search-settings">
    <SettingCard title="联网搜索 (Tavily)" info="AI 助手 web_search / 按薄弱点搜索 / 学情反馈时检索教程与文档; 配置后下次搜索生效">
      <div class="tavily-guide">
        <p>① 前往 <a href="https://tavily.com" target="_blank" rel="noopener">tavily.com</a> 注册 (免费 1000 次/月)</p>
        <p>② 在 Dashboard 复制 API Key</p>
        <p>③ 粘贴到下方并保存</p>
      </div>
      <el-input v-model="tavilyInput" type="password" show-password size="small" style="width: 260px"
                placeholder="tvly-..." data-test="tavily-key" @change="saveTavily" @keyup.enter="saveTavily" />
      <el-button size="small" type="primary" @click="saveTavily">保存</el-button>
      <span v-if="!ai.tavilyKey" class="tavily-hint">未配置则不联网搜索, 只返回 LLM 讲义</span>
    </SettingCard>

    <SettingCard title="网络代理" info="所有 LLM 出站请求通过此代理（影响后端 sidecar 进程）；改后需重启后端生效">
      <el-switch :model-value="ai.proxy.enabled" data-test="proxy-enabled"
                 @change="onProxyChange({ enabled: $event })" />
      <template v-if="ai.proxy.enabled">
        <el-input :model-value="ai.proxy.url" size="small" style="width: 240px"
                  placeholder="http://127.0.0.1:7890" data-test="proxy-url"
                  @change="onProxyChange({ url: $event })" />
        <el-select :model-value="ai.proxy.type" size="small" style="width: 110px"
                   @change="onProxyChange({ type: $event })">
          <el-option label="HTTP" value="http" />
          <el-option label="SOCKS5" value="socks5" />
        </el-select>
        <el-button size="small" type="primary" @click="restartBackend" :loading="restarting">重启后端</el-button>
      </template>
    </SettingCard>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAiSettingsStore } from '@/stores/aiSettings'
import SettingCard from './SettingCard.vue'

const ai = useAiSettingsStore()

// Tavily key 本地镜像: 输入流畅, 失焦/回车 @change 持久化
const tavilyInput = ref(ai.tavilyKey || '')
watch(() => ai.tavilyKey, (v) => { tavilyInput.value = v || '' })
function saveTavily() {
  ai.setTavilyKey(tavilyInput.value)
  ElMessage.success(tavilyInput.value ? 'Tavily Key 已保存' : '已清除 Tavily Key')
}

// 网络代理: 盘活 aiSettings.proxy; 落盘 + sidecar env 注入已接线 (Spec B 18-19 / issue-49)
const restarting = ref(false)
function onProxyChange(patch) {
  ai.setProxy(patch)
  window.api?.setProxyConfig?.(ai.proxy)
}
async function restartBackend() {
  restarting.value = true
  try { await window.api?.restartBackend?.() } finally { restarting.value = false }
}
</script>

<style scoped>
.tavily-guide { font-size: 12px; color: var(--km-gray-500); margin-bottom: 8px; line-height: 1.6; }
.tavily-guide p { margin: 0; }
.tavily-guide a { color: var(--km-primary); text-decoration: none; }
.tavily-guide a:hover { text-decoration: underline; }
.tavily-hint { margin-left: 8px; color: var(--km-gray-400); font-size: 12px; }
</style>
