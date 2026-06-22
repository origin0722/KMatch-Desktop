# Issue Tracker

本项目使用 **GitHub Issues**（仓库 `origin0722/KMatch-Desktop`）跟踪所有 bug、重构任务与文档工作。

## 工具

通过 [`gh` CLI](https://cli.github.com/) 操作（已验证可用，`gh version 2.93.0`）：

```bash
gh issue create --title "..." --body-file issue.md --label bug
gh issue list --state open
gh issue view <number>
gh issue close <number>
```

## 约定

- 新 bug / 新任务一律开 GitHub issue，不再往 `docs/BUG决策日志.md` 追加（该文件已转为历史存档）。
- 每个 issue 用 triage label 标注状态（见 [triage-labels.md](./triage-labels.md)），用分类 label 标注类型（`bug`/`refactor`/`documentation`/`competition`/`enhancement`）。
- 重构类 issue 的 body 必须含"验收标准"，其中嵌入赛题功能锚点回归（场景一/二闭环、(3)①可视化、(4)②导学、M5 指标、四层图谱契约）。
- 按依赖序发布（blocker 先），便于在 `Blocked by` 字段引用真实 issue 编号。
- vertical-slice 优先：issue 应是端到端薄切片（schema/API/UI/tests 都穿到），而非单层横切。
