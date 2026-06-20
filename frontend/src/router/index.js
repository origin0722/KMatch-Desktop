import { createRouter, createWebHashHistory } from 'vue-router'

// 阶段0 路由结构: hash history(Electron file:// 刷新不 404)
// /workspace — 场景二: IDE 式 AI 助手(阶段1 建设完整壳, 阶段0 先承载项目上传)
// /learn     — 场景一: 学习(测评/图谱/资源/Agent/看板)
const routes = [
  { path: '/', redirect: '/learn' },
  {
    path: '/workspace',
    name: 'Workspace',
    component: () => import('@/views/Workspace.vue'),
  },
  {
    path: '/learn',
    name: 'Learn',
    component: () => import('@/views/Learn.vue'),
    redirect: '/learn/assessment',
    children: [
      { path: 'assessment', name: 'Assessment', component: () => import('@/views/Assessment.vue') },
      { path: 'graph', name: 'Graph', component: () => import('@/views/KnowledgeGraph.vue') },
      { path: 'learning', name: 'Learning', component: () => import('@/views/Learning.vue') },
      { path: 'agents', name: 'Agents', component: () => import('@/views/AgentView.vue') },
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard.vue') },
    ],
  },
]

export default createRouter({ history: createWebHashHistory(), routes })
