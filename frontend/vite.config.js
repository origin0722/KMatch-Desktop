import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  base: './', // Electron 打包后加载本地文件需要相对路径
  server: {
    port: 5173,
    proxy: {
      '/api': {
        // 本地默认 127.0.0.1:8000 (同桌后端); Docker 容器内用 VITE_PROXY_TARGET=http://backend:8000
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  // Monaco editor worker 配置
  optimizeDeps: {
    include: ['monaco-editor'],
  },
})
