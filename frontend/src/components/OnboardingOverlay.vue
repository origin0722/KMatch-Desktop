<template>
  <transition name="ob-fade">
    <div v-if="visible" class="ob-overlay">
      <div class="ob-card">
        <!-- 品牌标 -->
        <div class="ob-brand">
          <div class="ob-logo">知</div>
          <span class="ob-brand-name">KMatch·知链</span>
        </div>

        <!-- 步骤内容 (key 触发切换动画) -->
        <transition name="ob-step" mode="out-in">
          <div :key="step" class="ob-step">
            <!-- Step 0: 欢迎 -->
            <template v-if="step === 0">
              <h2 class="ob-title">欢迎来到 KMatch·知链</h2>
              <p class="ob-sub">知识图谱驱动的个性化 Python 学习平台。几步配置, 开启你的专属学习路径。</p>
              <div class="ob-feat-list">
                <div class="ob-feat"><span class="ob-feat-ico">🎯</span><div><b>学习会话</b><span>答题诊断 → 专属图谱 → 讲义</span></div></div>
                <div class="ob-feat"><span class="ob-feat-ico">🕸️</span><div><b>知识图谱</b><span>可视化路径, 节点可溯源</span></div></div>
                <div class="ob-feat"><span class="ob-feat-ico">🤖</span><div><b>AI 助手</b><span>基于学情讲义答疑</span></div></div>
              </div>
            </template>

            <!-- Step 1: API Key -->
            <template v-else-if="step === 1">
              <h2 class="ob-title">连接你的 AI 助手</h2>
              <p class="ob-sub">配置 LLM API Key 以启用对话、学情诊断与内容生成。当前厂商: <b>{{ providerLabel }}</b>。</p>
              <el-input
                v-model="keyInput"
                type="password"
                show-password
                placeholder="sk-..."
                clearable
                size="large"
                class="ob-input"
                :class="{ set: aiSettings.apiKey && !keyInput }"
                @keydown.enter="next"
              >
                <template #prefix><span class="ob-input-prefix">🔑</span></template>
              </el-input>
              <p class="ob-hint" v-if="aiSettings.apiKey && !keyInput">已配置 API Key, 留空保持不变。可在「设置」页随时更换厂商。</p>
              <p class="ob-hint" v-else>可在「设置」页随时更换厂商或修改 Key。</p>
            </template>

            <!-- Step 2: 学习方向 -->
            <template v-else-if="step === 2">
              <h2 class="ob-title">你想学什么?</h2>
              <p class="ob-sub">选一个方向, 我们会在学习会话里为你量身规划起点。</p>
              <div class="ob-goal-grid">
                <button
                  v-for="g in GOALS"
                  :key="g.key"
                  type="button"
                  class="ob-goal"
                  :class="{ on: goal === g.key }"
                  @click="goal = g.key"
                >
                  <span class="ob-goal-ico">{{ g.icon }}</span>
                  <span class="ob-goal-name">{{ g.name }}</span>
                </button>
              </div>
            </template>

            <!-- Step 3: 就绪 -->
            <template v-else>
              <h2 class="ob-title">一切就绪</h2>
              <p class="ob-sub">从左侧「学习会话」开始, 或直接在右侧 AI 助手提问。你的学习图谱会随进度生长。</p>
              <div class="ob-ready-list">
                <div class="ob-check">✓ AI 助手 {{ aiSettings.apiKey ? '已连接' : '稍后配置' }}</div>
                <div class="ob-check">✓ 学习方向: {{ goalLabel }}</div>
                <div class="ob-check">✓ 知识图谱就绪</div>
              </div>
            </template>
          </div>
        </transition>

        <!-- 进度点 -->
        <div class="ob-dots">
          <span v-for="i in 4" :key="i" class="ob-dot" :class="{ on: i - 1 === step, done: i - 1 < step }" />
        </div>

        <!-- 操作 -->
        <div class="ob-actions">
          <el-button text size="small" class="ob-skip" @click="skipAll">跳过引导</el-button>
          <div class="ob-actions-right">
            <el-button v-if="step > 0" @click="prev">上一步</el-button>
            <el-button v-if="step < 3" type="primary" @click="next">
              {{ step === 1 ? (keyInput.trim() ? '保存并继续' : '继续') : '继续' }}
            </el-button>
            <el-button v-else type="primary" @click="finish">进入 KMatch</el-button>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useAiSettingsStore, PROVIDERS } from '@/stores/aiSettings'

const props = defineProps({
  visible: { type: Boolean, default: false },
})
const emit = defineEmits(['done'])

const aiSettings = useAiSettingsStore()

const GOALS = [
  { key: 'basic', icon: '🐍', name: 'Python 基础语法' },
  { key: 'crawler', icon: '🕸️', name: '网络爬虫' },
  { key: 'data', icon: '📊', name: '数据分析' },
  { key: 'web', icon: '🌐', name: 'Web 开发' },
]

// 续步: 从 localStorage 恢复上次进度 (未完成引导时重开可续)
const storedStep = Number(localStorage.getItem('kmatch-onboard-step')) || 0
const step = ref(isNaN(storedStep) ? 0 : Math.min(3, Math.max(0, storedStep)))
const keyInput = ref('')
const goal = ref(localStorage.getItem('kmatch-onboard-goal') || 'basic')

const providerLabel = computed(() => {
  const p = PROVIDERS.find((x) => x.id === aiSettings.provider)
  return p?.label || aiSettings.providerMeta()?.label || aiSettings.provider
})
const goalLabel = computed(() => GOALS.find((g) => g.key === goal.value)?.name || '未选择')

watch(step, (s) => localStorage.setItem('kmatch-onboard-step', String(s)))
watch(goal, (g) => localStorage.setItem('kmatch-onboard-goal', g))

async function next() {
  if (step.value === 1 && keyInput.value.trim()) {
    await aiSettings.setApiKey(keyInput.value.trim())
    keyInput.value = ''
  }
  if (step.value === 2) {
    // 方向已由 watch 持久化
  }
  if (step.value < 3) step.value++
}

function prev() {
  if (step.value > 0) step.value--
}

function finish() {
  localStorage.setItem('kmatch-onboarded', '1')
  localStorage.removeItem('kmatch-onboard-step')
  emit('done')
}

function skipAll() {
  finish()
}
</script>

<style scoped>
.ob-overlay {
  position: fixed;
  inset: 0;
  z-index: 2500;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(15, 18, 30, 0.42);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}

.ob-card {
  width: 100%;
  max-width: 520px;
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  padding: 36px 40px 28px;
  border-radius: 20px;
  background: var(--km-bg-layer-1);
  border: 1px solid var(--km-border-light);
  box-shadow: 0 28px 70px -16px rgba(15, 18, 30, 0.45);
  display: flex;
  flex-direction: column;
}

/* 品牌 */
.ob-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 24px;
}
.ob-logo {
  width: 40px; height: 40px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; font-weight: 700; color: #fff;
  background: linear-gradient(135deg, var(--km-primary), var(--km-primary-active));
  box-shadow: 0 6px 18px -6px var(--km-primary);
}
.ob-brand-name { font-size: 14px; font-weight: 600; color: var(--km-gray-700); letter-spacing: 0.3px; }

/* 步骤区 */
.ob-step { flex: 1; min-height: 0; }
.ob-title {
  font-size: 22px; font-weight: 600; color: var(--km-gray-800);
  margin: 0 0 10px; letter-spacing: 0.2px;
}
.ob-sub {
  font-size: 13.5px; color: var(--km-gray-500); line-height: 1.7;
  margin: 0 0 22px;
}
.ob-hint { font-size: 12px; color: var(--km-gray-500); margin: 10px 2px 0; line-height: 1.6; }

/* 特性列表 */
.ob-feat-list { display: flex; flex-direction: column; gap: 10px; }
.ob-feat {
  display: flex; align-items: center; gap: 14px;
  padding: 14px 16px;
  border-radius: 12px;
  background: var(--km-bg-layer-2);
  border: 1px solid var(--km-border-light);
}
.ob-feat-ico { font-size: 20px; flex-shrink: 0; }
.ob-feat b { display: block; font-size: 13.5px; font-weight: 600; color: var(--km-gray-700); }
.ob-feat span { font-size: 12px; color: var(--km-gray-500); }

/* API Key 输入 */
.ob-input { width: 100%; }
.ob-input.set :deep(.el-input__wrapper) {
  border-color: var(--km-primary);
  box-shadow: 0 0 0 2px var(--km-primary-light);
}
.ob-input-prefix { font-size: 14px; }

/* 目标网格 */
.ob-goal-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.ob-goal {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 20px 12px;
  border-radius: 12px;
  background: var(--km-bg-layer-2);
  border: 1.5px solid var(--km-border-light);
  cursor: pointer;
  transition: all 0.18s var(--km-ease);
}
.ob-goal:hover { border-color: var(--km-border-focus); transform: translateY(-1px); }
.ob-goal.on {
  border-color: var(--km-primary);
  background: var(--km-primary-light);
  box-shadow: 0 6px 18px -8px var(--km-primary);
}
.ob-goal-ico { font-size: 26px; }
.ob-goal-name { font-size: 13px; font-weight: 500; color: var(--km-gray-700); }

/* 就绪清单 */
.ob-ready-list { display: flex; flex-direction: column; gap: 10px; }
.ob-check {
  font-size: 13px; color: var(--km-gray-600);
  padding: 12px 16px;
  border-radius: 10px;
  background: var(--km-bg-layer-2);
  border: 1px solid var(--km-border-light);
}

/* 进度点 */
.ob-dots { display: flex; gap: 8px; justify-content: center; margin: 28px 0 18px; }
.ob-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--km-border);
  transition: all 0.2s var(--km-ease);
}
.ob-dot.done { background: var(--km-primary-light); }
.ob-dot.on { width: 22px; border-radius: 4px; background: var(--km-primary); }

/* 操作 */
.ob-actions {
  display: flex; align-items: center; justify-content: space-between;
  padding-top: 16px;
  border-top: 1px solid var(--km-border-light);
}
.ob-skip { color: var(--km-gray-500); }
.ob-actions-right { display: flex; gap: 8px; }

/* 过渡 */
.ob-fade-enter-active, .ob-fade-leave-active { transition: opacity 0.25s var(--km-ease); }
.ob-fade-enter-from, .ob-fade-leave-to { opacity: 0; }
.ob-fade-enter-active .ob-card { animation: obIn 0.32s var(--km-ease-out); }
@keyframes obIn { from { opacity: 0; transform: translateY(12px) scale(0.98); } to { opacity: 1; transform: none; } }

.ob-step-enter-active, .ob-step-leave-active { transition: opacity 0.18s var(--km-ease), transform 0.18s var(--km-ease); }
.ob-step-enter-from { opacity: 0; transform: translateX(10px); }
.ob-step-leave-to { opacity: 0; transform: translateX(-10px); }

@media (max-width: 520px) {
  .ob-card { padding: 28px 22px 22px; border-radius: 16px; }
  .ob-goal-grid { grid-template-columns: 1fr; }
}
</style>
