<template>
  <div class="agent-settings">
    <div v-if="apiUnified" class="unified-banner">
      已启用「统一 API 配置」（设置 → API 设置）：Agent 独立配置已被统一 Key 接管，此处修改会被覆盖；如需修改请到「API 设置」统一改。
    </div>
    <SettingCard title="启用 Agent 独立配置"
                 info="开启后，学情检测/资源生成/代码审查等 Agent 使用下方配置；关闭则自动使用 AI 助手的 Key（端用户无需改 .env）。开启后下方出现 厂商/API Key/模型/测试连接">
      <el-switch :model-value="agent.state.useOverrides" @change="agent.setUseOverrides" />
    </SettingCard>

    <!-- issue: 未配置 → 401 预警; 显示实际生效密钥来源 (独立 Key → AI 助手 Key → 后端默认) -->
    <div v-if="effectiveSrc.type !== 'engine'" class="agent-warn" data-test="effective-source">
      ⚠️ 出题/判分当前密钥来源：<b>{{ effectiveSrc.text }}</b>
      {{ effectiveSrc.type === 'env'
        ? '——请直接在上方填入有效 Key，或先到 设置 → AI 助手 配置（端用户无需、也无法修改 .env）。'
        : '——如需更稳定，可开启独立配置（优先于 AI 助手 Key）。' }}
    </div>

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
        <el-input v-model="apiKeyInput" type="password" show-password size="small" style="width: 320px"
                  placeholder="sk-..." @change="agent.setApiKey" />
      </SettingCard>

      <SettingCard v-if="isCustomProvider(agent.state.provider)" title="Base URL" info="自定义厂商端点">
        <el-input v-model="baseUrlInput" size="small" style="width: 320px"
                  placeholder="https://your-endpoint/v1" @change="agent.setBaseUrl" />
      </SettingCard>

      <SettingCard title="模型">
        <el-input v-model="modelInput" size="small" style="width: 280px" placeholder="模型 ID"
                  @change="agent.setModel" />
      </SettingCard>

      <SettingCard title="测试连接" info="调一次 /api/agents/ping 验证 key/baseUrl/model 可用">
        <el-button type="primary" size="small" data-test="test-conn" :loading="testing" @click="testConn">测试</el-button>
        <span v-if="testResult" :class="testResult.ok ? 'conn-ok' : 'conn-err'">{{ testResult.message }}</span>
      </SettingCard>
    </template>

    <!-- 反馈快模型: 独立于独立配置开关, 未开时部分覆写仅 model; key/baseUrl 走上方回退链 -->
    <SettingCard title="反馈快模型" info="仅「获取针对性反馈」请求生效：先跑此快模型减等待；留空 = 跟随引擎模型。换厂商时请确认模型属于该厂商">
      <el-input v-model="feedbackModelInput" size="small" style="width: 280px"
                placeholder="如 deepseek-v4-flash（留空跟随引擎）" @change="agent.setFeedbackModel" />
    </SettingCard>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useAgentLlmStore } from '@/stores/agentLlm'
import { PROVIDERS, isCustomProvider } from '@/stores/aiSettings'
import { useApiSettingsStore } from '@/stores/apiSettings'
import SettingCard from './SettingCard.vue'

const agent = useAgentLlmStore()
// issue: 显示当前生效密钥来源 (独立 Key / AI 助手回退 / .env)
const effectiveSrc = computed(() => agent.effectiveSource())
// 统一 API 配置接管时, 顶部提示用户此处为冗余入口 (减配置点)
const apiUnified = computed(() => useApiSettingsStore().mode === 'unified')
const testing = ref(false)
const testResult = ref(null)

// API Key 本地镜像 (修"粘贴不了": 受控 :model-value + @change 输入/粘贴间被 store 值重置)
const apiKeyInput = ref(agent.state.apiKey || '')
watch(() => agent.state.apiKey, (v) => { apiKeyInput.value = v || '' })

// 同款修复推广到其余受控文本输入 (Base URL / 模型 / 反馈快模型): 本地镜像 + v-model 输入流畅,
// 失焦 @change 落盘 store, watch 双向同步 (外部改写如切换厂商重置时输入框跟随)
const baseUrlInput = ref(agent.state.baseUrl || '')
watch(() => agent.state.baseUrl, (v) => { baseUrlInput.value = v || '' })
const modelInput = ref(agent.state.model || '')
watch(() => agent.state.model, (v) => { modelInput.value = v || '' })
const feedbackModelInput = ref(agent.state.feedbackModel || '')
watch(() => agent.state.feedbackModel, (v) => { feedbackModelInput.value = v || '' })

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
.unified-banner {
  padding: 8px 12px; font-size: 12px; line-height: 1.6;
  border: 1px dashed var(--km-primary); border-radius: var(--km-radius-sm);
  background: var(--km-bg-layer-2); color: var(--km-gray-700);
}
.agent-warn {
  padding: 10px 12px; font-size: 12.5px; line-height: 1.7; margin-bottom: 12px;
  border: 1px dashed color-mix(in srgb, var(--km-warning) 60%, transparent);
  border-radius: var(--km-radius-sm);
  background: color-mix(in srgb, var(--km-warning) 8%, transparent);
  color: var(--km-gray-700);
}
.agent-warn b { color: var(--km-danger); }
</style>
