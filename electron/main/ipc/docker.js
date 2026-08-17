/**
 * Docker 探测 IPC (用户体验 D 批: 数据底座引导第一阶段)
 *
 * 用途: 渲染层需要判断用户是否已装 Docker, 以给出差异化引导 —
 *   已装 → 提示 docker compose up -d 一键启动 Neo4j;
 *   未装 → 跳官网安装 + 受限模式说明。
 *
 * 实现: spawn `docker --version` (短超时) 采版本号; 不解析具体客户端/服务端版本。
 * 参考 backend-sidecar.js 的 spawn + 'error' 处理器模式 (不挂 error 会弹黑屏崩溃)。
 */
import { spawn } from 'child_process'
import { ipcMain } from 'electron'

const DOCKER_BIN = process.platform === 'win32' ? 'docker' : 'docker'

/**
 * 探测 docker 是否可用, 返回 { installed, version, hint }
 *  - installed: docker 命令可执行且返回版本信息
 *  - version: 首行原始输出 (如 "Docker version 27.3.1, build ...")
 *  - hint: 未安装时的引导文案
 */
function checkDockerVersion() {
  return new Promise((resolve) => {
    const proc = spawn(DOCKER_BIN, ['--version'], {
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    })
    let out = ''
    let err = ''
    const timer = setTimeout(() => {
      // 超时兜底: docker 命令挂起 (如 Docker Desktop 冷启动) 时 3s 判未就绪
      proc.kill()
      resolve({ installed: false, version: '', hint: 'Docker 探测超时, 请确认 Docker Desktop 已启动' })
    }, 3000)

    proc.stdout?.on('data', (d) => { out += String(d) })
    proc.stderr?.on('data', (d) => { err += String(d) })
    proc.on('error', (e) => {
      clearTimeout(timer)
      // ENOENT = 命令不存在 → 未安装
      resolve({ installed: false, version: '', hint: '未检测到 Docker, 请先安装 Docker Desktop' })
    })
    proc.on('close', (code) => {
      clearTimeout(timer)
      const text = (out || err).trim()
      const firstLine = text.split('\n')[0] || ''
      if (code === 0 && /docker/i.test(firstLine)) {
        resolve({ installed: true, version: firstLine, hint: '' })
      } else {
        resolve({ installed: false, version: firstLine || '', hint: 'Docker 命令不可用, 请检查安装与 PATH' })
      }
    })
  })
}

export function registerDockerIpc() {
  ipcMain.handle('docker:checkVersion', async () => {
    return checkDockerVersion()
  })
}