/**
 * preload 桥接层 (阶段1)
 * contextBridge 暴露受控 API 表面 (window.api), 渲染层无 Node 能力。
 * 阶段2/3 将追加 ai / permission / project 命名空间。
 */
import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('api', {
  workspace: {
    openProject: () => ipcRenderer.invoke('workspace:openProject'),
    setRoot: (dir) => ipcRenderer.invoke('workspace:setRoot', dir),
    getRoot: () => ipcRenderer.invoke('workspace:getRoot'),
    listRecent: () => ipcRenderer.invoke('workspace:listRecent'),
  },
  fs: {
    readFile: (p) => ipcRenderer.invoke('fs:readFile', p),
    stat: (p) => ipcRenderer.invoke('fs:stat', p),
    listDirectory: (p, opts) => ipcRenderer.invoke('fs:listDirectory', p, opts || {}),
    writeFile: (p, content) => ipcRenderer.invoke('fs:writeFile', p, content),
    createFile: (p) => ipcRenderer.invoke('fs:createFile', p),
    deleteFile: (p) => ipcRenderer.invoke('fs:deleteFile', p),
    rename: (a, b) => ipcRenderer.invoke('fs:rename', a, b),
    // 文件监听 (阶段8): 订阅外部文件变动事件, 返回 unsubscribe。
    // 事件 { kind:'add'|'change'|'unlink', path, absPath }。仿 http.onChunk 模式。
    onChange: (cb) => {
      const h = (_e, event) => cb(event)
      ipcRenderer.on('fs:watch:change', h)
      return () => ipcRenderer.removeListener('fs:watch:change', h)
    },
  },
  watcher: {
    // 兜底: 渲染层可主动启停 (主要靠 openProject 自动 start)
    start: (root) => ipcRenderer.invoke('fs:watch:start', root),
    stop: () => ipcRenderer.invoke('fs:watch:stop'),
  },
  http: {
    request: (method, urlPath, body, params, opts) =>
      ipcRenderer.invoke('http:request', method, urlPath, body, params, opts),
    // SSE: 启动流, 返回 reqId; 订阅 chunk/done/error 事件。
    // F3: 可传 reqId 以便并发多流按 reqId 过滤 (chat 与 diagnostics 评估并发不串扰)。
    stream: (urlPath, body, reqId) => ipcRenderer.invoke('http:stream', urlPath, body, reqId),
    onChunk: (cb) => {
      const h = (_e, reqId, block) => cb(reqId, block)
      ipcRenderer.on('http:stream:chunk', h)
      return () => ipcRenderer.removeListener('http:stream:chunk', h)
    },
    onDone: (cb) => {
      const h = (_e, reqId) => cb(reqId)
      ipcRenderer.on('http:stream:done', h)
      return () => ipcRenderer.removeListener('http:stream:done', h)
    },
    onError: (cb) => {
      const h = (_e, reqId, err) => cb(reqId, err)
      ipcRenderer.on('http:stream:error', h)
      return () => ipcRenderer.removeListener('http:stream:error', h)
    },
  },
  window: {
    openDevTools: () => ipcRenderer.invoke('window:openDevTools'),
  },
  docker: {
    // 探测 Docker 是否可用 (数据底座引导): 返回 { installed, version, hint }
    checkVersion: () => ipcRenderer.invoke('docker:checkVersion'),
  },
  // Spec B 18-19 / issue-49: 网络代理落盘 + 后端重启 (设置页「网络代理」)
  setProxyConfig: (config) => ipcRenderer.invoke('proxy:setConfig', config),
  getProxyConfig: () => ipcRenderer.invoke('proxy:getConfig'),
  restartBackend: () => ipcRenderer.invoke('backend:restart'),
})
