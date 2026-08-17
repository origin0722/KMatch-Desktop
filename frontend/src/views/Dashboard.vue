<template>
  <div class="dashboard-page km-workbench">
    <!-- ============================================================ -->
    <!-- 页面标题 (km-workbench-header 紧凑一行条, C4: 标题 15px + desc 内联) -->
    <!-- ============================================================ -->
    <div class="km-workbench-header">
      <div class="km-workbench-head-left">
        <h3 class="km-workbench-title">数据看板</h3>
        <p class="km-workbench-desc">
          个人学情与资源匹配度报告：知识盲区定位、难度匹配曲线、学习路径规划
        </p>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- 空状态 -->
    <!-- ============================================================ -->
    <el-empty
      v-if="!hasData"
      description="尚未完成学情测评，无报告数据"
      :image-size="120"
    >
      <el-button type="primary" @click="sidebar.setView('learning-session')">
        前往学习会话
      </el-button>
    </el-empty>

    <!-- ============================================================ -->
    <!-- 有数据时 -->
    <!-- ============================================================ -->
    <template v-else>
      <!-- 大数字卡行 (C3: 36px 数字 + 迷你环形/sparkline + 语义色) -->
      <div class="overview-row">
        <!-- 综合掌握度 -->
        <div class="stat-card km-surface">
          <div class="stat-head">
            <div class="stat-value" :class="toneClass(mastery)">{{ (mastery * 100).toFixed(0) }}%</div>
            <svg class="stat-ring" viewBox="0 0 44 44" width="44" height="44" aria-hidden="true">
              <circle class="ring-bg" cx="22" cy="22" :r="ringR" />
              <circle class="ring-fg" :class="toneClass(mastery)" cx="22" cy="22" :r="ringR"
                      :stroke-dasharray="ring.circumference" :stroke-dashoffset="ring.offset(mastery)" />
            </svg>
          </div>
          <div class="stat-label">综合掌握度</div>
          <div class="stat-sub">{{ blindSpots.summary.total }} 个节点 · 薄弱 {{ blindSpots.summary.weak }}</div>
        </div>

        <!-- 答题正确率 -->
        <div class="stat-card km-surface">
          <div class="stat-head">
            <div class="stat-value" :class="toneClass(accuracy)">{{ (accuracy * 100).toFixed(0) }}%</div>
            <svg class="stat-ring" viewBox="0 0 44 44" width="44" height="44" aria-hidden="true">
              <circle class="ring-bg" cx="22" cy="22" :r="ringR" />
              <circle class="ring-fg" :class="toneClass(accuracy)" cx="22" cy="22" :r="ringR"
                      :stroke-dasharray="ring.circumference" :stroke-dashoffset="ring.offset(accuracy)" />
            </svg>
          </div>
          <div class="stat-label">答题正确率</div>
          <div class="stat-sub">{{ assessment?.total_count || 0 }} 题</div>
        </div>

        <!-- 难度适配率 (sparkline = 逐资源难度偏差走势) -->
        <div class="stat-card km-surface">
          <div class="stat-head">
            <div class="stat-value" :class="toneClass(adaptationRate)">{{ (adaptationRate * 100).toFixed(0) }}%</div>
            <svg class="stat-spark" :viewBox="spark.viewBox" width="64" height="32" aria-hidden="true">
              <polyline class="spark-line" :class="spark.tone" :points="spark.points" />
            </svg>
          </div>
          <div class="stat-label">难度适配率</div>
          <div class="stat-sub">{{ diffMatch.summary.matched }}/{{ diffMatch.summary.total_resources }} 匹配</div>
        </div>

        <!-- 内容审核 (有报告才展示) -->
        <div v-if="reviewResults" class="stat-card km-surface">
          <div class="stat-head">
            <div class="stat-value" :class="reviewResults.passed ? 'ok' : 'warn'">{{ reviewScore }}%</div>
            <svg class="stat-ring" viewBox="0 0 44 44" width="44" height="44" aria-hidden="true">
              <circle class="ring-bg" cx="22" cy="22" :r="ringR" />
              <circle class="ring-fg" :class="reviewResults.passed ? 'ok' : 'warn'" cx="22" cy="22" :r="ringR"
                      :stroke-dasharray="ring.circumference" :stroke-dashoffset="ring.offset(reviewScoreNorm)" />
            </svg>
          </div>
          <div class="stat-label">内容审核 · {{ reviewResults.passed ? '通过' : '打回' }}</div>
          <div class="stat-sub">质量得分 {{ reviewScore }}%</div>
        </div>
      </div>

      <!-- 3 列栅格: 综合雷达 | 知识盲区 | 难度匹配 (C3, 小屏降级单列) -->
      <div class="dash-grid">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <span>综合能力雷达</span>
            <el-tag size="small" type="info">{{ radarActiveDims }}/5 维度达标</el-tag>
          </template>
          <div ref="radarChartRef" class="chart-box"></div>
        </el-card>

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

      <!-- 第三行: 学习路径规划图 -->
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
                :title="`${node.name} (Lv${node.difficulty}) - ${statusLabel(node.status)}`"
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

      <!-- 内容审核四维度报告 -->
      <el-card class="review-card" shadow="never" v-if="reviewResults">
        <template #header><span>④ 内容审核报告</span></template>
        <ReviewReport :review-results="reviewResults" />
      </el-card>

      <!-- 质量指标 -->
      <el-card class="quality-card" shadow="never" v-if="qualityMetrics">
        <template #header>
          <span>赛题 M5 质量检测指标</span>
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
            <div class="q-value km-mono-number" :class="qualityMetrics.hallucination_rate < 0.05 ? 'ok' : 'fail'">
              {{ (qualityMetrics.hallucination_rate * 100).toFixed(1) }}%
            </div>
            <div class="q-label">幻觉率</div>
            <div class="q-target">目标 &lt;5%</div>
          </div>
          <div class="quality-item">
            <div class="q-value km-mono-number" :class="qualityMetrics.adaptation_rate >= 0.85 ? 'ok' : 'fail'">
              {{ (qualityMetrics.adaptation_rate * 100).toFixed(1) }}%
            </div>
            <div class="q-label">适配率</div>
            <div class="q-target">目标 ≥85%</div>
          </div>
          <div class="quality-item">
            <div class="q-value km-mono-number" :class="qualityMetrics.coverage_rate >= 0.9 ? 'ok' : 'fail'">
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
 * 从 assessment store 取原始数据，客户端派生四类可视化:
 *   ① 综合能力雷达 — ECharts 雷达图 (5 维: 掌握度/正确率/覆盖度/难度适配/活跃度)
 *   ② 知识盲区定位 — ECharts 横向柱状图 (带均值线 markLine, C3)
 *   ③ 资源难度匹配曲线 — ECharts 散点图
 *   ④ 学习路径规划图 — 横向流程节点
 *
 * 可复用后端 report_builder.py 的等价 JS 逻辑，纯函数不调 API。
 *
 * 配色: THEME 常量镜像 --km-* token (ECharts canvas 不能读 CSS 变量, 故用 hex)。
 * C3: 顶部 4 stat 卡改为大数字卡 (36px 数字 + 迷你环形/sparkline + 语义色)。
 */
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
// C3: 全量 echarts → 按需 import (仿 ProfileRadar.vue:15-18, 减小 chunk)
import * as echarts from 'echarts/core'
import { BarChart, ScatterChart, RadarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useAssessmentStore } from '@/stores/assessment'
import { useSidebarStore } from '@/stores/sidebar'
import ReviewReport from '@/components/ReviewReport.vue'

echarts.use([BarChart, ScatterChart, RadarChart, GridComponent, TooltipComponent, CanvasRenderer])

const store = useAssessmentStore()
const sidebar = useSidebarStore()

// ============================================================
// 主题色常量 (镜像 styles/theme.css 的 --km-* token, 供 ECharts canvas 使用)
// ============================================================
const THEME = {
  primary: '#6c7ce0',
  success: '#34b37e',
  warning: '#f0a040',
  danger: '#e05555',
  info: '#5b9bd5',
  splitLine: '#f0efed',
  gray300: '#e4e3e1',
  gray500: '#9a9895',
}

// ============================================================
// Chart refs
// ============================================================
const radarChartRef = ref(null)
const blindChartRef = ref(null)
const matchChartRef = ref(null)
let radarChart = null
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
// 大数字卡派生 (C3)
// ============================================================
const mastery = computed(() => blindSpots.value.summary.overall_mastery || 0)

// 难度适配率: 优先后端 quality_metrics.adaptation.rate, fallback diffMatch 客户端派生
const adaptationRate = computed(() => {
  const q = qualityMetrics.value
  if (q) return q.adaptation_rate
  const dm = diffMatch.value.summary
  return dm.total_resources ? +(dm.matched / dm.total_resources).toFixed(3) : 0
})

// 内容审核得分 (0-100 展示 / 0-1 环形)
const reviewScore = computed(() => Math.round((reviewResults.value?.overall_score || 0) * 100))
const reviewScoreNorm = computed(() => reviewResults.value?.overall_score || 0)

// 迷你环形 (SVG stroke-dasharray 环形进度, 免额外 ECharts 实例)
const ringR = 18
const ringC = 2 * Math.PI * ringR
const ring = {
  circumference: ringC,
  offset: (ratio) => ringC * (1 - Math.max(0, Math.min(1, ratio || 0))),
}

/** 语义色: ≥0.8 ok (绿) / ≥0.5 warn (黄) / <0.5 fail (红) */
function toneClass(ratio) {
  if (ratio >= 0.8) return 'ok'
  if (ratio >= 0.5) return 'warn'
  return 'fail'
}

// 难度偏差 sparkline (最近 ≤24 条资源偏差走势)
const gapSeries = computed(() => diffMatch.value.points.map((p) => p.gap).slice(-24))
const spark = computed(() => {
  const v = gapSeries.value
  if (!v.length) return { viewBox: '0 0 64 32', points: '', tone: '' }
  const W = 64
  const H = 32
  const PAD = 3
  const min = Math.min(0, ...v)
  const max = Math.max(0, ...v)
  const span = max - min || 1
  const step = W / (v.length - 1 || 1)
  const pts = v.map((val, i) => {
    const x = i * step
    const y = H - PAD - ((val - min) / span) * (H - 2 * PAD)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  const avg = v.reduce((a, b) => a + b, 0) / v.length
  return {
    viewBox: `0 0 ${W} ${H}`,
    points: pts.join(' '),
    tone: Math.abs(avg) > 0.5 ? 'tone-warn' : 'tone-ok',
  }
})

// ============================================================
// ① 综合能力雷达 5 维 (C3, 全部归一化 0-1)
// ============================================================
const activityLevel = computed(() => {
  // 活跃度: 学习足迹条数为主 (20+ 条 = 满活跃), 无足迹时回退答题量 + 资源数 (30+ = 满)
  const profile = store.profile || {}
  const history = profile.learning_history
  if (Array.isArray(history) && history.length) {
    return Math.min(1, history.length / 20)
  }
  const answers = store.assessment?.total_count || 0
  const resources = store.generatedContent?.resources?.length || 0
  return Math.min(1, (answers + resources) / 30)
})

const radarDims = computed(() => {
  const q = qualityMetrics.value
  const coverage = q ? q.coverage_rate : 0
  const adaptation = q ? q.adaptation_rate : adaptationRate.value
  const clamp = (x) => Math.max(0, Math.min(1, x || 0))
  return {
    mastery: clamp(mastery.value),
    accuracy: clamp(store.accuracy),
    coverage: clamp(coverage),
    adaptation: clamp(adaptation),
    activity: clamp(activityLevel.value),
  }
})

const radarActiveDims = computed(() => {
  const d = radarDims.value
  return [d.mastery, d.accuracy, d.coverage, d.adaptation, d.activity].filter((x) => x >= 0.8).length
})

const RADAR_INDICATORS = [
  { name: '掌握度', max: 100 },
  { name: '正确率', max: 100 },
  { name: '覆盖度', max: 100 },
  { name: '难度适配', max: 100 },
  { name: '活跃度', max: 100 },
]

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
  if (m >= 0.8) return THEME.success
  if (m >= 0.5) return THEME.warning
  return THEME.danger
}

// ============================================================
// ECharts: 综合能力雷达 (C3)
// ============================================================
function renderRadarChart() {
  if (!radarChartRef.value) return
  if (!radarChart) {
    radarChart = echarts.init(radarChartRef.value)
  }

  const d = radarDims.value
  radarChart.setOption({
    tooltip: {
      formatter: (p) => {
        const v = p.value || []
        const rows = RADAR_INDICATORS.map((ind, i) => `${ind.name}: ${v[i] ?? 0}%`).join('<br/>')
        return `<b>能力画像</b><br/>${rows}`
      },
    },
    radar: {
      center: ['50%', '52%'],
      radius: '62%',
      indicator: RADAR_INDICATORS,
      axisName: { fontSize: 11, color: THEME.gray500 },
      splitLine: { lineStyle: { color: THEME.splitLine } },
      splitArea: { areaStyle: { color: ['rgba(108,124,224,0.04)', 'rgba(108,124,224,0.08)'] } },
    },
    series: [{
      type: 'radar',
      symbol: 'circle',
      symbolSize: 4,
      data: [{
        name: '能力画像',
        value: [d.mastery, d.accuracy, d.coverage, d.adaptation, d.activity]
          .map((x) => Math.round(x * 100)),
      }],
      lineStyle: { color: THEME.primary, width: 2 },
      areaStyle: { color: 'rgba(108,124,224,0.2)' },
      itemStyle: { color: THEME.primary },
    }],
  }, true)
}

// ============================================================
// ECharts: ① 盲区柱状图 (+ 均值线 markLine, C3)
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
    xAxis: {
      max: 100,
      axisLabel: { fontSize: 11, color: THEME.gray500 },
      splitLine: { lineStyle: { color: THEME.splitLine } },
    },
    yAxis: {
      type: 'category',
      data: names.reverse(),
      axisLabel: { fontSize: 11, width: 80, overflow: 'truncate', color: THEME.gray500 },
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
      // C3: 均值线标注 (整体掌握度均值)
      markLine: {
        silent: true,
        symbol: 'none',
        lineStyle: { color: THEME.warning, type: 'dashed', width: 1 },
        label: {
          formatter: `均值 ${(blindSpots.value.summary.overall_mastery * 100).toFixed(0)}%`,
          position: 'insideEndTop',
          fontSize: 10,
          color: THEME.warning,
        },
        data: [{ xAxis: +(blindSpots.value.summary.overall_mastery * 100).toFixed(1) }],
      },
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
    { name: '匹配', data: matched, color: THEME.success },
    { name: '偏难', data: tooHard, color: THEME.danger },
    { name: '偏易', data: tooEasy, color: THEME.warning },
  ].filter((s) => s.data.length > 0)

  matchChart.setOption({
    tooltip: {
      formatter: (p) => {
        const d = p.data
        return `<b>${d[2]}</b><br/>节点难度: Lv${d[0]}<br/>资源难度: Lv${d[1]}<br/>状态: ${d[3]}<br/>掌握度: ${((d[4] || 0) * 100).toFixed(0)}%`
      },
    },
    grid: { left: 8, right: 20, top: 8, bottom: 0, containLabel: true },
    xAxis: { name: '节点难度', min: 0, max: 6, axisLabel: { fontSize: 11, color: THEME.gray500 }, splitLine: { lineStyle: { color: THEME.splitLine } } },
    yAxis: { name: '资源难度', min: 0, max: 6, axisLabel: { fontSize: 11, color: THEME.gray500 } },
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
function renderAllCharts() {
  renderRadarChart()
  renderBlindChart()
  renderMatchChart()
}

function onWindowResize() {
  radarChart?.resize()
  blindChart?.resize()
  matchChart?.resize()
}

watch(hasData, async (ok) => {
  if (!ok) return
  await nextTick()
  renderAllCharts()
})

onMounted(() => {
  if (hasData.value) {
    nextTick(renderAllCharts)
  }
  window.addEventListener('resize', onWindowResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onWindowResize)
  radarChart?.dispose()
  blindChart?.dispose()
  matchChart?.dispose()
  radarChart = blindChart = matchChart = null
})
</script>

<style scoped>
.dashboard-page { padding: 0; }

/* ---- 大数字卡 (C3) ---- */
.overview-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.stat-card {
  padding: 14px 16px;
}
.stat-head {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
}
.stat-value {
  font-size: 36px; font-weight: 700;
  color: var(--km-gray-800);
  line-height: 1.1;
  letter-spacing: -0.02em;
}
.stat-value.ok { color: var(--km-success); }
.stat-value.warn { color: var(--km-warning); }
.stat-value.fail { color: var(--km-danger); }
.stat-label { font-size: 12px; color: var(--km-gray-600); margin-top: 8px; }
.stat-sub { font-size: 11px; color: var(--km-gray-400, var(--km-gray-500)); margin-top: 2px; }

/* 迷你环形 */
.stat-ring { flex-shrink: 0; transform: rotate(-90deg); }
.stat-ring .ring-bg { fill: none; stroke: var(--km-gray-300, #e4e3e1); stroke-width: 5; }
.stat-ring .ring-fg {
  fill: none; stroke-width: 5; stroke-linecap: round;
  transition: stroke-dashoffset 0.4s var(--km-ease);
}
.stat-ring .ring-fg.ok { stroke: var(--km-success); }
.stat-ring .ring-fg.warn { stroke: var(--km-warning); }
.stat-ring .ring-fg.fail { stroke: var(--km-danger); }

/* 迷你 sparkline (难度偏差走势) */
.stat-spark { flex-shrink: 0; }
.stat-spark .spark-line {
  fill: none; stroke-width: 1.8; stroke-linejoin: round; stroke-linecap: round;
}
.stat-spark .spark-line.tone-ok { stroke: var(--km-success); }
.stat-spark .spark-line.tone-warn { stroke: var(--km-warning); }

/* ---- 3 列图表栅格 (C3, 小屏降级单列) ---- */
.dash-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
@media (max-width: 1100px) {
  .dash-grid { grid-template-columns: 1fr; }
}
.chart-card { min-width: 0; }
.chart-card :deep(.el-card) {
  --el-card-bg-color: var(--km-bg-layer-2);
  --el-card-border-color: var(--km-border-light);
}
.chart-card :deep(.el-card__header) {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 16px; font-weight: 600; font-size: 14px;
  color: var(--km-gray-800);
  border-bottom: 1px solid var(--km-border-light);
}
.chart-card :deep(.el-card__header) .el-tag { margin-left: auto; }
.chart-box { height: 280px; }

/* ---- 学习路径 ---- */
.path-card { margin-bottom: 16px; }
.path-card :deep(.el-card) {
  --el-card-bg-color: var(--km-bg-layer-2);
  --el-card-border-color: var(--km-border-light);
}
.path-card :deep(.el-card__header) {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 16px; font-weight: 600; font-size: 14px;
  color: var(--km-gray-800);
  border-bottom: 1px solid var(--km-border-light);
}
.path-meta {
  margin-left: auto; font-size: 12px;
  color: var(--km-gray-500); font-weight: 400;
  font-family: var(--km-font-mono);
}

.path-graph { overflow-x: auto; padding: 8px 0; }
.path-flow { display: flex; align-items: flex-start; gap: 0; min-width: max-content; }

.path-node {
  flex-shrink: 0; width: 120px; padding: 10px 8px;
  border-radius: var(--km-radius-sm); border: 2px solid var(--km-border);
  background: var(--km-bg-layer-3); text-align: center;
  transition: all 0.2s var(--km-ease);
}
.path-node.status-mastered {
  border-color: var(--km-success);
  background: var(--km-success-light);
}
.path-node.status-learning {
  border-color: var(--km-warning);
  background: var(--km-warning-light);
}
.path-node.status-weak {
  border-color: var(--km-danger);
  background: var(--km-danger-light);
}
.path-node.status-unlearned {
  border-color: var(--km-border);
  background: var(--km-bg-layer-2);
}
.path-node.current { box-shadow: 0 0 0 3px rgba(108, 124, 224, 0.3); }

.pn-index {
  width: 24px; height: 24px; border-radius: 50%;
  background: var(--km-primary); color: var(--km-primary-text);
  font-size: 12px;
  display: inline-flex; align-items: center; justify-content: center;
  margin-bottom: 4px; font-weight: 600;
}
.pn-name {
  font-size: 13px; font-weight: 600; color: var(--km-gray-800);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  margin-bottom: 4px;
}
.pn-meta {
  font-size: 11px; color: var(--km-gray-500); margin-bottom: 6px;
  font-family: var(--km-font-mono);
}
.pn-mastery { padding: 0 4px; }

.path-arrow {
  flex-shrink: 0; display: flex; align-items: center;
  padding: 0 6px; font-size: 18px; color: var(--km-gray-400, var(--km-gray-500));
  padding-top: 16px;
}

/* ---- 质量指标 ---- */
.review-card { margin-bottom: 16px; }
.review-card :deep(.el-card) {
  --el-card-bg-color: var(--km-bg-layer-2);
  --el-card-border-color: var(--km-border-light);
}
.review-card :deep(.el-card__header) {
  padding: 10px 16px; font-weight: 600; font-size: 14px;
  color: var(--km-gray-800);
  border-bottom: 1px solid var(--km-border-light);
}
.quality-card { margin-bottom: 16px; }
.quality-card :deep(.el-card) {
  --el-card-bg-color: var(--km-bg-layer-2);
  --el-card-border-color: var(--km-border-light);
}
.quality-card :deep(.el-card__header) {
  padding: 10px 16px; font-weight: 600; font-size: 14px;
  color: var(--km-gray-800);
  border-bottom: 1px solid var(--km-border-light);
}
.quality-row { display: flex; gap: 24px; justify-content: center; padding: 8px 0; }
.quality-item { text-align: center; }
.q-value { font-size: 24px; font-weight: 700; }
.q-value.ok { color: var(--km-success); }
.q-value.fail { color: var(--km-danger); }
.q-label { font-size: 13px; color: var(--km-gray-800); margin-top: 4px; }
.q-target { font-size: 11px; color: var(--km-gray-500); }
</style>