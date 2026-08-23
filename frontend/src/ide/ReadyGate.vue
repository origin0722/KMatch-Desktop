<template>
  <!-- issue-62: 启动就绪门 — 后端/KG 就绪后再进入主界面, 避免 AI 助手一进来就报错 -->
  <div class="ready-gate" data-test="ready-gate">
    <div class="gate-card">
      <div class="gate-brand">
        <div class="gate-logo">知链</div>
        <h1 class="gate-title">KMatch·知链</h1>
        <p class="gate-sub">知识图谱驱动的个性化学习平台</p>
      </div>

      <div class="gate-steps">
        <div class="gate-step" :class="stateClass(backend.backendUp)">
          <span class="step-dot" />
          <span class="step-label">{{ backend.backendUp ? '学习引擎已就绪' : '正在启动学习引擎…' }}</span>
        </div>
        <div class="gate-step" :class="stateClass(kgReady)">
          <span class="step-dot" />
          <span class="step-label">
            {{ kgReady
              ? (backend.graphStore === 'embedded' ? '知识图谱引擎就绪（本地嵌入式）' : '知识图谱引擎就绪')
              : (backend.backendUp ? '正在检查知识图谱引擎…' : '等待学习引擎…') }}
          </span>
        </div>
      </div>

      <div v-if="failed" class="gate-error" data-test="gate-error">
        <p class="err-title">后端未就绪</p>
        <p class="err-msg">{{ backend.lastError || '超过等待时间仍未连接' }}</p>
        <div class="err-actions">
          <el-button size="small" @click="retry">重试</el-button>
          <el-button size="small" type="primary" plain @click="$emit('skip')">仍要进入（只读预览）</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * ReadyGate — 启动就绪门 (issue-62)
 *
 * 轮询后端健康 (复用 backendHealth store), 就绪后 emit('ready') 进入主界面;
 * 超过 TIMEOUT_MS 未就绪 → 错误卡片 (重试 / 跳过)。
 * 注意: 只以 backendUp 为准 (sidecar 起来即可用), 不阻塞 Neo4j/LLM 配置缺失
 * (否则无 Docker/无 key 的用户会被永久锁在门外; 缺失项由 StatusBar/设置页非阻塞提示)。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useBackendHealthStore } from '@/stores/backendHealth'

const backend = useBackendHealthStore()

const emit = defineEmits(['ready', 'skip'])

const TIMEOUT_MS = 18000
const FAILED_MS = 3000 // 首查失败后的展示缓冲, 避免闪错卡

const failed = ref(false)
let _timer = null
let _failedTimer = null

const kgReady = computed(() =>
  backend.backendUp && (backend.graphStore === 'embedded' || backend.neo4jConnected),
)

function stateClass(ok) {
  return { waiting: !backend.backendUp, ok }
}

function retry() {
  failed.value = false
  checkAndSchedule()
}

function checkAndSchedule() {
  if (_timer) { clearInterval(_timer); _timer = null }
  backend.check()
  _timer = setInterval(backend.check, 1500)
}

function armFailed() {
  if (_failedTimer) { clearInterval(_failedTimer); _failedTimer = null }
  if (!backend.backendUp) {
    _failedTimer = setTimeout(() => { failed.value = true }, FAILED_MS)
  }
}

// store 是 Pinia setup store: backendUp 为解包后的布尔值, watch 须用 getter
watch(() => backend.backendUp, (up) => {
  if (up) {
    if (_failedTimer) { clearInterval(_failedTimer); _failedTimer = null }
    if (_timer) { clearInterval(_timer); _timer = null }
    if (failed.value) failed.value = false
    // 就绪后短暂停留展示"已就绪", 再进入 (体验自然)
    setTimeout(() => emit('ready'), 500)
  } else {
    armFailed()
  }
})

onMounted(() => {
  backend.start() // 幂等; 既有轮询 8s 仅在后台兜底
  checkAndSchedule()
  armFailed()
  _timer = setInterval(() => {
    if (failed.value) { clearInterval(_timer); _timer = null; return }
    if (Date.now() - _began > TIMEOUT_MS) {
      failed.value = true
      clearInterval(_timer); _timer = null
    }
  }, 500)
})

const _began = Date.now()

onBeforeUnmount(() => {
  if (_timer) clearInterval(_timer)
  if (_failedTimer) clearInterval(_failedTimer)
})
</script>

<style scoped>
.ready-gate {
  position: fixed; inset: 0; z-index: 999;
  display: flex; align-items: center; justify-content: center;
  background:
    radial-gradient(1200px 600px at 20% 10%, rgba(108, 124, 224, 0.10), transparent 60%),
    radial-gradient(900px 500px at 85% 80%, rgba(52, 179, 126, 0.08), transparent 55%),
    var(--km-bg-layer-1);
}
.gate-card {
  width: min(420px, 88vw);
  padding: 36px 32px;
  border-radius: var(--km-radius-panel);
  background: color-mix(in srgb, var(--km-bg-layer-2) 86%, transparent);
  border: 1px solid var(--km-border-light);
  backdrop-filter: blur(16px);
  box-shadow: var(--km-shadow-md, 0 8px 32px rgba(0,0,0,0.10));
  text-align: center;
}
.gate-brand { margin-bottom: 24px; }
.gate-logo {
  width: 56px; height: 56px; margin: 0 auto 12px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 16px; font-size: 18px; font-weight: 700; color: #fff;
  background: linear-gradient(135deg, var(--km-primary), var(--km-primary-active));
  box-shadow: 0 6px 18px rgba(108, 124, 224, 0.35);
}
.gate-title { margin: 0; font-size: 22px; font-weight: 700; color: var(--km-gray-800); }
.gate-sub { margin: 6px 0 0; font-size: 12.5px; color: var(--km-gray-500); }
.gate-steps { display: flex; flex-direction: column; gap: 10px; margin-bottom: 8px; }
.gate-step {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; border-radius: var(--km-radius-sm);
  background: var(--km-bg-layer-3); border: 1px solid var(--km-border-light);
  font-size: 13px; color: var(--km-gray-600); text-align: left;
}
.step-dot {
  width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0;
  background: var(--km-gray-400);
}
.gate-step.ok { border-color: color-mix(in srgb, var(--km-success) 40%, transparent); color: var(--km-gray-700); }
.gate-step.ok .step-dot { background: var(--km-success); box-shadow: 0 0 0 3px rgba(52,179,126,0.15); }
.gate-step.waiting .step-dot { background: var(--km-warning); animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
.gate-error {
  margin-top: 14px; padding: 14px; border-radius: var(--km-radius-sm);
  border: 1px solid color-mix(in srgb, var(--km-danger) 35%, transparent);
  background: color-mix(in srgb, var(--km-danger) 6%, transparent);
  text-align: left;
}
.err-title { margin: 0 0 4px; font-size: 14px; font-weight: 650; color: var(--km-danger); }
.err-msg { margin: 0 0 10px; font-size: 12.5px; color: var(--km-gray-600); word-break: break-all; }
.err-actions { display: flex; gap: 8px; }
@media (prefers-reduced-motion: reduce) { .gate-step.waiting .step-dot { animation: none; } }
</style>
