import { createRouter, createWebHashHistory } from 'vue-router'
import Workspace from '@/views/Workspace.vue'
import Learn from '@/views/Learn.vue'

const routes = [
  { path: '/', redirect: '/workspace' },
  { path: '/workspace', name: 'Workspace', component: Workspace },   // 场景二: IDE式AI助手
  { path: '/learn', name: 'Learn', component: Learn },               // 场景一: 学习
]

export default createRouter({ history: createWebHashHistory(), routes })
