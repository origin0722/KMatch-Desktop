# KMatch-Desktop IDE 外壳与 AI 控制中心设计

> 日期: 2026-06-21  
> 范围: Electron + Vue 桌面 IDE 外壳、顶部自定义菜单、AI 设置界面、AI 助手交互控制  
> 状态: 设计确认稿

## 1. 背景与目标

KMatch-Desktop 当前已经具备 Electron 桌面壳、Monaco 编辑器、学习视图收编、AI 助手、工具调用、写文件审批门、图谱委派工具和启发式导学模式。下一步需要把界面从“功能已接入”提升到“可演示、可理解、可配置”的桌面 IDE 体验。

本设计聚焦第一轮前端体验升级：

1. 优化 IDE 外壳质感：标题栏、活动栏、文件树、状态栏统一视觉语言。
2. 替换 Electron 默认 `Window / Help` 菜单：隐藏原生菜单，改为 KMatch 自定义标题栏菜单。
3. 新增 AI 设置界面：集中管理模型连接、网络代理、工具权限、记忆卡和思考模式。
4. 在 AI 助手交互区暴露轻量控制：导学模式、深度思考/思考模式、当前模型摘要。

本轮不重做 Assessment、Learning、KnowledgeGraph、Dashboard 等业务视图内部页面，也不强行迁移 AI 后端架构。

## 2. 当前诊断

### 2.1 Electron 外壳

- 主进程当前没有设置应用菜单，Windows 会显示默认 `Window / Help` 等原生菜单。
- 渲染层已有自定义标题栏，但主要用于显示品牌、工作区名和一句提示，没有命令入口。
- 默认菜单与自定义标题栏并存，会削弱桌面应用完整度。

### 2.2 前端 IDE 布局

- `Workspace.vue` 承担三段式外壳：标题栏、主体、状态栏。
- `ActivityBar.vue` 负责主视图切换，已经是单一指示模型。
- `MainArea.vue` 负责代码区和学习/图谱/看板视图装载。
- `FileExplorer.vue`、`StatusBar.vue` 已具备基本功能，但视觉层级和交互反馈仍偏基础。

### 2.3 AI 助手

- `chat.js` 已支持多供应商、模型列表、API Key、工具调用、写文件审批门、图谱委派、导学模式。
- `AssistantPanel.vue` 已经较复杂，继续塞入代理、权限、记忆等设置会让聊天区拥挤。
- 当前只有 `write_file` 有审批门，其他工具缺少可视化权限矩阵。
- 已有 `msg.think` 展示能力，适合扩展为“思考模式”控制。

## 3. 总体设计

第一轮升级命名为 **AI 控制中心外壳升级**，包含两层：

1. **外壳层**：自定义标题栏菜单、隐藏原生菜单、活动栏/文件树/状态栏视觉统一。
2. **AI 控制层**：新增 AI 设置视图，集中配置模型、代理、权限、记忆、思考模式。

推荐信息架构：

```text
KMatch·知链   项目 ▾   学习 ▾   工具 ▾   AI 设置 ▾   帮助 ▾      当前工作区 / 后端状态
```

## 4. 顶部自定义菜单

### 4.1 主进程行为

Electron 主进程隐藏默认应用菜单，避免默认 `Window / Help` 出现。Windows/Linux 使用自定义标题栏承载应用命令。

### 4.2 渲染层菜单结构

标题栏左侧保留品牌，品牌右侧新增菜单组：

#### 项目

- 打开项目文件夹
- 刷新文件树
- 回到代码视图

#### 学习

- 答题测评
- 知识图谱
- 学习资源
- Agent 协同
- 数据看板

#### 工具

- 显示/隐藏 AI 助手
- 切换主题
- 打开开发者工具

#### AI 设置

- 模型与连接
- 网络代理
- 工具权限
- 记忆设置
- 思考模式

#### 帮助

- 后端与 Neo4j 启动提示
- 关于 KMatch·知链
- 项目文档入口

### 4.3 交互规则

- 菜单按钮位于可点击区域，必须设置 `-webkit-app-region: no-drag`。
- 空白标题栏区域保持可拖拽。
- 菜单项点击后执行已有 store 行为，例如 `sidebar.setView()`、`workspace.openProject()`、`theme.toggle()`。
- 菜单项使用当前设计 token，不引入新 UI 框架。

## 5. IDE 外壳视觉优化

### 5.1 视觉方向

采用“克制的桌面 IDE + 教学平台品牌感”：

- 不做强营销风格；
- 不使用大面积 AI 渐变；
- 保留暖 Indigo 品牌色；
- 加强层级、边界、状态反馈；
- 让外壳更像完整桌面产品。

### 5.2 标题栏

- 高度保持紧凑，避免占用编辑空间。
- 菜单按钮使用低饱和文本和 hover 背景。
- 当前工作区居中或靠右展示，附带文件夹图标。
- 后端状态可在标题栏右侧或状态栏右侧展示，但不重复堆叠。

### 5.3 活动栏

- 保留当前 48px 宽度。
- 增强 active 状态：左侧指示条、轻微背景、品牌色图标。
- hover/pressed 使用统一动画曲线。
- AI 助手和主题按钮继续位于底部区域。

### 5.4 文件树

- 标题区与菜单风格统一。
- 文件/目录 hover 和 active 状态更清楚。
- dirty 状态保持小点，但颜色与品牌色统一。
- 暂不做折叠树重构，避免扩大范围。

### 5.5 状态栏

- 保持 24px 高度。
- 后端状态、当前文件、未保存提示保留。
- 主题切换入口可逐步迁移到菜单/AI 设置，状态栏保留摘要即可。

## 6. AI 设置界面

### 6.1 入口形态

新增 `AISettings`，优先作为主区视图或右侧抽屉。第一轮建议使用主区视图，原因：

- 与现有 `MainArea.vue` 视图模型一致；
- 方便通过 ActivityBar 或顶部菜单进入；
- 空间足够容纳分组表单和记忆卡。

可在 `sidebar` 中新增 `ai-settings` 视图，或只通过标题栏菜单打开。推荐新增视图，便于状态一致和后续导航。

### 6.2 页面结构

```text
AI 设置
├─ 模型与连接
├─ 网络代理
├─ 工具权限
├─ 记忆设置
└─ 思考模式
```

页面采用左侧分组导航 + 右侧内容，或卡片分组纵向布局。第一轮推荐卡片分组纵向布局，实现成本低、适合当前 Element Plus 风格。

## 7. 模型与连接

迁移或复用当前 AssistantPanel 中的供应商、模型、API Key、Base URL 设置。

字段：

- 供应商：DeepSeek / OpenAI / Ollama / 自定义
- 模型：从 `/api/chat/models` 拉取或使用 fallback 列表
- API Key
- 自定义 Base URL
- 连接测试按钮

聊天面板底部只保留简短摘要：当前供应商、模型、API Key 状态和设置入口。

## 8. 网络代理

### 8.1 第一轮范围

先实现前端配置 UI 与持久化，不强行让后端代理立即生效。

字段：

- 启用代理
- 类型：HTTP / HTTPS / SOCKS
- 地址：例如 `http://127.0.0.1:7890`
- 生效范围：全部供应商 / 当前供应商 / 仅自定义供应商

### 8.2 生效说明

当前聊天请求链路为：

```text
Renderer → Electron IPC HTTP Proxy → FastAPI /api/chat/completions → OpenAI 兼容模型服务
```

因此代理真正生效需要后端读取代理配置并传递给 HTTP/LLM 客户端。第一轮只预留配置与 UI，第二轮在后端实现。

## 9. 工具权限矩阵

### 9.1 权限对象

对现有工具建立权限配置：

| 工具 | 默认策略 | 说明 |
|---|---|---|
| `read_file` | allow | 读取工作区文件 |
| `list_directory` | allow | 列目录 |
| `write_file` | ask | 写文件，继续保留安全预检 |
| `generate_project_graph` | allow | 离线解析代码图谱 |
| `code_review` | ask | 可能消耗 LLM 与 Neo4j |
| `code_test` | ask | 可能耗时并执行测试 |

策略：

- `allow`：自动允许；
- `ask`：执行前询问；
- `deny`：禁用，不向模型暴露或执行时拒绝。

### 9.2 执行规则

- 构建工具说明时可根据权限过滤 `deny` 工具，减少模型误用。
- 对 `ask` 工具，执行前弹出确认卡。
- `write_file` 的既有审批门保留，并作为 `ask` 的特殊强化版本。

## 10. 记忆设置与记忆卡

### 10.1 记忆类型

第一轮采用本地记忆卡，而不是直接接 Claude Managed Agents Memory Store。

原因：

- 当前后端是 OpenAI 兼容聊天接口；
- 桌面应用本地记忆更符合隐私和离线使用；
- 后续可再映射到 Claude memory tool、Managed Agents memory store 或本地数据库。

记忆类型：

1. **用户偏好**：语言、解释风格、代码输出偏好、主题偏好。
2. **学习画像**：理论水平、实践水平、薄弱知识点、最近学习路径。
3. **项目上下文**：项目目标、运行命令、架构约定、已确认决策。

### 10.2 记忆卡字段

每张记忆卡包含：

- `id`
- `type`: preference / learning / project
- `title`
- `content`
- `source`: manual / assessment / system
- `enabled`
- `createdAt`
- `updatedAt`

UI 操作：

- 新增
- 编辑
- 启用/禁用
- 删除

### 10.3 注入规则

发送消息时，将启用记忆注入 system prompt：

```text
## 用户记忆
- 用户偏好: 喜欢中文解释，先讲思路再给代码
- 学习画像: 异常处理、文件 IO 较薄弱
- 项目上下文: 当前项目是 Electron + Vue 桌面 IDE
```

为避免 prompt 过长，第一轮限制最多注入 10 条启用记忆，每条限制长度。

## 11. 思考模式 / 深度思考按钮

### 11.1 是否加入

建议加入，但不做成“所有模型通用的强开 thinking 参数”。应设计为模型能力自适应的 **思考模式**。

原因：

- 不同模型和供应商对 reasoning/thinking 参数支持不同；
- 当前项目使用 OpenAI 兼容接口，不能默认发送 Claude 原生 `thinking` 参数；
- 现有 UI 已有 `msg.think` 展示能力，可承接 reasoning 内容。

### 11.2 UI 形态

在 AI 助手输入区附近保留轻量按钮：

```text
[导学] [思考: 自动] [工具]
```

或在设置页中提供完整配置：

- 自动
- 快速
- 深度

聊天区只显示当前模式摘要。

### 11.3 模式语义

| 模式 | 行为 |
|---|---|
| 自动 | 默认，根据模型和任务类型决定 |
| 快速 | 不显式要求深度推理，适合短问答 |
| 深度 | 对支持模型启用 reasoning/thinking，未知模型用 prompt 降级 |

### 11.4 能力适配

第一轮使用静态能力表：

- `deepseek-reasoner`：支持 reasoning，推荐深度模式；
- `deepseek-v4-pro` / `deepseek-v3`：普通模式；
- `claude-opus-4-8` / `claude-opus-4-7` / `claude-opus-4-6` / `claude-fable-5`：支持 adaptive thinking / effort，但只有后续接 Claude 原生 API 时才能发送原生参数；
- `ollama` / `custom`：能力未知，默认降级为 prompt 提示。

### 11.5 第一轮生效方式

- 保存 `reasoningMode: auto | fast | deep`。
- `deep` 模式下，如果当前供应商是 DeepSeek 且模型列表包含 `deepseek-reasoner`，提示或自动切换到 `deepseek-reasoner`。
- 对未知能力模型，在 system prompt 增加简短提示：
  - “请更仔细地分析问题，先内部推理，再给出简洁结论。”
- 不在第一轮强行发送 Claude 原生 `thinking` 参数，避免 OpenAI 兼容后端报错。

## 12. 状态与数据存储

新增或扩展 Pinia store，建议命名 `aiSettings`，负责：

- 模型连接配置；
- 代理配置；
- 工具权限；
- 记忆卡；
- 思考模式。

也可以先扩展 `chat.js`，但长期看 `chat.js` 已经承担太多职责，建议新建 store，再由 `chat.js` 读取设置。

持久化第一轮使用 `localStorage`，后续可升级为 Electron 本地配置文件。

## 13. 与现有代码的集成点

### 13.1 `Workspace.vue`

- 增加自定义菜单组件。
- 标题栏菜单与当前工作区信息共存。

### 13.2 `MainArea.vue`

- 增加 `AISettings` 视图装载。

### 13.3 `sidebar.js`

- 增加 `ai-settings` 视图项，或只暴露 `setView('ai-settings')`。

### 13.4 `AssistantPanel.vue`

- 移除或弱化底部 API Key 设置入口，改为“打开 AI 设置”。
- 保留导学按钮。
- 增加思考模式轻量按钮或摘要。

### 13.5 `chat.js`

- 读取工具权限，过滤或拦截工具调用。
- 读取启用记忆并注入 prompt。
- 读取思考模式并调整 prompt / 模型建议。

### 13.6 Electron 主进程

- 隐藏默认原生菜单。
- 如需开发者工具菜单项，可通过 IPC 暴露或在 preload 中已有能力基础上添加安全入口。

## 14. 分阶段实施计划建议

### 第一批：外壳与入口

- 隐藏 Electron 默认菜单。
- 新增自定义标题栏菜单。
- 新增 AI 设置入口。
- ActivityBar、TitleBar、StatusBar、FileExplorer 小幅视觉统一。

### 第二批：AI 设置 UI 与本地状态

- 新建 `AISettings.vue`。
- 新建 `stores/aiSettings.js`。
- 实现模型连接、代理、权限、记忆、思考模式 UI。
- 持久化到 localStorage。

### 第三批：设置影响聊天

- 权限矩阵影响工具暴露与执行。
- 记忆卡注入 system prompt。
- 思考模式影响 prompt 和 DeepSeek reasoner 选择。
- AssistantPanel 显示当前模式摘要。

### 第四批：后端增强

- 后端支持代理配置。
- 模型能力探测。
- Claude 原生 thinking/effort 参数适配。
- 记忆持久化升级为本地文件/数据库或 Managed Agents memory store。

## 15. 验收标准

### UI 验收

- 默认 `Window / Help` 原生菜单不再出现。
- 标题栏有 KMatch 风格自定义菜单。
- 菜单能跳转项目、学习、工具和 AI 设置。
- AI 设置页面结构清晰，配置项分组明确。
- AI 助手输入区不拥挤，只保留高频控制。

### 功能验收

- 模型/API 设置仍可用。
- 工具权限配置可持久化。
- 记忆卡可新增、编辑、启用、禁用、删除。
- 启用记忆能影响后续 AI prompt。
- 深度思考模式不会导致不支持模型请求失败。

### 非目标

- 不要求第一轮代理真实生效到后端。
- 不要求第一轮支持 Claude 原生 thinking 参数。
- 不要求第一轮实现云端/Managed Agents 记忆。
- 不重做学习业务页面内部 UI。

## 16. 风险与控制

- **范围膨胀**：AI 设置项较多，必须分批实现，先 UI + 本地配置，再接聊天，再接后端。
- **模型参数兼容性**：不同供应商 reasoning 参数不同，第一轮只做 prompt 降级和 DeepSeek reasoner 适配。
- **隐私风险**：记忆卡可能包含用户信息，默认本地保存，明确提供删除/禁用。
- **权限绕过**：工具权限必须在执行工具前检查，而不只是 UI 上隐藏。
- **菜单拖拽冲突**：标题栏菜单必须使用 no-drag 区域。

## 17. AnySearch 后续接入

AnySearch 作为专业领域检索 Agent 工具的候选, 仅通过后端环境变量 `ANYSEARCH_API_KEY` 接入, 前端只暴露权限开关。详细见 `docs/superpowers/specs/2026-06-21-anysearch-agent-tool-design.md`。

本仓库不保存任何 AnySearch key 明文。如用户曾在对话中泄露 key, 必须在控制台轮换。
