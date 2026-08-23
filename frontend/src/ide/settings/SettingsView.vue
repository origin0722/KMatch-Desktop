<template>
  <div class="settings-view">
    <div v-if="renderErr" class="settings-fatal">
      <strong>设置页加载失败</strong>
      <pre>{{ renderErr }}</pre>
      <p class="hint">打开开发者工具 (Ctrl+Shift+I) 查看完整堆栈, 或刷新页面重试。</p>
    </div>
    <template v-else>
      <div ref="mainEl" class="settings-main" @scroll="onScroll">
        <div class="settings-topbar">
          <span class="settings-title">设置</span>
          <button class="settings-close" @click="sidebar.back()" title="关闭设置">×</button>
        </div>
        <div class="settings-content">
          <!-- issue-63: 设置收敛为三大配置块 + 通用: AI 助手 / 学习引擎 / 联网搜索 -->
          <section id="sec-assistant" ref="secAssistant" class="settings-section">
            <h2 class="section-title">AI 助手</h2>
            <AssistantSettings />
          </section>
          <section id="sec-agent" ref="secAgent" class="settings-section">
            <h2 class="section-title">学习引擎</h2>
            <AgentSettings />
          </section>
          <section id="sec-web" ref="secWeb" class="settings-section">
            <h2 class="section-title">联网搜索</h2>
            <WebSearchSettings />
          </section>
          <section id="sec-general" class="settings-section">
            <h2 class="section-title">通用</h2>
            <!-- issue-73: 启动偏好 (默认视图 / 导航默认折叠) -->
            <div class="general-row">
              <div class="general-info">
                <b>启动偏好</b>
                <span>打开应用时进入的视图；导航栏是否默认折叠为图标轨。</span>
              </div>
              <div class="general-actions">
                <el-select :model-value="themeStore.accent" size="small" style="width: 132px" data-test="accent" @change="onAccent">
                  <el-option label="靛蓝+琥珀 (默认)" value="default" />
                  <el-option label="深青+珊瑚" value="teal" />
                  <el-option label="紫罗兰+青柠" value="violet" />
                </el-select>
                <el-select :model-value="startView" size="small" style="width: 150px" data-test="default-view" @change="onDefaultView">
                  <el-option label="代码" value="code" />
                  <el-option label="学习会话" value="learning-session" />
                  <el-option label="AI 助手" value="chat" />
                  <el-option label="数据看板" value="dashboard" />
                  <el-option label="学习资源" value="learning" />
                </el-select>
                <span class="general-inline">
                  导航折叠
                  <el-switch :model-value="sidebar.navCollapsed" data-test="nav-collapsed-switch" @change="sidebar.toggleNavCollapsed()" />
                </span>
              </div>
            </div>
            <!-- issue-73: 学习偏好 (每周可学时长 → 折周展示) -->
            <div class="general-row">
              <div class="general-info">
                <b>学习偏好</b>
                <span>每周可投入学习时长（1-20h），用于学习路径"预计 N 周"的节奏估算。</span>
              </div>
              <div class="general-actions">
                <el-input-number :model-value="prefs.hoursPerWeek" :min="1" :max="20" size="small" data-test="hours-per-week" @change="onHoursPerWeek" />
                <span class="general-inline">h / 周</span>
              </div>
            </div>
            <!-- issue-73: 数据管理 (前端本地数据清理) -->
            <div class="general-row">
              <div class="general-info">
                <b>数据管理</b>
                <span>清除本地对话历史 / 学习资源（不删除后端运行记录）。</span>
              </div>
              <div class="general-actions">
                <el-button size="small" data-test="clear-chat" @click="clearChat">清对话历史</el-button>
                <el-button size="small" data-test="clear-resources" @click="clearResources">清学习资源</el-button>
              </div>
            </div>
            <div class="general-row">
              <div class="general-info">
                <b>重新查看首次引导</b>
                <span>API Key / 学习方向配置向导, 当前配置不会被重置。</span>
              </div>
              <el-button data-test="re-onboard" @click="sidebar.startOnboarding()">重新引导</el-button>
            </div>
            <!-- 数据底座 (D 批: Neo4j 状态 + Docker 引导) -->
            <div class="general-row">
              <div class="general-info">
                <b>数据底座 (Neo4j)
                  <span class="db-badge" :class="dbBadgeClass">{{ dbBadgeLabel }}</span>
                </b>
                <span>学习路径图谱 / 知识检索依赖本地图数据库。</span>
              </div>
              <el-popover
                placement="left"
                :width="340"
                trigger="click"
                popper-class="neo4j-guide-pop"
              >
                <template #reference>
                  <el-button size="small" :disabled="!backend.backendUp">启动引导</el-button>
                </template>
                <div class="neo4j-guide">
                  <div class="ng-title">数据底座 (Neo4j) {{ backend.neo4jStatus === 'connected' ? '已就绪' : '未就绪' }}</div>
                  <template v-if="dockerChecked && docker.installed">
                    <p class="ng-desc">已检测到 Docker。在项目根目录运行以下命令启动 Neo4j:</p>
                    <div class="ng-cmd">
                      <code>docker-compose up -d</code>
                      <el-button size="small" @click="copyDockerCmd">复制</el-button>
                    </div>
                    <p class="ng-hint">启动后约 10s 内后端自动连上图库。<a href="#" @click.prevent="backend.check()">重新检测</a></p>
                  </template>
                  <template v-else-if="dockerChecked && !docker.installed">
                    <p class="ng-desc">
                      未检测到 Docker。安装 <a href="https://www.docker.com/products/docker-desktop/" target="_blank" rel="noopener">Docker Desktop</a>
                      后运行 <code>docker-compose up -d</code> 启用完整图数据库功能。
                    </p>
                    <div class="ng-note">受限模式: 不装 Docker 时, 测评 / 对话 / 内容生成仍可用, 图谱检索与路径规划不可用。</div>
                  </template>
                  <template v-else>
                    <p class="ng-hint">正在探测 Docker…</p>
                  </template>
                </div>
              </el-popover>
            </div>
          </section>
        </div>
      </div>
      <aside class="settings-anchors">
        <a
          v-for="a in anchors"
          :key="a.id"
          class="settings-anchor"
          :class="{ active: activeAnchor === a.id }"
          @click="scrollTo(a.id)"
        >{{ a.label }}</a>
      </aside>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, onErrorCaptured } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AssistantSettings from './AssistantSettings.vue'
import AgentSettings from './AgentSettings.vue'
import WebSearchSettings from './WebSearchSettings.vue'
import { useSidebarStore } from '@/stores/sidebar'
import { useBackendHealthStore } from '@/stores/backendHealth'
import { usePrefsStore } from '@/stores/prefs'
import { useThemeStore } from '@/stores/theme'
import { useChatStore } from '@/stores/chat'
import { useLearningResourcesStore } from '@/stores/learningResources'

const sidebar = useSidebarStore()
const backend = useBackendHealthStore()
const prefs = usePrefsStore()
const themeStore = useThemeStore()

// ---- issue-73: 启动偏好 / 数据管理 ----
const startView = ref(sidebar.activeView)
function onAccent(v) {
  themeStore.setAccent(v)
  ElMessage.success('强调色已切换（即时生效）')
}
function onDefaultView(v) {
  sidebar.setDefaultView(v)
  ElMessage.success(`默认视图已设为「${v}」`)
}
function onHoursPerWeek(v) {
  prefs.setHoursPerWeek(v)
  ElMessage.success(`已保存：每周 ${prefs.hoursPerWeek}h`)
}
async function clearChat() {
  try {
    await ElMessageBox.confirm('清除所有 AI 对话历史？此操作不可撤销。', '清对话历史', { type: 'warning' })
  } catch { return }
  useChatStore().clearMessages()
  ElMessage.success('对话历史已清除')
}
async function clearResources() {
  try {
    await ElMessageBox.confirm('清除学习资源页的联网资源与生成内容？', '清学习资源', { type: 'warning' })
  } catch { return }
  useLearningResourcesStore().clear()
  const { useAssessmentStore } = await import('@/stores/assessment')
  const a = useAssessmentStore()
  if (a.generatedContent) a.generatedContent = null
  ElMessage.success('学习资源已清除')
}

// ---- 数据底座 (D 批): Docker 探测 + Neo4j 状态徽标 ----
const dockerChecked = ref(false)
const docker = ref({ installed: false, version: '', hint: '' })

async function probeDocker() {
  if (!window.api?.docker) return
  try {
    docker.value = await window.api.docker.checkVersion()
  } catch {
    docker.value = { installed: false, version: '', hint: '' }
  } finally {
    dockerChecked.value = true
  }
}

async function copyDockerCmd() {
  try {
    await navigator.clipboard.writeText('docker-compose up -d')
    ElMessage.success('启动命令已复制, 在项目根目录运行')
  } catch {
    ElMessage.warning('复制失败, 请手动复制: docker-compose up -d')
  }
}

const dbBadgeLabel = computed(() => {
  if (!backend.backendUp) return '后端未起'
  return backend.neo4jStatus === 'connected' ? '已连接' : '未连接'
})
const dbBadgeClass = computed(() => ({
  ok: backend.backendUp && backend.neo4jStatus === 'connected',
  bad: backend.backendUp && backend.neo4jStatus !== 'connected',
}))

onMounted(() => {
  backend.start()
  probeDocker()
})

const anchors = [
  { id: 'sec-assistant', label: 'AI 助手' },
  { id: 'sec-agent', label: '学习引擎' },
  { id: 'sec-web', label: '联网搜索' },
  { id: 'sec-general', label: '通用' },
]

const mainEl = ref(null)
const activeAnchor = ref('sec-assistant')
const renderErr = ref(null)
let observer = null

// 错误边界: 子组件渲染崩溃时捕获并显示, 避免白屏表现为"点设置没反应"
onErrorCaptured((err) => {
  renderErr.value = err?.stack || err?.message || String(err)
  console.error('[SettingsView] 子组件渲染错误:', err)
  return false
})

function scrollTo(id) {
  activeAnchor.value = id
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function onScroll() {
  // 兜底: IntersectionObserver 在某些环境不触发时, 按滚动位置近似
  if (!mainEl.value) return
  const tops = anchors.map((a) => {
    const el = document.getElementById(a.id)
    return { id: a.id, top: el ? el.getBoundingClientRect().top : Infinity }
  })
  // 选 top 最接近 0 且 >= 负高度一半的段
  const visible = tops.filter((t) => t.top < 120)
  if (visible.length) activeAnchor.value = visible[visible.length - 1].id
}

onMounted(async () => {
  await nextTick()
  if (!('IntersectionObserver' in window) || !mainEl.value) return
  observer = new IntersectionObserver(
    (entries) => {
      const entering = entries.filter((e) => e.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (entering[0]) activeAnchor.value = entering[0].target.id
    },
    { root: mainEl.value, rootMargin: '-20% 0px -70% 0px', threshold: 0 },
  )
  anchors.forEach((a) => {
    const el = document.getElementById(a.id)
    if (el) observer.observe(el)
  })
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<style scoped>
.settings-fatal {
  flex: 1;
  padding: 24px;
  color: var(--km-danger, #f56c6c);
  font-family: var(--km-font-mono, monospace);
  font-size: 12.5px;
}
.settings-fatal strong { font-size: 15px; display: block; margin-bottom: 8px; }
.settings-fatal pre { white-space: pre-wrap; word-break: break-all; background: var(--km-bg-layer-2); padding: 10px; border-radius: var(--km-radius-sm); margin: 8px 0; }
.settings-fatal .hint { color: var(--km-gray-500); margin-top: 10px; font-family: inherit; }
.settings-view {
  display: flex;
  height: 100%;
  min-height: 0;
  background: var(--km-bg-layer-1);
}
.settings-topbar { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px 10px 28px; border-bottom: 1px solid var(--km-border-light); position: sticky; top: 0; background: var(--km-bg-layer-1); z-index: 2; }
.settings-title { font-size: 15px; font-weight: 650; color: var(--km-gray-800); }
.settings-close { border: 0; background: transparent; color: var(--km-gray-500); cursor: pointer; font-size: 22px; line-height: 1; width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--km-radius-sm); }
.settings-close:hover { background: var(--km-gray-100); color: var(--km-gray-800); }
.settings-main {
  flex: 1;
  overflow-y: auto;
  scroll-behavior: smooth;
}
.settings-content {
  max-width: 760px;
  margin: 0 auto;
  padding: 24px 28px 60px;
}
.settings-section { margin-bottom: 8px; scroll-margin-top: 16px; }
/* 通用段行 (T2 重新引导入口): 左说明右按钮, 视觉对齐其他段的列表行 */
.general-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border-radius: var(--km-radius);
  background: var(--km-bg-layer-2);
  border: 1px solid var(--km-border-light);
}
.general-info b { display: block; font-size: 13.5px; font-weight: 600; color: var(--km-gray-700); }
.general-info span { font-size: 12px; color: var(--km-gray-500); }
/* issue-73: 通用段右侧操作组 (启动偏好/学习偏好/数据管理) */
.general-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: flex-end; }
.general-inline { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--km-gray-500); white-space: nowrap; }
/* 数据底座徽标 (D 批) */
.db-badge {
  display: inline-block; margin-left: 8px;
  font-size: 10px; font-weight: 700;
  padding: 1px 8px; border-radius: 999px;
  vertical-align: 1px;
}
.db-badge.ok { color: var(--km-success); background: var(--km-success-light); }
.db-badge.bad { color: var(--km-warning); background: var(--km-warning-light); }
.section-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--km-gray-800);
  margin: 20px 0 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--km-border-light);
}
.settings-anchors {
  width: 160px;
  flex-shrink: 0;
  padding: 28px 16px;
  border-left: 1px solid var(--km-border-light);
  position: sticky;
  top: 0;
  align-self: flex-start;
}
.settings-anchor {
  display: block;
  padding: 6px 10px;
  margin-bottom: 4px;
  font-size: 12.5px;
  color: var(--km-gray-500);
  border-radius: var(--km-radius-sm);
  cursor: pointer;
  border-left: 2px solid transparent;
  transition: color 0.16s var(--km-ease), background 0.16s var(--km-ease), border-color 0.16s var(--km-ease);
}
.settings-anchor:hover { color: var(--km-gray-700); background: var(--km-gray-100); }
.settings-anchor.active {
  color: var(--km-primary-active);
  border-left-color: var(--km-primary-active);
  background: var(--km-primary-light);
}
/* 设置页按钮质感 (2026-08-12 用户反馈"按钮太粗糙"): 统一圆角/字重/主按钮轻阴影 */
.settings-content :deep(.el-button) {
  border-radius: var(--km-radius-sm);
  font-weight: 500;
  letter-spacing: 0.2px;
}
.settings-content :deep(.el-button--primary:not(.is-plain):not(.is-link):not(.is-text)) {
  box-shadow: 0 1px 2px rgba(108, 124, 224, 0.28), 0 0 0 1px rgba(108, 124, 224, 0.08);
}
.settings-content :deep(.el-button--primary.is-plain) {
  color: var(--km-primary-active);
}
.settings-content :deep(.el-button-group .el-button:first-child) {
  border-top-left-radius: 7px;
  border-bottom-left-radius: 7px;
}
.settings-content :deep(.el-button-group .el-button:last-child) {
  border-top-right-radius: 7px;
  border-bottom-right-radius: 7px;
}
</style>
