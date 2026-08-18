# ADR-0005: Apix 借鉴范围收口

- 状态：Accepted
- 日期：2026-06-22
- 关联：阶段8/10，Apix 借鉴三大项全部完成

## 背景

阶段6–10 陆续从 Apix 借鉴了若干工程实践。需记录借鉴范围，避免无界扩散。

## 决策

Apix 借鉴三大项（均已落地）：

1. **文件监听 Worker**（阶段8，ADR-0004）— worker_threads + chokidar v4。
2. **消息 chunks 判别联合**（阶段6b，ADR-0002）— MessageChunk 模型。
3. **消息分支（重生成分支）**（阶段10，ADR-0003）— 线性 versions + trailingAfter。

## 不借鉴（YAGNI）

- 用户消息编辑（只做助手重生成）。
- 树形消息分支（线性 versions 已满足需求）。
- 平等分屏容器布局（用主从分屏，见 session store）。

## 后果

- 三大项完成，Apix 借鉴路线收官。
- 后续若再引入借鉴项，需新开 ADR 说明范围与理由。
- Apix 审查报告（`docs/评审记录/Apix借鉴与代码审查报告_2026-06-20.md`）中 S1–S9 已全部修复；F1–F15 脆弱点转入 GitHub Issues 跟踪。
