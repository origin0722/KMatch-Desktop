# AnySearch Agent Tool Design

> 状态: 未来后端集成设计稿。当前前端 redesign 阶段不实现任何 AnySearch 调用。

## 安全规则

AnySearch API Key 绝不允许写入：

- 前端代码
- localStorage
- Pinia state
- 文档
- 测试
- git 历史

Key 来源只能是后端环境变量 `ANYSEARCH_API_KEY`。

历史教训: 用户曾在对话中直接发送过一次 AnySearch key。该 key 视为已泄露, 必须在 AnySearch 控制台轮换。本仓库不保存任何 key 明文。

## 预期架构

```
渲染层 → FastAPI Agent 工具端点 → AnySearch CLI/API → 结构化检索结果 → Agent 回复
```

AnySearch 作为后端 Agent 工具层的一个能力, 不作为前端直连能力。前端只控制权限, 不持有密钥。

## 前端控制项

前端只暴露权限开关 (复用 `frontend/src/stores/aiSettings.js` 工具权限机制):

| 工具 | 默认策略 | 说明 |
|---|---|---|
| `anysearch_search` | ask | 普通/垂直领域检索 |
| `anysearch_extract` | ask | URL 内容抽取 |
| `anysearch_domain_search` | ask | 垂直领域结构化检索 |

禁止项:

- 不做 API Key 输入框
- 不做前端直连
- 不保存用户提供的 key

## 后端工具

未来在 `backend/app/agents/` 下新增工具调用入口, 由 orchestrator 或 graph_controller 调度:

- `anysearch_search(query, max_results)`
- `anysearch_extract(url)`
- `anysearch_domain_search(domain, sub_domain, params)`

后端读取 `ANYSEARCH_API_KEY` 环境变量, 通过 `Authorization: Bearer` 调用 `https://api.anysearch.com`。参考 anysearch-skill 仓库 `SKILL.md` 的命令形态, 但本项目走后端 HTTP, 不在前端跑 CLI。

## 适用场景

- 学习资源生成时检索专业资料
- 知识点解释时查外部权威来源
- 项目二次开发时查框架/库文档
- 内容审核 Agent 核验事实
- 图谱扩展 Agent 补充领域知识

## 本阶段不实现

- 不安装 anysearch-skill
- 不实现后端调用
- 不实现前端权限 UI (留给后续 AI 设置页)
- 不在仓库任何位置写入 key

## 关联

- 前端权限机制: `frontend/src/stores/aiSettings.js` `TOOL_PERMISSION`
- 主设计文档: `docs/superpowers/specs/2026-06-21-ai-control-center-shell-design.md`
- 实现计划: `docs/superpowers/plans/2026-06-21-ui-redesign-navigation-agent-assessment-plan.md`
