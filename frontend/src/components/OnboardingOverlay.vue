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
              <p class="ob-sub">围绕知识图谱组织的 Python 学习工具: 先摸底你的水平, 再按依赖顺序组装学习路径, 生成配套讲义与练习。三步配置即可开始。</p>
              <div class="ob-feat-list">
                <div class="ob-feat"><span class="ob-feat-ico">①</span><div><b>学习会话</b><span>答题摸底 → 生成学习路径 → 配套讲义</span></div></div>
                <div class="ob-feat"><span class="ob-feat-ico">②</span><div><b>知识图谱</b><span>知识点依赖关系可视化, 每个论断可溯源</span></div></div>
                <div class="ob-feat"><span class="ob-feat-ico">③</span><div><b>AI 助手</b><span>结合你的学情讲义答疑与导学</span></div></div>
              </div>
            </template>

            <!-- Step 1: API Key -->
            <template v-else-if="step === 1">
              <h2 class="ob-title">连接你的 AI 助手</h2>
              <p class="ob-sub">配置 LLM API Key 以启用对话、学情诊断与内容生成。当前厂商: <b>{{ providerLabel }}</b>。</p>
              <div class="ob-provider-chips">
                <button
                  v-for="p in quickProviders"
                  :key="p.id"
                  type="button"
                  class="ob-provider-chip"
                  :class="{ on: aiSettings.provider === p.id }"
                  @click="aiSettings.setProvider(p.id)"
                >
                  <img :src="iconUrlOf(p.iconKey)" class="ob-chip-icon" alt="" />
                  <span>{{ p.label }}</span>
                </button>
              </div>
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
                <template #prefix><span class="ob-input-prefix">KEY</span></template>
              </el-input>
              <div class="ob-key-meta">
                <a v-if="providerKeyUrl" :href="providerKeyUrl" target="_blank" rel="noopener" class="ob-key-link">获取 {{ providerLabel }} Key ↗</a>
                <span class="ob-privacy">密钥仅存本机, 不上传</span>
              </div>
              <p class="ob-hint" v-if="aiSettings.apiKey && !keyInput">已配置 API Key, 留空保持不变。可在「设置」页随时更换厂商。</p>
              <p class="ob-hint ob-hint-warn" v-else-if="keyInput.trim() && keyInput.trim().length < 20">这个 Key 看起来偏短, 请确认已完整粘贴 (可继续, 保存后可测试连接)。</p>
              <p class="ob-hint" v-else>可在「设置」页随时更换厂商或修改 Key。</p>
            </template>

            <!-- Step 2: 学习场景 + 方向 -->
            <template v-else-if="step === 2">
              <h2 class="ob-title">你想怎么开始?</h2>
              <p class="ob-sub">选一个场景, 我们会为你打开对应的工作区。</p>
              <div class="ob-scene-grid">
                <button
                  v-for="s in SCENES"
                  :key="s.key"
                  type="button"
                  class="ob-scene"
                  :class="{ on: scene === s.key }"
                  @click="scene = s.key"
                >
                  <span class="ob-scene-ico">{{ s.icon }}</span>
                  <span class="ob-scene-name">{{ s.name }}</span>
                  <span class="ob-scene-desc">{{ s.desc }}</span>
                </button>
              </div>
              <!-- 学新技能: 展开方向选择 -->
              <template v-if="scene === 'learn'">
                <p class="ob-sub-section">选一个方向, 我们会在学习会话里为你量身规划起点。</p>
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
              <!-- 有项目: 提示打开项目 -->
              <template v-else>
                <p class="ob-hint ob-hint-project">完成后从左侧文件管理器「打开项目」, 我们会自动解析代码生成知识图谱, AI 助手也能基于项目结构回答架构问题。</p>
              </template>
            </template>

            <!-- Step 3: 就绪 -->
            <template v-else>
              <h2 class="ob-title">一切就绪</h2>
              <p class="ob-sub">{{ scene === 'learn' ? '马上为你打开学习会话, 你的学习图谱会随进度生长。' : '马上为你打开代码视图, 打开项目后自动生成知识图谱。' }}</p>
              <div class="ob-ready-list">
                <div class="ob-check">✓ AI 助手 {{ aiSettings.apiKey ? '已连接' : '稍后配置' }}</div>
                <div class="ob-check" v-if="scene === 'learn'">✓ 学习方向: {{ goalLabel }}</div>
                <div class="ob-check" v-else>✓ 场景: 有项目二次开发</div>
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
            <el-button v-else type="primary" @click="finish()">进入 KMatch</el-button>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useAiSettingsStore, PROVIDERS } from '@/stores/aiSettings'
import { iconUrlOf } from '@/services/llm/icons'

const props = defineProps({
  visible: { type: Boolean, default: false },
})
const emit = defineEmits(['done'])

const aiSettings = useAiSettingsStore()

const SCENES = [
  { key: 'learn', icon: '🎓', name: '学新技能', desc: '无项目, 从零开始学' },
  { key: 'project', icon: '🔧', name: '有项目二次开发', desc: '已有项目, 想理解并改进' },
]
const GOALS = [
  { key: 'basic', icon: '🐍', name: 'Python 基础语法', direction: 'Python 基础语法入门' },
  { key: 'crawler', icon: '🕸️', name: '网络爬虫', direction: '网络爬虫' },
  { key: 'data', icon: '📊', name: '数据分析', direction: '数据分析与可视化' },
  { key: 'web', icon: '🌐', name: 'Web 开发', direction: 'Web 后端开发' },
]

// 续步: 从 localStorage 恢复上次进度 (未完成引导时重开可续)
const storedStep = Number(localStorage.getItem('kmatch-onboard-step')) || 0
const step = ref(isNaN(storedStep) ? 0 : Math.min(3, Math.max(0, storedStep)))
const keyInput = ref('')
const scene = ref(localStorage.getItem('kmatch-onboard-scene') || 'learn')
const goal = ref(localStorage.getItem('kmatch-onboard-goal') || 'basic')

const providerLabel = computed(() => {
  const p = PROVIDERS.find((x) => x.id === aiSettings.provider)
  return p?.label || aiSettings.providerMeta()?.label || aiSettings.provider
})
// B4: 厂商快速切换 chips + "获取 Key"链接
const quickProviders = PROVIDERS.filter((p) => p.id !== 'custom')
const providerKeyUrl = computed(() => PROVIDERS.find((p) => p.id === aiSettings.provider)?.keyUrl || '')
const goalLabel = computed(() => GOALS.find((g) => g.key === goal.value)?.name || '未选择')

watch(step, (s) => localStorage.setItem('kmatch-onboard-step', String(s)))
watch(scene, (s) => localStorage.setItem('kmatch-onboard-scene', s))
watch(goal, (g) => localStorage.setItem('kmatch-onboard-goal', g))

async function next() {
  if (step.value === 1 && keyInput.value.trim()) {
    await aiSettings.setApiKey(keyInput.value.trim())
    keyInput.value = ''
  }
  if (step.value === 2) {
    // 学新技能场景: goal -> 方向文本写入 kmatch-onboard-direction (StageGoal.vue 读取预填)
    if (scene.value === 'learn') {
      const g = GOALS.find((x) => x.key === goal.value)
      if (g?.direction) localStorage.setItem('kmatch-onboard-direction', g.direction)
    } else {
      localStorage.removeItem('kmatch-onboard-direction')
    }
  }
  if (step.value < 3) step.value++
}

function prev() {
  if (step.value > 0) step.value--
}

// done 事件携带场景, 由 Workspace.vue 决定落地视图; onboarded 标记由 sidebar store 单点写
function finish(skipped = false) {
  // 跳过/完成时清 step 残留 (goal/scene/direction 保留供后续读取)
  localStorage.removeItem('kmatch-onboard-step')
  emit('done', skipped, skipped ? null : scene.value)
}

function skipAll() {
  finish(true)
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
.ob-hint-warn { color: var(--km-warning, #b88230); }

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

/* B4: 厂商快速切换 chips + Key 获取链接 + 隐私文案 */
.ob-provider-chips {
  display: flex; flex-wrap: wrap; gap: 6px;
  margin: 0 0 16px;
}
.ob-provider-chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 5px 10px;
  border: 1px solid var(--km-border-light);
  border-radius: 999px;
  background: var(--km-bg-layer-2);
  font-size: 12px; color: var(--km-gray-600);
  cursor: pointer;
  transition: all 0.15s var(--km-ease);
}
.ob-provider-chip:hover { border-color: var(--km-border-focus); }
.ob-provider-chip.on {
  border-color: var(--km-primary);
  background: var(--km-primary-light);
  color: var(--km-primary); font-weight: 600;
}
.ob-chip-icon { width: 13px; height: 13px; }
.ob-key-meta {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-top: 10px;
}
.ob-key-link {
  font-size: 12px; color: var(--km-primary); text-decoration: none;
}
.ob-key-link:hover { text-decoration: underline; }
.ob-privacy { font-size: 11px; color: var(--km-gray-500); }

/* 目标网格 */
.ob-sub-section { font-size: 12px; color: var(--km-gray-500); margin: 16px 0 10px; }
.ob-scene-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.ob-scene {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 18px 12px;
  border-radius: 12px;
  background: var(--km-bg-layer-2);
  border: 1.5px solid var(--km-border-light);
  cursor: pointer;
  transition: all 0.18s var(--km-ease);
}
.ob-scene:hover { border-color: var(--km-border-focus); transform: translateY(-1px); }
.ob-scene.on {
  border-color: var(--km-primary);
  background: var(--km-primary-light);
  box-shadow: 0 6px 18px -8px var(--km-primary);
}
.ob-scene-ico { font-size: 26px; }
.ob-scene-name { font-size: 13px; font-weight: 600; color: var(--km-gray-700); }
.ob-scene-desc { font-size: 11px; color: var(--km-gray-500); }
.ob-hint-project { margin-top: 14px; padding: 12px 14px; border-radius: 10px; background: var(--km-bg-layer-2); border: 1px solid var(--km-border-light); line-height: 1.7; }

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
  .ob-scene-grid { grid-template-columns: 1fr; }
}
</style>
