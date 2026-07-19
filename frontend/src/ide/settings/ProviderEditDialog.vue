<template>
  <el-dialog :model-value="modelValue" title="自定义厂商" width="480px"
             @update:model-value="$emit('update:modelValue', $event)">
    <el-form label-width="90px" size="small">
      <el-form-item label="名称">
        <el-input :model-value="form.name" placeholder="如 OpenRouter" @input="form.name = $event" />
      </el-form-item>
      <el-form-item label="Base URL">
        <el-input :model-value="form.baseUrl" placeholder="https://.../v1" @input="form.baseUrl = $event" />
      </el-form-item>
      <el-form-item label="API Key">
        <el-input :model-value="form.apiKey" type="password" show-password placeholder="sk-..."
                  @input="form.apiKey = $event" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input :model-value="form.description" @input="form.description = $event" />
      </el-form-item>
      <el-form-item label="模型">
        <el-input :model-value="modelsText" type="textarea" :rows="2"
                  placeholder="自动获取或每行一个" @input="onModelsInput" />
        <el-button link size="small" :loading="fetching" @click="autoFetch">自动获取</el-button>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { useCustomProvidersStore } from '@/stores/customProviders'

defineOptions({ name: 'ProviderEditDialog' })

const props = defineProps({
  modelValue: Boolean,
  provider: { type: Object, default: null }, // 编辑时传入；新建时 null
})
const emit = defineEmits(['update:modelValue', 'save'])

const cps = useCustomProvidersStore()
const form = ref({ name: '', baseUrl: '', apiKey: '', description: '', models: [] })
const fetching = ref(false)

watch(() => props.modelValue, (open) => {
  if (open) {
    form.value = props.provider
      ? { ...props.provider, models: [...(props.provider.models || [])] }
      : { name: '', baseUrl: '', apiKey: '', description: '', models: [] }
  }
}, { immediate: true })

const modelsText = computed(() => (form.value.models || []).join('\n'))
function onModelsInput(v) { form.value.models = v.split('\n').map((s) => s.trim()).filter(Boolean) }

// 编辑现有厂商: 直调原 id 探测 (store 原地 update models)
// 新建厂商: 临时 add 探测后立即 remove, 不留孤儿 (计划原版两路径都 add, 编辑会错建 tmp、新建保存后会留 tmp 孤儿)
async function autoFetch() {
  if (!form.value.baseUrl) return
  fetching.value = true
  try {
    if (props.provider) {
      const r = await cps.autoFetchModels(props.provider.id)
      if (r.ok) form.value.models = r.models
    } else {
      const tmp = cps.add({ name: form.value.name || 'tmp', baseUrl: form.value.baseUrl, apiKey: form.value.apiKey })
      const r = await cps.autoFetchModels(tmp.id)
      cps.remove(tmp.id)
      if (r.ok) form.value.models = r.models
    }
  } finally {
    fetching.value = false
  }
}

function save() {
  emit('save', { ...form.value })
  emit('update:modelValue', false)
}
</script>
