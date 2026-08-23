<template>
  <div class="git-view" data-test="git-view">
    <!-- ① Git 未安装 -->
    <div v-if="gitReady === false" class="git-center">
      <el-empty description="未检测到 Git 命令">
        <p class="git-hint">请先安装 <a href="https://git-scm.com/download/win" target="_blank" rel="noreferrer">Git for Windows</a>，安装后重启 KMatch。</p>
        <el-button size="small" @click="checkGit">重新检测</el-button>
      </el-empty>
    </div>

    <!-- ② 正在检测 -->
    <div v-else-if="gitReady === null" class="git-center">
      <el-empty description="正在检测 Git…" />
    </div>

    <!-- ③ 未打开项目 -->
    <div v-else-if="!workspace.root" class="git-center">
      <el-empty description="先打开或克隆一个项目，即可像 VS Code 一样管理 Git 仓库">
        <div class="git-actions">
          <el-button type="primary" @click="cloneRepo">克隆远程仓库</el-button>
          <el-button @click="openProject">打开本地项目</el-button>
        </div>
      </el-empty>
    </div>

    <!-- ④ 已打开项目但非 Git 仓库 -->
    <div v-else-if="!status.isRepo" class="git-center">
      <el-empty description="当前文件夹还不是 Git 仓库">
        <div class="git-actions">
          <el-button type="primary" @click="initRepo">初始化 Git 仓库</el-button>
          <el-button @click="cloneRepo">克隆远程仓库</el-button>
        </div>
        <p class="git-hint">初始化后将本文件夹纳入版本控制；克隆则从远程拉取一个全新项目。</p>
      </el-empty>
    </div>

    <!-- ⑤ 仓库面板 -->
    <div v-else class="git-repo">
      <!-- 头部: 分支 + 操作 -->
      <div class="git-head">
        <div class="git-branch" data-test="git-branch">
          <span class="git-branch-dot" />
          <span class="git-branch-name">{{ status.branch || '（无分支）' }}</span>
        </div>
        <div class="git-head-actions">
          <el-button size="small" :loading="busy" data-test="git-pull" @click="pull">拉取</el-button>
          <el-button size="small" type="primary" :loading="busy" data-test="git-push" @click="push">推送</el-button>
          <el-button size="small" :loading="busy" data-test="git-refresh" @click="refresh">刷新</el-button>
        </div>
      </div>

      <!-- 更改文件 -->
      <div class="git-section">
        <div class="git-section-title">更改（{{ status.files.length }}）</div>
        <div v-if="!status.files.length" class="git-clean" data-test="git-clean">工作区干净，没有未提交的更改。</div>
        <div v-else class="git-files">
          <div v-for="(f, i) in status.files" :key="i" class="git-file" data-test="git-file">
            <span class="git-st" :class="statusKind(f.status).cls" :title="statusKind(f.status).label">
              {{ statusKind(f.status).label }}
            </span>
            <span class="git-file-path">{{ f.path }}</span>
          </div>
        </div>
      </div>

      <!-- 提交区 -->
      <div class="git-section">
        <div class="git-section-title">提交更改</div>
        <el-input
          v-model="commitMsg"
          type="textarea"
          :rows="2"
          placeholder="输入提交说明（如：修复登录页空指针）"
          data-test="git-commit-input"
        />
        <div class="git-commit-row">
          <el-button
            size="small"
            type="primary"
            :loading="busy"
            :disabled="!commitMsg.trim()"
            data-test="git-commit"
            @click="commitAll"
          >
            暂存全部并提交
          </el-button>
          <span class="git-hint-inline">提交前会自动 git add -A</span>
        </div>
      </div>

      <!-- 最近提交 -->
      <div class="git-section">
        <div class="git-section-title">最近提交</div>
        <div v-if="!commits.length" class="git-clean">暂无提交记录。</div>
        <div v-else class="git-commits">
          <div v-for="(c, i) in commits" :key="i" class="git-commit" data-test="git-commit-item">
            <span class="git-hash">{{ c.hash }}</span>
            <span class="git-msg">{{ c.message }}</span>
          </div>
        </div>
      </div>

      <!-- 命令输出 -->
      <div v-if="output" class="git-section">
        <div class="git-section-title">命令输出</div>
        <pre class="git-output" :class="{ err: outputError }" data-test="git-output">{{ output }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * Git 视图 (issue-93, 方案A) — 主进程调系统 git CLI, 无真实 PTY 终端。
 * 能力: 检测 git / 打开或克隆项目 / git init / 状态 / 拉取 / 暂存提交 / 推送 / 最近提交。
 * 凭据: HTTPS 依赖系统 git 配置(凭据管理器/token), 应用不保存任何密钥。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useWorkspaceStore } from '@/stores/workspace'

const workspace = useWorkspaceStore()

const gitReady = ref(null)       // null=检测中, true/false
const gitVersion = ref('')
const busy = ref(false)
const status = ref({ isRepo: false, branch: '', files: [] })
const commitMsg = ref('')
const commits = ref([])
const output = ref('')
const outputError = ref(false)

const hasGitApi = computed(() => !!(window.api && window.api.git))

function showOut(res, fallbackOk = '完成') {
  if (res && res.ok) {
    output.value = res.output || fallbackOk
    outputError.value = false
  } else {
    output.value = (res && res.error) || '操作失败'
    outputError.value = true
  }
}

async function checkGit() {
  if (!hasGitApi.value) { gitReady.value = false; return }
  const res = await window.api.git.check()
  if (res && res.ok) {
    gitReady.value = true
    gitVersion.value = res.version || ''
  } else {
    gitReady.value = false
  }
}

async function refresh() {
  if (!hasGitApi.value || !workspace.root || gitReady.value !== true) return
  busy.value = true
  try {
    const [st, lg] = await Promise.all([
      window.api.git.status(workspace.root),
      window.api.git.log({ cwd: workspace.root, max: 10 }),
    ])
    if (st && st.ok) status.value = st
    else status.value = { isRepo: true, branch: '', files: [] }
    if (lg && lg.ok) {
      commits.value = lg.output.split(/\r?\n/).filter(Boolean).map((line) => ({
        hash: line.slice(0, 7),
        message: line.slice(8) || line,
      }))
    } else {
      commits.value = []
    }
  } finally {
    busy.value = false
  }
}

async function initRepo() {
  if (!workspace.root) return
  busy.value = true
  try {
    const res = await window.api.git.init(workspace.root)
    showOut(res, '已初始化 Git 仓库')
    if (res.ok) { ElMessage.success('Git 仓库已初始化'); await refresh() }
    else ElMessage.error(res.error || '初始化失败')
  } finally { busy.value = false }
}

async function cloneRepo() {
  let url = ''
  try {
    const r = await ElMessageBox.prompt('输入远程仓库地址（HTTPS 或 SSH）', '克隆远程仓库', {
      confirmButtonText: '下一步',
      cancelButtonText: '取消',
      inputPlaceholder: 'https://github.com/user/repo.git',
      inputValidator: (v) => (v && v.trim() ? true : '请输入仓库地址'),
    })
    url = (r.value || '').trim()
  } catch { return } // 用户取消

  if (!hasGitApi.value) { ElMessage.error('当前环境不支持 Git 操作'); return }
  busy.value = true
  try {
    const res = await window.api.git.clone({ url })
    if (res && res.ok && res.root) {
      // 切到克隆出的项目 → 自动触发文件树加载 + 项目图谱解析
      await workspace.setRoot(res.root)
      output.value = res.output || '克隆完成'
      outputError.value = false
      ElMessage.success(`已克隆到 ${res.root}`)
      await refresh()
    } else if (res && res.canceled) {
      output.value = ''
    } else {
      const msg = (res && res.error) || '克隆失败'
      output.value = msg
      outputError.value = true
      ElMessage.error(msg)
    }
  } finally { busy.value = false }
}

async function openProject() {
  await workspace.openProject()
}

async function pull() {
  if (!workspace.root) return
  busy.value = true
  try {
    const res = await window.api.git.pull(workspace.root)
    showOut(res, '已拉取')
    if (res.ok) ElMessage.success('拉取完成')
    else ElMessage.error(res.error || '拉取失败')
    await refresh()
  } finally { busy.value = false }
}

async function commitAll() {
  if (!workspace.root || !commitMsg.value.trim()) return
  busy.value = true
  try {
    const res = await window.api.git.commit({ cwd: workspace.root, message: commitMsg.value.trim(), stageAll: true })
    showOut(res, '已提交')
    if (res.ok) {
      ElMessage.success('提交成功')
      commitMsg.value = ''
      await refresh()
    } else {
      ElMessage.error(res.error || '提交失败')
    }
  } finally { busy.value = false }
}

async function push() {
  if (!workspace.root) return
  busy.value = true
  try {
    const res = await window.api.git.push(workspace.root)
    showOut(res, '已推送')
    if (res.ok) ElMessage.success('推送成功')
    else ElMessage.error(res.error || '推送失败')
  } finally { busy.value = false }
}

/** 前置两个字符 → 语义标签/颜色类 */
function statusKind(s) {
  const st = (s || '  ').padEnd(2, ' ')
  if (st.startsWith('??')) return { label: '未跟踪', cls: 'untracked' }
  if (st[0] === 'A' || st[1] === 'A') return { label: '新增', cls: 'added' }
  if (st[0] === 'D' || st[1] === 'D') return { label: '删除', cls: 'deleted' }
  if (st[0] === 'M' || st[1] === 'M') return { label: '修改', cls: 'modified' }
  if (st[0] === 'R') return { label: '重命名', cls: 'renamed' }
  if (st.includes('U')) return { label: '冲突', cls: 'conflicted' }
  return { label: '变更', cls: 'modified' }
}

watch(() => workspace.root, () => { refresh() })

onMounted(async () => {
  await checkGit()
  if (gitReady.value) await refresh()
})
</script>

<style scoped>
.git-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}
.git-center {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
}
.git-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
  margin-top: 4px;
}
.git-hint {
  font-size: 13px;
  color: var(--km-gray-500);
  margin-top: 8px;
  line-height: 1.6;
}
.git-hint-inline { font-size: 12px; color: var(--km-gray-500); margin-left: 10px; }

.git-repo {
  max-width: 860px;
  width: 100%;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding-bottom: 12px;
}
.git-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.git-branch {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--km-gray-800);
}
.git-branch-dot {
  width: 9px; height: 9px;
  border-radius: 50%;
  background: var(--km-success, #2eb872);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--km-success, #2eb872) 20%, transparent);
}
.git-head-actions { display: flex; gap: 8px; }

.git-section { display: flex; flex-direction: column; gap: 8px; }
.git-section-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--km-gray-600);
  letter-spacing: 0.3px;
  text-transform: uppercase;
}
.git-clean {
  font-size: 13px;
  color: var(--km-gray-500);
  padding: 6px 2px;
}
.git-files {
  border: 1px solid var(--km-border-light);
  border-radius: var(--km-radius-sm);
  overflow: hidden;
}
.git-file {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 12px;
  font-size: 13px;
  color: var(--km-gray-800);
  background: var(--km-bg-layer-2);
}
.git-file + .git-file { border-top: 1px solid var(--km-border-light); }
.git-st {
  flex-shrink: 0;
  min-width: 42px;
  text-align: center;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
}
.git-st.untracked { background: color-mix(in srgb, #e6a23c 16%, transparent); color: #b9750e; }
.git-st.added     { background: color-mix(in srgb, #2eb872 16%, transparent); color: #1f8a55; }
.git-st.modified  { background: color-mix(in srgb, #409eff 16%, transparent); color: #2d6fc2; }
.git-st.deleted   { background: color-mix(in srgb, #f56c6c 16%, transparent); color: #c24545; }
.git-st.renamed   { background: color-mix(in srgb, #9b59b6 16%, transparent); color: #7d3d99; }
.git-st.conflicted{ background: color-mix(in srgb, #f56c6c 26%, transparent); color: #a83232; }
.git-file-path { font-family: var(--km-font-mono, monospace); font-size: 12.5px; word-break: break-all; }

.git-commit-row { display: flex; align-items: center; }
.git-commits {
  border: 1px solid var(--km-border-light);
  border-radius: var(--km-radius-sm);
  overflow: hidden;
}
.git-commit {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 12px;
  font-size: 13px;
  color: var(--km-gray-800);
  background: var(--km-bg-layer-2);
}
.git-commit + .git-commit { border-top: 1px solid var(--km-border-light); }
.git-hash {
  flex-shrink: 0;
  font-family: var(--km-font-mono, monospace);
  font-size: 12px;
  color: var(--km-primary-active, #4a7dfa);
}
.git-msg { word-break: break-all; }

.git-output {
  margin: 0;
  padding: 10px 12px;
  font-family: var(--km-font-mono, monospace);
  font-size: 12px;
  line-height: 1.6;
  background: var(--km-bg-layer-2);
  border: 1px solid var(--km-border-light);
  border-radius: var(--km-radius-sm);
  color: var(--km-gray-700);
  white-space: pre-wrap;
  word-break: break-all;
}
.git-output.err { color: #c24545; border-color: color-mix(in srgb, #f56c6c 40%, transparent); }
</style>
