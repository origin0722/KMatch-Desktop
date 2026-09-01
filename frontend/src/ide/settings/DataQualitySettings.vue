<template>
  <div class="dq-settings">
    <!-- 语义检索 (Embedding): 图谱语义搜索 / AI 助手 search_knowledge 依赖 -->
    <SettingCard title="语义检索 (Embedding)" info="图谱语义搜索与 AI 助手知识检索依赖；此前只能改 .env，现可在本页配置并即时生效。Key 仅存本机。">
      <div class="dq-rows">
        <div class="dq-row">
          <span class="dq-label">状态</span>
          <el-tag :type="semanticBadge.type" size="small" data-test="emb-status">{{ semanticBadge.text }}</el-tag>
          <span class="dq-hint">来源: {{ embSourceLabel }}</span>
        </div>
        <div class="dq-row">
          <span class="dq-label">API Key</span>
          <el-input
            v-model="emb.keyInput" type="password" show-password size="small" style="width: 300px"
            data-test="emb-key"
            :placeholder="emb.configured ? `已配置 (尾${emb.keyTail}) — 留空保持不变` : 'sk-...'"
          />
        </div>
        <div class="dq-row">
          <span class="dq-label">Base URL</span>
          <el-input v-model="emb.baseUrl" size="small" style="width: 300px" placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
        </div>
        <div class="dq-row">
          <span class="dq-label">模型</span>
          <el-input v-model="emb.model" size="small" style="width: 300px" placeholder="text-embedding-v2" />
          <span class="dq-hint">需为 Embedding 模型（text-embedding-v2 / v3 等）；DeepSeek 无嵌入端点，请配千问等支持 embedding 的服务</span>
        </div>
        <div class="dq-row">
          <el-button type="primary" size="small" :loading="emb.saving" data-test="emb-save" @click="saveEmbedding">保存并生效</el-button>
          <el-button size="small" :disabled="!emb.configured" @click="clearEmbeddingKey">清除已存 Key</el-button>
        </div>
        <transition name="ob-fade">
          <div v-if="emb.msg" class="dq-msg" :class="emb.msg.ok ? 'ok' : 'fail'">{{ emb.msg.text }}</div>
        </transition>
      </div>
    </SettingCard>

    <!-- 质量裁判 (异源): M5 独立裁判口径 -->
    <SettingCard title="质量裁判 (异源)" info="独立裁判质检生成内容的幻觉/适配度。与主模型不同源时才计入「独立裁判」口径；未启用则回落主模型（同源）。">
      <div class="dq-rows">
        <div class="dq-row">
          <span class="dq-label">状态</span>
          <el-tag :type="judgeBadge.type" size="small" data-test="judge-status">{{ judgeBadge.text }}</el-tag>
          <el-switch
            :model-value="judge.enabled" size="small" style="margin-left: 8px"
            data-test="judge-enabled" @change="(v) => saveJudge({ enabled: v })"
          />
          <span class="dq-hint">启用异源裁判</span>
        </div>
        <template v-if="judge.enabled">
          <div class="dq-row">
            <span class="dq-label">API Key</span>
            <el-input
              v-model="judge.keyInput" type="password" show-password size="small" style="width: 300px"
              data-test="judge-key"
              :placeholder="judge.configured ? `已配置 (尾${judge.keyTail}) — 留空保持不变` : 'sk-...'"
            />
          </div>
          <div class="dq-row">
            <span class="dq-label">Base URL</span>
            <el-input v-model="judge.baseUrl" size="small" style="width: 300px" placeholder="留空 = 跟随主模型端点" />
          </div>
          <div class="dq-row">
            <span class="dq-label">模型</span>
            <el-input v-model="judge.model" size="small" style="width: 300px" placeholder="留空 = 跟随主模型" />
          </div>
          <div class="dq-row">
            <el-button type="primary" size="small" :loading="judge.saving" data-test="judge-save" @click="saveJudge()">保存</el-button>
            <el-button size="small" :loading="judge.testing" data-test="judge-test" @click="testJudge">测试连接</el-button>
          </div>
        </template>
        <transition name="ob-fade">
          <div v-if="judge.msg" class="dq-msg" :class="judge.msg.ok ? 'ok' : 'fail'">{{ judge.msg.text }}</div>
        </transition>
      </div>
    </SettingCard>

    <!-- 数据与存储 (只读) -->
    <SettingCard title="数据与存储" info="本机数据位置与引擎状态（只读）。全部数据仅存本机，不上传服务器。">
      <div class="dq-rows">
        <div class="dq-row">
          <span class="dq-label">存储模式</span>
          <el-tag size="small" type="info" data-test="store-kind">{{ storeKindLabel }}</el-tag>
          <span class="dq-hint">{{ storeKindHint }}</span>
        </div>
        <div class="dq-row">
          <span class="dq-label">语义就绪</span>
          <el-tag :type="storeInfo.semanticReady ? 'success' : 'warning'" size="small">{{ storeInfo.semanticReady ? '就绪' : '未就绪' }}</el-tag>
        </div>
        <div class="dq-row">
          <span class="dq-label">数据目录</span>
          <code class="dq-path">{{ storeInfo.localDir }}</code>
        </div>
      </div>
    </SettingCard>
  </div>
</template>

<script setup>
/**
 * 数据与质量设置段 (W?): Embedding / 异源裁判 配置下发 + 存储状态只读卡。
 * 治"端用户被迫改 .env": 语义检索与裁判配置此前只能环境变量, 现经
 * /api/settings/backend 持久化到本机 (LOCAL_DIR/backend_settings.json) 并即时生效。
 * key 回显脱敏 (configured + 尾4位), 留空 = 保持不变。
 */
import { computed, onMounted, reactive } from 'vue'
import http from '@/api'
import SettingCard from './SettingCard.vue'

const emb = reactive({
  configured: false, keyTail: '', source: '', baseUrl: '', model: '',
  keyInput: '', saving: false, msg: null,
})
const judge = reactive({
  enabled: false, configured: false, keyTail: '', source: '', sameSource: true,
  baseUrl: '', model: '', keyInput: '', saving: false, testing: false, msg: null,
})
const storeInfo = reactive({ kind: null, semanticReady: false, localDir: '' })

const embSourceLabel = computed(() => ({ runtime: '本页配置', env: '.env 环境变量', unset: '未配置' }[emb.source] || '未配置'))
const semanticBadge = computed(() => {
  if (!emb.configured) return { type: 'info', text: '未配置（纯图模式）' }
  return storeInfo.semanticReady
    ? { type: 'success', text: '就绪' }
    : { type: 'warning', text: '已配置，待生效/回填' }
})
const judgeBadge = computed(() => {
  if (!judge.enabled) return { type: 'info', text: '同源回退（未启用异源）' }
  return judge.sameSource
    ? { type: 'warning', text: '同源' }
    : { type: 'success', text: '异源独立裁判' }
})
const storeKindLabel = computed(() => ({ embedded: '本地嵌入存储', neo4j: 'Neo4j 图数据库' }[storeInfo.kind] || storeInfo.kind || '未知'))
const storeKindHint = computed(() => ({
  embedded: '安装包默认：零依赖单机运行',
  neo4j: '完整图数据库（Docker / 本机服务）',
}[storeInfo.kind] || ''))

async function load() {
  try {
    // @/api 响应拦截器已解包: http.get 直接返回 body —— `const { data } =` 解构必得 undefined
    // (v1.0.5 同类横扫漏网, 本文件 v1.2.0 新增时引入; 症状: 保存后报 reading 'embedding_applied')
    const data = (await http.get('/api/settings/backend')) || {}
    emb.configured = !!data.embedding?.configured
    emb.keyTail = data.embedding?.key_tail || ''
    emb.source = data.embedding?.source || 'unset'
    emb.baseUrl = data.embedding?.base_url || ''
    emb.model = data.embedding?.model || ''
    judge.enabled = !!data.judge?.enabled
    judge.configured = !!(data.judge?.key_tail)
    judge.keyTail = data.judge?.key_tail || ''
    judge.source = data.judge?.source || 'unset'
    judge.sameSource = !!data.judge?.same_source
    judge.baseUrl = data.judge?.base_url || ''
    judge.model = data.judge?.model || ''
    storeInfo.kind = data.store?.kind || null
    storeInfo.semanticReady = !!data.store?.semantic_ready
    storeInfo.localDir = data.data?.local_dir || ''
  } catch (e) {
    emb.msg = { ok: false, text: e?.response?.data?.detail || e?.message || '加载设置失败（后端未就绪?）' }
  }
}

async function saveEmbedding() {
  emb.saving = true
  emb.msg = null
  try {
    // key 留空 = 不变 (后端 None 合并语义); 显式清除用"清除已存 Key"按钮
    // (同上: 拦截器已解包, 直接拿 body)
    const data = (await http.post('/api/settings/backend', {
      embedding: {
        api_key: emb.keyInput || null,
        base_url: emb.baseUrl || null,
        model: emb.model || null,
      },
    })) || {}
    const applied = data.embedding_applied
    if (applied?.ok) {
      emb.msg = { ok: true, text: '已保存并生效（语义检索就绪）' }
    } else if (applied && applied.ok === false) {
      emb.msg = { ok: false, text: applied.reason ? `已保存，但生效失败: ${applied.reason}` : '已保存，但探活失败（已降级纯图），请检查 Key/模型' }
    } else {
      emb.msg = { ok: true, text: '已保存' }
    }
    emb.keyInput = ''
    await load()
  } catch (e) {
    emb.msg = { ok: false, text: e?.response?.data?.detail || e?.message || '保存失败' }
  } finally {
    emb.saving = false
  }
}

async function clearEmbeddingKey() {
  emb.saving = true
  try {
    await http.post('/api/settings/backend', { embedding: { clear_api_key: true } })
    emb.msg = { ok: true, text: '已清除（回落 .env 或纯图模式）' }
    emb.keyInput = ''
    await load()
  } catch (e) {
    emb.msg = { ok: false, text: e?.response?.data?.detail || e?.message || '清除失败' }
  } finally {
    emb.saving = false
  }
}

async function saveJudge(patch = {}) {
  judge.saving = true
  judge.msg = null
  try {
    await http.post('/api/settings/backend', {
      judge: {
        enabled: patch.enabled ?? judge.enabled,
        api_key: judge.keyInput || null,
        base_url: judge.baseUrl || null,
        model: judge.model || null,
      },
    })
    judge.msg = { ok: true, text: '已保存（下次质检调用生效）' }
    judge.keyInput = ''
    await load()
  } catch (e) {
    judge.msg = { ok: false, text: e?.response?.data?.detail || e?.message || '保存失败' }
  } finally {
    judge.saving = false
  }
}

async function testJudge() {
  judge.testing = true
  judge.msg = null
  try {
    // 拦截器已解包, 直接拿 body (解构会得 undefined → data.ok 抛 TypeError)
    const data = (await http.post('/api/settings/test-judge')) || {}
    judge.msg = data.ok
      ? { ok: true, text: `✓ 连接成功 (${data.same_source ? '同源' : '异源'}裁判)` }
      : { ok: false, text: `✗ 探活返回空响应 (${data.same_source ? '同源' : '异源'})` }
  } catch (e) {
    judge.msg = { ok: false, text: e?.response?.data?.detail || e?.message || '探活失败' }
  } finally {
    judge.testing = false
  }
}

onMounted(load)
</script>

<style scoped>
.dq-rows { display: flex; flex-direction: column; gap: 10px; }
.dq-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.dq-label { font-size: 13px; font-weight: 600; color: var(--km-gray-700); width: 72px; flex-shrink: 0; }
.dq-hint { font-size: 11.5px; color: var(--km-gray-500); }
.dq-msg {
  font-size: 12px; padding: 6px 10px;
  border-radius: var(--km-radius-sm);
}
.dq-msg.ok { color: var(--km-success, #67c23a); background: var(--km-success-light, #f0f9eb); }
.dq-msg.fail { color: var(--km-danger, #f56c6c); background: var(--km-danger-light, #fef0f0); }
.dq-path { font-size: 11.5px; color: var(--km-gray-600); font-family: var(--km-font-mono); word-break: break-all; }
</style>
