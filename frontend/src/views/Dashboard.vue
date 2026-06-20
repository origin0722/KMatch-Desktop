<template>
  <div class="dashboard-page">
    <!-- ============================================================ -->
    <!-- 页面标题 -->
    <!-- ============================================================ -->
    <div class="page-header">
      <h3>数据看板</h3>
      <p class="page-desc">
        个人学情与资源匹配度报告：知识盲区定位 · 难度匹配曲线 · 学习路径规划
      </p>
    </div>

    <!-- ============================================================ -->
    <!-- 空状态 -->
    <!-- ============================================================ -->
    <el-empty
      v-if="!hasData"
      description="尚未完成学情测评，无报告数据"
      :image-size="120"
    >
      <el-button type="primary" @click="sidebar.setView('assessment')">
        前往学情测评
      </el-button>
    </el-empty>

    <!-- ============================================================ -->
    <!-- 有数据时 -->
    <!-- ============================================================ -->
    <template v-else>
      <!-- 概览卡片行 -->
      <div class="overview-row">
        <div class="stat-card">
          <div class="stat-value">{{ (blindSpots.summary.overall_mastery * 100).toFixed(0) }}%</div>
          <div class="stat-label">综合掌握度</div>
          <div class="stat-sub">{{ blindSpots.summary.total }} 个节点</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ (accuracy * 100).toFixed(0) }}%</div>
          <div class="stat-label">答题正确率</div>
          <div class="stat-sub">{{ assessment?.total_count || 0 }} 题</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" :class="diffMatch.summary.avg_gap > 1 ? 'warn' : 'ok'">
            {{ diffMatch.summary.avg_gap > 0 ? '+' : '' }}{{ diffMatch.summary.avg_gap.toFixed(1) }}
          </div>
          <div class="stat-label">平均难度偏差</div>
          <div class="stat-sub">{{ diffMatch.summary.matched }}/{{ diffMatch.summary.total_resources }} 匹配</div>
        </div>
        <div class="stat-card" v-if="reviewResults">
          <div class="stat-value" :class="reviewResults.passed ? 'ok' : 'warn'">
            {{ reviewResults.passed ? '通过' : '打回' }}
          </div>
          <div class="stat-label">内容审核</div>
          <div class="stat-sub">得分 {{ ((reviewResults.overall_score || 0) * 100).toFixed(0) }}%</div>
        </div>
      </div>

      <!-- 第一行: 盲区定位 + 难度匹配 -->
      <div class="charts-row">
        <!-- ① 知识盲区定位 -->
        <el-card class="chart-card" shadow="never">
          <template #header>
            <span>① 知识盲区定位</span>
            <el-tag size="small" type="danger" v-if="blindSpots.summary.weak > 0">
              {{ blindSpots.summary.weak }} 个薄弱
            </el-tag>
          </template>
          <div ref="blindChartRef" class="chart-box"></div>
        </el-card>

        <!-- ② 资源难度匹配 -->
        <el-card class="chart-card" shadow="never">
          <template #header>
            <span>② 资源难度匹配曲线</span>
            <el-tag size="small" :type="diffMatch.summary.too_hard > 0 ? 'warning' : 'success'">
              {{ diffMatch.summary.matched }} 匹配
            </el-tag>
          </template>
          <div ref="matchChartRef" class="chart-box"></div>
        </el-card>
      </div>

      <!-- 第二行: 学习路径规划图 -->
      <el-card class="path-card" shadow="never">
        <template #header>
          <span>③ 学习路径规划图</span>
          <span class="path-meta">
            {{ pathData.nodes.length }} 节点 · {{ pathData.estimated_total_hours?.toFixed(1) || '--' }}h
            · 预计 {{ pathData.estimated_completion_weeks || '--' }} 周
          </span>
        </template>
        <div class="path-graph">
          <!-- 路径节点横向流程 -->
          <div class="path-flow">
            <template v-for="(node, idx) in pathData.nodes" :key="node.node_id">
              <div
                class="path-node"
                :class="[`status-${node.status}`, { current: node.is_current }]"
                :title="`${node.name} (Lv${node.difficulty}) — ${statusLabel(node.status)}`"
              >
                <div class="pn-index">{{ idx + 1 }}</div>
                <div class="pn-name">{{ node.name }}</div>
                <div class="pn-meta">Lv{{ node.difficulty }} · {{ node.estimated_minutes }}min</div>
                <div class="pn-mastery" v-if="node.mastery > 0">
                  <el-progress
                    :percentage="Math.round(node.mastery * 100)"
                    :stroke-width="4"
                    :color="masteryColor(node.mastery)"
                    :show-text="false"
                  />
                </div>
              </div>
              <div v-if="idx < pathData.nodes.length - 1" class="path-arrow">→</div>
            </template>
          </div>
        </div>
      </el-card>

      <!-- 第三行: 质量指标 -->
      <el-card class="quality-card" shadow="never" v-if="qualityMetrics">
        <template #header>
          <span>📊 赛题 M5 质量检测指标</span>
          <el-tag
            :type="qualityMetrics.all_passed ? 'success' : 'danger'"
            size="small"
            style="margin-left: 12px;"
          >
            {{ qualityMetrics.all_passed ? '✓ 三项全达标' : '✗ 存在未达标项' }}
          </el-tag>
          <el-tag
            :type="qualityMetrics.source === 'backend' ? 'success' : 'warning'"
            size="small"
            style="margin-left: 8px;"
          >
            {{ qualityMetrics.source === 'backend' ? '后端真实计算' : '客户端估算' }}
          </el-tag>
        </template>
        <div class="quality-row">
          <div class="quality-item">
            <div class="q-value" :class="qualityMetrics.hallucination_rate < 0.05 ? 'ok' : 'fail'">
              {{ (qualityMetrics.hallucination_rate * 100).toFixed(1) }}%
            </div>
            <div class="q-label">幻觉率</div>
            <div class="q-target">目标 &lt;5%</div>
          </div>
          <div class="quality-item">
            <div class="q-value" :class="qualityMetrics.adaptation_rate >= 0.85 ? 'ok' : 'fail'">
              {{ (qualityMetrics.adaptation_rate * 100).toFixed(1) }}%
            </div>
            <div class="q-label">适配率</div>
            <div class="q-target">目标 ≥85%</div>
          </div>
          <div class="quality-item">
            <div class="q-value" :class="qualityMetrics.coverage_rate >= 0.9 ? 'ok' : 'fail'">
              {{ (qualityMetrics.coverage_rate * 100).toFixed(1) }}%
            </div>
            <div class="q-label">覆盖率</div>
            <div class="q-target">目标 ≥90%</div>
          </div>
        </div>
      </el-card>
    </template>
  </div>
</template>

<script setup>
/**
 * KMatch 数据看板 — 赛题(3)① 可视化报告
 *
 * 从 assessment store 取原始数据，客户端派生三类可视化:
 *   ① 知识盲区定位 — ECharts 横向柱状图
 *   ② 资源难度匹配曲线 — ECharts 散点图
 *   ③ 学习路径规划图 — 横向流程节点
 *
 * 可复用后端 report_builder.py 的等价 JS 逻辑，纯函数不调 API。
 */
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import * as echarts from 'echarts'
import { useAssessmentStore } from '@/stores/assessment'
import { useSidebarStore } from '@/stores/sidebar'

const store = useAssessmentStore()
const sidebar = useSidebarStore()

// ============================================================
// Chart refs
// ============================================================
const blindChartRef = ref(null)
const matchChartRef = ref(null)
let blindChart = null
let matchChart = null

// ============================================================
// 是否已测评
// ============================================================
const hasData = computed(() => store.hasResults && store.profile)

const accuracy = computed(() => store.accuracy || 0)
const assessment = computed(() => store.assessment)
const reviewResults = computed(() => store.reviewResults)

// ============================================================
// ① 知识盲区定位 (等价 report_builder._build_blind_spots)
// ============================================================
const blindSpots = computed(() => {
  const profile = store.profile || {}
  const learningPath = store.knowledgeGraph?.learning_path || []

  const lookup = {}
  for (const n of learningPath) {
    if (n?.node_id) lookup[n.node_id] = n
  }

  const nodes = []
  const weakIds = new Set()

  for (const t of (profile.weak_topics || [])) {
    if (!t?.node_id) continue
    weakIds.add(t.node_id)
    const n = lookup[t.node_id] || {}
    nodes.push({
      node_id: t.node_id,
      name: n.name || t.node_id,
      difficulty: n.difficulty || 0,
      mastery: t.mastery || 0,
      status: masteryStatus(t.mastery || 0),
      error_patterns: t.error_patterns || [],
    })
  }

  for (const t of (profile.known_topics || [])) {
    if (!t?.node_id || weakIds.has(t.node_id)) continue
    const n = lookup[t.node_id] || {}
    nodes.push({
      node_id: t.node_id,
      name: n.name || t.node_id,
      difficulty: n.difficulty || 0,
      mastery: t.mastery || 0,
      status: masteryStatus(t.mastery || 0),
      error_patterns: [],
    })
  }

  nodes.sort((a, b) => a.mastery - b.mastery)

  const counts = { mastered: 0, learning: 0, weak: 0 }
  let sum = 0
  for (const n of nodes) {
    counts[n.status] = (counts[n.status] || 0) + 1
    sum += n.mastery
  }

  return {
    nodes,
    summary: {
      total: nodes.length,
      mastered: counts.mastered,
      learning: counts.learning,
      weak: counts.weak,
      overall_mastery: nodes.length ? +(sum / nodes.length).toFixed(3) : 0,
    },
  }
})

// ============================================================
// ② 资源难度匹配 (等价 report_builder._build_difficulty_match)
// ============================================================
const diffMatch = computed(() => {
  const profile = store.profile || {}
  const learningPath = store.knowledgeGraph?.learning_path || []
  const resources = store.generatedContent?.resources || []

  const lookup = {}
  for (const n of learningPath) {
    if (n?.node_id) lookup[n.node_id] = n
  }

  const masteryByNode = {}
  for (const section of ['known_topics', 'weak_topics']) {
    for (const t of (profile[section] || [])) {
      if (t?.node_id) masteryByNode[t.node_id] = t.mastery || 0
    }
  }

  const points = []
  for (const res of resources) {
    if (!res) continue
    const nid = res.target_node_id || ''
    const node = lookup[nid] || {}
    const nodeDiff = node.difficulty || 0
    const resDiff = res.difficulty_level || 0
    const gap = (resDiff || 0) - (nodeDiff || 0)

    let matchStatus = 'matched'
    if (gap > 1) matchStatus = 'too_hard'
    else if (gap < -1) matchStatus = 'too_easy'

    points.push({
      node_id: nid,
      name: node.name || nid,
      content_type: res.content_type || '',
      node_difficulty: nodeDiff,
      resource_difficulty: resDiff,
      mastery: masteryByNode[nid] || 0,
      gap,
      match_status: matchStatus,
    })
  }

  const statusCounts = { matched: 0, too_hard: 0, too_easy: 0 }
  let gapSum = 0
  for (const p of points) {
    statusCounts[p.match_status]++
    gapSum += p.gap
  }

  return {
    points,
    summary: {
      total_resources: points.length,
      matched: statusCounts.matched,
      too_hard: statusCounts.too_hard,
      too_easy: statusCounts.too_easy,
      avg_gap: points.length ? +(gapSum / points.length).toFixed(2) : 0,
    },
  }
})

// ============================================================
// ③ 学习路径 (等价 report_builder._build_learning_path_graph)
// ============================================================
const pathData = computed(() => {
  const kg = store.knowledgeGraph || {}
  const profile = store.profile || {}
  const learningPath = kg.learning_path || []
  const statusUpdates = kg.node_status_updates || {}
  const recPath = profile.recommended_path || {}

  const masteryByNode = {}
  for (const section of ['known_topics', 'weak_topics']) {
    for (const t of (profile[section] || [])) {
      if (t?.node_id) masteryByNode[t.node_id] = t.mastery || 0
    }
  }

  const nodes = learningPath
    .filter((n) => n?.node_id)
    .map((n, i) => {
      let status
      if (statusUpdates[n.node_id]) {
        status = statusUpdates[n.node_id]
      } else if (n.node_id in masteryByNode) {
        status = masteryStatus(masteryByNode[n.node_id])
      } else {
        status = 'unlearned'
      }
      return {
        node_id: n.node_id,
        name: n.name || n.node_id,
        difficulty: n.difficulty || 0,
        estimated_minutes: n.estimated_minutes || 0,
        mastery: masteryByNode[n.node_id] || 0,
        status,
        is_current: n.node_id === (recPath.current_node || ''),
        position: i,
      }
    })

  return {
    nodes,
    estimated_total_hours: kg.estimated_total_hours || 0,
    path_length: nodes.length,
    current_node: recPath.current_node || '',
    next_nodes: recPath.next_nodes || [],
    estimated_completion_weeks: recPath.estimated_completion_weeks || 0,
  }
})

// ============================================================
// 质量指标 (S8: 优先用后端真实 learning_report.quality_metrics, fallback 客户端派生)
// 赛题 M5: 幻觉率<5% / 适配率≥85% / 覆盖率≥90%
// ============================================================
const qualityMetrics = computed(() => {
  // 1. 优先用后端真实指标 (compute_quality_metrics 产出, 含真实幻觉率/适配率/覆盖率)
  const real = store.learningReport?.quality_metrics
  if (real && (real.hallucination || real.adaptation || real.coverage)) {
    const h = real.hallucination?.rate ?? 0
    const a = real.adaptation?.rate ?? 0
    const c = real.coverage?.rate ?? 0
    return {
      hallucination_rate: h,
      adaptation_rate: a,
      coverage_rate: c,
      all_passed: real.all_passed ?? (h < 0.05 && a >= 0.85 && c >= 0.9),
      source: 'backend',
      detail: real,
    }
  }

  // 2. fallback: 从 store 派生 (后端未返回 learning_report 时, 仅作占位)
  const review = store.reviewResults
  const gen = store.generatedContent
  const profile = store.profile
  if (!review || !gen || !profile) return null

  const coveredNodeIds = new Set()
  for (const r of (gen.resources || [])) {
    if (r?.target_node_id) coveredNodeIds.add(r.target_node_id)
  }
  const allNodeIds = new Set()
  for (const section of ['known_topics', 'weak_topics']) {
    for (const t of (profile[section] || [])) {
      if (t?.node_id) allNodeIds.add(t.node_id)
    }
  }
  const totalNodes = allNodeIds.size || 1
  const coverageRate = +(coveredNodeIds.size / totalNodes).toFixed(3)
  const dm = diffMatch.value
  const adaptationRate = dm.summary.total_resources
    ? +(dm.summary.matched / dm.summary.total_resources).toFixed(3)
    : 0
  const hallucinationRate = 1 - (review.dimensions?.factual_accuracy?.score ?? 1)
  return {
    hallucination_rate: hallucinationRate,
    adaptation_rate: adaptationRate,
    coverage_rate: coverageRate,
    all_passed: hallucinationRate < 0.05 && adaptationRate >= 0.85 && coverageRate >= 0.9,
    source: 'derived',
  }
})

// ============================================================
// Helpers
// ============================================================
function masteryStatus(m) {
  if (m >= 0.8) return 'mastered'
  if (m >= 0.5) return 'learning'
  return 'weak'
}

function statusLabel(s) {
  return { mastered: '已掌握', learning: '学习中', weak: '薄弱', unlearned: '未学习' }[s] || s
}

function masteryColor(m) {
  if (m >= 0.8) return '#67c23a'
  if (m >= 0.5) return '#e6a23c'
  return '#f56c6c'
}

// ============================================================
// ECharts: ① 盲区柱状图
// ============================================================
function renderBlindChart() {
  if (!blindChartRef.value) return
  if (!blindChart) {
    blindChart = echarts.init(blindChartRef.value)
  }

  const data = blindSpots.value.nodes
  if (!data.length) {
    blindChart.clear()
    return
  }

  // 取前 15 个 (最多展示)
  const sliced = data.slice(0, 15)
  const names = sliced.map((n) => n.name)
  const values = sliced.map((n) => +(n.mastery * 100).toFixed(0))
  const colors = sliced.map((n) => masteryColor(n.mastery))

  blindChart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: (p) => {
        const d = p[0]
        const item = sliced[d.dataIndex]
        return `<b>${item.name}</b><br/>掌握度: ${d.value}%<br/>难度: Lv${item.difficulty}<br/>状态: ${statusLabel(item.status)}`
      },
    },
    grid: { left: 8, right: 20, top: 8, bottom: 0, containLabel: true },
    xAxis: { max: 100, axisLabel: { fontSize: 11 }, splitLine: { lineStyle: { color: '#f0f0f0' } } },
    yAxis: {
      type: 'category',
      data: names.reverse(),
      axisLabel: { fontSize: 11, width: 80, overflow: 'truncate' },
      inverse: true,
    },
    series: [{
      type: 'bar',
      data: values.reverse().map((v, i) => ({
        value: v,
        itemStyle: { color: colors.reverse()[i], borderRadius: [0, 4, 4, 0] },
      })),
      barMaxWidth: 18,
      label: { show: true, position: 'right', fontSize: 11, formatter: '{c}%' },
    }],
  }, true)
}

// ============================================================
// ECharts: ② 难度匹配散点图
// ============================================================
function renderMatchChart() {
  if (!matchChartRef.value) return
  if (!matchChart) {
    matchChart = echarts.init(matchChartRef.value)
  }

  const points = diffMatch.value.points
  if (!points.length) {
    matchChart.clear()
    return
  }

  const mapped = points.map((p) => [p.node_difficulty, p.resource_difficulty, p.name, p.match_status, p.mastery])
  const matched = mapped.filter((p) => p[3] === 'matched')
  const tooHard = mapped.filter((p) => p[3] === 'too_hard')
  const tooEasy = mapped.filter((p) => p[3] === 'too_easy')

  const seriesDef = [
    { name: '匹配', data: matched, color: '#67c23a' },
    { name: '偏难', data: tooHard, color: '#f56c6c' },
    { name: '偏易', data: tooEasy, color: '#e6a23c' },
  ].filter((s) => s.data.length > 0)

  matchChart.setOption({
    tooltip: {
      formatter: (p) => {
        const d = p.data
        return `<b>${d[2]}</b><br/>节点难度: Lv${d[0]}<br/>资源难度: Lv${d[1]}<br/>状态: ${d[3]}<br/>掌握度: ${((d[4] || 0) * 100).toFixed(0)}%`
      },
    },
    grid: { left: 8, right: 20, top: 8, bottom: 0, containLabel: true },
    xAxis: { name: '节点难度', min: 0, max: 6, axisLabel: { fontSize: 11 }, splitLine: { lineStyle: { color: '#f0f0f0' } } },
    yAxis: { name: '资源难度', min: 0, max: 6, axisLabel: { fontSize: 11 } },
    series: seriesDef.map((s) => ({
      name: s.name,
      type: 'scatter',
      data: s.data,
      symbolSize: (val) => 8 + (val[4] || 0) * 10,
      itemStyle: { color: s.color, opacity: 0.8 },
    })),
  }, true)
}

// ============================================================
// 响应式渲染 + 窗口 resize
// ============================================================
watch(hasData, async (ok) => {
  if (!ok) return
  await nextTick()
  renderBlindChart()
  renderMatchChart()
})

onMounted(() => {
  if (hasData.value) {
    nextTick(() => {
      renderBlindChart()
      renderMatchChart()
    })
  }
  window.addEventListener('resize', () => {
    blindChart?.resize()
    matchChart?.resize()
  })
})
</script>

<style scoped>
.dashboard-page { padding: 0; }

/* ---- 页面标题 ---- */
.page-header { margin-bottom: 16px; }
.page-header h3 { margin: 0 0 4px; font-size: 20px; }
.page-desc { margin: 0; color: #909399; font-size: 13px; }

/* ---- 概览卡片 ---- */
.overview-row {
  display: flex; gap: 12px; margin-bottom: 16px;
  flex-wrap: wrap;
}
.stat-card {
  flex: 1; min-width: 120px;
  background: #f5f7fa; border-radius: 8px;
  padding: 14px 16px; text-align: center;
}
.stat-value {
  font-size: 28px; font-weight: 700; color: #303133;
  line-height: 1.2;
}
.stat-value.ok { color: #67c23a; }
.stat-value.warn { color: #e6a23c; }
.stat-label { font-size: 12px; color: #909399; margin-top: 4px; }
.stat-sub { font-size: 11px; color: #c0c4cc; margin-top: 2px; }

/* ---- 图表行 ---- */
.charts-row {
  display: flex; gap: 16px; margin-bottom: 16px;
}
.chart-card { flex: 1; min-width: 0; }
.chart-card :deep(.el-card__header) {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 16px; font-weight: 600; font-size: 14px;
}
.chart-card :deep(.el-card__header) .el-tag { margin-left: auto; }
.chart-box { height: 260px; }

/* ---- 学习路径 ---- */
.path-card { margin-bottom: 16px; }
.path-card :deep(.el-card__header) {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 16px; font-weight: 600; font-size: 14px;
}
.path-meta { margin-left: auto; font-size: 12px; color: #909399; font-weight: 400; }

.path-graph { overflow-x: auto; padding: 8px 0; }
.path-flow { display: flex; align-items: flex-start; gap: 0; min-width: max-content; }

.path-node {
  flex-shrink: 0; width: 120px; padding: 10px 8px;
  border-radius: 8px; border: 2px solid #e4e7ed;
  background: #fff; text-align: center;
  transition: all 0.2s;
}
.path-node.status-mastered { border-color: #67c23a; background: #f0f9eb; }
.path-node.status-learning  { border-color: #e6a23c; background: #fdf6ec; }
.path-node.status-weak      { border-color: #f56c6c; background: #fef0f0; }
.path-node.status-unlearned { border-color: #e4e7ed; background: #fafafa; }
.path-node.current { box-shadow: 0 0 0 3px rgba(64,158,255,0.3); }

.pn-index {
  width: 24px; height: 24px; border-radius: 50%;
  background: #409eff; color: #fff; font-size: 12px;
  display: inline-flex; align-items: center; justify-content: center;
  margin-bottom: 4px; font-weight: 600;
}
.pn-name {
  font-size: 13px; font-weight: 600; color: #303133;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  margin-bottom: 4px;
}
.pn-meta { font-size: 11px; color: #909399; margin-bottom: 6px; }
.pn-mastery { padding: 0 4px; }

.path-arrow {
  flex-shrink: 0; display: flex; align-items: center;
  padding: 0 6px; font-size: 18px; color: #c0c4cc;
  padding-top: 16px;
}

/* ---- 质量指标 ---- */
.quality-card { margin-bottom: 16px; }
.quality-card :deep(.el-card__header) {
  padding: 10px 16px; font-weight: 600; font-size: 14px;
}
.quality-row { display: flex; gap: 24px; justify-content: center; padding: 8px 0; }
.quality-item { text-align: center; }
.q-value { font-size: 24px; font-weight: 700; }
.q-value.ok { color: #67c23a; }
.q-value.fail { color: #f56c6c; }
.q-label { font-size: 13px; color: #303133; margin-top: 4px; }
.q-target { font-size: 11px; color: #909399; }
</style>
