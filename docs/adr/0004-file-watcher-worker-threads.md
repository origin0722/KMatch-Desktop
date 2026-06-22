# ADR-0004: 文件监听用 worker_threads + chokidar v4

- 状态：Accepted
- 日期：2026-06-22
- 关联：阶段8

## 背景

IDE 需要监听项目目录的文件变化以刷新文件树、失效项目图谱、提示 Monaco 外部改动。监听大目录（赛题泛化到其他 AI 垂直领域时可能含数据/模型文件）会阻塞主线程。

## 决策

用 **Node `worker_threads` 跑 chokidar v4** 监听项目目录，主线程仅转发事件到渲染层。

- `electron/main/watcher-worker.cjs`（CJS，因 main 输出为 CJS）+ rollup 多入口 build 到 `out/main/watcher-worker.js`。
- `createWatcherController` 纯工厂（依赖注入 Worker + getMainWindow）便于单测。
- chokidar **v4 非 v5**：v5 ESM-only，与 main 的 CJS 输出冲突。
- 150ms 去抖，`unlink` 优先于 `change`。

## 理由

- worker_threads 把监听工作移出主线程，UI 不卡。
- 纯工厂 + 依赖注入对齐既有 `window-ipc.test.js` 模式，可单测。
- 选 v4 是 ESM/CJS 兼容性的硬约束，非偏好。

## 后果

- workspace `openProject`/`setRoot` 后 start watcher，`setRoot(null)` 与 `before-quit` stop。
- 文件变化 → `workspace.onFileChange` → `projectGraph.markStale`（赛题场景二正确性）+ Monaco 失效。`workspace→projectGraph` 硬编码调用是已知耦合点（见重构方案 C2）。
- 测试：`watcher-factory.test.js` + `workspace-watcher.test.js`。
