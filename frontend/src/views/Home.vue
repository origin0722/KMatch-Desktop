<template>
  <div class="home-page">
    <el-card class="welcome-card">
      <h2>欢迎使用 KMatch·知链</h2>
      <p>知识图谱驱动的多智能体协同个性化学习平台</p>
      <el-divider />
      <div class="quick-start">
        <el-steps :active="1" align-center>
          <el-step title="学情测评" description="三维能力测评" />
          <el-step title="知识图谱" description="个性化学习路径" />
          <el-step title="资源学习" description="讲义+实操+测试" />
          <el-step title="反馈迭代" description="动态调整难度" />
        </el-steps>
      </div>
      <div class="actions">
        <el-button type="primary" size="large" @click="$router.push('/assessment')">
          开始测评 →
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
// 首页 - 后续扩展功能引导卡片
</script>

<style scoped>
.home-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 70vh;
}

.welcome-card {
  width: 700px;
  text-align: center;
}

.welcome-card h2 {
  color: #303133;
  margin-bottom: 8px;
}

.welcome-card p {
  color: #909399;
}

.quick-start {
  margin: 24px 0;
}

.actions {
  margin-top: 24px;
}
</style>
