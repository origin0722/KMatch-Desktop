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
        // 127.0.0.1 而非 localhost: 本机 localhost 优先解析 ::1, 而后端只绑 IPv4,
        // 走 localhost 会随机撞连接拒绝 → "后端未运行" (实测)
        target: 'http://127.0.0.1:8000',
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
