# ADR-0001: Web 前端迁移到 Electron + Monaco 桌面 IDE

- 状态：Accepted
- 日期：2026-06-19
- 决策者：单人全栈（原三人协作 → 6/20 起单人）

## 背景

原 KMatch 是 Vue3 + Element Plus + AntV G6 的 Web 前端（port 5173），三人 A/B/C 协作开发。6/19 起项目转为单人全栈，赛题要求一个统一的本地学习平台。

## 决策

迁移为 **KMatch-Desktop**：Electron + electron-vite 壳 + Monaco Editor，做成类 VSCode 的桌面 IDE。原 Web 学习功能（Assessment / KnowledgeGraph / AgentView / Dashboard / Learning）收编进 IDE 主区与侧栏，新增 AI 助手面板。

## 理由

- 桌面 IDE 形态更贴合"本地个性化学习平台"定位，且统一收编散落 Web 视图。
- Monaco 提供代码视图，支撑场景二（有项目二次开发）的代码审查/测试联动。
- 单人维护下，一套 Electron 壳比 Web + 后端 + 部署更收敛。

## 后果

- 原 Web 三人协作文档归档到 `docs/legacy/`（B 端文档簇、W1-2 审查报告等）。
- `README.md` 需重写为 Desktop 版（阶段 D）。
- 后端改为 PyInstaller sidecar，随安装包自启（见 ADR-0005 / 阶段5）。
