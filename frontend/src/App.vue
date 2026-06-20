<template>
  <div id="kmatch-app">
    <el-container class="app-container">
      <!-- 顶部导航: 切换两大场景 -->
      <el-header height="56px" class="app-header">
        <div class="header-left">
          <h1 class="app-title">KMatch·知链</h1>
          <span class="app-subtitle">知识图谱驱动的多智能体协同学习平台</span>
        </div>
        <el-menu
          :default-active="activeTop"
          mode="horizontal"
          router
          class="top-menu"
          background-color="transparent"
          text-color="#bfcbd9"
          active-text-color="#ffffff"
        >
          <el-menu-item index="/workspace">
            <el-icon><Monitor /></el-icon>
            <span>工作区(二次开发)</span>
          </el-menu-item>
          <el-menu-item index="/learn">
            <el-icon><Reading /></el-icon>
            <span>学习(技能训练)</span>
          </el-menu-item>
        </el-menu>
        <div class="header-right">
          <el-tag type="info" size="small" effect="dark">v0.1.0</el-tag>
        </div>
      </el-header>

      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
// 顶栏高亮: 按 path 一级段决定
const activeTop = computed(() => '/' + (route.path.split('/')[1] || 'learn'))
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#kmatch-app {
  height: 100vh;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.app-container {
  height: 100vh;
}

.app-header {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  border-bottom: 1px solid #0f1a30;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.app-title {
  color: #ffffff;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 2px;
}

.app-subtitle {
  color: #8a9bb8;
  font-size: 12px;
}

.top-menu {
  border-bottom: none !important;
  flex: 0 1 auto;
}

.top-menu .el-menu-item {
  border-bottom: none !important;
  height: 56px;
  line-height: 56px;
}

.header-right {
  display: flex;
  align-items: center;
}

.app-main {
  background-color: #f0f2f5;
  padding: 0;
  height: calc(100vh - 56px);
  overflow: hidden;
}
</style>
