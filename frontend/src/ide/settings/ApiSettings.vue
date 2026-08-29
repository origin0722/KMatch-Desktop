<template>
  <div class="api-settings">
    <!-- 统一/分开 模式 -->
    <div class="mode-row">
      <label class="mode-toggle">
        <input type="checkbox" :checked="api.mode === 'unified'" @change="onModeToggle" />
        <span>统一 API 配置（AI 助手 与 出题/Agent 引擎 共用一套）</span>
      </label>
      <span class="mode-hint">{{ api.mode === 'unified' ? '统一模式: 下方一份配置写到两端' : '分开模式: 两通道各自独立' }}</span>
    </div>

    <!-- 统一模式: 一份配置 -->
    <div v-if="api.mode === 'unified'" class="row-card unified">
      <div class="card-title">统一配置</div>
      <div class="field">
        <label>厂商</label>
        <select v-model="uProvider" @change="onUnifiedProvider">
          <option v-for="p in PROVIDERS" :key="p.id" :value="p.id">{{ p.label }}</option>
        </select>
      </div>
      <div class="field">
        <label>Base URL</label>
        <input v-model="uBaseUrl" class="inp" placeholder="https://api.…/v1" />
      </div>
      <div class="field">
        <label>模型</label>
        <input v-model="uModel" class="inp" list="km-model-presets" placeholder="选择或输入模型名" />
      </div>
      <div class="field">
        <label>API Key</label>
        <input v-model="uApiKey" type="password" class="inp" placeholder="sk-…" autocomplete="off" />
      </div>
      <div class="actions">
        <button class="btn" :disabled="busy" @click="onTest(uProvider, uBaseUrl, uModel, uApiKey, unifiedProtocol)">测试连通性</button>
        <button class="btn primary" :disabled="busy || !uApiKey" @click="onApplyUnified">应用到全部 →</button>
      </div>
    </div>

    <!-- 分开模式: 两行 -->
    <div v-else class="separate">
      <div class="row-card">
        <div class="card-title">① AI 助手（聊天）</div>
        <div class="field row">
          <label>厂商</label>
          <select :value="ai.provider" @change="onChatProvider($event.target.value)">
            <option v-for="p in PROVIDERS" :key="p.id" :value="p.id">{{ p.label }}</option>
          </select>
          <label>模型</label>
          <input v-model="sepChatModel" @change="onChatModel($event.target.value)" class="inp" list="km-model-presets" placeholder="模型名" />
        </div>
        <div class="field">
          <label>API Key</label>
          <input v-model="sepChatKey" @change="onChatKey($event.target.value)" type="password" class="inp" placeholder="sk-…" autocomplete="off" />
        </div>
        <div class="actions">
          <button class="btn" :disabled="busy || !ai.apiKey" @click="onTest(ai.provider, ai.getBaseUrl(), ai.model, ai.apiKey, chatProtocol)">测试连通性</button>
        </div>
      </div>

      <div class="row-card">
        <div class="card-title">② 出题 / Agent 引擎（学情检测 · 生成 · 审查）</div>
        <div class="field row">
          <label>厂商</label>
          <select :value="ag.state.provider" @change="onAgentProvider($event.target.value)">
            <option v-for="p in PROVIDERS" :key="p.id" :value="p.id">{{ p.label }}</option>
          </select>
          <label>模型</label>
          <input v-model="sepAgentModel" @change="onAgentModel($event.target.value)" class="inp" list="km-model-presets" placeholder="模型名" />
        </div>
        <div class="field">
          <label>API Key</label>
          <input v-model="sepAgentKey" @change="onAgentKey($event.target.value)" type="password" class="inp" placeholder="sk-…" autocomplete="off" />
        </div>
        <div class="field note">
          引擎默认「跟随内置服务端 .env」；在本处填写 Key 后即切换到独立 Key（等效开启 Agent 独立 key）。
        </div>
        <div class="actions">
          <button class="btn" :disabled="busy" @click="onTest(ag.state.provider, ag.state.baseUrl, ag.state.model, ag.state.apiKey, 'openai')">测试连通性</button>
        </div>
      </div>
    </div>

    <datalist id="km-model-presets">
      <option v-for="m in allPresets" :key="m" :value="m">{{ m }}</option>
    </datalist>

    <div v-if="status" class="status" :class="{ err: statusErr }">{{ status }}</div>
  </div>
</template>

<script setup>
/**
 * ApiSettings — 设置页「API 设置」栏目
 *
 * 统一/分开两种模式管理 AI 助手(aiSettings) 与 出题(agentLlm) 两条 LLM 通道:
 *   - 统一: setUnified 维护一份, applyUnified 落到两端
 *   - 分开: 直接编辑两端既有 store (单一真相源不变)
 * 预设模型走 MODEL_PRESETS 的 <datalist>; 连通性用 POST /api/agents/ping。
 */
import { ref, computed, onMounted, watch } from 'vue'
import { PROVIDERS, useAiSettingsStore } from '@/stores/aiSettings'
import { useAgentLlmStore } from '@/stores/agentLlm'
import { useApiSettingsStore, allPresetModels } from '@/stores/apiSettings'

const ai = useAiSettingsStore()
const ag = useAgentLlmStore()
const api = useApiSettingsStore()

const busy = ref(false)
const status = ref('')
const statusErr = ref(false)
const allPresets = computed(() => allPresetModels())

const providerMetaOf = (pid) => PROVIDERS.find((p) => p.id === pid) || { protocol: 'openai', baseUrl: '' }
const unifiedProtocol = computed(() => providerMetaOf(uProvider.value).protocol || 'openai')
const chatProtocol = computed(() => ai.providerMeta?.().protocol || 'openai')

// 统一模式表单镜像 (local, 应用时才写两端)
// 注: pinia setup store 会把 ref 自动解包, 这里用 api.unified.* (非 .value)
const uProvider = ref(api.unified.provider)
const uBaseUrl = ref(api.unified.baseUrl)
const uModel = ref(api.unified.model)
const uApiKey = ref(api.unified.apiKey)

function syncUnifiedForm() {
  uProvider.value = api.unified.provider
  uBaseUrl.value = api.unified.baseUrl
  uModel.value = api.unified.model
  uApiKey.value = api.unified.apiKey
}

onMounted(syncUnifiedForm)

function onModeToggle(e) {
  api.setMode(e.target.checked ? 'unified' : 'separate')
  syncUnifiedForm()
}

function onUnifiedProvider() {
  uBaseUrl.value = PROVIDERS.find((p) => p.id === uProvider.value)?.baseUrl || uBaseUrl.value
  api.setUnified({ provider: uProvider.value, baseUrl: uBaseUrl.value })
}
function setUnifiedFromForm() {
  api.setUnified({ provider: uProvider.value, baseUrl: uBaseUrl.value, model: uModel.value, apiKey: uApiKey.value })
}

async function onApplyUnified() {
  setUnifiedFromForm()
  busy.value = true
  try {
    await api.applyUnified()
    setStatus('已应用到 AI 助手 + 出题引擎')
  } catch (e) {
    setStatus(e?.response?.data?.detail || e?.message || '应用失败', true)
  } finally {
    busy.value = false
  }
}

async function onTest(providerId, baseUrl, model, apiKey, protocol = 'openai') {
  if (!apiKey) { setStatus('请先填写 API Key', true); return }
  busy.value = true
  try {
    const meta = PROVIDERS.find((p) => p.id === providerId)
    const url = baseUrl || meta?.baseUrl || ''
    const r = await api.testConnectivity({ apiKey, baseUrl: url, model, protocol })
    setStatus(r?.ok ? `连接成功 · 模型响应: ${(r.content || '').slice(0, 60) || 'ok'}` : `连接失败: ${r?.error || r?.detail || JSON.stringify(r) || '未知错误'}`)
    if (!r?.ok) statusErr.value = true
  } catch (e) {
    setStatus(e?.response?.data?.detail || e?.message || '连接失败', true)
  } finally {
    busy.value = false
  }
}

function setStatus(msg, err = false) { status.value = msg || ''; statusErr.value = err }

// 分开模式表单镜像 (W? 同"粘贴不了"修复): 原生 :value + @change 在重渲染时会重置输入
const sepChatModel = ref(ai.model || '')
const sepChatKey = ref(ai.apiKey || '')
const sepAgentModel = ref(ag.state.model || '')
const sepAgentKey = ref(ag.state.apiKey || '')
watch(() => ai.model, (v) => { sepChatModel.value = v || '' })
watch(() => ai.apiKey, (v) => { sepChatKey.value = v || '' })
watch(() => ag.state.model, (v) => { sepAgentModel.value = v || '' })
watch(() => ag.state.apiKey, (v) => { sepAgentKey.value = v || '' })

// 分开模式: 直接写两端 store
function onChatProvider(pid) { ai.setProvider(pid) }
function onChatModel(m) { ai.setModel(m) }
function onChatKey(k) { ai.setApiKey(k) }
function onAgentProvider(pid) { ag.setProvider(pid) }
function onAgentModel(m) { ag.setModel(m) }
function onAgentKey(k) { ag.setApiKey(k); if (k) ag.setUseOverrides(true) }
</script>

<style scoped>
.api-settings { display: flex; flex-direction: column; gap: 12px; color: var(--km-gray-800); }
.mode-row { display: flex; align-items: center; gap: 8px; }
.mode-toggle { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; font-weight: 600; }
.mode-hint { font-size: 12px; color: var(--km-gray-500); }
.row-card { border: 1px solid var(--km-border-light); border-radius: var(--km-radius-sm); padding: 12px; background: var(--km-bg-layer-2); display: flex; flex-direction: column; gap: 8px; }
.row-card.unified { border-color: var(--km-primary); }
.card-title { font-size: 13px; font-weight: 650; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field.row { flex-direction: row; align-items: center; gap: 8px; }
.field.row input { flex: 1; }
.field label { font-size: 12px; color: var(--km-gray-600); }
.field.note { font-size: 11px; color: var(--km-gray-500); }
.inp, select { padding: 6px 8px; font-size: 12px; border: 1px solid var(--km-border-light); border-radius: var(--km-radius-sm); background: var(--km-bg-layer-1); color: var(--km-gray-800); }
.actions { display: flex; gap: 8px; }
.btn { padding: 6px 12px; font-size: 12px; border: 1px solid var(--km-border-light); border-radius: var(--km-radius-sm); background: var(--km-bg-layer-1); color: var(--km-gray-800); cursor: pointer; }
.btn.primary { border-color: var(--km-primary); color: var(--km-primary); }
.btn:disabled { opacity: .45; cursor: default; }
.status { font-size: 12px; color: var(--km-success); }
.status.err { color: var(--km-danger); }
.separate { display: flex; flex-direction: column; gap: 10px; }
</style>
