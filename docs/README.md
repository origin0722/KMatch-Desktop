# KMatch·知链 — 文档中心

> 项目文档统一入口。所有文档按主题分类收纳于 `docs/` 下；仓库根目录仅保留
> [README.md](../README.md)（仓库入口）、[CONTEXT.md](../CONTEXT.md)（领域词汇单一源）、
> [CLAUDE.md](../CLAUDE.md)（Claude 速查卡）三个约定文件。

## 分类导航

| 分类目录 | 内容 | 文档 |
|:---|:---|:---|
| [项目规划](项目规划/) | 开发计划、赛题对标 | [项目开发计划书.md](项目规划/项目开发计划书.md)、[赛题XH-202630比赛方案.md](项目规划/赛题XH-202630比赛方案.md) |
| [指南手册](指南手册/) | 环境/数据准备、知识库扩展 | [前置数据准备指南.md](指南手册/前置数据准备指南.md)、[知识库扩展指南.md](指南手册/知识库扩展指南.md) |
| [架构与设计](架构与设计/) | 架构总览、依赖、重构方案 | [ARCHITECTURE.md](架构与设计/ARCHITECTURE.md)、[DEPENDENCIES.md](架构与设计/DEPENDENCIES.md)、[重构方案_解耦.md](架构与设计/重构方案_解耦.md) |
| [adr](adr/) —— 决策记录 | 架构决策记录 (ADR-0001 ~ 0007) | [0001-web-to-desktop-migration.md](adr/0001-web-to-desktop-migration.md) 等 |
| [质量与验收](质量与验收/) | M5 质检指标与交付报告 | [质量检测报告.md](质量与验收/质量检测报告.md)、[M5质量检测方法论升级.md](质量与验收/M5质量检测方法论升级.md) |
| [接口对接](接口对接/) | 前后端/多端 API 契约 | [A端后端对接文档.md](接口对接/A端后端对接文档.md) |
| [评审记录](评审记录/) | 第三方/框架评审 | [Apix借鉴与代码审查报告_2026-06-20.md](评审记录/Apix借鉴与代码审查报告_2026-06-20.md) |
| [研究与调研](研究与调研/) | 模型调研、界面模板分析 | [模型更新调研_2026-08.md](研究与调研/模型更新调研_2026-08.md)、[研究_界面布局交互模板分析与KMatch优化.md](研究与调研/研究_界面布局交互模板分析与KMatch优化.md) |
| [合规与安全](合规与安全/) | 数据合规与隐私 | [数据合规与隐私保护说明.md](合规与安全/数据合规与隐私保护说明.md) |
| [交付材料](交付材料/) | 赛题提交材料 | [提交材料_视频脚本与方案大纲.md](交付材料/提交材料_视频脚本与方案大纲.md)、[软件说明_v1.1.0.md](交付材料/软件说明_v1.1.0.md)、[真机核验清单_v1.0.0.md](交付材料/真机核验清单_v1.0.0.md) |
| [缺陷管理](缺陷管理/) | BUG 记录与决策（历史存档） | [BUG决策日志.md](缺陷管理/BUG决策日志.md) |
| [agents](agents/) | Agent 协同约定（Issue/Triage/Domain） | [issue-tracker.md](agents/issue-tracker.md)、[triage-labels.md](agents/triage-labels.md)、[domain.md](agents/domain.md) |
| [devlogs](devlogs/) | 开发日志（按端分类，持续更新） | [README.md](devlogs/README.md)、[Desktop_阶段总览.md](devlogs/Desktop_阶段总览.md) |
| [legacy](legacy/) | 历史归档（**冻结**，不更新） | 三人协作时代协作文档、早期开发日志 |

## 维护约定

- **新文档放哪**：按上表主题对号入座；拿不准的放对应分类目录并在 [devlogs](devlogs/) 中记一笔。
- **开发日志**：每次会话结束写 `docs/devlogs/<端>/YYYY-MM-DD_主题.md`，别放分类目录。
- **架构决策**：记 `docs/adr/ADR-XXXX-<slug>.md`（沿用 docs/adr 编号递增）。
- **BUG**：新 bug 开 GitHub Issue（见 [agents/issue-tracker.md](agents/issue-tracker.md)）；`缺陷管理/BUG决策日志.md` 为历史存档，不再追加。
- **`legacy/` 与 `superpowers/` 冻结**：历史快照文字与其中链接一律不改，避免伪造历史。
- **移动文档**：改名/挪目录后，全仓 `grep` 修复引用（`docs/<旧路径>` 与相对链接两种形态都要查）。

## 相关链接

- 仓库入口：[README.md](../README.md) ｜ 领域词汇：[CONTEXT.md](../CONTEXT.md) ｜ Agent 速查：[CLAUDE.md](../CLAUDE.md) / AGENTS.md（本地）
