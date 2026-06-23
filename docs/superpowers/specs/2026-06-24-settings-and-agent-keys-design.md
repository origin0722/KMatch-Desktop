# Spec B — 设置页（Apix 线性式 + 锚点）+ Agent 学习引擎独立 key + 盘活孤儿 store

**日期**：2026-06-24
**作者**：origin0722
**借鉴来源**：[Apix](https://github.com/JJJJSTIYYYY/Apix) — `settingPage.vue` / `ai_configuration.js` / 后端 set_proxy / clear_vision_cache
**前置**：Spec A（[2026-06-24-llm-providers-design.md](2026-06-24-llm-providers-design.md)）已 merge

> 三 spec 中的第二个。
>
> - **Spec A**（已写）：聊天框 Apix 化
> - **Spec B（本文件）**：设置页 + Agent 独立 key + 盘活孤儿 store
> - **Spec C**（推迟）：联网搜索 + 资源时效性

---

## 1. 背景与目标

赛题 XH-202630 要求"多智能体协同 + 个性化学习资源生成"，但当前后端 7 个 agent（diagnostics/content_generator/reviewer/code_reviewer/code_tester/orchestrator/graph_controller）全部通过 [backend/app/agents/llm.py:32-37](backend/app/agents/llm.py#L32-L37) 用 `.env` 里硬编码的 `LLM_API_KEY`，用户无法在 UI 上指定 Agent 用谁的 key。

此外 [aiSettings.js](frontend/src/stores/aiSettings.js) 里 `toolPermissions`、`memories`、`proxy` 三个 store 字段**有完整数据结构但无 UI**（孤儿）。

Spec A 落地后聊天框已经能用任意厂商 key 对话；Spec B 把整个"任意模型可配置"上升到产品形态：**一个 Apix 线性式设置页 + 三个 Tab（AI 助手 / Agent 学习引擎 / 供应商管理），盘活所有孤儿 store**。

### 用户故事

- 「我从活动栏底部点齿轮 → 进设置页 → AI 助手段、Agent 学习引擎段、供应商管理段一页能滚完。」
- 「Agent 学习引擎能填我自己的 DeepSeek key，跟 AI 助手用 Claude 各跑各的。」
- 「我在'供应商管理'里新建 OpenRouter / 公司内部代理 / 个人 302.ai 三个自定义厂商，各自模型列表+key 独立。」
- 「我能在设置里看到 read_file/write_file 等工具权限，把 write_file 改 ask 或 deny。」
- 「我能在设置里加几条个人偏好记忆（"我用 Python 3.13"、"喜欢简洁注释"），AI 对话时自动带上。」

---

## 2. 范围与不在范围

### 范围

- 设置视图：MainArea 加 `settings` 视图分支；sidebar `activeView` 扩 `'settings'`；TitlebarMenu 加菜单项；ActivityBar 底部加齿轮 icon
- 设置页主体：Apix 线性式（长滚动 + `group-divider` 分段）+ 粘性锚点导航
- **Tab 1 AI 助手**：聚合 Spec A 已落地的厂商/模型/key 配置完整表单；新增 toolPermissions 三态切换、memories CRUD、清除聊天历史
- **Tab 2 Agent 学习引擎**：开关 + 独立 key/baseUrl/model；"测试连接"按钮；前端 axios interceptor 注入 `llm_overrides`；后端 7 agent 透传到 `get_chat_model(overrides=)`
- **Tab 3 供应商管理**：customProviders 多组 CRUD；自动获取模型；批量 vision 探测；清 vision 缓存；网络代理设置
- Agent 端**只支持 OpenAI 兼容协议**，用户选 Anthropic 时弹 toast 提示

### 不在范围

- 外观 / 主题 Tab（KMatch 已有 themeStore + 顶栏切换，不重复做）
- 快捷键 Tab（暂无键位需要配置）
- 关于 Tab（版本号已在 TitlebarMenu 显示）
- Anthropic SDK 接入 Agent 调用链（推到 Spec D 或更后期）
- 联网搜索（Spec C）
- API Key 加密存储

---

## 3. 设计

### §1 设置视图装载

#### 1.1 sidebar store 扩字段

[frontend/src/stores/sidebar.js](frontend/src/stores/sidebar.js) 的 `activeView` 已有 `'code'/'learning-session'/'graph'/'learning'/'dashboard'`，扩 `'settings'`：

```js
const activeView = ref('code')   // 已有
function setView(id) { activeView.value = id }   // 已有, 自动复用
```

#### 1.2 入口

**ActivityBar 底部齿轮**（仿 VS Code 左下角）：

[frontend/src/ide/ActivityBar.vue](frontend/src/ide/ActivityBar.vue) 在已有视图按钮下方加一个分隔 + 底部按钮组：

```vue
<!-- 顶部: 现有视图按钮 (code/graph/...) -->
<div class="ab-top">...</div>

<!-- 底部: 设置 (单一指示模型沿用) -->
<div class="ab-bottom">
  <el-button
    :class="{ active: sidebar.activeView === 'settings' }"
    text size="large"
    @click="sidebar.setView('settings')"
    title="设置"
  >
    <el-icon :size="20"><Setting /></el-icon>
  </el-button>
</div>
```

**TitlebarMenu 菜单项**：

[frontend/src/ide/TitlebarMenu.vue](frontend/src/ide/TitlebarMenu.vue) 加一项 emit `'open-settings'`，App.vue 或 Workspace.vue 监听后调 `sidebar.setView('settings')`。

#### 1.3 MainArea 路由

[frontend/src/ide/MainArea.vue:19-22](frontend/src/ide/MainArea.vue#L19-L22) v-if 链加分支：

```vue
<SettingsView v-if="sidebar.activeView === 'settings'" />
<LearningSession v-else-if="sidebar.activeView === 'learning-session'" />
<KnowledgeGraph v-else-if="sidebar.activeView === 'graph'" />
...
```

`SettingsView` 是本 spec 的主组件，文件 [frontend/src/ide/settings/SettingsView.vue](frontend/src/ide/settings/SettingsView.vue)。

---

### §2 设置页主体（Apix 线性式 + 锚点）

#### 2.1 总体布局

```text
┌───────────────────────────────────────────────────┐
│ SettingsView                                       │
├─────────────────────────────────┬─────────────────┤
│ 主内容区 (overflow-y: auto)      │ 锚点侧栏(sticky) │
│                                  │                  │
│ ## §1 AI 助手                    │ ● AI 助手        │
│   - 厂商/模型/key                │ ○ Agent 学习引擎 │
│   - 思考模式                     │ ○ 供应商管理     │
│   - 工具权限                     │                  │
│   - 个人记忆                     │                  │
│   - 清除聊天历史                 │                  │
│                                  │                  │
│ ## §2 Agent 学习引擎              │                  │
│   - 启用独立 key 开关             │                  │
│   - key/baseUrl/model            │                  │
│   - 测试连接                     │                  │
│                                  │                  │
│ ## §3 供应商管理                  │                  │
│   - 自定义厂商列表 (CRUD)         │                  │
│   - 批量 vision / 清缓存          │                  │
│   - 网络代理                     │                  │
│                                  │                  │
└─────────────────────────────────┴─────────────────┘
```

[frontend/src/ide/settings/SettingsView.vue](frontend/src/ide/settings/SettingsView.vue)：

```vue
<template>
  <div class="settings-view">
    <div class="settings-main" ref="mainEl" @scroll="onScroll">
      <div class="settings-content">
        <section id="sec-assistant" class="settings-section">
          <h2 class="section-title">AI 助手</h2>
          <AssistantSettings />
        </section>
        <section id="sec-agent" class="settings-section">
          <h2 class="section-title">Agent 学习引擎</h2>
          <AgentSettings />
        </section>
        <section id="sec-providers" class="settings-section">
          <h2 class="section-title">供应商管理</h2>
          <ProvidersSettings />
        </section>
      </div>
    </div>
    <aside class="settings-anchors">
      <a v-for="a in anchors" :key="a.id"
         :class="{ active: activeAnchor === a.id }"
         @click="scrollTo(a.id)">
        {{ a.label }}
      </a>
    </aside>
  </div>
</template>
```

锚点高亮用 IntersectionObserver 监听三个 section，进入视口时标当前。点击锚点 `scrollIntoView({behavior: 'smooth'})`。

#### 2.2 公共控件 / 视觉规则

按 Apix `setting-card` 模板，每个设置项一卡：

```vue
<div class="setting-card">
  <div class="setting-title">{{ title }}</div>
  <div class="setting-info">{{ info }}</div>      <!-- 说明文字, 灰色 -->
  <div class="setting-control">                    <!-- 控件位 -->
    <slot />
  </div>
</div>
```

把这个抽成 [frontend/src/ide/settings/SettingCard.vue](frontend/src/ide/settings/SettingCard.vue) slot 组件复用。

**按钮风格"顺畅平滑"**：

- 切换类按钮（on/off、auto/fast/deep）用滑动指示条 + `transition: 0.18s cubic-bezier(0.4, 0, 0.2, 1)`（Apix 同款）
- hover 状态用背景色淡入而非边框跳变
- 主按钮（保存、测试连接、删除）用 Element Plus type=primary/danger，size=default
- 列表项 hover 整行背景色淡入 + 右侧操作按钮淡入
- 进 Spec B 实现阶段时调 `design-taste-frontend` skill 复审一遍 CSS

---

### §3 Tab 1：AI 助手

下面每项都是一张 SettingCard。

#### 3.1 厂商 / 模型 / API Key 完整表单

聚合 Spec A 的工具栏状态，提供完整表单视图：

- 厂商选择（带 icon）—— 等价于聊天框头部下拉
- API Key（password input + 显示/隐藏切换）—— 替代聊天框 🔑 弹窗
- Base URL（仅 custom 时可编辑，预设厂商灰显）
- 模型选择（带 vision/reasoning/context 徽章）
- "测试连接"按钮：调 `/api/chat/completions` 发一句 `"ping"`，看回包 200。

#### 3.2 思考模式

- 三态 radio：auto/fast/deep（等价于聊天框工具栏的 radio）
- deep 在不支持模型上 disabled + tooltip 灰提示（沿用 Spec A §5.3）

#### 3.3 工具权限（盘活 toolPermissions）

[aiSettings.js:99 `toolPermissions`](frontend/src/stores/aiSettings.js#L99) 当前数据：6 个工具 × 3 态 `allow|ask|deny`。

```vue
<SettingCard title="工具权限" info="AI 助手调用工具时的默认行为">
  <div v-for="tool in TOOLS" :key="tool.id" class="tool-perm-row">
    <span class="tool-name">{{ tool.label }}</span>
    <span class="tool-desc">{{ tool.description }}</span>
    <el-radio-group :model-value="aiSettings.permissionFor(tool.id)"
                    size="small"
                    @change="aiSettings.setToolPermission(tool.id, $event)">
      <el-radio-button label="allow">允许</el-radio-button>
      <el-radio-button label="ask">询问</el-radio-button>
      <el-radio-button label="deny">禁用</el-radio-button>
    </el-radio-group>
  </div>
</SettingCard>
```

6 个工具的 label/description 从 [frontend/src/ide/tools/registry.js](frontend/src/ide/tools/registry.js) 读，单一信息源。

#### 3.4 个人记忆（盘活 memories）

[aiSettings.js:120 `memories`](frontend/src/stores/aiSettings.js#L120) 当前：`{id, type, title, content, enabled, source, createdAt, updatedAt}` 列表 + `addMemory/updateMemory/removeMemory/formatEnabledMemories` 全套 actions。

```vue
<SettingCard title="个人记忆" info="AI 对话时自动附加的偏好/事实，避免每次手动告知">
  <div class="memory-list">
    <div v-for="m in aiSettings.memories" :key="m.id" class="memory-item">
      <el-switch :model-value="m.enabled"
                 @change="aiSettings.updateMemory(m.id, { enabled: $event })" />
      <el-input :model-value="m.title" placeholder="标题(如: 偏好语言版本)"
                @change="aiSettings.updateMemory(m.id, { title: $event })" />
      <el-input :model-value="m.content" type="textarea" :rows="2"
                placeholder="内容(如: Python 3.13, 类型标注, 简洁注释)"
                @change="aiSettings.updateMemory(m.id, { content: $event })" />
      <el-button type="danger" link @click="aiSettings.removeMemory(m.id)">删除</el-button>
    </div>
  </div>
  <el-button type="primary" plain @click="aiSettings.addMemory({title: '', content: '', type: 'preference'})">
    + 添加记忆
  </el-button>
</SettingCard>
```

#### 3.5 清除聊天历史

```vue
<SettingCard title="清除聊天历史" info="清空当前 AI 助手对话记录(不可恢复)">
  <el-button type="danger" plain @click="confirmClearHistory">清除</el-button>
</SettingCard>
```

[chat.js](frontend/src/stores/chat.js) 现有 `messages.value = []` 已能清。本期补一个 `clearMessages()` 公开方法即可。

---

### §4 Tab 2：Agent 学习引擎（核心新功能）

#### 4.1 数据模型

新增 [frontend/src/stores/agentLlm.js](frontend/src/stores/agentLlm.js)，独立 localStorage key `kmatch-agent-llm`：

```js
// 数据形状: {
//   useOverrides: boolean,        // false = 后端 .env (默认); true = 用下方覆写
//   provider: string,             // 预设 8 项或 'custom:<uuid>'
//   apiKey: string,
//   baseUrl: string,              // custom 时用户填; 预设时 = providerMeta.baseUrl
//   model: string,
//   protocol: 'openai',           // 本期固定 openai;Anthropic 留给后续
// }

export const useAgentLlmStore = defineStore('agentLlm', () => {
  const state = ref(loadState())   // 默认 { useOverrides: false, ... }

  function setUseOverrides(on)  { state.value.useOverrides = on; persist() }
  function setProvider(pid)     { /* 同 aiSettings.setProvider 逻辑 */ }
  function setApiKey(key)       { state.value.apiKey = key; persist() }
  function setBaseUrl(url)      { state.value.baseUrl = url; persist() }
  function setModel(m)          { state.value.model = m; persist() }

  /** 返回供 axios interceptor 注入的 overrides;关闭时返回 null */
  function buildOverrides() {
    if (!state.value.useOverrides) return null
    if (!state.value.apiKey?.trim()) return null
    return {
      api_key: state.value.apiKey,
      base_url: state.value.baseUrl,
      model: state.value.model,
      protocol: state.value.protocol,
    }
  }

  return { state, setUseOverrides, setProvider, setApiKey, setBaseUrl, setModel, buildOverrides }
})
```

#### 4.2 前端 axios interceptor

[frontend/src/api/index.js](frontend/src/api/index.js) 当前是 Axios 实例 + Electron IPC / Vite proxy 双模式。加 request interceptor：

```js
import { useAgentLlmStore } from '@/stores/agentLlm'

const AGENT_ROUTES = [
  '/api/diagnostics/',
  '/api/learning/',
  '/api/project/review',
  '/api/project/test',
  // /api/project/parse 不调 LLM, 不注入
]

axiosInstance.interceptors.request.use((config) => {
  const isAgentRoute = AGENT_ROUTES.some((p) => config.url.startsWith(p))
  if (!isAgentRoute) return config

  const overrides = useAgentLlmStore().buildOverrides()
  if (!overrides) return config   // 没启用 / 没填 key → 走后端 .env

  config.data = { ...(config.data || {}), llm_overrides: overrides }
  return config
})
```

⚠️ 触发 SSE 流式的端点（`/api/diagnostics/assess/stream`）也走这套：FastAPI 接受 POST body 即可，SSE 是返回侧的事。

#### 4.3 后端改造

**1. [backend/app/agents/llm.py](backend/app/agents/llm.py) get_chat_model 加 overrides 参数：**

```python
from typing import TypedDict

class LlmOverrides(TypedDict, total=False):
    api_key: str
    base_url: str
    model: str
    protocol: str   # 本期仅 'openai'

def get_chat_model(
    temperature: float | None = None,
    overrides: LlmOverrides | None = None,
) -> ChatOpenAI:
    """创建 Chat 模型实例。
    overrides: 来自请求体 llm_overrides 字段; None 时走 settings 默认。
    """
    api_key  = (overrides or {}).get('api_key')  or settings.LLM_API_KEY
    base_url = (overrides or {}).get('base_url') or settings.LLM_BASE_URL
    model    = (overrides or {}).get('model')    or settings.LLM_MODEL

    return ChatOpenAI(
        model=model, api_key=api_key, base_url=base_url,
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
        max_retries=2, timeout=settings.LLM_TIMEOUT,
    )
```

⚠️ `get_default_chat_model()` 的 lru_cache 单例**移除**（带 overrides 时不能缓存）。改为：每个 agent 调用方传入 overrides 即按需构造。性能损失可接受（ChatOpenAI 构造 < 1ms）。

**2. 7 个 agent 函数加 `llm_overrides` 参数透传：**

[backend/app/agents/diagnostics.py](backend/app/agents/diagnostics.py)、[content_generator.py](backend/app/agents/content_generator.py)、[reviewer.py](backend/app/agents/reviewer.py)、[code_reviewer.py](backend/app/agents/code_reviewer.py)、[code_tester.py](backend/app/agents/code_tester.py)、[graph_controller.py](backend/app/agents/graph_controller.py)、[orchestrator.py](backend/app/agents/orchestrator.py)

每个 agent 入口函数（共 10 处调用 `get_default_chat_model()`）改为：

```python
# 改前
model = get_default_chat_model()

# 改后
model = get_chat_model(overrides=llm_overrides)
```

agent 函数签名加 `llm_overrides: dict | None = None`。

**3. API 路由从请求体读：**

每个用 agent 的路由从 request body 提 `llm_overrides`：

```python
# backend/app/api/diagnostics.py 例
class AssessRequest(BaseModel):
    user_profile: dict
    target_concepts: list[str] | None = None
    llm_overrides: dict | None = None   # 新增

@router.post("/assess")
async def assess(req: AssessRequest):
    result = await diagnostics_node(
        user_profile=req.user_profile,
        target_concepts=req.target_concepts,
        llm_overrides=req.llm_overrides,
    )
    return result
```

涉及端点（**全部** 8 个）：

| 端点 | Agent |
| --- | --- |
| POST /api/diagnostics/assess | diagnostics + content_generator + reviewer |
| POST /api/diagnostics/assess/stream | 同上 SSE |
| POST /api/diagnostics/submit | diagnostics 判分 |
| POST /api/diagnostics/feedback | content_generator |
| POST /api/learning/report | content_generator + reviewer |
| POST /api/project/review | code_reviewer |
| POST /api/project/test | code_tester |

**4. orchestrator 把 overrides 透传到子 agent：**

[backend/app/agents/orchestrator.py](backend/app/agents/orchestrator.py) 编排时把 `llm_overrides` 传给每个子 agent 调用。

#### 4.4 UI

```vue
<SettingCard title="启用 Agent 独立配置"
             info="开启后，学情检测/资源生成/代码审查等 Agent 使用下方配置；关闭则走后端默认 .env">
  <el-switch :model-value="agentLlm.state.useOverrides"
             @change="agentLlm.setUseOverrides($event)" />
</SettingCard>

<template v-if="agentLlm.state.useOverrides">
  <SettingCard title="厂商">
    <el-select :model-value="agentLlm.state.provider" @change="agentLlm.setProvider">
      <!-- 同 AI 助手厂商下拉, 但 anthropic 选项加 disabled + tooltip -->
      <el-option v-for="p in PROVIDERS" :key="p.id" :label="p.label" :value="p.id"
                 :disabled="p.protocol === 'anthropic'"
                 :title="p.protocol === 'anthropic' ? 'Agent 本期仅支持 OpenAI 兼容协议' : ''" />
    </el-select>
  </SettingCard>

  <SettingCard title="API Key">
    <el-input type="password" show-password
              :model-value="agentLlm.state.apiKey"
              @change="agentLlm.setApiKey" />
  </SettingCard>

  <SettingCard title="Base URL" v-if="isCustomProvider(agentLlm.state.provider)">
    <el-input :model-value="agentLlm.state.baseUrl" @change="agentLlm.setBaseUrl" />
  </SettingCard>

  <SettingCard title="模型">
    <el-select :model-value="agentLlm.state.model" @change="agentLlm.setModel">
      <el-option v-for="m in agentLlm.models" :key="m" :value="m" />
    </el-select>
  </SettingCard>

  <SettingCard title="测试连接" info="调一次 /api/diagnostics/assess 的最小 ping, 验证可用">
    <el-button type="primary" @click="testAgentConnection" :loading="testing">
      测试
    </el-button>
    <span v-if="testResult" :class="testResult.ok ? 'ok' : 'err'">
      {{ testResult.message }}
    </span>
  </SettingCard>
</template>
```

"测试连接"调一个轻量端点（**新增** `POST /api/agents/ping`）：

```python
@router.post("/ping")
async def agents_ping(req: PingRequest):
    """用 req.llm_overrides 构造 ChatOpenAI 发一句 'ping', 验证可用。"""
    model = get_chat_model(overrides=req.llm_overrides)
    try:
        resp = await asyncio.to_thread(model.invoke, "ping")
        return {"ok": True, "content": resp.content[:100]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
```

---

### §5 Tab 3：供应商管理

#### 5.1 自定义厂商列表 CRUD

主体来自 Spec A 已经建好的 customProviders store（Spec A §2 已落地多组 store schema，本期只补 UI）：

```vue
<SettingCard title="自定义厂商">
  <div class="custom-provider-list">
    <div v-for="cp in customProviders.list" :key="cp.id" class="cp-item">
      <div class="cp-header">
        <span class="cp-name">{{ cp.name }}</span>
        <span class="cp-baseurl">{{ cp.baseUrl }}</span>
        <span class="cp-models">{{ cp.models.length }} 个模型</span>
        <el-button-group>
          <el-button @click="editProvider(cp.id)">编辑</el-button>
          <el-button type="danger" link @click="removeProvider(cp.id)">删除</el-button>
        </el-button-group>
      </div>
    </div>
  </div>
  <el-button type="primary" plain @click="openNewProviderDialog">+ 新建厂商</el-button>
</SettingCard>

<!-- 编辑对话框 (复用一个组件给"新建"+"编辑") -->
<ProviderEditDialog v-model="dialogVisible" :provider="editingProvider" @save="onSave" />
```

[frontend/src/ide/settings/ProviderEditDialog.vue](frontend/src/ide/settings/ProviderEditDialog.vue) 仿 Apix 的 ProviderEditDialog —— name / endpoint / apiKey / models (input-tag + 自动获取) / description。

#### 5.2 批量 vision 探测 + 清缓存

```vue
<SettingCard title="视觉能力探测" info="逐个调用每个模型探测是否支持图像输入, 结果缓存; 消耗少量 token">
  <el-button @click="batchProbeVision" :loading="probing">
    👁 批量检测（{{ knownVisionCount }}/{{ totalModelsCount }} 已知）
  </el-button>
  <el-button type="danger" plain @click="clearVisionCache">
    🗑 清除视觉缓存
  </el-button>
</SettingCard>
```

批量探测流程：

1. 弹「即将探测 X 个未知模型，约消耗 ¥{X×0.001}，继续？」
2. 串行调 `/api/chat/probe-vision` 每个未知 (baseUrl, model)
3. 进度条 + 可中途取消
4. 完成弹「探测完成，新发现 N 个 vision 模型」

清缓存：DELETE `/api/chat/probe-vision/cache`（Spec A 已有），刷新前端 store。

#### 5.3 网络代理（盘活 proxy）

[aiSettings.js:13 `DEFAULT_PROXY`](frontend/src/stores/aiSettings.js#L13) 已有 `{enabled, type, url, scope}` 字段。

```vue
<SettingCard title="网络代理" info="所有 LLM 出站请求通过此代理（影响后端 sidecar 进程的 OpenAI/Anthropic SDK）">
  <el-switch :model-value="aiSettings.proxy.enabled"
             @change="aiSettings.setProxy({ enabled: $event })" />
  <template v-if="aiSettings.proxy.enabled">
    <el-input :model-value="aiSettings.proxy.url"
              placeholder="http://127.0.0.1:7890"
              @change="aiSettings.setProxy({ url: $event })" />
    <el-select :model-value="aiSettings.proxy.type" @change="aiSettings.setProxy({ type: $event })">
      <el-option label="HTTP" value="http" />
      <el-option label="SOCKS5" value="socks5" />
    </el-select>
  </template>
</SettingCard>
```

⚠️ 设置代理仅前端 store 化是不够的 —— 后端 sidecar 启动时要读这个配置设置 `HTTP_PROXY/HTTPS_PROXY` 环境变量。流程：

1. 用户在设置页改 proxy → renderer 进程 store 改完后 IPC 调 `window.api.setProxyConfig(proxyState)`
2. main 进程接收，缓存到 main-side 模块变量
3. main 进程下次 [spawnBackend()](electron/main/backend-sidecar.js#L50) 时把缓存的 proxy 值塞进 `env` 参数（`HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`）
4. 前端弹「需重启 backend」按钮 → 用户点 → main 进程 kill 现有 sidecar + 重 spawn

不落盘 `runtime.env` 文件 —— main 进程内存缓存就够，重启 Electron 后 main 进程会从 renderer localStorage 重新拉一次（启动握手）。

**启动顺序细节**：main 进程 ready 时第一次 spawn sidecar 早于 renderer 准备好。处理：

- main 进程启动时**先读** `app.getPath('userData')/proxy-cache.json`（只有 proxy 这一个轻量配置落盘）
- 用户改 proxy 时 main 进程同时写 store + 写 proxy-cache.json
- 第一次启动且无 proxy-cache.json 时 sidecar 不带 proxy（与现状一致）

这是唯一需要轻量落盘的配置；其他设置（apiKey/model/...）只 renderer 用，不需要 main 进程感知。

---

## 4. 测试策略

### 4.1 前端单测

- `agentLlm-store.test.js`：useOverrides on/off、buildOverrides 在 key 为空时返回 null、各 setter 正确 persist
- `axios-interceptor.test.js`：AGENT_ROUTES 命中时注入 llm_overrides；非 agent route 不注入；useOverrides=false 不注入
- `settings-toolperm.test.js`：6 工具 × 3 态全组合可切换 + persist
- `settings-memories.test.js`：add/update/remove/enable 切换 + persist；空 title 或 content 不允许保存
- `settings-providers-crud.test.js`：customProviders 列表渲染、编辑对话框保存写回 store
- `settings-vision-batch.test.js`：批量探测进度跟踪、取消、消耗预估

### 4.2 后端单测

- `test_llm_overrides.py`：get_chat_model(overrides=) 各字段正确传入；overrides=None 时走 settings 默认
- `test_agents_with_overrides.py`：每个 agent 函数 llm_overrides 参数透传（用 mock 验证 get_chat_model 调用入参）
- `test_routes_llm_overrides.py`：每个 agent 路由从 body 读 llm_overrides 并下传
- `test_agents_ping.py`：/api/agents/ping 用 overrides ping；auth 错走 ok=false 分支
- `test_orchestrator_overrides_propagation.py`：orchestrator 把 overrides 传给所有子 agent

### 4.3 手测（CDP + 真实 key）

- 进设置 → AI 助手填 DeepSeek key → 测试连接 → 回到聊天 → 发消息验证用的是这个 key
- 进设置 → Agent 学习引擎开启 → 填自己的 DeepSeek key → 测试连接 → 跑场景一学情测评 → 后端日志看 LLM 调用用的是这个 key
- 进设置 → 供应商管理新建 OpenRouter → 自动获取模型 → 批量探测 vision → 切回 AI 助手用此厂商对话
- proxy 启用 → 重启 backend → 看 sidecar 环境是否注入 HTTP_PROXY → curl ipconfig.me 验证

---

## 5. 影响面 / 文件清单

### 新增

- [frontend/src/stores/agentLlm.js](frontend/src/stores/agentLlm.js)
- [frontend/src/ide/settings/SettingsView.vue](frontend/src/ide/settings/SettingsView.vue) — 主壳
- [frontend/src/ide/settings/SettingCard.vue](frontend/src/ide/settings/SettingCard.vue) — 公共卡片
- [frontend/src/ide/settings/AssistantSettings.vue](frontend/src/ide/settings/AssistantSettings.vue) — Tab 1
- [frontend/src/ide/settings/AgentSettings.vue](frontend/src/ide/settings/AgentSettings.vue) — Tab 2
- [frontend/src/ide/settings/ProvidersSettings.vue](frontend/src/ide/settings/ProvidersSettings.vue) — Tab 3
- [frontend/src/ide/settings/ProviderEditDialog.vue](frontend/src/ide/settings/ProviderEditDialog.vue) — 新建/编辑 custom provider
- 后端 `/api/agents/ping` 端点（小路由文件 [backend/app/api/agents.py](backend/app/api/agents.py)）

### 修改

- [frontend/src/stores/sidebar.js](frontend/src/stores/sidebar.js) — activeView 扩 `'settings'`
- [frontend/src/ide/ActivityBar.vue](frontend/src/ide/ActivityBar.vue) — 底部齿轮
- [frontend/src/ide/TitlebarMenu.vue](frontend/src/ide/TitlebarMenu.vue) — 加"设置"菜单项
- [frontend/src/ide/MainArea.vue](frontend/src/ide/MainArea.vue) — v-if 分支加 SettingsView
- [frontend/src/api/index.js](frontend/src/api/index.js) — axios interceptor 注入 llm_overrides
- [frontend/src/stores/chat.js](frontend/src/stores/chat.js) — 加 clearMessages() 方法
- [backend/app/agents/llm.py](backend/app/agents/llm.py)
  - get_chat_model 加 overrides 参数
  - 移除 get_default_chat_model 的 lru_cache（或保留但 overrides 不走单例）
- 7 个 agent 文件 + 8 个路由 — 加 llm_overrides 参数透传
- [electron/main/backend-sidecar.js](electron/main/backend-sidecar.js) — 启动 sidecar 时按 proxy store 注入 HTTP_PROXY env

---

## 6. 实施顺序（PR 分包）

1. **PR-1 设置视图骨架**：§1 + §2 主壳 + SettingCard + 锚点导航（空三 Tab 占位）
2. **PR-2 Tab 1 AI 助手**：§3 完整（聚合现有 store + toolPermissions UI + memories UI + 清聊天历史）
3. **PR-3 Tab 2 Agent 独立 key**：§4 完整（store + interceptor + 后端 overrides 透传 + /agents/ping）
4. **PR-4 Tab 3 供应商管理**：§5.1 自定义厂商 CRUD + ProviderEditDialog
5. **PR-5 Vision 批量 + 清缓存 UI**：§5.2
6. **PR-6 网络代理**：§5.3 + Electron sidecar env 注入

---

## 7. 风险清单

- ⚠️ Agent 链 lru_cache 单例移除：性能影响需 benchmark；正常 < 1ms 应可接受
- ⚠️ orchestrator 子 agent 参数透传容易漏：写 test_orchestrator_overrides_propagation.py 全覆盖
- ⚠️ axios interceptor 注入到 SSE 端点：fetch 风格 SSE 不走 axios 时漏注入；要看 [chat.js _runToolRound](frontend/src/stores/chat.js#L660) 是不是用 fetch 直接发，agent 路由是否也直发 → 检查后补
- ⚠️ Element Plus el-radio-button 单项 disabled 样式：Spec A 同款风险，复用解法
- ⚠️ proxy 配 SOCKS5：Python 标准 urllib 不直接支持 socks5；OpenAI SDK 底层 httpx 通过 `HTTPS_PROXY=socks5://...` 也需要 `httpx[socks]` 装包。本期文档标明"需 pip install httpx[socks]"，requirements.txt 加
- ⚠️ 设置页"顺畅平滑"是审美指标：实现阶段调 design-taste-frontend skill 复审 CSS；至少要做到滚动惯性、卡片 hover 阴影、按钮 transition、锚点高亮平滑
