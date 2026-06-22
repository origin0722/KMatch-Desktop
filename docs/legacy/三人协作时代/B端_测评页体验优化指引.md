# B 端任务:学情测评页(Assessment.vue)用户体验优化

> 写给 B 端(前端)。A 端代码审查发现测评表单把**开发者/调度参数直接暴露给了真实用户**,造成 4 个体验硬伤。本文逐一说明问题、原因、建议改法、涉及文件与后端契约,B 端可独立据此修改,无需再问 A。
>
> 归属:本任务改 `frontend/src/views/Assessment.vue`(B 端目录),A 端不碰。

---

## 背景:为什么现在这样不行

当前测评表单(`Assessment.vue` 状态A 输入区)有 5 个字段:学习目标方向、已掌握知识点、测评模式、场景、最大重试轮数。其中后 3 个是**给开发/调度用的内部参数**,真实用户看不懂、也不该改。赛题本意是"**学情检测推断用户画像**",不是让用户自报家门。

---

## 问题 1:学习目标方向 —— 用户不知道填什么

### 现状
`Assessment.vue:17-24`,自由文本输入,placeholder "例如:Python 基础语法入门"。

### 问题
- 知识库目前只有 Python 一个领域(92 节点,6 个分类),用户填"机器学习"匹配不到内容。
- 用户不知道有哪些方向可选,容易填空或填无效值。

### 建议改法:预设方向按钮 + 自由输入
- 提供 6 个预设方向按钮(对齐知识库 6 个分类),点击自动填入 `form.targetDirection`:
  - `Python 基础语法入门`(对应分类"基础语法")
  - `数据结构与算法`
  - `面向对象编程`
  - `Python 进阶`
  - `常用库与工具`
  - `项目实战`
- 保留自由输入框(高级用户可自定义),预设按钮只是一种快捷填入。
- 用 Element Plus 的 `el-radio-group`(按钮样式)或 `el-tag` 可点选,置于输入框上方。

### 为什么这样改
`target_direction` 在后端是**语义检索的 query**(`engine.hybrid_retrieve` 用它做向量检索找相关知识点),不是硬匹配分类。预设成分类名能保证检索命中,自由输入也仍可用。**无需改后端**。

---

## 问题 2:已掌握知识点 —— 用户不知道节点 ID(硬伤)

### 现状
`Assessment.vue:27-45`,让用户输入节点 ID(如 `PY-001`),回车添加成 tag。

### 问题
- 真实用户**根本不知道 PY-012 是啥**,不可能填节点 ID。
- 这违背赛题"学情检测"本意——用户来做测评,就是因为不知道自己啥水平;让用户自报已掌握节点,逻辑反了。

### 建议改法:去掉该字段,由测评自动推断(推荐)

**直接删除"已掌握知识点"整个 `el-form-item`(`Assessment.vue:26-45`)**,提交时不传 `known_topics`(后端默认空数组,见契约)。

- 测评流程本身会推断掌握度:`diagnostics` 出题 → 用户答 → `_grade` 判分 → `_build_profile` 算 mastery → mastery≥0.8 自动归入 `known_topics`。
- 所以"已掌握"是**测评的输出**,不是输入。用户做完测评,画像里的 `known_topics` 自然就有值了(结果区 `Assessment.vue:192-205` 已展示"已掌握节点"tag,那才是正确的展示位置)。
- 删除输入字段后,首次测评 `known_topics=[]`,系统按零基础处理(从难度 1-2 入口节点出题),这正是预期行为。

### 备选(若产品上一定要保留自报入口)
改成**知识点名称下拉多选**:调 `GET /api/graph/category/{category}` 拉某分类下节点列表(`[{node_id, name, difficulty, ...}]`),用户按**名称**选,前端把选中的 `node_id` 填入 `knownTopics`。但这对首次用户仍是负担,**不推荐**,优先用"去掉"方案。

### 后端契约(确认安全)
`backend/app/api/diagnostics.py:56`:
```python
known_topics: list = Field(default_factory=list, description="用户自报已学节点 [{node_id, mastery}]")
```
有默认值 `[]`,前端不传不会报错。`Assessment.vue:327` 提交时传 `knownTopics: [...]`,改成 `knownTopics: []` 或直接从请求体去掉即可。

---

## 问题 3:测评模式 —— demo 不该给真实用户选

### 现状
`Assessment.vue:47-53`,radio 让用户选 Demo / Interactive。

### 问题
- `demo` = LLM 自动作答跑通闭环(开发/演示用,用户不答题)。
- `interactive` = 用户自己答题(真实场景)。
- 真实用户看到"Demo(自动作答)"会困惑——他来测评就是要答题的,为什么要选"自动作答"。

### 建议改法:默认 interactive,demo 降级为"快速体验"

**方案 A(推荐,改动小)**:
- 表单里去掉模式 radio,`form.mode` 固定为 `'interactive'`(`Assessment.vue:287` 默认值改掉)。
- demo 模式作为**独立的"快速体验"按钮**,放在表单下方或首页入口,文案改为"一键体验完整流程(LLM 自动作答)",明确它是演示用途,不是正常测评。
- 点"快速体验"时 `mode='demo'`,点"开始测评"时 `mode='interactive'`。

**方案 B(更彻底)**:
- demo 模式完全藏起来,只通过 URL 参数 `?demo=1` 触发(评委/开发者用),主表单只有 interactive。

### 为什么 demo 要保留(但不暴露)
demo 模式对**演示/调试有价值**——评委想快速看完整 Agent 闭环(学情→图谱→生成→审核),不想手动答 10 题等几分钟。所以不删,只藏。

### 后端契约
`backend/app/api/diagnostics.py:55`:
```python
mode: str = Field("demo", description="demo=LLM自动作答跑通闭环; interactive=仅返回题目，前端提交答案")
```
两种模式后端都支持,前端怎么传都行。

---

## 问题 4:最大重试轮数 —— 用户完全看不懂

### 现状
`Assessment.vue:63-67`,`el-input-number` 让用户选 1-5,提示"审核不通过时的最大打回次数"。

### 问题
- 用户不知道什么是"审核打回",也不该能改这个数。
- 改大了浪费 LLM 调用(每轮 9 次),改小了内容没打磨好就降级交付。

### 它到底是什么
`max_retries` 是 orchestrator 的**内容审核循环上限**:content_generator 生成 → reviewer 审核 → 不通过打回重生成 → 再审核……最多 N 轮,超过降级交付(防死循环)。默认 3。

### 建议改法:去掉该字段,后端默认 3

**直接删除"最大重试轮数"整个 `el-form-item`(`Assessment.vue:63-67`)**,提交时不传 `max_retries`(后端默认 3)。

### 后端契约(确认安全)
`backend/app/api/diagnostics.py:58`:
```python
max_retries: int = Field(3, description="审核打回最大轮数", ge=1, le=5)
```
有默认值 3,前端不传就用默认。`Assessment.vue:329` 提交时去掉 `maxRetries` 字段即可。

---

## 改完后的理想表单

优化后测评输入区应该只有 **2 个用户字段**:

```
┌─ 学情测评 ────────────────────────────────┐
│                                            │
│  学习目标方向 *                             │
│  [Python基础] [数据结构] [面向对象]          │  ← 预设按钮(问题1)
│  [Python进阶] [常用库]   [项目实战]          │
│  或自定义: [________________________]       │
│                                            │
│  场景                                      │
│  [无项目技能训练 ▼]                         │  ← 保留(可选,或也简化)
│                                            │
│  [ 开始测评 → ]    [ ⚡快速体验(自动作答) ]   │  ← interactive主按钮 + demo次按钮(问题3)
│                                            │
│  (已掌握知识点字段:删除,由测评自动推断)      │  ← 问题2
│  (最大重试轮数字段:删除,后端默认3)           │  ← 问题4
└────────────────────────────────────────────┘
```

---

## 涉及文件(只改前端,不动后端)

| 文件 | 改动 |
|:---|:---|
| `frontend/src/views/Assessment.vue` | 主改动:模板区删/改 4 个 form-item,脚本区 `form` 默认值 + `handleStart` 提交体 |
| `frontend/src/stores/assessment.js` | 若提交体字段变了,同步 `startAssessment` 的 payload(去掉 knownTopics/maxRetries,或 mode 固定) |

**后端无需改动**——`known_topics`/`max_retries`/`mode` 都有默认值,前端少传字段后端照常工作。

---

## 可用的后端 API(B 改下拉时用)

若问题2用"名称下拉"备选方案,拉节点列表:
```
GET /api/graph/category/{category}
返回: [{node_id, name, difficulty, summary, ...}, ...]
```
category 取值(6 个):`基础语法` / `数据结构与算法` / `面向对象编程` / `Python进阶` / `常用库与工具` / `项目实战`

文档:`http://localhost:8000/api/docs`(Swagger)

---

## 验证

改完后:
1. `npm run dev` 起前端,打开 `/assessment`。
2. 确认表单只剩"学习目标方向(+预设按钮)"和"场景",有"开始测评"和"快速体验"两个按钮。
3. 点预设按钮 → 输入框自动填入。
4. 点"开始测评"(interactive)→ 正常出题答题流程。
5. 点"快速体验"(demo)→ LLM 自动作答跑通闭环。
6. 结果区"已掌握节点"tag 正常展示(测评自动推断的)。

---

## 联系 A 端

若改过程中发现后端契约不够用(如需要新 API 支持下拉),在 `docs/BUG决策日志.md` 或群里提,A 端补 API。本次优化 A 端预期不改后端。
