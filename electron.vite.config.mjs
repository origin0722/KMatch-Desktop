import { defineConfig } from 'electron-vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  main: {
    build: {
      outDir: 'out/main',
      rollupOptions: {
        external: ['electron', 'path', 'url', 'child_process', 'fs', 'fs/promises', 'worker_threads'],
        // watcher-worker.cjs 作为额外入口, 与 index.js 一起 build 到 out/main/。
        // Node worker_threads 直接 require 该路径运行 (chokidar v4 支持 CJS)。
        input: {
          index: path.resolve(__dirname, 'electron/main/index.js'),
          'watcher-worker': path.resolve(__dirname, 'electron/main/watcher-worker.cjs'),
        },
        output: {
          format: 'cjs',
          entryFileNames: '[name].js',
        },
      },
    },
  },
  preload: {
    build: {
      outDir: 'out/preload',
      lib: { entry: 'electron/preload/index.js' },
      rollupOptions: {
        external: ['electron'],
      },
    },
  },
  renderer: {
    root: path.resolve(__dirname, 'frontend'),
    base: './',
    build: {
      outDir: path.resolve(__dirname, 'out/renderer'),
      rollupOptions: {
        input: path.resolve(__dirname, 'frontend/index.html'),
      },
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'frontend/src'),
      },
    },
    server: {
      port: 5173,
      proxy: {
        // 阶段1: 渲染层经 IPC 代理后端, 此 proxy 仅 dev 浏览器调试用
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    plugins: [vue()],
  },
})
