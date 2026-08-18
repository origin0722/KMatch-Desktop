# Domain Docs

本仓库为 **single-context** 布局：根目录一个 `CONTEXT.md` 描述项目 ubiquitous language，`docs/adr/` 存放架构决策记录。

## 布局

- `CONTEXT.md`（仓库根）— 项目领域词汇表。`improve-codebase-architecture`、`diagnose`、`tdd` 等 skill 会读取它来对齐术语。
- `docs/adr/` — ADR（Architecture Decision Records），编号 `NNNN-kebab-title.md`。只记录已成形决策，不重开争论。
- `docs/架构与设计/ARCHITECTURE.md` — 架构总览（进程拓扑 + 数据流 + 状态更新流），是 CONTEXT 的结构化补充。

## 消费规则

- skill 提出重构建议时，domain 词汇必须用 `CONTEXT.md` 的定义；architecture 词汇（module/interface/seam/depth 等）用 `improve-codebase-architecture` 的 [LANGUAGE.md](../../.claude/skills/improve-codebase-architecture/LANGUAGE.md)。
- 若建议与现有 ADR 冲突，只有当 friction 真实到值得重开 ADR 时才提出，并在建议中显式标注"contradicts ADR-NNNN"。
- 对话中收紧了模糊术语 → 立即更新 `CONTEXT.md`；用有分量理由拒绝了某 refactor → 提议记成 ADR。
