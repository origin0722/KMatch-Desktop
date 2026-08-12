// KMatch-Desktop dev 启动器
//
// 修复 Electron 宿主 IDE (Trae CN / VSCode 等基于 Electron 的编辑器) 注入环境变量的坑:
//   ELECTRON_RUN_AS_NODE=1         → electron 退化为 node 模式跑, app 为 undefined, 窗口黑屏
//   ELECTRON_FORCE_IS_PACKAGED=true → app.isPackaged 恒为 true, 误导 backend-sidecar 走
//                                      KMatchBackend.exe 打包分支 → dev 下 ENOENT 崩溃
// 这两个变量会从 IDE 集成终端传播到 npm run dev 的子进程。本启动器先清除再调 electron-vite dev,
// 保证任何终端下 `npm run dev` 都稳定可用。相关修复: electron/main/backend-sidecar.js (existsSync 判定)。
import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

delete process.env.ELECTRON_RUN_AS_NODE
delete process.env.ELECTRON_FORCE_IS_PACKAGED

const here = path.dirname(fileURLToPath(import.meta.url))
const ext = process.platform === 'win32' ? '.cmd' : ''
const bin = path.join(here, '..', 'node_modules', '.bin', `electron-vite${ext}`)

const child = process.platform === 'win32'
  ? spawn('cmd.exe', ['/c', bin, 'dev'], { stdio: 'inherit' })
  : spawn(bin, ['dev'], { stdio: 'inherit' })

child.on('exit', (code) => process.exit(code ?? 0))
child.on('error', (err) => {
  console.error('[dev] 启动 electron-vite 失败:', err.message)
  console.error('[dev] 请确认已 npm install (node_modules/.bin/electron-vite 存在)')
  process.exit(1)
})
