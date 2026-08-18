import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.{test,spec}.{js,jsx}'],
    // Windows jsdom 下重 store 模块导入 + 真实短定时器用例 (chat-attachments/workspace-watcher)
    // 在并行满载时接近默认 5s 上限而偶发失败; 提到 10s (真死锁仍会超时, 不掩盖问题)
    testTimeout: 10_000,
  },
})
