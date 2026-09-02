# P0 可信项目图谱与运行记录 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复项目图谱/协同状态中会误导用户的现有缺陷，使单文件质量检查、运行历史和 Agent 状态均反映真实范围与真实阶段。

**Architecture:** 保持现有 Python 项目图谱和工作流不变。后端将 run 列表投影为专用展示摘要，前端不再反查内部 `request`；协同面板把“资源生成后才会运行”的 Agent 标为延后启动，而不是未完成。项目语义图谱的通用 Adapter 只在本批稳定后另开纵切。

**Tech Stack:** Vue 3 + Pinia + Vitest、FastAPI + pytest、现有 Electron IPC 与 REST API。

---

## 文件结构与责任

| 文件 | 本批责任 |
|---|---|
| `frontend/src/views/ProjectGraphView.vue` | 修复未定义画像 store；将单文件检查的范围、名称与说明改为真实语义；接入本地历史单项删除。 |
| `frontend/src/__tests__/project-graph-view.test.js` | 新增单文件检查的单位回归，验证 Python 守卫、默认目标和 API 参数。 |
| `backend/app/agents/run_store.py` | 生成稳定的 run 列表展示投影，不泄漏完整请求。 |
| `backend/tests/test_run_store.py` | 验证场景、标题、目标、项目名和状态投影。 |
| `frontend/src/ide/RunsPanel.vue` | 只消费展示投影；用赛题术语显示场景与标题。 |
| `frontend/src/__tests__/runs-panel.test.js` | 使用真实列表响应形状，防止 mock 比 API 丰富。 |
| `frontend/src/composables/useAgentStatus.js` | 区分 `idle` 与诊断结束后的 `deferred` 资源阶段。 |
| `frontend/src/components/session/StageAgent.vue` | 使用中性图标/状态点文案，告知用户资源审核尚未启动的原因。 |
| `frontend/src/__tests__/use-agent-status.test.js` | 验证 `deferred` 只在诊断和图谱就绪、资源尚未生成时派生。 |
| `frontend/src/__tests__/stage-agent-collab.test.js` | 验证交互测评完成时内容生成/审核显示延后启动而非失败或卡死。 |
| `frontend/src/views/KnowledgeGraph.vue` | 在历史菜单项增加“删除此快照”，不影响 live 图谱。 |
| `frontend/src/stores/graphHistory.js` | 保持现有 `remove(id)` 的局部删除语义，不新增删除底层项目源码的行为。 |
| `frontend/src/__tests__/graph-history.test.js` | 保留 store 删除回归，并添加 UI 删除回归。 |

## Task 1: 修复并诚实命名单文件质量检查

**Files:**
- Modify: `frontend/src/views/ProjectGraphView.vue:120-136, 454-490, 982-1034`
- Create: `frontend/src/__tests__/project-graph-view.test.js`

- [ ] **Step 1: 写入失败的入口回归测试**

在 `project-graph-view.test.js` mock `useWorkspaceStore`、`useAssessmentStore`、`runProjectPipeline` 与 `window.api.fs.readFile`。挂载页面后设置 `activeFile='src/a.py'`、`profile.target_direction='Python Web 后端'`，确认点击 `[data-test="run-pipeline"]` 后：

```js
expect(ElMessageBox.prompt).toHaveBeenCalledWith(
  expect.stringContaining('当前文件'),
  '当前文件质量检查',
  expect.objectContaining({ inputValue: 'Python Web 后端' }),
)
expect(runProjectPipeline).toHaveBeenCalledWith(expect.objectContaining({
  code: 'def ok(): pass', filename: 'a.py', targetDirection: 'Python Web 后端',
}))
```

另设 `activeFile='README.md'`，断言不调用 API，且提示文本包含“仅支持 Python 文件”。

- [ ] **Step 2: 运行测试确认当前缺陷**

Run:

```powershell
cd frontend
npx vitest run src/__tests__/project-graph-view.test.js
```

Expected: FAIL；当前实现没有 `useAssessmentStore` 的 `store`，运行 Python 入口会抛 `ReferenceError`，并且按钮/弹窗仍称“协同流水线”。

- [ ] **Step 3: 实现最小修复**

在 `ProjectGraphView.vue`：

```js
import { useAssessmentStore } from '@/stores/assessment'

const assessment = useAssessmentStore()
```

将入口改为：

```js
if (!path || !path.toLowerCase().endsWith('.py')) {
  ElMessage.warning('当前文件质量检查仅支持 Python 文件')
  return
}
let direction = assessment.profile?.target_direction || 'Python 项目质量检查'
```

按钮文本、弹窗标题和辅助文案统一为“当前文件质量检查”；说明必须包含“代码审查 → 代码测试 → 修复指引”“只读，不会修改源文件”“当前仅支持 Python 文件”。保留 API 名 `runProjectPipeline` 和结果对话框，避免改变后端契约。

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
cd frontend
npx vitest run src/__tests__/project-graph-view.test.js src/__tests__/project-graph-store.test.js
```

Expected: PASS，且既有项目图谱 store 回归通过。

- [ ] **Step 5: 提交本任务**

```powershell
git add frontend/src/views/ProjectGraphView.vue frontend/src/__tests__/project-graph-view.test.js
git commit -m "fix(project-graph): 修复当前文件质量检查入口"
```

## Task 2: 固化运行历史展示契约

**Files:**
- Modify: `backend/app/agents/run_store.py:169-196`
- Modify: `backend/tests/test_run_store.py:78-151`
- Modify: `frontend/src/ide/RunsPanel.vue:1-125`
- Modify: `frontend/src/__tests__/runs-panel.test.js:28-115`

- [ ] **Step 1: 写入后端失败测试**

在 `test_run_store.py` 保存两条 run：

```python
run_store.save_run(
    session_id="learn-java", mode="interactive",
    request={"target_direction": "Java Spring Boot", "scene": "no_project"},
    summary={"status": "completed"},
)
run_store.save_run(
    session_id="shop-pipeline", mode="pipeline",
    request={"project_name": "shop-service", "scene": "with_project"},
    summary={"status": "completed"},
)
```

断言 `list_runs()` 的每项含：

```python
assert learn["display_title"] == "学习 · Java Spring Boot"
assert learn["scene"] == "no_project"
assert learn["scene_label"] == "无项目技能学习"
assert shop["display_title"] == "shop-service · 项目质量流水线"
assert "request" not in learn
```

- [ ] **Step 2: 运行后端测试确认失败**

Run:

```powershell
pytest backend/tests/test_run_store.py -q
```

Expected: FAIL；现有 `list_runs()` 没有展示字段，前端只能从未返回的 `request` 猜标题。

- [ ] **Step 3: 实现 `run_list_item` 投影**

在 `run_store.py` 增加纯函数：

```python
def _run_list_item(meta: dict, fallback_id: str) -> dict:
    request = meta.get("request") if isinstance(meta.get("request"), dict) else {}
    summary = meta.get("summary") if isinstance(meta.get("summary"), dict) else {}
    scene = request.get("scene") or summary.get("scene") or ""
    target = request.get("target_direction") or summary.get("target_direction") or ""
    project_name = request.get("project_name") or summary.get("project_name") or ""
    is_project = scene == "with_project" or meta.get("mode") == "pipeline"
    title = f"{project_name or target or '未命名项目'} · 项目质量流水线" if is_project else f"学习 · {target or '未命名目标'}"
    return {"session_id": meta.get("session_id", fallback_id), "mode": meta.get("mode"), "display_title": title, "scene": scene, "scene_label": "有项目二次开发" if is_project else "无项目技能学习", "target_direction": target or None, "project_name": project_name or None, "status": summary.get("status") or "completed", "created_at": meta.get("created_at"), "updated_at": meta.get("updated_at"), "summary": summary}
```

让 `list_runs()` 仅返回该投影。不要返回答案、画像、完整 request 或 artifact 内容。

在 `RunsPanel.vue` 删除 `targetOf/sceneOf` 对 `request` 的读取，改为 `r.display_title` 与 `r.scene_label`；详情与重新测评继续使用 `fetchRun()` 的完整记录。将“初次对话”改为“无项目技能学习”，并用 Element Plus 图标或纯文本替代标题中的 Emoji。

- [ ] **Step 4: 用真实 API 形状更新前端测试并运行**

将 `SAMPLE` 与 `SAMPLE2` 改为仅包含 `list_runs()` 的展示字段；在 detail mock 中保留 request。运行：

```powershell
pytest backend/tests/test_run_store.py -q
cd frontend
npx vitest run src/__tests__/runs-panel.test.js src/__tests__/diagnostics-api.test.js
```

Expected: PASS，列表在没有 `request` 时仍显示标题和场景。

- [ ] **Step 5: 提交本任务**

```powershell
git add backend/app/agents/run_store.py backend/tests/test_run_store.py frontend/src/ide/RunsPanel.vue frontend/src/__tests__/runs-panel.test.js
git commit -m "fix(runs): 固化运行历史展示契约"
```

## Task 3: 给图谱历史提供可见的单项删除

**Files:**
- Modify: `frontend/src/views/KnowledgeGraph.vue:12-40, 121-155, 1287-1299`
- Modify: `frontend/src/views/ProjectGraphView.vue:43-72, 1141-1160`
- Modify: `frontend/src/__tests__/graph-history.test.js`
- Create: `frontend/src/__tests__/knowledge-graph-history.test.js`

- [ ] **Step 1: 写入失败的 UI 删除回归**

在新测试中预置一个 learning snapshot，挂载 `KnowledgeGraph.vue`，点击历史条目里的 `[data-test="history-delete-learning:s1"]`，确认：

```js
expect(useGraphHistoryStore().items).toHaveLength(0)
expect(useGraphHistoryStore().learningViewing).toBe(null)
```

在项目图谱历史中使用 `[data-test="history-delete-project:p1"]`，确认只调用 `graphHistory.remove('project:p1')`，不调用文件系统、项目删除 API 或源码删除动作。

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
cd frontend
npx vitest run src/__tests__/graph-history.test.js src/__tests__/knowledge-graph-history.test.js
```

Expected: FAIL；当前页面没有删除控件。

- [ ] **Step 3: 实现删除控件与安全文案**

在两个历史列表项末尾加入 `el-button`，使用 `@click.stop`：

```vue
<el-button text type="danger" size="small"
  :data-test="`history-delete-learning:${h.sessionId}`"
  @click.stop="removeLearningHistory(h)">
  移除
</el-button>
```

实现 `removeLearningHistory/removeProjectHistory`：调用 `ElMessageBox.confirm('仅从本地历史列表移除快照；不会删除当前图谱、项目源码或已累计的学习画像。', '移除历史快照')` 后调用 `graphHistory.remove(h.id)`。项目历史使用同一语义；不要调用后端 project graph 删除接口。

- [ ] **Step 4: 运行历史测试确认通过**

Run:

```powershell
cd frontend
npx vitest run src/__tests__/graph-history.test.js src/__tests__/knowledge-graph-history.test.js src/__tests__/project-graph-store.test.js
```

Expected: PASS；删除回看中的学习快照会退出回看态。

- [ ] **Step 5: 提交本任务**

```powershell
git add frontend/src/views/KnowledgeGraph.vue frontend/src/views/ProjectGraphView.vue frontend/src/__tests__/graph-history.test.js frontend/src/__tests__/knowledge-graph-history.test.js
git commit -m "feat(graph-history): 支持单项移除历史快照"
```

## Task 4: 让 Agent 协同状态如实表达“尚未启动”

**Files:**
- Modify: `frontend/src/composables/useAgentStatus.js:15-230`
- Modify: `frontend/src/components/session/StageAgent.vue:1-145`
- Create: `frontend/src/__tests__/use-agent-status.test.js`
- Modify: `frontend/src/__tests__/stage-agent-collab.test.js`

- [ ] **Step 1: 写入失败的 deferred 状态测试**

先在 `use-agent-status.test.js` 设置：

```js
mockAssessment.hasResults = true
mockAssessment.profile = { theory_level: 2, practical_level: 1, weak_topics: [] }
mockAssessment.knowledgeGraph = { learning_path: [{ node_id: 'PY-001' }] }
mockAssessment.generatedContent = null
mockAssessment.reviewResults = null
mockAssessment.orchestrationLog = ['[10:00] ✅ 学情检测 完成']
```

断言 `agentNodes` 中内容生成和内容审核的状态是 `deferred`，且 `activationHint` 是“生成学习资源后启动”；加入已有 `generatedContent.resources` 时状态回到 `done` 的反向回归。

再在 `stage-agent-collab.test.js` 使用同一测评状态，断言这两个 Agent 的 badge 文案是“生成资源后启动”，而不是“待触发”“失败”或“完成”。

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
cd frontend
npx vitest run src/__tests__/use-agent-status.test.js src/__tests__/stage-agent-collab.test.js
```

Expected: FAIL；当前两个 Agent 都被笼统标为 `idle/待触发`。

- [ ] **Step 3: 实现 `deferred` 状态**

在 `useAgentStatus.js` 中定义：

```js
const resourcePipelineDeferred = computed(() => Boolean(
  store.hasResults && store.profile && store.knowledgeGraph
  && !store.generatedContent?.resources?.length && !store.reviewResults,
))
```

仅当 `content_generator` 或 `reviewer` 当前为 `idle` 且 `resourcePipelineDeferred` 为真时，将状态改为 `deferred` 并返回 `activationHint: '生成学习资源后启动'`。已有资源、审核结果、`running/failed/degraded` 事件优先于该派生状态。

在 `StageAgent.vue` 映射：

```js
deferred: '生成资源后启动'
```

并显示 `agent.activationHint || agent.role`。使用文字状态和 CSS 状态点；不要新增 Emoji 作为正式状态。`pendingCount` 仍包含 `idle/deferred`，但进度文案改为“待后续资源流程启动”。

- [ ] **Step 4: 运行协同测试确认通过**

Run:

```powershell
cd frontend
npx vitest run src/__tests__/use-agent-status.test.js src/__tests__/stage-agent-collab.test.js
```

Expected: PASS；诊断结束后的未启动内容流程不会被表示为卡死。

- [ ] **Step 5: 提交本任务**

```powershell
git add frontend/src/composables/useAgentStatus.js frontend/src/components/session/StageAgent.vue frontend/src/__tests__/stage-agent-collab.test.js
git commit -m "fix(agent-status): 区分延后启动的资源审核阶段"
```

## Task 5: 批次验收与文档同步

**Files:**
- Modify: `docs/项目规划/2026-09-02_画像协同历史与体验升级总方案.md`
- Modify: `docs/superpowers/specs/2026-09-02-project-semantic-graph-design.md`

- [ ] **Step 1: 运行前后端相关回归**

Run:

```powershell
pytest backend/tests/test_run_store.py backend/tests/test_run_delete.py -q
cd frontend
npx vitest run src/__tests__/project-graph-view.test.js src/__tests__/project-graph-store.test.js src/__tests__/runs-panel.test.js src/__tests__/graph-history.test.js src/__tests__/knowledge-graph-history.test.js src/__tests__/stage-agent-collab.test.js
npm run build
```

Expected: 所有指定 pytest/Vitest 测试及前端构建通过。

- [ ] **Step 2: 更新状态与已知边界**

在总方案 P0 清单中标记已完成项；在项目语义图谱设计中保留“当前产品代码图谱仅 Python，Spring Boot 为下一独立纵切”的事实，不能提前宣称 Java 已实现。

- [ ] **Step 3: 提交验收文档**

```powershell
git add docs/项目规划/2026-09-02_画像协同历史与体验升级总方案.md docs/superpowers/specs/2026-09-02-project-semantic-graph-design.md
git commit -m "docs(plan): 记录 P0 项目图谱可信度验收"
```
