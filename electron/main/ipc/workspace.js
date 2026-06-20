/**
 * 工作区 IPC (阶段1)
 * 打开/切换项目根目录, 最近项目记忆 (userData/recent.json)
 */
import { ipcMain, dialog, app } from 'electron'
import fs from 'fs/promises'
import path from 'path'
import { setWorkspaceRoot, getWorkspaceRoot } from './fs.js'

// lazy: app.getPath 在模块顶层执行时可能尚未就绪, 延迟到首次调用
function recentFile() {
  return path.join(app.getPath('userData'), 'recent-projects.json')
}

async function loadRecent() {
  try {
    const data = await fs.readFile(recentFile(), 'utf-8')
    const arr = JSON.parse(data)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

async function saveRecent(list) {
  const f = recentFile()
  await fs.mkdir(path.dirname(f), { recursive: true })
  await fs.writeFile(f, JSON.stringify(list, null, 2), 'utf-8')
}

async function pushRecent(dir) {
  const list = (await loadRecent()).filter((p) => p !== dir)
  list.unshift(dir)
  await saveRecent(list.slice(0, 10))
}

export function registerWorkspaceIpc() {
  ipcMain.handle('workspace:openProject', async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openDirectory'],
      title: '选择项目根目录',
    })
    if (result.canceled || !result.filePaths.length) return null
    const dir = result.filePaths[0]
    setWorkspaceRoot(dir)
    await pushRecent(dir)
    return { root: dir, name: path.basename(dir) }
  })

  ipcMain.handle('workspace:setRoot', async (_e, dir) => {
    setWorkspaceRoot(dir)
    await pushRecent(dir)
    return { root: dir, name: path.basename(dir) }
  })

  ipcMain.handle('workspace:getRoot', () => getWorkspaceRoot())

  ipcMain.handle('workspace:listRecent', () => loadRecent())
}
