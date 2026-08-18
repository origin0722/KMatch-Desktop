# Desktop 开发阶段总览（阶段0–16 + Spec B）

> 从 CLAUDE.md 迁出的历史阶段日志。详细 devlog 见同目录按端分类的日期文件。架构决策见 [../adr/](../adr/)。

## 阶段16 (2026/08/14): 动态建域 — 领域未收录时 LLM 当场构建知识图谱 ✅

用户想学的领域不在 6 域知识库内时的兜底链路（详见 [A_后端/2026-08-14_动态建域.md](A_后端/2026-08-14_动态建域.md) + [../../data/prompts/08_domain_bootstrap_agent.txt](../../data/prompts/08_domain_bootstrap_agent.txt)）：

- **修静默错域**：`target_direction` 原先不参与选点（想学 Java 会静默拿到 PY 基础题）；现 LLM 分类到域注册表（内置 6 域 + 动态域），命中→方向子图出题，未命中→动态建域，LLM/向量皆无→回退旧行为
- **动态建域落库**：[domain_bootstrap.py](../../backend/app/agents/domain_bootstrap.py)（Tavily 检索作事实锚 → LLM 生成 10 节点 DAG + 每节点 2 题 → validate 同套校验 → JSON 真相源/Neo4j/embedding 同通道落库，`source=llm_generated` 打标）；二次同域学习命中复用不重建
- **schema 扩字段**：category 加"动态领域" + 可选 source/domain_label（additionalProperties:false 需显式扩）
- **接线**：/assess interactive miss→同步建域（前端 timeout 300s + loading 文案"构建知识图谱"）；LLM 未配置且 miss→503 明确文案；出题 prompt 去硬编码 Python；demo 选点不动（M5 基线稳定）
- **口径**：动态域事实基准来自 LLM（Tavily 缓解），不纳入 M5 质检指标
- **测试**：504 后端（+16）/ 281 前端（+2）全过


## 阶段0 (6/19): 迁移现有 Vue 前端 + 双场景路由骨架 ✅

## 阶段1 (6/19-20): Electron 壳 + Monaco IDE + TRAE 风格亮暗主题 + IDE 三栏布局 + 学习功能收编 ✅
- 1.5: 收编学习功能进 IDE 侧栏
- 1.6: 三栏布局重构 — 主区多视图 + 右侧 AI 面板
- 1.7: 去顶部 Tab + 修活动栏重复指示 + 空白/黑屏修复
- 1.8: 设计系统重构（--km-* token + Apix 风格暖 Indigo 主题）

## 阶段2 (6/20): AI 助手 — 多模型对话 SSE + 工具调用循环 (read_file/list_directory) + 工作区上下文注入 ✅
- 2.1: 修赛题 3 断点 — S7 Learning 视图挂载主区；S8 Dashboard M5 用真实 learning_report；S9 interactive 测评三阶段闭环

## 阶段3 (6/21): write_file 工具 + 权限审批门 ✅
- 后端抽 `app/agents/code_safety.py`（纯 AST，无 langchain/neo4j 依赖），code_reviewer re-export 兼容
- 新增 `POST /api/chat/safety-check`（.py 才真检，high 阻断/medium 提示）
- chat.js: write_file + pendingApproval 审批门；AssistantPanel.vue 审批卡 UI

## 阶段4 (6/21): 图谱委派工具 + Monaco 符号联动 ✅
- 4a: 三项委派工具（generate_project_graph/code_review/code_test）接入 chat tool 循环，前端驱动，零后端改动；http:request 加 opts.timeoutMs（code_test 180s）
- 4b: Monaco 符号联动 — 新建 stores/projectGraph.js；MonacoEditor revealTarget/activeLine 双向
- 4c: 启发式交互导学模式（赛题(4)②）— chat.js tutorMode + buildSystemPrompt 导学分支；AssistantPanel 开关
- 对题：code_review/code_test 需 Neo4j 在线，generate_project_graph 可离线

## 阶段5 (6/21): PyInstaller 打包 backend sidecar + Windows 安装包 ✅
- S3: backend PyInstaller 打包通（KMatchBackend.spec 修 cipher 废弃参数 + hiddenimport + collect_all）
- config.py 支持 KMATCH_DATA_DIR；运行时验证 /api/health 200 优雅降级
- electron-builder.yml 映射；第一版 NSIS 安装包（239M）
- 瘦身：spec 只收集 langchain_core/openai/langgraph，excludes 排重依赖 → 548M→141M
- **沙箱强化 DockerSandboxExecutor 仍待做**；打包后 code_test 沙箱不可用属已知限制

## 阶段6 (6/22): chat 深度思考收尾 + 消息 chunks 判别联合重构 ✅
- 6a: DeepSeek 深度思考收尾（commit 9ccb4e8）— 删 deepThinking 孤儿状态，统一由 aiSettings.reasoningMode 驱动；http-proxy 保留非 200 错误回传
- 6b: 消息模型重构为 chunks 判别联合（commit 2b69416，借鉴 Apix）— Chunk 判别联合 + 工具状态机；删 role:'tool'；后端契约不变；80 测试过

## 阶段7 (6/22): 学习视图主题收编（Dashboard/KnowledgeGraph/Learning/Assessment）✅
- 阶段1.8 建了 --km-* token，但只 AgentView/Assessment 收编；其余仍用 Element 默认色（"AI-web-template feeling"残留）
- 各视图硬编码色 → token + THEME 镜像（ECharts/G6 canvas 不能读 CSS 变量）；去 emoji-as-icon
- utils/format.js 共享 masteryColor；Redesign-Preserve：只动视觉层，业务逻辑一字未改；80 测试过

## 阶段8 (6/22): 文件监听 Worker + S6 治理 + 项目图谱失效 ✅
- worker_threads + chokidar v4（v5 ESM-only 与 main CJS 冲突）；createWatcherController 纯工厂可单测
- S6 治愈：MainArea code 视图 v-if→v-show 常驻；MonacoEditor externalChanges watcher
- 项目图谱失效（赛题场景二正确性）：projectGraph stale + markStale；AssistantPanel stale alert + 禁用跳转
- 93 测试过（新增 13）；手动 e2e 待跑

## 阶段9 (6/22): 学习会话三合一（答题 + Agent 协同 + 专属图谱）✅
- Assessment + AgentView + 知识图谱三合一成 LearningSession；4 阶段卡（目标→答题→协同→图谱）
- 新增 stores/session.js（activeStage 派生自 assessment，splitView 白名单）；SplitPane 主从分屏
- 双向联动：chat 非导学模式也注入学情画像
- 删除 Assessment.vue/AgentView.vue + 孤儿报告组件 + 4 测试
- 82 测试过；subagent-driven 12 commits，code review Approved

## 阶段10 (6/23): 消息分支（重生成分支）— Apix 借鉴收官 ✅
- 助手消息重生成不覆盖原回复，新建 version，‹n/m› 切换；用户消息编辑不做（YAGNI）
- 线性 versions + trailingAfter（非树形）；任意助手可重生成，后续消息隐藏不删
- **关键**：spanEnd 单索引 → trailingAfter（id 集）。spanEnd 分不清"旧 trailing 隐藏"vs"regen 后新消息显示"，导致"重生末条→追问"静默丢消息
- 94 测试过（新增 12 含 Critical 回归）；subagent-driven 9 commits，code review Approved
- Apix 借鉴三大项（文件监听 Worker / 消息 chunks / 消息分支）全部完成

## 阶段11 (6/24): 聊天框 Apix 化（Spec A — 多厂商 + 模型能力 + Vision + 图片上传 + Anthropic 原生协议）✅
- 借鉴 Apix `llm_adapter.py` / `assistPage.vue`，把聊天框本身做成多厂商可用
- **PR-1 厂商注册表 + customProviders**：PROVIDERS 扩 8 项（+protocol/iconKey/fallbackModels）；`provider='custom:<uuid>'` 值域 + 旧 customBaseUrl 一次性迁移；`/models` 加 protocol 字段（Anthropic 短路硬编码列表）
- **PR-2 模型能力 + reasoning UI**：`services/llm/modelCapabilities.js` 静态表（reasoning/context 按 modelPattern）；`modelReasoningSupport` 四态收敛为 native|prompt-only 单委托；后端 `ChatRequest` 改 `reasoning_mode`+`protocol` + `_build_request_extras` 三态；reasoning radio 三态（auto/fast/deep）+ 不支持模型 deep 灰 + 自动降级 watch
- **PR-3 Anthropic 原生协议**：anthropic SDK + `_get_anthropic_client` lru 缓存；`_split_system` + `_openai_msg_to_anthropic` 消息转换；`_stream_openai`/`_stream_anthropic` 双 stream 发**完全相同 SSE 帧**（前端无感）；`_resolve_client` 拆双协议派发（tuple）
- **PR-4 Vision 探测**：`/probe-vision` endpoint + `vision_cache.json` 原子写 + DELETE 清空；`modelVision` store（dedupe + 三态 hasVision）；切 model 异步起探 + 切 apiKey 清同 baseUrl 缓存；模型 select + 👁/🧠/上下文徽章
- **PR-5 图片上传**：`pendingAttachments` + add/remove/clear（≤5MB×5）；`sendMessage` 多模态 OpenAI 数组 content + `contentTextOf` 数组兼容；📎 按钮 + 拖拽 + 预览条（仅 vision 模型启用）；user 气泡附件缩略图 + ElImageViewer 大图预览；8 厂商 SVG 图标（占位，后续可替换 Apix 官方 logo）
- 23 commits（subagent-driven，每任务 implementer + spec/quality review）；前端 195 + 后端 430 测试全过；最终 cross-task review Approved（修了 I-1 modelReasoningSupport dual-call 不一致）
- **Deferred**：Task 13 Anthropic 端到端手测（需真实 key + 代理 + 桌面 app）；Anthropic 非流式 fallback；多组 customProviders CRUD UI / 清缓存按钮（Spec B）

## 阶段12 (2026/07/19): Spec B 设置页 + Agent 独立 key (Task 1-17 已合并 main a38cd98) ✅
- 设置页主壳 + 锚点导航 (SettingsView/SettingCard)；AI 助手段盘活 aiSettings (厂商/模型/key + 思考模式 + 工具权限 + 记忆 + 清历史)
- Agent 独立 key: 后端 ContextVar per-request llm_overrides (use_llm_overrides) + AgentState 字段 + 5 agent 透传 + 8 路由 (assess/stream/submit/feedback/learning/project + /api/agents/ping) + 前端 agentLlm store + withOverrides 6 注入点 + AgentSettings UI
- 供应商管理: customProviders CRUD + ProviderEditDialog + 视觉批量探测 + 网络代理 UI
- 459 后端 + 223 前端测试全过；feature/settings FF 合并 main
- **Deferred**: Task 18-19 代理主进程落盘 (preload setProxyConfig/restartBackend + sidecar env 注入)；Task 20 全量收尾

## 阶段13 (2026/07/29): 学情报告组件回填（KMatch 源仓借鉴）✅
> 源仓 `D:\Origin_jerry\KMatch` 的 B 端报告/引导组件，Desktop 迁移时只取了 GraphDemo/MarkdownViewer/ProfileRadar，三个高价值组件被内联或丢弃。后端数据已就绪，纯前端补全。逐任务推进。

**借鉴来源对比结论**：Desktop 后端已是 KMatch 超集（多 code_safety/chat.py/agents.py/search.py），故借鉴全部集中在前端可视化/报告组件。

| 任务 | 组件 | 缺口 | 数据就绪 | 落点 |
|:---:|:---|:---|:---|:---|
| T1 | `ScaffoldGuide.vue` | 后端 content_generator 明确生成 5 级渐进式实操指南（"第1级…第5级…首次仅呈现第1级"），但前端把 practice_guide 当扁平 markdown 渲染，逐级揭示教学法 UX 完全没落地 | ✅ content_generator.py prompt 已约定 5 级格式 | StageQuiz feedback 资源区 + Learning 实操指南 tab |
| T2 | `ReviewReport.vue` | 后端 reviewer 产四维度（factual_accuracy 40%/hallucination 30%/logic_consistency 20%/teaching_appropriateness 10% + issues），store 有 reviewResults.dimensions，但 Dashboard 只显示"通过/打回+得分"小卡，四维度明细与打回原因从未展示 | ✅ reviewer.py 键名与组件完全对齐 | Dashboard 审核卡区展开 / 报告区 |
| T3 | `AssessmentReport.vue` | StageQuiz feedback 只显示正确率/理论水平/策略+雷达图+资源，无逐题回顾（对错/正确答案/按节点汇总） | ✅ store.assessment.{questions,answers,per_node} 齐全 | StageQuiz feedback 阶段补"错题回顾" |

**不借鉴（已冗余）**：BlindSpotHeatmap/DifficultyMatchCurve（Dashboard 已有等价 ECharts 内联图）、QuizCard（已被 StageQuiz 取代）、ProjectUpload（Web 上传范式，Desktop 用 IDE 打开文件夹+ProjectGraphView）、LearningPathGraph（Dashboard 用横向卡片流替代；REQUIRES 依赖边丢失属可接受取舍，必要时再评估）。

**移植注意**：源组件用旧 `--color-*`/`--space-*` token + 原生 Element Plus，Desktop 是 `km-surface`/`km-workbench` 设计语言；组件自带 CSS fallback 可直接跑，落地后按需对齐主题 token。

**T1 ScaffoldGuide ✅**：新建 `utils/scaffold.js`（纯函数 `splitScaffoldLevels` + 5 级标题常量）+ `components/ScaffoldGuide.vue`（km-* token 适配，el-collapse 5 级折叠，默认仅展开第 1 级）+ 13 单测；接线 Learning.vue 实操指南 tab + StageQuiz.vue feedback 资源区（practice_guide 走 ScaffoldGuide，余走 MarkdownViewer；顺手修 StageQuiz CT map `practice`->`practice_guide` 死键）。正则较源仓放宽（允许可选 `#`/`*` 前缀，应对 prompt 未强制标题格式）；拆分失败降级整体 MarkdownViewer 不回归。236 测试过 + build 过。

**T2 ReviewReport ✅**：新建 `components/ReviewReport.vue`（verdict-bar + 四维度卡片 grid + 打回原因 alert；km-* token 适配，el-progress 进度色用 hex 常量镜像 Dashboard THEME 保持全看板配色一致）+ 6 单测；接线 Dashboard.vue 新增「④ 内容审核报告」卡（path-card 与 quality-card 之间，v-if="reviewResults"）。维度键名与 reviewer.py 完全对齐（factual_accuracy 40%/hallucination 30%/logic_consistency 20%/teaching_appropriateness 10%），缺省 threshold 85%、缺省 dimensions 0 分兜底。242 测试过 + build 过。

**T3 AssessmentReport ✅**：新建 `components/AssessmentReport.vue`（逐题回顾：对错标记/正确答案/按知识点节点汇总；km-* token 适配）+ 6 单测；接线 StageQuiz.vue feedback 阶段 el-collapse「题目明细与错题回顾」（测评完成后才可见，v-if 时机正确）。数据来自 submitAnswers 返回的 questions/answers/per_node/correct_count/total_count（判分三态 BUG-019/BUG-029 注释明确）。阶段13 全部收官：248 前端 + 471 后端测试过（含阶段14）。

## 阶段14 (2026/07/30-08/02): 联网搜索 + 图谱增强 + 代码梳理 ✅

阶段13 期间连续开发的第二批功能，2026-08-02 统一梳理修复后收尾。赛题呼应：实时联网资源（降幻觉/学情反馈个性化）、学习路径规划、场景二项目图谱可视化。

**F1 联网搜索 (Tavily)**：
- 后端：`utils/web_search.py`（`search_web` + `search_weak_topics`：画像薄弱点最多 3 点 x 2 条 web_link 资源，带 `target_node_id` 溯源；无 key 静默降级）+ `api/search.py`（`POST /api/search/web` 任意 query，key 前端传入优先 / `settings.TAVILY_API_KEY` 兜底，双无 503）+ config/.env.example 加 TAVILY_API_KEY
- 前端：ProvidersSettings「联网搜索」key 配置 UI（localStorage 持久化）；chat.js `web_search` 工具（max_results 钳制 1-8）+ `generate_learning_resources` 透传 tavily_key；learningResources store（url 去重、新结果置顶）；Learning.vue「联网资源」tab（空态引导 + transition-group 入场动画）
- diagnostics feedback 弱知识点联网资源：`FeedbackRequest.tavily_key` + `resources.extend(search_weak_topics(...))`，学习资源模块 web_link 与讲义/实操/测试合并展示

**F2 图谱路径查找**：`PathFinderModal.vue`（选起点/目标 → prereqMap 邻接表 BFS 最短学习路径，同色板，无可达路径空态）；KnowledgeGraph 工具栏「路径查找」按钮触发。呼应赛题"学习路径规划图"。

**F3 项目代码图谱视图（场景二可视化）**：`ProjectGraphView.vue`（462 行）+ backend `project.py` `source_type="files"`（读工作区全部 .py 拼 sources 解析）+ chat.js `generate_project_graph` 目录解析分支 + MainArea/sidebar 视图注册 + AssistantPanel「看图谱」快捷入口。

**F4 2026-08-02 梳理修复**（双 agent 审查 + 手工核对）：
- chat.js `web_search` 结果字段 bug：`x.content`→`x.snippet`（后端返回键是 snippet，原恒 undefined → 联网资源摘要全空）
- SettingsView `boundClientRect`→`boundingClientRect` 拼写回归（IntersectionObserver 排序 TypeError，锚点高亮失效）
- KnowledgeGraph tooltip 死代码清理（tooltipData/labelOf/.node-tooltip CSS 从未使用）+ 详情面板补「关键点」展示（useGraphData 的 key_points 字段原先无人消费，persona 进阶/高级设计意图落地）
- 补 `test_web_search.py` 12 单测（search_web 解析/降级 + search_weak_topics 溯源 + /api/search/web 503/422/200/key 优先级/max_results 边界）
- http-proxy body 防双重序列化修复（axios adapter 场景 422）

**测试**：248 前端 + 471 后端（459+12）全过。已知限制：联网资源 store 纯内存不持久化（重启清空，UI 无清空入口）；Tavily 搜索词硬编码 `Python {name} 教程`（平台定位 Python，可接受）。

## 阶段15 (2026/08/10-08/14): M5 质检升级 + Codex 化 UI 收官 + 反馈快模型 + 后端去重 ✅

赛题冲刺批：M5 三指标从"作者自评"升级为独立裁判双口径（经得起评委追问），同时完成 UI Codex 化收尾与性能/代码质量打磨。

**M1 M5 质检升级（独立裁判 LLM-as-Judge）**：
- 新增 [quality_judge.py](../../backend/app/agents/quality_judge.py)（逐资源判定 grounded/hallucinated/unverifiable，只拿资源内容+图谱事实，不拿生成过程/reviewer 结论）+ [quality_metrics.py](../../backend/app/agents/quality_metrics.py) 双口径指标（自评 + 独立裁判双列）
- 裁判 LLM 经 `.env JUDGE_LLM_*` 独立配置（可异源）；`--judge-only` 只跑裁判；三批迭代收官（标准修正 + 真实错误证据链）
- 扩样本：3 画像 → 10 画像（`data/user_profiles/`），单领域 → ML 第二领域；终报 10 画像 × 83 资源：裁判幻觉率 2.4%（达标 <5%，主口径）/ 适配率 94% / 覆盖率 100%；见 [../质量与验收/质量检测报告.md](../质量与验收/质量检测报告.md) + [../质量与验收/M5质量检测方法论升级.md](../质量与验收/M5质量检测方法论升级.md)

**M2 图谱扩域**：4 新域 100 节点（DA/DB/EN/WD 各 25 + ML 30）→ 222 节点 6 域（`data/knowledge_base/nodes/` 11 文件）；内容生成丰富度升级（针对性反馈产物落学习资源视图：知识点入 generatedContent + 网址入联网资源 tab + 自动开分屏）。

**M3 Codex 化 UI V2 收官**（5 提交，详见 [B_前端/2026-08-14_Codex化UI收官.md](B_前端/2026-08-14_Codex化UI收官.md)）：
- T1 删 ActivityBar.vue 死代码（NavSidebar 完全替代）；T2 设置页「通用」段重新引导入口（onboardingActive 收口 sidebar store）
- T3 图谱详情侧栏浮层 → split 分栏（flex 推挤画布，删 panelGap 避让，折叠延迟 220ms 重建）
- T4 AI 助手双形态：主区 `chat` 视图（760px 居中 + 建议 chip，`variant="wide"` 纯样式层）+ 右侧分栏共存，chat 视图下侧栏不重复挂载
- T5 引导收尾：走完自动落 chat 视图（跳过保持 code）+ Key 过短软提示不阻断

**M4 反馈快模型**（详见 [B_前端/2026-08-14_反馈快模型落地.md](B_前端/2026-08-14_反馈快模型落地.md)）：agentLlm `feedbackModel`（默认 deepseek-v4-flash）+ `buildFeedbackOverrides` 三态 + `withFeedbackOverrides` 注入；纯前端（后端 `use_llm_overrides` 部分覆写逐字段回退）；针对性反馈 22s → ~8s，主引擎模型不变。

**M5 后端去重 R1-R4**（详见 [A_后端/2026-08-14_后端重构R1-R4.md](A_后端/2026-08-14_后端重构R1-R4.md)）：`@with_state_overrides` 装饰器 + `safe_llm_call`（llm.py，3 agent 节点/worker 复用）；`knowledge_context.py` 共享（code_reviewer/code_tester）；graph_controller `_empty_kg_result`；`CONTENT_GEN_CONCURRENCY` 入 settings。净减 30 行，行为零变化。

**M6 学习会话修复**：阶段② loading 文案按 phase 区分（出题不再误称"生成学习内容"，判分期遮罩补上修白屏）+ Agent 协同面板重做 + 针对性反馈超时纵深修复（主进程默认 120s + chat 委派 150s）+ AI 厂商模型名线上核实更新（新增智谱 GLM）。

**测试**：279 前端 + 488 后端全过。已知 flaky：chat-attachments 满负载并发偶发超时（隔离 7/7 过）。

## 已知待修
- Apix 审查 S1–S9 全部已修（见各阶段 + ADR-0005）
- 沙箱强化已落地（DockerSandboxExecutor + SANDBOX_MODE auto/subprocess/docker，实现 backend/app/agents/sandbox.py）
- F 系列脆弱点修复 + C1–C4 解耦已合并 main（feature/regularization 已并入；见 [../架构与设计/重构方案_解耦.md](../架构与设计/重构方案_解耦.md) + ADR-0006）
- Spec B Task 18-19 代理主进程落盘未接线（UI 已就绪，preload/IPC/env 注入待做）

## 规范化（2026-06-23，feature/regularization 分支）

文档/流程规范化，不改业务代码：
- 领域文档：`CONTEXT.md` + `docs/adr/0001..0005`
- 架构梳理：`docs/架构与设计/ARCHITECTURE.md`（进程拓扑/6 数据流/状态更新流）+ `docs/架构与设计/重构方案_解耦.md`（C1–C4 + F1–F15 决策表）
- 文档重构：README 重写为 Desktop 版、旧 Web 文档归档 `docs/legacy/`、CLAUDE.md 瘦身、devlog 索引补全
- 用例注释：6 裸 + 4 部分前端测试补场景注释（94 测试全过）
- Skills：装 Matt Pocock 中文版 skills 到 `.claude/skills/`；建 GitHub triage + 分类 label
- **bug/任务转 GitHub Issues**（24 条）：#1 赛题锚点 / #2 总览 / #3–#6 C1–C4 解耦 / #7–#22 F1–F15 bug+refactor / #23–#24 docs。后续按 issue 优先级 TDD 推进。
