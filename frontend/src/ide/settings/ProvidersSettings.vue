<template>
  <div class="providers-settings">
    <SettingCard title="自定义厂商" info="新增 OpenRouter / 内部代理 / 302.ai 等自定义厂商，各自模型列表+key 独立">
      <div class="cp-list" style="width: 100%">
        <div v-for="cp in cps.list" :key="cp.id" class="cp-item">
          <div class="cp-info">
            <span class="cp-name">{{ cp.name }}</span>
            <span class="cp-baseurl">{{ cp.baseUrl }}</span>
            <span class="cp-models">{{ (cp.models || []).length }} 个模型</span>
          </div>
          <el-button-group>
            <el-button size="small" @click="editProvider(cp)">编辑</el-button>
            <el-button size="small" type="danger" data-test="cp-delete" @click="removeProvider(cp.id)">删除</el-button>
          </el-button-group>
        </div>
      </div>
      <el-button type="primary" plain size="small" data-test="cp-new" @click="openNew">+ 新建厂商</el-button>
    </SettingCard>

    <SettingCard title="视觉能力探测" info="逐个探测每个模型是否支持图像输入，结果缓存；消耗少量 token">
      <el-button size="small" data-test="vision-batch" :loading="probing" @click="batchProbeVision">
        👁 批量检测（{{ probeProgress.done }}/{{ probeProgress.total || allModels.length }}）
      </el-button>
      <el-button v-if="probing" size="small" @click="probeCancelled = true">取消</el-button>
      <el-button size="small" type="danger" plain data-test="vision-clear" @click="clearVisionCache">🗑 清除视觉缓存</el-button>
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

    <SettingCard title="联网搜索" info="学情反馈时搜索薄弱知识点相关网站 (Tavily); 配置后下次反馈生效">
      <div class="tavily-guide">
        <p>① 前往 <a href="https://tavily.com" target="_blank" rel="noopener">tavily.com</a> 注册 (免费 1000 次/月)</p>
        <p>② 在 Dashboard 复制 API Key</p>
        <p>③ 粘贴到下方</p>
      </div>
      <el-input v-model="tavilyInput" type="password" show-password size="small" style="width: 260px"
                placeholder="tvly-..." data-test="tavily-key" @change="saveTavily" @keyup.enter="saveTavily" />
      <el-button size="small" type="primary" @click="saveTavily">保存</el-button>
      <span v-if="!ai.tavilyKey" class="tavily-hint">未配置则不联网搜索, 只返回 LLM 讲义</span>
    </SettingCard>

    <ProviderEditDialog v-model="dialogVisible" :provider="editing" @save="onSave" />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useCustomProvidersStore } from '@/stores/customProviders'
import { useModelVisionStore } from '@/stores/modelVision'
import { useAiSettingsStore } from '@/stores/aiSettings'
import SettingCard from './SettingCard.vue'
import ProviderEditDialog from './ProviderEditDialog.vue'

const cps = useCustomProvidersStore()
const modelVision = useModelVisionStore()
const ai = useAiSettingsStore()
// Tavily key 本地镜像: v-model 双向输入流畅, 失焦 @change 持久化
// (修: 原 :model-value 受控 + @change 导致粘贴/输入后被 store 空值重置, 表现为"粘贴不了")
const tavilyInput = ref(ai.tavilyKey || '')
watch(() => ai.tavilyKey, (v) => { tavilyInput.value = v || '' })
function saveTavily() {
  ai.setTavilyKey(tavilyInput.value)
  ElMessage.success(tavilyInput.value ? 'Tavily Key 已保存' : '已清除 Tavily Key')
}
const dialogVisible = ref(false)
const editing = ref(null)

function openNew() { editing.value = null; dialogVisible.value = true }
function editProvider(cp) { editing.value = cp; dialogVisible.value = true }

function onSave(payload) {
  if (editing.value) cps.update(editing.value.id, payload)
  else cps.add(payload)
}

async function removeProvider(id) {
  try {
    await ElMessageBox.confirm('确定删除该自定义厂商？', '删除', { type: 'warning' })
    cps.remove(id)
  } catch { /* cancel */ }
}

// 视觉能力批量探测: 串行探测所有 customProviders 的模型, 进度 + 可取消
const probing = ref(false)
const probeProgress = ref({ done: 0, total: 0 })
let probeCancelled = false

const allModels = computed(() => {
  const out = []
  cps.list.forEach((cp) => {
    (cp.models || []).forEach((m) => out.push({ baseUrl: cp.baseUrl, apiKey: cp.apiKey, model: m, name: cp.name }))
  })
  return out
})

async function batchProbeVision() {
  const targets = allModels.value
  if (!targets.length) return
  try {
    await ElMessageBox.confirm(`即将探测 ${targets.length} 个模型的视觉能力，约消耗少量 token，继续？`, '批量探测', { type: 'info' })
  } catch { return }
  probing.value = true
  probeCancelled = false
  probeProgress.value = { done: 0, total: targets.length }
  for (const t of targets) {
    if (probeCancelled) break
    await modelVision.probe(t.baseUrl, t.apiKey, t.model, 'openai')
    probeProgress.value.done++
  }
  probing.value = false
}

async function clearVisionCache() {
  await modelVision.clearAll()
}

// 网络代理: 盘活 aiSettings.proxy ({enabled,type,url,scope})。UI 改 store;
// 落盘 + sidecar env 注入在 Task 18-19 (window.api.setProxyConfig/restartBackend 暂为 preload 占位)
const restarting = ref(false)

function onProxyChange(patch) {
  ai.setProxy(patch)
  // 通知 main 进程落盘 + 准备下次 spawn 注入
  window.api?.setProxyConfig?.(ai.proxy)
}

async function restartBackend() {
  restarting.value = true
  try { await window.api?.restartBackend?.() } finally { restarting.value = false }
}
</script>

<style scoped>
.cp-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
.cp-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; border: 1px solid var(--km-border-light); border-radius: var(--km-radius-md);
}
.cp-info { display: flex; flex-direction: column; min-width: 0; }
.cp-name { font-size: 13px; font-weight: 600; color: var(--km-gray-800); }
.cp-baseurl { font-size: 11.5px; color: var(--km-gray-500); }
.cp-models { font-size: 11.5px; color: var(--km-gray-400); }
.tavily-guide { font-size: 12px; color: var(--km-gray-500); margin-bottom: 8px; line-height: 1.6; }
.tavily-guide p { margin: 0; }
.tavily-guide a { color: var(--km-primary); text-decoration: none; }
.tavily-guide a:hover { text-decoration: underline; }
.tavily-hint { margin-left: 8px; color: var(--km-gray-400); font-size: 12px; }
</style>
