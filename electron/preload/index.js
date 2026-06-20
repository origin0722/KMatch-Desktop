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
  },
  http: {
    request: (method, urlPath, body, params, opts) =>
      ipcRenderer.invoke('http:request', method, urlPath, body, params, opts),
    // SSE: 启动流, 返回 reqId; 订阅 chunk/done/error 事件
    stream: (urlPath, body) => ipcRenderer.invoke('http:stream', urlPath, body),
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
})
