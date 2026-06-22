# B 端任务:SSE 流式测评对接

> 写给 B 端(前端)。A 端新增了 SSE 流式测评端点,解决 demo 模式全流程 2-4 分钟超前端 60s 超时问题。B 端需把 demo 模式的测评请求改用 SSE 端点,实时展示进度。

## 背景

demo 模式跑完整工作流(学情检测→画像审核→图谱→内容生成→内容审核)需 **2-4 分钟**(13-15 次 LLM 调用)。原 `POST /api/diagnostics/assess` 是阻塞调用,前端 axios 60s 超时必然失败。

A 端新增 `POST /api/diagnostics/assess/stream`(SSE),逐步推送节点进度,前端实时显示"学情检测中→生成内容中→...",跑完推最终结果。**不再超时**。

## SSE 端点

```
POST /api/diagnostics/assess/stream
Content-Type: application/json
Body: 同 /assess (target_direction/mode/scene/max_retries)
  - mode 必须为 "demo" (interactive 会被拒 400, 用原 /assess)
Response: text/event-stream (SSE)
```

### 事件流

```
event: start
data: {"session_id": "...", "target_direction": "..."}

event: progress
data: {"node": "diagnostics", "message": "学情检测中（出题→自动作答→判分）", "log_tail": ["📖 取得候选节点 8 个", ...]}

event: progress
data: {"node": "reviewer", "message": "审核中（画像/内容审核）", "log_tail": [...]}

event: progress
data: {"node": "graph_controller", "message": "组装个性化学习路径中", "log_tail": [...]}

event: progress
data: {"node": "content_generator", "message": "生成学习内容中（讲义/实操/测试题，最耗时）", "log_tail": [...]}

event: progress
data: {"node": "finish", "message": "组装可视化报告", "log_tail": [...]}

event: done
data: {完整 AssessResponse: session_id/profile/review_results/assessment/knowledge_graph/generated_content/learning_report/orchestration_log}

(异常时)
event: error
data: {"detail": "测评流程失败: ..."}
```

### 节点进度文案映射(后端已内置,前端直接展示 message)

| node | message |
|:--|:--|
| diagnostics | 学情检测中（出题→自动作答→判分） |
| reviewer | 审核中（画像/内容审核） |
| graph_controller | 组装个性化学习路径中 |
| content_generator | 生成学习内容中（讲义/实操/测试题，最耗时） |
| finish | 组装可视化报告 |

## 前端对接代码示例

SSE 用 POST + JSON body,**不能用 EventSource**(它只支持 GET)。用 `fetch` + `ReadableStream` 手动解析 SSE:

```javascript
// stores/assessment.js 或 api 层
async function startAssessmentStream(payload, { onProgress, onDone, onError }) {
  const resp = await fetch('/api/diagnostics/assess/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) { onError(await resp.text()); return }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // SSE 事件以 \n\n 分隔
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() // 最后一块可能不完整, 留 buffer
    for (const block of blocks) {
      const event = block.match(/^event: (.+)$/m)?.[1]
      const dataStr = block.match(/^data: (.+)$/m)?.[1]
      if (!event || !dataStr) continue
      const data = JSON.parse(dataStr)
      if (event === 'progress') onProgress(data)
      else if (event === 'done') onDone(data)
      else if (event === 'error') onError(data.detail)
      // start 事件可忽略或用于初始化
    }
  }
}

// 调用
startAssessmentStream(
  { targetDirection, mode: 'demo', scene, maxRetries: 3 },
  {
    onProgress: (p) => {
      // 更新 store: store.currentStep = p.message
      // 可选展示 p.log_tail (节点日志尾部)
    },
    onDone: (result) => {
      // result 即原 AssessResponse, 同步给 store.hasResults=true
      store.profile = result.profile
      store.generatedContent = result.generated_content
      // ...
    },
    onError: (detail) => ElMessage.error(`测评失败: ${detail}`),
  }
)
```

## UI 建议

测评进行中(原 Loading 卡片 `Assessment.vue:88`)改造:
- 用 `store.currentStep` 显示当前节点文案(从 `onProgress` 的 `message` 取)
- 可加一个步骤进度条:学情检测 ✓ → 画像审核 ✓ → 图谱组装 ✓ → 内容生成(进行中) → 内容审核
- 内容生成阶段最久(2 分钟),文案明确"最耗时",避免用户以为卡死
- `log_tail` 可选折叠展示(调试用,普通用户可隐藏)

## interactive 模式不变

interactive 模式(用户自己答题)仍用原 `POST /api/diagnostics/assess`(出题快,2-3 次 LLM,10 秒内返回,无需流式)。SSE 仅 demo 模式用。

## 注意

- SSE 连接保持期间不要设 axios 超时(用 fetch 直连,无 60s 限制)
- 后端 `StreamingResponse` 已设 `Cache-Control: no-cache`,代理不缓冲
- 若用 nginx 反代(生产),需加 `proxy_buffering off`(后端已设 `X-Accel-Buffering: no`)

## 验证

1. demo 模式点"开始测评" → 应实时看到"学情检测中→审核中→生成内容中→..."逐步更新
2. 全程不再 60s 超时报错
3. 跑完(done 事件)→ 结果区正常展示画像/资源/报告(同原 assess 结果)
4. 后端异常 → error 事件 → 前端提示
