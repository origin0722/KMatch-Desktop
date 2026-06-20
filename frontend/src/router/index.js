import { createRouter, createWebHashHistory } from 'vue-router'

// 单一 IDE 形态: 工作区承载所有功能 (文件编辑 + 学习面板收编进侧栏)
// hash history: Electron file:// 刷新不 404
const routes = [
  { path: '/', redirect: '/workspace' },
  {
    path: '/workspace',
    name: 'Workspace',
    component: () => import('@/views/Workspace.vue'),
  },
]

export default createRouter({ history: createWebHashHistory(), routes })
