<template>
  <div class="assistant-settings">
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
    </SettingCard>

    <SettingCard title="API Key" info="用于鉴权；仅本地存储，不上传">
      <el-input :model-value="ai.apiKey" type="password" show-password size="small" style="width: 320px"
                placeholder="sk-..." @change="ai.setApiKey" />
    </SettingCard>

    <SettingCard v-if="isCustomProvider(ai.provider)" title="Base URL" info="自定义厂商的 OpenAI 兼容端点">
      <el-input :model-value="customBaseUrl" size="small" style="width: 320px"
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
      <el-radio-group :model-value="ai.reasoningMode" size="small" @change="ai.setReasoningMode">
        <el-radio-button label="auto">自动</el-radio-button>
        <el-radio-button label="fast">快速</el-radio-button>
        <el-radio-button label="deep" :disabled="deepDisabled"
          :title="deepDisabled ? deepDisabledTooltip : ''">深度</el-radio-button>
      </el-radio-group>
    </SettingCard>

    <!-- 工具权限 -->
    <SettingCard title="工具权限" info="AI 助手调用工具时的默认行为">
      <div v-for="tool in TOOLS" :key="tool.name" class="tool-perm-row">
        <div class="tool-info">
          <span class="tool-name">{{ tool.name }}</span>
          <span class="tool-desc">{{ tool.description }}</span>
        </div>
        <el-radio-group :model-value="ai.permissionFor(tool.name)" size="small"
                        @change="ai.setToolPermission(tool.name, $event)">
          <el-radio-button label="allow">允许</el-radio-button>
          <el-radio-button label="ask">询问</el-radio-button>
          <el-radio-button label="deny">禁用</el-radio-button>
        </el-radio-group>
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

    <!-- 清除聊天历史 -->
    <SettingCard title="清除聊天历史" info="清空当前 AI 助手对话记录（不可恢复）">
      <el-button type="danger" plain size="small" data-test="clear-history" @click="onClearHistory">清除</el-button>
    </SettingCard>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useAiSettingsStore, isCustomProvider, customProviderUuid, PROVIDERS } from '@/stores/aiSettings'
import { useCustomProvidersStore } from '@/stores/customProviders'
import { useChatStore } from '@/stores/chat'
import { useModelVisionStore } from '@/stores/modelVision'
import { TOOLS } from '@/ide/tools/registry'
import { capabilityOf, formatContext } from '@/services/llm/modelCapabilities'
import { iconUrlOf } from '@/services/llm/icons'
import SettingCard from './SettingCard.vue'

const ai = useAiSettingsStore()
const chat = useChatStore()
const customProviders = useCustomProvidersStore()
const modelVision = useModelVisionStore()

const customBaseUrl = computed(() => {
  if (!isCustomProvider(ai.provider)) return ''
  const uuid = customProviderUuid(ai.provider)
  return customProviders.get(uuid)?.baseUrl || ''
})

function onProviderChange(pid) {
  if (pid === 'custom') return ai.setProvider('custom:default')
  ai.setProvider(pid)
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

async function onClearHistory() {
  try {
    await ElMessageBox.confirm('确定清空所有 AI 助手对话记录？此操作不可恢复。', '清除聊天历史', {
      type: 'warning', confirmButtonText: '清除', cancelButtonText: '取消',
    })
    chat.clearMessages()
  } catch { /* 用户取消 */ }
}
</script>

<style scoped>
.provider-icon { width: 14px; height: 14px; vertical-align: middle; margin-right: 4px; }
.provider-row { display: inline-flex; align-items: center; gap: 4px; }
.model-row { display: inline-flex; align-items: center; gap: 6px; }
.tool-perm-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 0; border-bottom: 1px solid var(--km-border-light);
}
.tool-perm-row:last-child { border-bottom: 0; }
.tool-info { display: flex; flex-direction: column; min-width: 0; }
.tool-name { font-size: 13px; font-weight: 600; color: var(--km-gray-800); }
.tool-desc { font-size: 11.5px; color: var(--km-gray-500); margin-top: 2px; }
.memory-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; width: 100%; }
.memory-item { display: flex; align-items: center; gap: 8px; width: 100%; }
</style>
