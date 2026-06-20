<template>
  <div class="learn-layout">
    <!-- 侧边导航: 场景一学习子页 -->
    <el-aside width="200px" class="learn-aside">
      <el-menu
        :default-active="activeMenu"
        router
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
      >
        <el-menu-item index="/learn/assessment">
          <el-icon><Edit /></el-icon>
          <span>学情测评</span>
        </el-menu-item>
        <el-menu-item index="/learn/graph">
          <el-icon><Share /></el-icon>
          <span>知识图谱</span>
        </el-menu-item>
        <el-menu-item index="/learn/learning">
          <el-icon><Reading /></el-icon>
          <span>学习资源</span>
        </el-menu-item>
        <el-menu-item index="/learn/agents">
          <el-icon><Connection /></el-icon>
          <span>Agent 协同</span>
        </el-menu-item>
        <el-menu-item index="/learn/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <span>数据看板</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 主内容区: 嵌套子路由 -->
    <el-main class="learn-main">
      <router-view />
    </el-main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeMenu = computed(() => route.path)
</script>

<style scoped>
.learn-layout {
  display: flex;
  height: 100%;
}

.learn-aside {
  background-color: #304156;
  height: 100%;
}

.learn-main {
  background-color: #f0f2f5;
  padding: 20px;
  height: 100%;
  overflow: auto;
}
</style>
