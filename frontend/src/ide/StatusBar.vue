<template>
  <div class="status-bar">
    <div class="status-left">
      <span class="status-item" v-if="ws.hasProject">
        <el-icon :size="13"><FolderOpened /></el-icon>{{ ws.rootName }}
      </span>
      <span class="status-item" v-if="ws.activeFile">{{ ws.activeFile }}</span>
      <span class="status-item muted" v-if="ws.activeFile && dirty">未保存</span>
    </div>
    <div class="status-right">
      <!-- Neo4j 状态 + 数据底座引导 (D 批: 已装 docker → 一键复制启动命令; 未装 → 官网 + 受限说明) -->
      <el-popover
        v-if="backend.backendUp && backend.neo4jStatus !== 'connected'"
        placement="top-start"
        :width="360"
        trigger="click"
        popper-class="neo4j-guide-pop"
      >
        <template #reference>
          <span class="status-item clickable neo4j-item" :title="neo4jTitle">
            <span class="dot neo4j-dot"></span>图库未连
          </span>
        </template>
        <div class="neo4j-guide">
          <div class="ng-title">数据底座 (Neo4j) 未就绪</div>
          <p class="ng-desc">
            学习路径图谱 / 知识检索等功能依赖本地图数据库。后端已就绪, 但连不上图库。
          </p>

          <template v-if="dockerChecked && docker.installed">
            <div class="ng-step">
              <b>已检测到 Docker</b> — 一键启动 Neo4j:
            </div>
            <div class="ng-cmd">
              <code>docker-compose up -d</code>
              <el-button size="small" class="ng-copy" @click="copyDockerCmd">复制</el-button>
            </div>
            <p class="ng-hint">在项目根目录运行后, 后端会在 ~10s 内自动连上图库。已复制? <a href="#" @click.prevent="backend.check()">重新检测</a></p>
          </template>

          <template v-else-if="dockerChecked && !docker.installed">
            <div class="ng-step"><b>未检测到 Docker</b></div>
            <p class="ng-desc">
              数据底座需要 <a href="https://www.docker.com/products/docker-desktop/" target="_blank" rel="noopener">Docker Desktop</a>。
              安装并启动后, 在项目根目录运行 <code>docker compose up -d</code> 即可启用完整功能。
            </p>
            <div class="ng-note">
              受限模式: 不装 Docker 时, 测评/对话/内容生成仍可用, 但图谱检索与路径规划不可用。
            </div>
          </template>

          <template v-else>
            <p class="ng-hint">正在探测 Docker…</p>
          </template>
        </div>
      </el-popover>

      <!-- 端用户免 Docker: 嵌入式存储状态 (无 Docker/JVM/端口) -->
      <span v-if="backend.backendUp && backend.graphStore === 'embedded'"
        class="status-item ok" title="进程内嵌入式存储, 无需 Docker / JVM / 端口">
        <span class="dot"></span>本地存储
      </span>
      <!-- 语义检索降级: 温和提示而非报错 -->
      <span v-if="backend.backendUp && backend.semanticState === 'degraded'"
        class="status-item semantic-degraded"
        title="语义检索未就绪(配置 Embedding key 后自动启用), 当前使用图谱精准检索, 功能不受影响">
        <span class="dot"></span>纯图模式
      </span>

      <span class="status-item" :class="backendClass" :title="backendTitle">
        <span class="dot"></span>{{ backend.label }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useWorkspaceStore } from '@/stores/workspace'
import { useBackendHealthStore } from '@/stores/backendHealth'

const ws = useWorkspaceStore()
const backend = useBackendHealthStore()

const dirty = computed(() => ws.activeFile && ws.dirtyFiles.has(ws.activeFile))

const backendClass = computed(() => ({
  ok: backend.backendUp,
  bad: backend.status === false,
}))
const backendTitle = computed(() => backend.backendUp ? 'localhost:8000' : '后端未运行, 测评/图谱等功能不可用 (见 scripts/start_all.py)')
const neo4jTitle = computed(() => {
  if (backend.neo4jStatus === 'connected') return 'Neo4j 已连接'
  if (backend.neo4jStatus === 'down') return 'Neo4j 未连接 — 点击查看启动引导'
  return 'Neo4j 状态未知'
})

// ---- Docker 探测 (数据底座引导) ----
const dockerChecked = ref(false)
const docker = ref({ installed: false, version: '', hint: '' })

async function probeDocker() {
  if (!window.api?.docker) return // 浏览器 dev 无 IPC, 跳过探测
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

// 健康检查轮询在 backendHealth store 内启动 (幂等); StatusBar 触发首次启动
onMounted(() => {
  backend.start()
  probeDocker()
})
</script>

<style scoped>
.status-bar {
  height: 24px;
  background: var(--km-statusbar-bg);
  color: var(--km-gray-600);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  font-size: 12px;
  flex-shrink: 0;
  border-top: 1px solid var(--km-border-light);
}
.status-left, .status-right { display: flex; align-items: center; gap: 14px; }
.status-item { display: flex; align-items: center; gap: 4px; }
.status-item.muted { opacity: 0.6; }
.status-item.clickable { cursor: pointer; }
.dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--km-gray-400);
  transition: background 0.3s var(--km-ease);
}
.status-item.ok .dot { background: var(--km-success); box-shadow: 0 0 4px var(--km-success); }
.status-item.bad .dot { background: var(--km-danger); }
.neo4j-item { color: var(--km-warning); }
.neo4j-item:hover { color: var(--km-warning); }
.neo4j-dot { background: var(--km-warning); box-shadow: 0 0 4px var(--km-warning); }
.semantic-degraded { color: var(--km-warning); }
.semantic-degraded .dot { background: var(--km-warning); box-shadow: 0 0 4px var(--km-warning); }
</style>