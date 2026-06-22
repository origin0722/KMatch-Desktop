# Triage Label Vocabulary

`triage` skill 处理 incoming issue 时按下列 state machine 移动 label。仓库已建好对应 GitHub label。

## Canonical triage roles（状态机）

| Label | 含义 |
|---|---|
| `needs-triage` | maintainer 需要评估 |
| `needs-info` | 等待 reporter 补充信息 |
| `ready-for-agent` | 已完全规约，AFK agent 可无人交互领取 |
| `ready-for-human` | 需要人工实现 |
| `wontfix` | 不会处理 |

## 项目分类 label（与 triage role 正交，标注类型）

| Label | 含义 |
|---|---|
| `bug` | Something isn't working（GitHub 默认） |
| `refactor` | 代码重构/解耦，不改外部行为 |
| `documentation` | 文档改进（GitHub 默认） |
| `competition` | 赛题功能锚点——重构不可破坏的约束 |
| `enhancement` | 新功能/增强（GitHub 默认） |

## 规则

- 一个 issue 同时带 **一个 triage role label** + **零或多个分类 label**。
- `competition` label 用于"赛题锚点清单"参照 issue，以及任何触及赛题功能面的 refactor/bug issue。
- `triage` skill 不应创建重复 label；如需新 label，先在此文件登记再 `gh label create`。
