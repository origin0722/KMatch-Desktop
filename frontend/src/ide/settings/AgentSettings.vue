<template>
  <div class="agent-settings">
    <SettingCard title="启用 Agent 独立配置"
                 info="开启后，学情检测/资源生成/代码审查等 Agent 使用下方配置；关闭则走后端默认 .env">
      <el-switch :model-value="agent.state.useOverrides" @change="agent.setUseOverrides" />
    </SettingCard>

    <template v-if="agent.state.useOverrides">
      <SettingCard title="厂商" info="Agent 本期仅支持 OpenAI 兼容协议（Anthropic 暂不支持）">
        <el-select data-test="agent-provider" :model-value="agent.state.provider" size="small" style="width: 220px"
                   @change="agent.setProvider">
          <el-option v-for="p in PROVIDERS" :key="p.id" :label="p.label" :value="p.id"
                     :disabled="p.protocol === 'anthropic'"
                     :title="p.protocol === 'anthropic' ? 'Agent 本期仅支持 OpenAI 兼容协议' : ''" />
        </el-select>
      </SettingCard>

      <SettingCard title="API Key" info="Agent 学习引擎独立 key；仅本地存储">
        <el-input :model-value="agent.state.apiKey" type="password" show-password size="small" style="width: 320px"
                  placeholder="sk-..." @change="agent.setApiKey" />
      </SettingCard>

      <SettingCard v-if="isCustomProvider(agent.state.provider)" title="Base URL" info="自定义厂商端点">
        <el-input :model-value="agent.state.baseUrl" size="small" style="width: 320px"
                  placeholder="https://your-endpoint/v1" @change="agent.setBaseUrl" />
      </SettingCard>

      <SettingCard title="模型">
        <el-input :model-value="agent.state.model" size="small" style="width: 280px" placeholder="模型 ID"
                  @change="agent.setModel" />
      </SettingCard>

      <SettingCard title="测试连接" info="调一次 /api/agents/ping 验证 key/baseUrl/model 可用">
        <el-button type="primary" size="small" data-test="test-conn" :loading="testing" @click="testConn">测试</el-button>
        <span v-if="testResult" :class="testResult.ok ? 'conn-ok' : 'conn-err'">{{ testResult.message }}</span>
      </SettingCard>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useAgentLlmStore } from '@/stores/agentLlm'
import { PROVIDERS, isCustomProvider } from '@/stores/aiSettings'
import SettingCard from './SettingCard.vue'

const agent = useAgentLlmStore()
const testing = ref(false)
const testResult = ref(null)

async function testConn() {
  const overrides = agent.buildOverrides()
  if (!overrides) {
    testResult.value = { ok: false, message: '请先填写 API Key' }
    return
  }
  testing.value = true
  testResult.value = null
  try {
    const res = await window.api.http.request('POST', '/api/agents/ping', { llm_overrides: overrides })
    const data = res.body || {}
    if (res.ok && data.ok) {
      testResult.value = { ok: true, message: `✓ 连接成功（${(data.content || '').slice(0, 40)}）` }
    } else {
      testResult.value = { ok: false, message: `✗ ${data.error || '连接失败'}` }
    }
  } catch (e) {
    testResult.value = { ok: false, message: `✗ ${e.message || '请求失败'}` }
  } finally {
    testing.value = false
  }
}
</script>

<style scoped>
.conn-ok { color: var(--km-success, #67c23a); margin-left: 8px; font-size: 12.5px; }
.conn-err { color: var(--km-danger, #f56c6c); margin-left: 8px; font-size: 12.5px; }
</style>
