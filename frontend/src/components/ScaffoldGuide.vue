<template>
  <div class="scaffold-guide">
    <div v-if="!content" class="guide-empty">暂无实操指南内容</div>

    <!-- 拆分失败降级：整体渲染 -->
    <MarkdownViewer v-else-if="levels.length < 2" :content="content" />

    <!-- 5 级折叠展开 -->
    <template v-else>
      <div class="guide-tip">
        <el-icon><InfoFilled /></el-icon>
        <span>阶梯式引导：建议按顺序逐级尝试，先独立思考再查看下一级提示</span>
      </div>
      <el-collapse v-model="activeNames" class="scaffold-collapse">
        <el-collapse-item
          v-for="(lvl, i) in levels"
          :key="i"
          :name="i"
        >
          <template #title>
            <span class="level-title">
              <span class="level-badge" :class="levelClass(i)">{{ i + 1 }}</span>
              {{ levelTitle(i) }}
            </span>
          </template>
          <MarkdownViewer :content="lvl" />
        </el-collapse-item>
      </el-collapse>
    </template>
  </div>
</template>

<script setup>
/**
 * 阶梯式引导组件（阶段13 T1，借鉴源仓 KMatch）
 *
 * 数据源: practice_guide 资源的 content（markdown 字符串）。
 * content_generator prompt 约定 5 级渐进提示；拆分逻辑见 utils/scaffold.js。
 * 默认仅展开第 1 级（对齐 prompt "首次仅呈现第1级"）。
 */
import { ref, computed } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import MarkdownViewer from './MarkdownViewer.vue'
import { splitScaffoldLevels, SCAFFOLD_LEVEL_TITLES } from '@/utils/scaffold'

const props = defineProps({
  content: { type: String, default: '' },
})

const levels = computed(() => splitScaffoldLevels(props.content))

// 默认仅展开第 1 级
const activeNames = ref([0])

function levelTitle(i) {
  return `第 ${i + 1} 级 · ${SCAFFOLD_LEVEL_TITLES[i] || '进阶提示'}`
}
function levelClass(i) {
  return `lvl-${i + 1}`
}
</script>

<style scoped>
.scaffold-guide {
  width: 100%;
}

.guide-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  margin-bottom: 12px;
  background: var(--km-warning-light);
  border-radius: var(--km-radius);
  font-size: 13px;
  color: var(--km-gray-600);
}

.guide-tip :deep(.el-icon) {
  color: var(--km-warning);
  flex-shrink: 0;
}

.scaffold-collapse {
  border-radius: var(--km-radius);
  border: 1px solid var(--km-border-light);
}

.level-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--km-gray-800);
}

.level-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
}

/* 5 级语义递进色阶（绿→蓝→紫→橙→红），非 token：表达难度攀升，亮暗主题通用 */
.level-badge.lvl-1 { background: var(--km-success); }
.level-badge.lvl-2 { background: var(--km-primary); }
.level-badge.lvl-3 { background: #8B5CF6; }
.level-badge.lvl-4 { background: var(--km-warning); }
.level-badge.lvl-5 { background: var(--km-danger); }

.guide-empty {
  padding: 32px;
  text-align: center;
  color: var(--km-gray-400);
  font-size: 14px;
}
</style>
