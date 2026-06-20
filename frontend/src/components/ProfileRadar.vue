<template>
  <div class="profile-radar">
    <div ref="chartRef" class="radar-chart"></div>
  </div>
</template>

<script setup>
/**
 * 用户画像雷达图
 *
 * 展示画像 v3 核心五维: 理论水平 / 实操能力 / 学习节奏 / 投入时间 / 整体掌握度
 * 数据源: useAssessmentStore.profile (对齐 data/user_profiles/profile_schema.json)
 */
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts/core'
import { RadarChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import { GridComponent, LegendComponent } from 'echarts/components'

echarts.use([RadarChart, CanvasRenderer, GridComponent, LegendComponent])

const props = defineProps({
  /** 画像 v3 对象（useAssessmentStore.profile） */
  profile: {
    type: Object,
    required: true,
  },
})

const chartRef = ref(null)
let chart = null

// --- 常量 ---
const DIMENSIONS = [
  { key: 'theory', name: '理论水平', max: 5 },
  { key: 'practical', name: '实操能力', max: 5 },
  { key: 'pace', name: '学习节奏', max: 5 },
  { key: 'time', name: '投入时间', max: 5 },
  { key: 'mastery', name: '整体掌握度', max: 5 },
]

// --- 工具 ---
function paceToValue(pace) {
  const map = { slow: 2, normal: 3, fast: 5 }
  return map[pace] ?? 3
}

function timeToValue(hours, maxHours = 20) {
  return Math.min(5, Math.round(((hours ?? 6) / maxHours) * 5))
}

function calcMastery(profile) {
  const known = profile?.known_topics?.length ?? 0
  const weak = profile?.weak_topics?.length ?? 0
  const total = known + weak
  if (total === 0) return 1
  return Math.round((known / total) * 5)
}

function buildChartData(profile) {
  return [
    {
      name: '当前画像',
      value: [
        profile.theory_level ?? 1,
        profile.practical_level ?? 1,
        paceToValue(profile.preferred_pace),
        timeToValue(profile.time_per_week),
        calcMastery(profile),
      ],
    },
  ]
}

// --- 渲染 ---
function renderChart() {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
  }

  const data = buildChartData(props.profile || {})

  chart.setOption({
    radar: {
      center: ['50%', '50%'],
      radius: '65%',
      indicator: DIMENSIONS.map((d) => ({ name: d.name, max: d.max })),
      axisName: { fontSize: 12, color: '#606266' },
      shape: 'polygon',
      splitArea: {
        areaStyle: {
          color: ['rgba(64,158,255,0.05)', 'rgba(64,158,255,0.1)'],
        },
      },
    },
    series: [
      {
        type: 'radar',
        data,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { color: '#409EFF', width: 2 },
        areaStyle: { color: 'rgba(64,158,255,0.2)' },
        itemStyle: { color: '#409EFF' },
      },
    ],
  })
}

// --- 生命周期 ---
onMounted(() => {
  renderChart()
})

onBeforeUnmount(() => {
  chart?.dispose()
})

watch(() => props.profile, () => {
  renderChart()
}, { deep: true })
</script>

<style scoped>
.profile-radar {
  width: 100%;
  display: flex;
  justify-content: center;
}

.radar-chart {
  width: 380px;
  height: 380px;
}
</style>
