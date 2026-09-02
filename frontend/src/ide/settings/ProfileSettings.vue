<template>
  <div class="profile-settings">
    <!-- 加载中 -->
    <SettingCard v-if="loading" title="学习画像" info="正在读取本地画像档案…">
      <div class="ps-loading">读取中…</div>
    </SettingCard>

    <!-- 无档案空态 -->
    <SettingCard v-else-if="notFound || !learnerKey" title="学习画像" info="稳定学习者档案，跨次测评自动累积掌握度">
      <div class="ps-empty">
        <p>尚未生成画像档案——完成一次学习测评后自动创建。</p>
        <p class="ps-empty-sub">前往「学习会话」选择一个目标方向开始测评，测评完成即生成画像，之后每次测评都会更新它。</p>
      </div>
    </SettingCard>

    <!-- 有档案 -->
    <template v-else-if="profile">
      <!-- 概览 -->
      <SettingCard title="画像概览" info="理论/实操等级 + 学习风格徽标（来源标记）">
        <div class="ps-overview">
          <div class="ov-cell">
            <span class="ov-num">{{ profile.theory_level ?? '—' }}</span>
            <span class="ov-label">理论等级 (1-5)</span>
          </div>
          <div class="ov-cell">
            <span class="ov-num">{{ profile.practical_level ?? '—' }}</span>
            <span class="ov-label">实操等级 (1-5)</span>
          </div>
          <div class="ov-cell style-cell">
            <span class="ov-style">{{ styleLabel }}</span>
            <span class="ov-label">{{ styleSourceLabel }}</span>
          </div>
          <div class="ov-cell">
            <span class="ov-num sm">{{ fmtPace }}</span>
            <span class="ov-label">{{ profile.time_per_week || 6 }} h/周 · 节奏</span>
          </div>
        </div>
        <div v-if="lastUpdated" class="ps-meta">最近更新：{{ lastUpdated }}</div>
      </SettingCard>

      <!-- 知识点掌握度 -->
      <SettingCard title="知识点掌握度" info="已掌握与待巩固知识点 (mastery 条形)">
        <div v-if="!profile.known_topics?.length && !profile.weak_topics?.length" class="ps-empty-sub">
          暂无知识点记录——完成测评后展示已掌握/薄弱点。
        </div>
        <template v-else>
          <div class="ps-topics">
            <div v-for="t in profile.known_topics" :key="t.node_id" class="topic-row">
              <span class="topic-name">{{ t.name || t.node_id }}</span>
              <span class="topic-badge known">已掌握</span>
              <div class="mastery-bar"><i class="fill known" :style="{ width: Math.round((t.mastery || 0) * 100) + '%' }" /></div>
              <span class="topic-mastery">{{ Math.round((t.mastery || 0) * 100) }}%</span>
            </div>
            <div v-for="t in profile.weak_topics" :key="t.node_id" class="topic-row">
              <span class="topic-name">{{ t.name || t.node_id }}</span>
              <span class="topic-badge weak">待巩固</span>
              <div class="mastery-bar"><i class="fill weak" :style="{ width: Math.round((t.mastery || 0) * 100) + '%' }" /></div>
              <span class="topic-mastery">{{ Math.round((t.mastery || 0) * 100) }}%</span>
            </div>
          </div>
        </template>
      </SettingCard>

      <!-- 编辑画像 -->
      <SettingCard title="编辑画像" info="学习背景 + 每周学时 + 学习节奏（可选，保存后写回档案）">
        <div class="ps-form">
          <div class="pf-field"><span class="pf-label">教育背景</span>
            <el-select v-model="form.education" placeholder="学历" clearable size="small" style="width: 160px">
              <el-option v-for="e in EDU_OPTIONS" :key="e" :label="e" :value="e" />
            </el-select>
          </div>
          <div class="pf-field"><span class="pf-label">专业</span>
            <el-input v-model="form.major" placeholder="专业" size="small" style="width: 200px" :maxlength="60" />
          </div>
          <div class="pf-field"><span class="pf-label">年龄段</span>
            <el-select v-model="form.age_range" placeholder="可选" clearable size="small" style="width: 110px">
              <el-option v-for="a in AGE_OPTIONS" :key="a" :label="a" :value="a" />
            </el-select>
          </div>
          <div class="pf-field"><span class="pf-label">编程经验 (月)</span>
            <el-input-number v-model="form.programming_experience_months" :min="0" :max="10000" controls-position="right" size="small" style="width: 120px" />
          </div>
          <div class="pf-field"><span class="pf-label">Python 经验 (月)</span>
            <el-input-number v-model="form.python_experience_months" :min="0" :max="10000" controls-position="right" size="small" style="width: 120px" />
          </div>
          <div class="pf-field"><span class="pf-label">每周可投入 (h)</span>
            <el-input-number v-model="form.time_per_week" :min="1" :max="168" controls-position="right" size="small" style="width: 120px" />
          </div>
          <div class="pf-field"><span class="pf-label">学习节奏</span>
            <el-select v-model="form.preferred_pace" placeholder="跟随推荐" clearable size="small" style="width: 140px">
              <el-option v-for="p in PACE_OPTIONS" :key="p.value" :label="p.label" :value="p.value" />
            </el-select>
          </div>
        </div>
        <div class="ps-actions">
          <el-button type="primary" size="small" :loading="saving" data-test="profile-save" @click="save">保存修改</el-button>
          <span v-if="saveMsg" class="ps-save-msg">{{ saveMsg }}</span>
        </div>
      </SettingCard>

      <!-- 学习历史摘要 -->
      <SettingCard title="学习历史摘要" info="跨次测评的画像版本记录 (最近 20 次)">
        <div v-if="!history.length" class="ps-empty-sub">暂无历史记录。</div>
        <div v-else class="ps-history">
          <div v-for="(h, i) in history.slice().reverse()" :key="i" class="hist-row">
            <span class="hist-ts">{{ fmtTs(h.ts) }}</span>
            <span class="hist-level">等级 {{ h.theory_level ?? '—' }}</span>
            <span class="hist-count">{{ h.known ?? 0 }} 已知 · {{ h.weak ?? 0 }} 薄弱</span>
          </div>
        </div>
      </SettingCard>

      <!-- 操作: 导出 / 重置 -->
      <div class="ps-danger">
        <el-button size="small" data-test="profile-export" @click="exportProfile">导出画像 JSON</el-button>
        <el-button size="small" type="danger" plain data-test="profile-reset" @click="resetProfile">重置画像</el-button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import SettingCard from './SettingCard.vue'
import { fetchProfile, updateProfile, deleteProfile, isDemographicsFilled } from '@/api/diagnostics'

const EDU_OPTIONS = ['高中及以下', '大专', '本科', '硕士', '博士', '非科班自学者']
const AGE_OPTIONS = ['<18', '18-25', '26-35', '36+']
const PACE_OPTIONS = [
  { label: '跟随推荐 (normal)', value: 'normal' },
  { label: '稳扎稳打 (slow)', value: 'slow' },
  { label: '快速推进 (fast)', value: 'fast' },
]
const STYLE_META = {
  visual: { label: '视觉型' },
  auditory: { label: '听觉型' },
  read_write: { label: '阅读写作型' },
  kinesthetic: { label: '动手实践型' },
}
const STYLE_SOURCE = {
  quiz: '实测 (VARK 问卷)',
  default: '占位 (未作答)',
}
const PACE_LABEL = { slow: '稳扎稳打', normal: '跟随推荐', fast: '快速推进' }

const learnerKey = ref('')
try { learnerKey.value = localStorage.getItem('kmatch-learner') || '' } catch { /* private */ }

const loading = ref(true)
const notFound = ref(false)
const saving = ref(false)
const saveMsg = ref('')
const profile = ref(null)
const history = ref([])

const form = reactive({
  education: '', major: '', age_range: '',
  programming_experience_months: null, python_experience_months: null,
  time_per_week: 6, preferred_pace: 'normal',
})

const styleLabel = computed(() => {
  const s = profile.value?.learning_style
  return s ? (STYLE_META[s]?.label || s) : '—'
})
const styleSourceLabel = computed(() => STYLE_SOURCE[profile.value?.style_source] || '')

const fmtPace = computed(() => PACE_LABEL[profile.value?.preferred_pace] || '跟随推荐')

const lastUpdated = computed(() => {
  const ts = history.value[history.value.length - 1]?.ts || profile.value?.created_at
  return ts ? fmtTs(ts) : ''
})

function fmtTs(t) {
  if (!t) return '—'
  try {
    const dt = new Date(t)
    return dt.toLocaleString('zh-CN', { hour12: false })
  } catch { return String(t) }
}

function fillForm(p) {
  const d = p?.demographics || {}
  form.education = d.education || ''
  form.major = d.major || ''
  form.age_range = d.age_range || ''
  form.programming_experience_months = d.programming_experience_months ?? null
  form.python_experience_months = d.python_experience_months ?? null
  form.time_per_week = p?.time_per_week || 6
  form.preferred_pace = p?.preferred_pace || 'normal'
}

async function load() {
  loading.value = true
  notFound.value = false
  if (!learnerKey.value) { notFound.value = true; loading.value = false; return }
  try {
    const data = await fetchProfile(learnerKey.value)
    profile.value = data.profile
    history.value = data.history || []
    fillForm(data.profile)
  } catch (e) {
    if (e?.response?.status === 404) { notFound.value = true; profile.value = null; history.value = [] }
    else ElMessage.error(e?.response?.data?.detail || e?.message || '读取画像失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  saveMsg.value = ''
  const demographics = {
    education: form.education || undefined,
    major: form.major || undefined,
    age_range: form.age_range || undefined,
    programming_experience_months: form.programming_experience_months ?? undefined,
    python_experience_months: form.python_experience_months ?? undefined,
  }
  const payload = {
    // 仅当学习背景含任一字段才上送 (全空不清除已有档案)
    ...(isDemographicsFilled(demographics) ? { demographics } : {}),
    time_per_week: form.time_per_week || undefined,
    preferred_pace: form.preferred_pace || undefined,
  }
  try {
    profile.value = await updateProfile(learnerKey.value, payload)
    fillForm(profile.value)
    saveMsg.value = '已保存'
    ElMessage.success('画像已更新')
    setTimeout(() => { saveMsg.value = '' }, 2000)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function exportProfile() {
  const payload = {
    learner_key: learnerKey.value,
    exported_at: new Date().toISOString(),
    profile: profile.value,
    history: history.value,
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `kmatch-profile-${learnerKey.value}.json`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('画像已导出')
}

async function resetProfile() {
  try {
    await ElMessageBox.confirm(
      '将删除该学习画像档案（含掌握度历史），重新测评后将重建。确定重置？',
      '重置画像', { type: 'warning', confirmButtonText: '确认重置', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await deleteProfile(learnerKey.value)
    profile.value = null
    history.value = []
    notFound.value = true
    ElMessage.success('画像已重置')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '重置失败')
  }
}

onMounted(load)
</script>

<style scoped>
.ps-loading { padding: 20px 0; text-align: center; color: var(--km-gray-500); font-size: 13px; }
.ps-empty { padding: 10px 0; }
.ps-empty p { margin: 0 0 6px; color: var(--km-gray-600); font-size: 13px; }
.ps-empty-sub { color: var(--km-gray-400); font-size: 12px; }

.ps-overview { display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: center; }
.ov-cell { display: flex; flex-direction: column; gap: 2px; min-width: 84px; }
.ov-num { font-size: 22px; font-weight: 700; color: var(--km-gray-800); }
.ov-num.sm { font-size: 16px; line-height: 26px; }
.ov-style { font-size: 14px; font-weight: 600; color: var(--km-primary-active); }
.ov-label { font-size: 11px; color: var(--km-gray-500); }
.ps-meta { margin-top: 10px; font-size: 12px; color: var(--km-gray-400); }

.ps-topics { display: flex; flex-direction: column; gap: 8px; }
.topic-row { display: flex; align-items: center; gap: 10px; }
.topic-name { flex: 1; min-width: 120px; font-size: 12.5px; color: var(--km-gray-700); }
.topic-badge { font-size: 11px; padding: 1px 8px; border-radius: 999px; flex-shrink: 0; }
.topic-badge.known { color: var(--km-success); background: var(--km-success-light); }
.topic-badge.weak { color: var(--km-warning); background: var(--km-warning-light); }
.mastery-bar { flex: 2; height: 8px; border-radius: 999px; background: var(--km-bg-layer-1); overflow: hidden; }
.mastery-bar .fill { display: block; height: 100%; border-radius: 999px; }
.mastery-bar .fill.known { background: var(--km-success); }
.mastery-bar .fill.weak { background: var(--km-warning); }
.topic-mastery { width: 42px; text-align: right; font-size: 12px; color: var(--km-gray-500); font-variant-numeric: tabular-nums; }

.ps-form { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; }
.pf-field { display: inline-flex; align-items: center; gap: 6px; }
.pf-label { font-size: 12px; color: var(--km-gray-500); flex-shrink: 0; }
.ps-actions { margin-top: 12px; display: flex; align-items: center; gap: 10px; }
.ps-save-msg { font-size: 12px; color: var(--km-success); }

.ps-history { display: flex; flex-direction: column; gap: 6px; max-height: 260px; overflow-y: auto; }
.hist-row { display: flex; align-items: center; gap: 12px; font-size: 12px; color: var(--km-gray-600); }
.hist-ts { flex: 1; min-width: 140px; color: var(--km-gray-500); }
.hist-level { width: 90px; }
.hist-count { color: var(--km-gray-400); }

.ps-danger { display: flex; gap: 10px; margin-top: 4px; }
</style>
