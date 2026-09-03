# 2026-06-19 — B 端 ActionItem 修复（BUG-027~030 + W5 接口封装 + 拦截器 404）

**参与成员**: B（前端）
**会话目标**: 落地 A 端"B 端修复与联调指引" §一/§二/§五 全部 ActionItem
**耗时**: 1 小时

---

## 一、背景

A 端 6-18 超前完成 W3-W7 后端工作并 push（commit `17a227c`），同步交付 4 份 B 端对接文档：
- `docs/接口对接/A端后端对接文档.md`
- `docs/B-C端环境准备清单.md`
- `docs/B端修复与联调指引.md`
- `docs/B端联调用例集.md`

B 端阅读完毕后，按指引 §一 4 项 BUG（BUG-027~030，A 端审查发现移交 B）+ §二 W5 新接口封装 + §五 拦截器 404 分支补全，一并落地。

---

## 二、产出

### 2.1 BUG 修复（4 项）

| BUG | 文件 | 改动要点 |
|:---|:---|:---|
| **BUG-027** | `frontend/src/views/Assessment.vue:98-113` | 删除 `:description="store.error"` prop，改为 `<template #default>` 内 `<p>{{ store.error }}</p>` + 按钮，让 alert 真正显示后端错误原因 |
| **BUG-028** | `frontend/src/stores/assessment.js` `startAssessment` try 块 | 成功路径检测空画像 `!data.profile \|\| Object.keys(data.profile).length === 0`，把 `review_results.retry_hint` 写入 `error.value`，并显式 `profile.value = null` 防 hasResults 误判 |
| **BUG-029** | `frontend/src/components/AssessmentReport.vue:152` | `answer: answers[idx] ?? ''` → `?? null`，保留 null 让模板 `??` 兜底真正生效（`''` 不是 nullish） |
| **BUG-030** | `frontend/src/stores/assessment.js` 4 处散点 | state 新增 `knowledgeGraph` / `generatedContent` 两个 ref；try 块成功路径补两行映射；reset 补两行清空；return 补两个导出 |

### 2.2 W5 新接口封装

| 文件 | 改动 |
|:---|:---|
| `frontend/src/api/diagnostics.js` | 新增 `submitAnswers({sessionId, answers}, signal)` → POST `/api/diagnostics/submit` |
|  | 新增 `requestFeedback({sessionId, strategy, profile}, signal)` → POST `/api/diagnostics/feedback` |
|  | 两函数都支持可选 `signal` 透传（与 `submitAssessment` 对齐） |

### 2.3 拦截器 404 分支

| 文件 | 改动 |
|:---|:---|
| `frontend/src/api/index.js` 响应拦截器 | 在 422/503/500 之后补 `else if (status === 404)` 分支，文案"资源不存在：{detail \|\| 会话已失效，请重新开始测评}"。专门覆盖 W5 submit/feedback 的 session_id 失效场景（后端 LRU 上限 100 / 服务重启） |

### 2.4 单测补强

| 文件 | 新增用例 |
|:---|:---|
| `frontend/src/__tests__/assessment-store.test.js` | BUG-028 三档（retry_hint / 默认提示 / profile=null）、BUG-030 两档（成功填充 / 响应缺字段）、reset 增强 |
| `frontend/src/__tests__/diagnostics-api.test.js`（**新增**）| `submitAssessment` 字段映射 + signal 透传；`submitAnswers` 路径与 body；`requestFeedback` 三档 strategy |

测试结果：**4 文件 / 42 用例全部通过**（旧 26 → 新 42，+16 用例）。

---

## 三、关键设计决策

### 3.1 BUG-028 用 `data.profile === null` 也走空画像分支

A 给的补丁条件是 `!data.profile || Object.keys(data.profile).length === 0`，第一个分支 `!data.profile` 已覆盖 `null`/`undefined`/`0`/`''`/`false`。后端实际只可能返回 `{}` 或合法 profile，但保留 null 防御能让前端在后端契约异常时也不崩。新增的"profile=null 防御"vitest 用例锁定该行为。

### 3.2 store 的 `knowledgeGraph` / `generatedContent` 命名用 camelCase

后端响应字段是 `knowledge_graph` / `generated_content`（snake_case），store ref 用 camelCase 与 Vue/JS 习惯对齐。映射在 try 块一次完成，下游消费方（W3 图谱页、W4 资源页）只看 store 的 camelCase 字段。

### 3.3 拦截器 404 分支不直接 return，仅 toast

A 在指引 §五 提示"建议各业务调用处单独 catch 404 引导用户重新发起 assess"。本次只在拦截器统一 toast，**不在拦截器内执行业务跳转**（如清空 store、回到表单），原因：
- 拦截器跳转会绕过业务方的 try/catch
- W5 答题页可能想用 404 触发"会话失效，已为你保存草稿"等定制 UI
- 业务方仍可在 then/catch 链路里继续处理，toast 只是兜底提示

### 3.4 vitest mock `@/api/index` 而非 axios 本身

`diagnostics-api.test.js` 直接 mock 我们自己的 http 实例（`@/api/index`），而非 axios。这样：
- 测试只验证我们的封装逻辑（字段映射 / 路径 / signal 透传）
- 拦截器/baseURL/超时等下层细节不参与测试，关注点清晰
- 比 mock axios 更轻，不需要 `vi.spyOn(axios, 'create')` 等魔法

---

## 四、踩坑

### Pitfall-1: el-alert 的默认插槽是描述插槽，不是"额外内容插槽"

Element Plus 文档不显眼地在 slots 表里写了 `default — Alert 内容描述`。直觉上我会以为 `:description` prop 与 `#default` 插槽是叠加关系（prop 给基础文案，插槽追加自定义内容），但实际是**插槽替换 prop**。BUG-027 就是踩了这个坑。
**记录**：以后用 Element Plus 任何带 `description` / `content` prop 的组件，要么只用 prop 要么只用插槽，别同时给。

### Pitfall-2: `??` 与 `||` 兜底差异（BUG-029 的本质）

```js
'' ?? '默认' // → ''（?? 只在 null/undefined 触发）
'' || '默认' // → '默认'（|| 在所有 falsy 时触发）
```

`answers[idx] ?? ''` 会把 undefined 转成空串，下游模板再用 `??` 就再也无法兜底 — 这条 bug 链是"双重 ?? 把 undefined 信息丢了"。修法是**保住 null/undefined 不让它降级**，让最外层兜底处统一处理。

### Pitfall-3: vitest mock 文件级 `vi.mock` 必须在 import 之前

`diagnostics-api.test.js` 写法：
```js
vi.mock('@/api/index', () => ({ default: { post: vi.fn(), get: vi.fn() } }))
import http from '@/api/index'
import { submitAssessment, ... } from '@/api/diagnostics'
```

`vi.mock` 会被 vitest 提升到文件顶部（hoist），所以在 `import` 后写也工作。但显式放在 import 之前能让阅读顺序与执行顺序一致，避免后续维护者疑惑。

---

## 五、对后端的反馈

无需后端配合。A 在指引 §七 已声明"4 个 BUG 都是纯前端，A 侧无需改动"，本次落地全部在 B 端目录内。

唯一一点观察：BUG-028 修复依赖后端 `review_results.retry_hint` 文案是用户友好的（不是堆栈/调试串）。A 当前实现里 retry_hint 形如"后端 LLM 未配置"，符合预期。后续若 retry_hint 加入技术细节（API 错误码、节点 ID 等），建议保留一个 user-facing 字段（如 `retry_hint_human`）让前端能直接展示给用户看。

---

## 六、下一步建议

按指引 §四"真实环境联调补充"：

1. **BUG-027/028 真实环境验证**：起完整后端但留 `LLM_API_KEY=sk-placeholder`，跑一次 demo，确认 alert 显示 retry_hint。需要先把环境跑起来。
2. **拦截器 404 真实场景测**：先 assess(interactive) 拿 session_id → 重启后端 → submit 应得 404 toast"资源不存在"。
3. **W3 KnowledgeGraph 主图组件开工**：现在 store 已有 `knowledgeGraph.learning_path`，可以基于 G6 静态布局先把节点与边画出来。这是 W3 主线最大价值产出。
4. **W5 答题页**：interactive 三步流程 UI，可以在 W3 主图之后做（依赖更少：仅 store + 已封装的 3 个 API 函数）。

---

## 七、相关 commit

- 上一轮：`16a9ad8 docs: 同步 B 端 6-18 第二轮 devlog + BUG-021~026 决策日志`
- A 端拉下后：`17a227c`（A 端 W3-W7 + 4 份对接文档）
- 本次（待 push）：`feat(frontend): B 端 ActionItem 修复 — BUG-027~030 + W5 接口封装 + 拦截器 404 分支`

## 八、相关文档

- [docs/B端修复与联调指引.md](../../B端修复与联调指引.md)（指引来源）
- 接口对接文档（API 契约，后续已移出仓库）
- [docs/B端联调用例集.md](../../B端联调用例集.md)（联调用例）
- [docs/缺陷管理/BUG决策日志.md](../../缺陷管理/BUG决策日志.md) BUG-027/028/029/030（已标 ✅）
