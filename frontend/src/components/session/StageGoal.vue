<template>
  <section class="stage-card stage-goal km-surface">
    <header class="stage-head">
      <span class="stage-no">01</span>
      <h4>目标设定</h4>
    </header>
    <div class="stage-body">
      <el-form :model="form" label-width="100px" label-position="left" @submit.prevent="handleStart">
        <el-form-item label="学习目标方向" required>
          <div class="preset-directions">
            <el-tag
              v-for="d in presetDirections"
              :key="d"
              :effect="form.targetDirection === d ? 'dark' : 'plain'"
              :type="form.targetDirection === d ? '' : 'info'"
              class="preset-tag"
              @click="form.targetDirection = d"
            >{{ d }}</el-tag>
          </div>
          <el-input
            v-model="form.targetDirection"
            placeholder="或自定义方向（如：Python 基础语法入门）"
            :maxlength="200"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="场景">
          <el-select v-model="form.scene" style="width: 200px;">
            <el-option label="无项目技能训练" value="no_project" />
            <el-option label="有项目二次开发" value="with_project" />
          </el-select>
          <span class="hint-text">选择学习场景类型</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" :disabled="!canStart" :loading="store.loading" @click="handleStart">
            开始测评 →
          </el-button>
          <span v-if="!canStart" class="hint-text">请选择或输入学习目标方向</span>
        </el-form-item>
      </el-form>
    </div>
  </section>
</template>

<script setup>
import { reactive, computed } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'

const store = useAssessmentStore()

const form = reactive({ targetDirection: '', scene: 'no_project' })
const presetDirections = [
  'Python 基础语法入门', '数据结构与算法', '面向对象编程',
  'Python 进阶', '常用库与工具', '项目实战',
]
const canStart = computed(() => form.targetDirection.trim().length > 0)

async function handleStart() {
  if (!canStart.value) return
  await store.startAssessment({ targetDirection: form.targetDirection.trim(), scene: form.scene })
}
</script>

<style scoped>
.stage-card { border-left: 3px solid var(--km-border-light); border-radius: var(--km-radius); overflow: hidden; }
.stage-head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--km-border-light); }
.stage-no { font-family: var(--km-font-mono); font-size: 12px; color: var(--km-gray-500); }
.stage-head h4 { margin: 0; font-size: 14px; color: var(--km-gray-800); }
.stage-body { padding: 16px; }
.preset-directions { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.preset-tag { cursor: pointer; font-size: 13px; user-select: none; }
.preset-tag:hover { opacity: 0.85; }
.hint-text { margin-left: 12px; color: var(--km-gray-500); font-size: 13px; }
</style>
