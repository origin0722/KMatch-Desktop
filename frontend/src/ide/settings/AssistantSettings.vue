<template>
  <div class="assistant-settings">
    <div v-if="apiUnified" class="unified-banner">
      已启用「统一 API 配置」（设置 → API 设置）：AI 助手与出题引擎共用一份 Key，此处独立配置的修改会被统一配置覆盖；如需修改请到「API 设置」统一改。
    </div>
    <!-- 厂商 / API Key / Base URL / 模型 -->
    <SettingCard title="厂商" info="AI 助手对话使用的模型供应商">
      <el-select :model-value="ai.provider" size="small" style="width: 220px" @change="onProviderChange">
        <template #prefix>
          <img :src="iconUrlOf(ai.providerMeta().iconKey)" class="provider-icon" alt="" />
        </template>
        <el-option v-for="p in PROVIDERS" :key="p.id" :label="p.label" :value="p.id">
          <span class="provider-row"><img :src="iconUrlOf(p.iconKey)" class="provider-icon" alt="" /><span>{{ p.label }}</span></span>
        </el-option>
      </el-select>
      <div class="provider-chips">
        <button
          v-for="p in quickProviders"
          :key="p.id"
          type="button"
          class="provider-chip"
          :class="{ on: ai.provider === p.id }"
          @click="onProviderChange(p.id)"
        >
          <img :src="iconUrlOf(p.iconKey)" class="provider-icon" alt="" />
          <span>{{ p.label }}</span>
        </button>
      </div>
    </SettingCard>

    <SettingCard title="API Key" info="用于鉴权；仅本地存储，不上传">
      <div class="apikey-row">
        <el-input v-model="apiKeyInput" type="password" show-password size="small" style="width: 300px"
                  placeholder="sk-..." @change="onApiKeyChange" />
        <el-button size="small" :loading="testConn.loading" @click="runTest">测试连接</el-button>
        <a v-if="providerKeyUrl" :href="providerKeyUrl" target="_blank" rel="noopener" class="key-link">获取 Key ↗</a>
      </div>
      <transition name="ob-fade">
        <div v-if="testConn.result" class="test-result" :class="testConn.result.ok ? 'ok' : 'fail'">
          {{ testConn.result.ok ? `✓ 连接成功（${testConn.result.count} 个模型）` : `✗ ${testConn.result.error}` }}
        </div>
      </transition>
    </SettingCard>

    <SettingCard v-if="isCustomProvider(ai.provider)" title="Base URL" info="自定义厂商的 OpenAI 兼容端点">
      <el-input v-model="customBaseUrlInput" size="small" style="width: 320px"
                placeholder="https://your-endpoint/v1" @change="onCustomBaseUrlChange" />
    </SettingCard>

    <SettingCard title="模型" info="带能力徽章（👁 vision / 🧠 reasoning / 上下文）">
      <el-select :model-value="ai.model" size="small" style="width: 280px" @change="ai.setModel">
        <el-option v-for="m in ai.models" :key="m" :label="m" :value="m">
          <span class="model-row">
            <span>{{ m }}</span>
            <el-tag v-if="capOf(m).reasoning === 'native'" size="small" type="warning" effect="plain">🧠</el-tag>
            <el-tag v-if="capOf(m).context" size="small" type="info" effect="plain">{{ formatContext(capOf(m).context) }}</el-tag>
          </span>
        </el-option>
      </el-select>
    </SettingCard>

    <!-- 思考模式 -->
    <SettingCard title="思考模式" info="控制 AI 推理深度；深度模式仅原生 reasoning 模型可用">
      <SegmentedControl
        :model-value="ai.reasoningMode"
        :options="REASONING_OPTIONS"
        @update:model-value="ai.setReasoningMode"
      />
    </SettingCard>

    <!-- 工具权限 -->
    <SettingCard title="工具权限" info="AI 助手调用工具时的默认行为">
      <div v-for="tool in TOOLS" :key="tool.name" class="tool-perm-row">
        <div class="tool-info">
          <span class="tool-name">{{ tool.name }}</span>
          <span class="tool-desc">{{ tool.description }}</span>
        </div>
        <SegmentedControl
          class="perm-seg"
          :model-value="ai.permissionFor(tool.name)"
          :options="PERM_OPTIONS"
          @update:model-value="ai.setToolPermission(tool.name, $event)"
        />
      </div>
    </SettingCard>

    <!-- 个人记忆 -->
    <SettingCard title="个人记忆" info="AI 对话时自动附加的偏好/事实，避免每次手动告知">
      <div class="memory-list">
        <div v-for="m in ai.memories" :key="m.id" class="memory-item">
          <el-switch :model-value="m.enabled" @change="ai.updateMemory(m.id, { enabled: $event })" />
          <el-input :model-value="m.title" size="small" style="width: 160px" placeholder="标题"
                    @change="ai.updateMemory(m.id, { title: $event })" />
          <el-input :model-value="m.content" type="textarea" :rows="2" style="flex:1" placeholder="内容"
                    @change="ai.updateMemory(m.id, { content: $event })" />
          <el-button type="danger" link @click="ai.removeMemory(m.id)">删除</el-button>
        </div>
      </div>
      <el-button type="primary" plain size="small" data-test="add-memory"
                 @click="ai.addMemory({ title: '', content: '', type: 'preference' })">+ 添加记忆</el-button>
    </SettingCard>

    <!-- W? 高级参数 (默认折叠) -->
    <SettingCard title="高级参数" info="对话采样温度 / 最大输出 / 工具循环轮数；默认值适合绝大多数场景">
      <div class="adv-rows">
        <div class="adv-row">
          <span class="adv-label">采样温度</span>
          <el-slider
            :model-value="ai.chatTemperature"
            :min="0" :max="2" :step="0.1"
            style="width: 200px"
            @change="(v) => saveChatParams({ temperature: v })"
          />
          <span class="adv-value">{{ ai.chatTemperature.toFixed(1) }}</span>
          <span class="adv-hint">越低越稳定, 越高越发散 (默认 0.7)</span>
        </div>
        <div class="adv-row">
          <span class="adv-label">最大输出</span>
          <el-input-number
            :model-value="ai.chatMaxTokens"
            :min="256" :max="32768" :step="256"
            size="small" style="width: 130px"
            @change="(v) => saveChatParams({ maxTokens: v })"
          />
          <span class="adv-hint">tokens；长讲义类回答建议 ≥8192</span>
        </div>
        <div class="adv-row">
          <span class="adv-label">工具循环轮数</span>
          <el-input-number
            :model-value="ai.toolRounds"
            :min="1" :max="12" :step="1"
            size="small" style="width: 130px"
            @change="(v) => saveChatParams({ rounds: v })"
          />
          <span class="adv-hint">复杂连招 (审查→测试→导出) 可调高</span>
        </div>
      </div>
    </SettingCard>

    <!-- 清除聊天历史 -->
    <SettingCard title="清除聊天历史" info="清空当前 AI 助手对话记录（不可恢复）">
      <el-button type="danger" plain size="small" data-test="clear-history" @click="onClearHistory">清除</el-button>
    </SettingCard>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useApiSettingsStore } from '@/stores/apiSettings'
// 统一 API 配置接管时, 顶部提示用户此处独立配置属冗余入口 (减配置点)
const apiUnified = computed(() => useApiSettingsStore().mode === 'unified')
import { ElMessageBox } from 'element-plus'
import { useAiSettingsStore, isCustomProvider, customProviderUuid, PROVIDERS } from '@/stores/aiSettings'
import { useCustomProvidersStore } from '@/stores/customProviders'
import { useChatStore } from '@/stores/chat'
import { useModelVisionStore } from '@/stores/modelVision'
import { TOOLS } from '@/ide/tools/registry'
import { capabilityOf, formatContext } from '@/services/llm/modelCapabilities'
import { iconUrlOf } from '@/services/llm/icons'
import SettingCard from './SettingCard.vue'
import SegmentedControl from './SegmentedControl.vue'

const ai = useAiSettingsStore()
const chat = useChatStore()
const customProviders = useCustomProvidersStore()
const modelVision = useModelVisionStore()

const customBaseUrl = computed(() => {
  if (!isCustomProvider(ai.provider)) return ''
  const uuid = customProviderUuid(ai.provider)
  return customProviders.get(uuid)?.baseUrl || ''
})

// 本地镜像 (同 API Key 的"粘贴不了"修复): v-model 输入流畅, 失焦 @change 落盘
const customBaseUrlInput = ref('')
watch(customBaseUrl, (v) => { customBaseUrlInput.value = v || '' }, { immediate: true })

function onProviderChange(pid) {
  if (pid === 'custom') return ai.setProvider('custom:default')
  ai.setProvider(pid)
}

// B4: 厂商预设 chips (快速选择, 排除 custom) + 当前厂商"获取 Key"链接
const quickProviders = PROVIDERS.filter((p) => p.id !== 'custom')
const providerKeyUrl = computed(() => PROVIDERS.find((p) => p.id === ai.provider)?.keyUrl || '')

// B4: 测试连接闭环 (按钮 -> /models -> 行内结果); 保存 Key 后自动复测
const testConn = reactive({ loading: false, result: null })
async function runTest() {
  testConn.loading = true
  testConn.result = null
  try {
    testConn.result = await ai.testConnection()
  } finally {
    testConn.loading = false
  }
}

// API Key 本地镜像 (修"粘贴不了": 受控 :model-value + @change 会在输入/粘贴间被 store
// 旧值重置 — 与 Tavily 输入框同款修复)。v-model 输入流畅, 失焦 @change 落盘 store。
const apiKeyInput = ref(ai.apiKey || '')
watch(() => ai.apiKey, (v) => { apiKeyInput.value = v || '' })

async function onApiKeyChange(key) {
  await ai.setApiKey(key)
  if (key) await runTest()
}

function onCustomBaseUrlChange(url) {
  const uuid = customProviderUuid(ai.provider)
  customProviders.update(uuid, { baseUrl: url })
  ai.fetchModels()
}

function capOf(m) {
  const base = capabilityOf(ai.provider, m)
  const baseUrl = ai.getBaseUrl()
  return { ...base, vision: modelVision.hasVision(baseUrl, m) }
}

const deepDisabled = computed(() => capabilityOf(ai.provider, ai.model).reasoning !== 'native')
const deepDisabledTooltip = computed(() => `当前模型 (${ai.model}) 不支持原生推理；如需思考请用「快速/自动」`)

// #28 思考程度分段控件 (四档: off/default/high/max 递进)
const REASONING_OPTIONS = computed(() => [
  { label: '关闭', value: 'off', title: '关闭思考，直接回答' },
  { label: '默认', value: 'default', title: '由模型默认决定' },
  { label: '高', value: 'high', disabled: deepDisabled.value, title: deepDisabled.value ? deepDisabledTooltip.value : '增强思考' },
  { label: '最高', value: 'max', disabled: deepDisabled.value, title: deepDisabled.value ? deepDisabledTooltip.value : '最充分思考' },
])
const PERM_OPTIONS = [
  { label: '允许', value: 'allow', tone: 'success' },
  { label: '询问', value: 'ask', tone: 'warning' },
  { label: '禁用', value: 'deny', tone: 'danger' },
]

async function onClearHistory() {
  try {
    await ElMessageBox.confirm('确定清空所有 AI 助手对话记录？此操作不可恢复。', '清除聊天历史', {
      type: 'warning', confirmButtonText: '清除', cancelButtonText: '取消',
    })
    chat.clearMessages()
  } catch { /* 用户取消 */ }
}

// W? 高级参数: 控件受控 (:model-value 绑 store), @change 把新值显式交给 store 校验+落盘
function saveChatParams(patch) {
  ai.setChatParams(patch)
}
</script>

<style scoped>
.provider-icon { width: 14px; height: 14px; vertical-align: middle; margin-right: 4px; }
.provider-row { display: inline-flex; align-items: center; gap: 4px; }
.model-row { display: inline-flex; align-items: center; gap: 6px; }
/* B4: 厂商预设 chips */
.provider-chips {
  display: flex; flex-wrap: wrap; gap: 6px;
  margin-top: 10px;
}
.provider-chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px;
  border: 1px solid var(--km-border-light);
  border-radius: 999px;
  background: var(--km-bg-layer-2);
  font-size: 12px; color: var(--km-gray-600);
  cursor: pointer;
  transition: all 0.15s var(--km-ease);
}
.provider-chip:hover { border-color: var(--km-border-focus); color: var(--km-gray-700); }
.provider-chip.on {
  border-color: var(--km-primary);
  background: var(--km-primary-light);
  color: var(--km-primary);
  font-weight: 600;
}
.provider-chip .provider-icon { width: 13px; height: 13px; margin: 0; }
/* B4: API Key 行 + 测试连接 + 获取链接 */
.apikey-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.key-link {
  font-size: 12px; color: var(--km-primary);
  text-decoration: none; white-space: nowrap;
}
.key-link:hover { text-decoration: underline; }
.test-result {
  margin-top: 8px;
  font-size: 12px; padding: 6px 10px;
  border-radius: var(--km-radius-sm);
}
.test-result.ok { color: var(--km-success, #67c23a); background: var(--km-success-light, #f0f9eb); }
.test-result.fail { color: var(--km-danger, #f56c6c); background: var(--km-danger-light, #fef0f0); }
.tool-perm-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 0; border-bottom: 1px solid var(--km-border-light);
}
.tool-perm-row:last-child { border-bottom: 0; }
.tool-info { display: flex; flex-direction: column; min-width: 0; }
.unified-banner {
  padding: 8px 12px; font-size: 12px; line-height: 1.6;
  border: 1px dashed var(--km-primary); border-radius: var(--km-radius-sm);
  background: var(--km-bg-layer-2); color: var(--km-gray-700);
}
.tool-name { font-size: 13px; font-weight: 600; color: var(--km-gray-800); }
.tool-desc { font-size: 11.5px; color: var(--km-gray-500); margin-top: 2px; }
.perm-seg { width: 168px; }
.memory-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; width: 100%; }
.memory-item { display: flex; align-items: center; gap: 8px; width: 100%; }
/* W? 高级参数 */
.adv-rows { display: flex; flex-direction: column; gap: 12px; }
.adv-row { display: flex; align-items: center; gap: 12px; }
.adv-label { font-size: 13px; font-weight: 600; color: var(--km-gray-700); width: 96px; flex-shrink: 0; }
.adv-value { font-size: 12.5px; color: var(--km-gray-600); font-family: var(--km-font-mono); width: 28px; }
.adv-hint { font-size: 11.5px; color: var(--km-gray-500); }
</style>
