<template>
  <section class="stage-card stage-goal km-surface">
    <header class="stage-head">
      <span class="stage-no">01</span>
      <h4>目标设定</h4>
    </header>
    <div class="stage-body">
      <!-- #30: 学习目标方向压成一行 — 顶部胶囊标签 (点击即选) + 内联自定义输入, 不换行可横向滚动 -->
      <div class="direction-row">
        <el-tag
          v-for="d in presetDirections"
          :key="d"
          :effect="form.targetDirection === d ? 'dark' : 'plain'"
          :type="form.targetDirection === d ? 'primary' : 'info'"
          class="preset-tag"
          @click="form.targetDirection = d"
        >{{ d }}</el-tag>
        <el-input
          v-model="form.targetDirection"
          placeholder="自定义方向…"
          :maxlength="120"
          class="direction-input"
        />
      </div>
      <!-- #30 反馈: 学习会话是"无项目技能训练"场景一专属, 不暴露"有项目二次开发"选项 (场景二走项目图谱视图) -->
      <div class="control-row actions">
        <el-button type="primary" size="large" :disabled="!canStart" :loading="store.loading" @click="handleStart">
          开始测评 →
        </el-button>
        <span v-if="!canStart" class="hint-text">请选择或输入学习目标方向</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { reactive, computed } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'

const store = useAssessmentStore()

const form = reactive({ targetDirection: '' })
const presetDirections = [
  'Python 基础语法入门', '数据结构与算法', '面向对象编程',
  'Python 进阶', '常用库与工具', '项目实战',
  '机器学习入门', '数据分析与可视化', 'Web 后端开发',
  '数据库与缓存', '工程化实践',
]
const canStart = computed(() => form.targetDirection.trim().length > 0)

async function handleStart() {
  if (!canStart.value) return
  // 学习会话固定场景一 (无项目技能训练), scene 默认 no_project
  await store.startAssessment({ targetDirection: form.targetDirection.trim(), scene: 'no_project' })
}
</script>

<style scoped>
.stage-card { border-left: 3px solid var(--km-border-light); border-radius: var(--km-radius); overflow: hidden; }
.stage-head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--km-border-light); }
.stage-no { font-family: var(--km-font-mono); font-size: 12px; color: var(--km-gray-500); }
.stage-head h4 { margin: 0; font-size: 14px; color: var(--km-gray-800); }
.stage-body { padding: 16px; }

/* #30: 单行方向 — 胶囊 + 输入同行, 溢出横向滚动 (隐藏滚动条) */
.direction-row { display: flex; align-items: center; gap: 8px; overflow-x: auto; padding-bottom: 2px; margin-bottom: 4px; }
.direction-row::-webkit-scrollbar { display: none; }
.preset-tag { cursor: pointer; font-size: 13px; user-select: none; flex-shrink: 0; margin: 0 !important; }
.preset-tag:hover { opacity: 0.85; }
.direction-input { flex: 1; min-width: 200px; }
.control-row { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
.field-label { font-size: 13px; font-weight: 600; color: var(--km-gray-700); flex-shrink: 0; }
.actions { margin-top: 16px; }
.hint-text { color: var(--km-gray-500); font-size: 13px; }
</style>
