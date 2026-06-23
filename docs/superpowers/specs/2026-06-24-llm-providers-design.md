# Spec A — 聊天框 Apix 化（多厂商 + 模型能力 + Vision + 图片上传）

**日期**：2026-06-24
**作者**：origin0722
**借鉴来源**：[Apix](https://github.com/JJJJSTIYYYY/Apix) — `llm_adapter.py` / `assistPage.vue`

> 本 spec 是三 spec 中的第一个。
>
> - **Spec A（本文件）**：聊天框 Apix 化（厂商/模型/vision/思考/上传图），聚焦 AI 助手对话体验
> - **Spec B**（待开）：设置页（线性 + 锚点）+ Agent 学习引擎独立 key + 盘活 toolPermissions/memories/proxy 三个孤儿 store
> - **Spec C**（推迟，不在 brainstorming 范围内）：联网搜索 + Python 知识时效性

---

## 1. 背景与目标

KMatch-Desktop 的 AI 助手当前支持 4 个厂商（DeepSeek/OpenAI/Ollama/custom），custom 只能存 1 组，没有模型能力可视化，没有视觉能力探测，思考模式有 UI 状态但**没有控件**（孤儿）。

Spec A 目标：把**聊天框本身**变得跟 Apix 一样能用 —— 多厂商下拉 + 动态模型 + 模型能力徽章 + 思考模式可控 + 图片上传 + Anthropic 原生协议。

### 用户故事

- 「切到 Claude Opus 时能看见 200K context、🧠 reasoning、👁 vision 三个徽章，知道能干什么。」
- 「点 📎 上传截图给 GPT-4o 解读，非 vision 模型时按钮自动灰。」
- 「我能选 fast/deep 思考。不支持 reasoning 的模型 deep 档自动灰。」
- 「用 Anthropic 原生 API 跟 Claude 对话，不用走 302.ai 代理。」

---

## 2. 范围与不在范围

### 范围

- 厂商注册表从 4 项扩到 8 项（DeepSeek/OpenAI/Anthropic/Moonshot/Qwen/Gemini/Ollama/custom），加 `protocol`/`iconKey`/`fallbackModels` 元数据
- aiSettings 的 `provider` 值域扩展，predefined 用 `'deepseek'/...`、custom 用 `'custom:<uuid>'` 字符串协议
- 自定义厂商的 store 改造为列表形态（**本期仍仅允许 1 组**，UI 沿用聊天框 🔑 弹窗；多组 CRUD 推到 Spec B）
- 模型能力静态表（reasoning / context window），按模型族正则匹配
- 视觉能力**后端探测**（复刻 Apix 探测协议），结果持久化到 `vision_cache.json`；前端按需懒探（切模型时异步起、点 📎 时等待）
- 思考模式控件：三态 radio（auto/fast/deep），deep 在不支持模型上 disabled + tooltip 灰提示
- 输入框 📎 上传按钮 + 拖拽，仅 vision 模型启用，图片 ≤5MB × ≤5 张
- Anthropic 原生 SDK 分支：纯对话 + thinking + vision + 提示词工具循环与其他厂商对等

### 不在范围（推到 Spec B）

- 设置页（VS Code 式 / 线性 / 锚点导航）
- Agent 学习引擎独立 key（7 个 agent 用用户的 key 而不是 .env）
- 自定义厂商**多组 CRUD**（ProviderManagerDialog）+ 批量 vision 探测 + 清 vision 缓存按钮
- toolPermissions/memories/proxy 三个孤儿 store 的 UI 化
- 联网搜索（属于 Spec C）

### 不在范围（推后）

- API Key 加密存储 —— 单独 spec
- 模型描述、定价、TPS 等元数据展示
- 多模态消息持久化到磁盘 —— chat history 本来就不持久化

---

## 3. 设计

### §1 厂商注册表（PROVIDERS）

[frontend/src/stores/aiSettings.js](frontend/src/stores/aiSettings.js) 的 `PROVIDERS` 数组扩 8 项 + custom，每项加 `protocol`/`iconKey`/`fallbackModels`：

```js
export const PROVIDERS = Object.freeze([
  { id: 'deepseek',  label: 'DeepSeek',   baseUrl: 'https://api.deepseek.com/v1',
    protocol: 'openai',     iconKey: 'deepseek',
    fallbackModels: ['deepseek-v4-pro', 'deepseek-v3', 'deepseek-reasoner'] },

  { id: 'openai',    label: 'OpenAI',     baseUrl: 'https://api.openai.com/v1',
    protocol: 'openai',     iconKey: 'openai',
    fallbackModels: ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'o1', 'o3-mini'] },

  { id: 'anthropic', label: 'Anthropic',  baseUrl: 'https://api.anthropic.com',
    protocol: 'anthropic',  iconKey: 'claude',
    fallbackModels: ['claude-fable-5', 'claude-opus-4-8', 'claude-sonnet-4-6', 'claude-haiku-4-5'] },

  { id: 'moonshot',  label: 'Moonshot',   baseUrl: 'https://api.moonshot.cn/v1',
    protocol: 'openai',     iconKey: 'moonshot',
    fallbackModels: ['moonshot-v1-128k', 'moonshot-v1-32k', 'kimi-k2-0905-preview'] },

  { id: 'qwen',      label: '通义千问',    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    protocol: 'openai',     iconKey: 'qwen',
    fallbackModels: ['qwen-max', 'qwen-plus', 'qwen-turbo', 'qwen-vl-max'] },

  { id: 'gemini',    label: 'Google Gemini', baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    protocol: 'openai',     iconKey: 'google',
    fallbackModels: ['gemini-2.5-pro', 'gemini-2.5-flash'] },

  { id: 'ollama',    label: 'Ollama (本地)', baseUrl: 'http://localhost:11434/v1',
    protocol: 'openai',     iconKey: 'ollama',
    fallbackModels: ['llama3', 'qwen2.5', 'codellama'] },

  { id: 'custom',    label: '自定义',      baseUrl: '',
    protocol: 'openai',     iconKey: 'custom',
    fallbackModels: [] },
])
```

**关键点**：

- `protocol` 字段只两种取值：`'openai'`（绝大多数厂商；走 AsyncOpenAI）/ `'anthropic'`（走 anthropic SDK）。**这是后端唯一的协议分支条件**。
- Gemini 走 OpenAI 兼容模式 endpoint，避免后端引第三个 SDK。
- 8 个 svg 图标从 Apix 复制到 `frontend/src/assets/icons/llm_providers/`（Apix LICENSE 已确认开源）。

### §2 自定义厂商 store（仅 schema 改造，UI 保持现状）

新增 [frontend/src/stores/customProviders.js](frontend/src/stores/customProviders.js)，localStorage key `kmatch-ai-custom-providers`：

```js
// 数据形状: {
//   id: string,           // uuid
//   name: string,         // 用户起的名字
//   baseUrl: string,      // OpenAI 兼容 endpoint
//   apiKey: string,
//   models: string[],     // 用户手填 / 自动获取
//   protocol: 'openai',   // 本期固定; 留字段以备未来
//   description: string,
//   createdAt: ISOString,
//   updatedAt: ISOString,
// }

export const useCustomProvidersStore = defineStore('customProviders', () => {
  const list = ref(loadList())

  function add(input)        { /* push + persist; 返回新建项 */ }
  function update(id, patch) { /* find + replace + persist */ }
  function remove(id)        { /* filter + persist */ }
  function get(id)           { /* find */ }
  async function autoFetchModels(id) { /* GET {baseUrl}/models, 解析 + 写入 */ }

  return { list, add, update, remove, get, autoFetchModels }
})
```

**与 aiSettings 的接驳**：

`aiSettings.provider` 值域扩展：

| `provider` 值 | 含义 |
| --- | --- |
| 预设 8 项的 id（`'deepseek'`, `'openai'`, …） | 配置查 PROVIDERS 静态表 |
| `'custom:<uuid>'` | 配置查 customProviders.list |

唯一改造的两个出口函数：

```js
function providerMeta() {
  if (provider.value.startsWith('custom:')) {
    const uuid = provider.value.slice('custom:'.length)
    const cp = useCustomProvidersStore().get(uuid)
    return cp
      ? { id: provider.value, label: cp.name, baseUrl: cp.baseUrl,
          protocol: cp.protocol, iconKey: 'custom', fallbackModels: cp.models }
      : PROVIDERS[0]   // 兜底
  }
  return PROVIDERS.find((p) => p.id === provider.value) || PROVIDERS[0]
}

function getBaseUrl() {
  return providerMeta().baseUrl || ''
}
```

**本期 UI 限制**：

- 现有 [AssistantPanel.vue](frontend/src/ide/AssistantPanel.vue) 工具栏 `🔑` 弹窗的「自定义 base URL」逻辑保留：选 `custom` 厂商时弹的对话框里能填 baseUrl + apiKey，**实质保存为 customProviders 列表里的"唯一一项"**（id 固定为 `default`，name 固定为 "自定义"）。
- 用户感知上"自定义还是 1 组"，但 store 已是列表形态。Spec B 引入设置页时直接加多组 CRUD UI，store schema 不用改。

**数据迁移（一次性）**：

`loadProviderConfig` 检测旧 `providerConfig.customBaseUrl` 存在时：

```js
const uuid = 'default'   // 第一次迁移用固定 id 'default', 避免每次启动 uuid 变
const cp = {
  id: uuid,
  name: '自定义',
  baseUrl: saved.providerConfig.customBaseUrl,
  apiKey: saved.providerConfig.provider === 'custom' ? saved.providerConfig.apiKey : '',
  models: [],
  protocol: 'openai',
  description: '',
  createdAt: nowIso(),
  updatedAt: nowIso(),
}
useCustomProvidersStore().add(cp)
if (saved.providerConfig.provider === 'custom') {
  saved.providerConfig.provider = `custom:${uuid}`
  saved.providerConfig.apiKey = ''
}
delete saved.providerConfig.customBaseUrl
persist()
```

`apiKey` 当前是 ref 单值；改造后**仍是单值** —— 切到不同 `provider` 时从对应来源加载（预设走 providerApiKeys 字典，custom 走 customProviders.get(uuid).apiKey）。setApiKey 写回对应位置。

### §3 动态拉模型 + 模型能力 metadata

#### 3.1 fetchModels 路径

后端 `/api/chat/models` 加 `protocol` 字段：

```python
class ModelsRequest(BaseModel):
    base_url: str
    api_key: str
    protocol: Literal['openai', 'anthropic'] = 'openai'

ANTHROPIC_MODELS = [
    'claude-fable-5', 'claude-opus-4-8', 'claude-sonnet-4-6',
    'claude-haiku-4-5', 'claude-opus-4-7', 'claude-sonnet-4',
]   # 硬编码;Anthropic API 无 /models 端点;按需更新

@router.post("/models")
async def list_models(req: ModelsRequest):
    if req.protocol == 'anthropic':
        return {"models": ANTHROPIC_MODELS}
    try:
        client = _get_async_client(req.base_url, req.api_key)
        resp = await client.models.list()
        return {"models": [m.id for m in resp.data]}
    except Exception as exc:
        return {"error": str(exc)}
```

前端 [aiSettings.js:181 `fetchModels()`](frontend/src/stores/aiSettings.js#L181) 在 body 里带上 `protocol: providerMeta().protocol`。

#### 3.2 modelCapabilities 静态表

新增 [frontend/src/services/llm/modelCapabilities.js](frontend/src/services/llm/modelCapabilities.js)：

```js
const CAPABILITY_TABLE = [
  // OpenAI
  { provider: 'openai', modelPattern: /^o(1|3)/,       reasoning: 'native',      context: 128_000 },
  { provider: 'openai', modelPattern: /^gpt-4\.1/,     reasoning: 'prompt-only', context: 1_000_000 },
  { provider: 'openai', modelPattern: /^gpt-4o/,       reasoning: 'prompt-only', context: 128_000 },

  // DeepSeek
  { provider: 'deepseek', modelPattern: /^deepseek-v4/,       reasoning: 'native', context: 128_000 },
  { provider: 'deepseek', modelPattern: /^deepseek-reasoner/, reasoning: 'native', context:  64_000 },

  // Anthropic
  { provider: 'anthropic', modelPattern: /^claude-(opus|sonnet|haiku|fable|mythos)-(4|5)/,
    reasoning: 'native', context: 200_000 },

  // Qwen
  { provider: 'qwen', modelPattern: /^qwen-/,         reasoning: 'prompt-only', context: 128_000 },

  // Gemini
  { provider: 'gemini', modelPattern: /^gemini-2\.5/,  reasoning: 'native',      context: 1_000_000 },

  // 兜底
  { provider: '*', modelPattern: /.*/,                  reasoning: 'prompt-only', context: null },
]

export function capabilityOf(provider, modelId) {
  // 1) 找 provider 精确匹配的第一条
  // 2) 没找到再用 '*' 兜底
  // 返回 { reasoning, context }
}
```

**vision 不在这张表里** —— vision 走后端探测（§4），由 modelVision store 提供。UI 上展示时通过 helper 合并：

```js
function capOf(model) {
  const cap = capabilityOf(aiSettings.provider, model)
  const vision = useModelVisionStore().hasVision(aiSettings.getBaseUrl(), model)
  return { ...cap, vision }
}
```

#### 3.3 UI：model select + 徽章

[AssistantPanel.vue:330](frontend/src/ide/AssistantPanel.vue#L330) 的 `<span class="model-hint">` 换成 select：

```vue
<el-select :model-value="aiSettings.model" size="small" class="model-select" @change="aiSettings.setModel">
  <el-option v-for="m in aiSettings.models" :key="m" :label="m" :value="m">
    <span class="model-row">
      <span class="model-name">{{ m }}</span>
      <span class="model-badges">
        <el-tag v-if="capOf(m).vision === true"      size="small" type="success">👁</el-tag>
        <el-tag v-if="capOf(m).reasoning === 'native'" size="small" type="warning">🧠</el-tag>
        <el-tag v-if="capOf(m).context"               size="small" type="info">{{ formatContext(capOf(m).context) }}</el-tag>
      </span>
    </span>
  </el-option>
</el-select>
```

#### 3.4 modelReasoningSupport / reasoningInstruction 薄包装

[aiSettings.js:278 `modelReasoningSupport`](frontend/src/stores/aiSettings.js#L278) 被 [chat.js:614](frontend/src/stores/chat.js#L614) 和两个测试调用。**不删函数**，改为内部委托 modelCapabilities：

```js
function modelReasoningSupport(provider, model) {
  return capabilityOf(provider, model).reasoning   // 'native' | 'prompt-only'
}
```

⚠️ **破坏性变更**：旧版返回值有 `'native-when-supported-by-backend'` 第三态。本期 anthropic SDK 已接通，这一态不再需要。`ai-settings-store.test.js` 旧断言 Claude → `'native-when-supported-by-backend'` 改为 `'native'`。`reasoningInstruction` 内部分支随之简化。

---

### §4 Vision 探测 + 持久化缓存

#### 4.1 后端 probe-vision 端点

新加 [backend/app/api/chat.py](backend/app/api/chat.py)：

```python
TEST_IMG_BASE64 = "..."   # 复用 Apix 76x100 写了 'test vision' 文字的图

class ProbeVisionRequest(BaseModel):
    base_url: str
    api_key: str
    model: str
    protocol: Literal['openai', 'anthropic'] = 'openai'

@router.post("/probe-vision")
async def probe_vision(req: ProbeVisionRequest):
    cache = _load_vision_cache()
    key = f"{req.base_url}::{req.model}"
    if key in cache:
        return {"vision": cache[key], "cached": True}

    prompt = ("You are given an image.\n"
              "The image contains only text.\n"
              "Extract the exact text from the image.\n"
              "Return only the text. No explanation.")

    try:
        if req.protocol == 'openai':
            client = _get_async_client(req.base_url, req.api_key)
            resp = await client.chat.completions.create(
                model=req.model,
                messages=[
                    {"role": "system", "content": "You are a precise OCR assistant."},
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/png;base64,{TEST_IMG_BASE64}"}},
                    ]},
                ],
                max_tokens=100, stream=False,
            )
            content = (resp.choices[0].message.content or "").strip().lower()
        else:  # anthropic
            from anthropic import AsyncAnthropic
            ac = AsyncAnthropic(api_key=req.api_key)
            resp = await ac.messages.create(
                model=req.model, max_tokens=100,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/png", "data": TEST_IMG_BASE64}},
                ]}],
            )
            content = (resp.content[0].text if resp.content else "").strip().lower()

        is_vision = ("test" in content and "vision" in content)
    except Exception as exc:
        err = str(exc).lower()
        if any(k in err for k in ['unauthorized', 'authentication', 'invalid api key',
                                   'api key', 'permission denied', '401']):
            return {"vision": False, "cached": False, "error": "auth"}
        is_vision = False   # 非 auth 错都判 False, 但写缓存

    cache[key] = is_vision
    _save_vision_cache(cache)
    return {"vision": is_vision, "cached": False}

@router.delete("/probe-vision/cache")
async def clear_vision_cache():
    _save_vision_cache({})
    return {"ok": True}
```

cache 文件路径：`{settings.DATA_DIR}/vision_cache.json`。原子写：`.tmp` + rename。

清缓存的 DELETE 端点本期实现（后端 ready），但**清缓存按钮的 UI 推到 Spec B**（在「供应商管理」Tab 里）。

#### 4.2 前端：modelVision store + 触发时机

新增 [frontend/src/stores/modelVision.js](frontend/src/stores/modelVision.js)：

```js
// 内存 cache (key: `${baseUrl}::${model}`) + 启动时主动从 backend 拉一次
// state:
//   cache: Map<string, bool>
//   pending: Set<string>   // 正在探测中
//
// actions:
//   async probe(baseUrl, apiKey, model, protocol) → Promise<bool>
//   hasVision(baseUrl, model) → bool | undefined  (undefined = 没探过)
//   isPending(baseUrl, model) → bool
//   async clearAll()        // DELETE /probe-vision/cache + 清内存
//   clearForBaseUrl(url)    // 切 key 时清同 baseUrl 全部条目
```

`hasVision` 返回三态：

- `true` → 👁 徽章亮，📎 启用
- `false` → 不显示徽章，📎 disabled + title「当前模型不支持图像 ({model})」
- `undefined` → 显示 ⋯ 徽章（检测中或未检测），📎 disabled

**本期触发时机**：

| 触发点 | 行为 |
| --- | --- |
| 用户切到一个 model | `probe()` 异步起；不阻塞 UI |
| 用户点 📎 但当前模型 undefined | 弹 toast「正在检测视觉能力…」，等结果 |
| 用户改 API Key | 清同 baseUrl 全部 cache 条目（换 key 等于换厂商） |

⚠️ 「批量检测视觉能力」按钮（一次探一个厂商所有模型）**推到 Spec B**（在设置页「供应商管理」Tab）。

#### 4.3 边界

- 探测**只对 openai / anthropic 协议生效**。Ollama 走 OpenAI 协议但本地模型多不支持 vision —— 仍按统一流程探，结果通常 False，可接受。
- 单次探测约 100 tokens；每个未知模型一次；**所有探测都用用户自己的 key**。
- 探测不计入 chat 对话历史：独立 endpoint。
- cache 文件并发安全：file-level lock + atomic rename。

---

### §5 思考模式（保三态 + 不支持时灰提示）

#### 5.1 后端 _build_request_extras

[chat.py:77 `_build_extra_body`](backend/app/api/chat.py#L77) 重命名 + 重构为：

```python
def _build_request_extras(protocol: str, model: str, reasoning_mode: str) -> dict:
    """
    reasoning_mode: 'auto' | 'fast' | 'deep'
    返回额外 kwargs 字典(不含 messages/model/stream/max_tokens)。
    """
    # DeepSeek-V4 系列 + xiaomi MiMo: extra_body.thinking
    if protocol == 'openai' and _is_thinking_extra_body_model(model):
        thinking = 'disabled' if reasoning_mode == 'fast' else 'enabled'
        return {'extra_body': {'thinking': {'type': thinking}}}

    # Anthropic Claude 4+: thinking param
    if protocol == 'anthropic' and _is_anthropic_reasoning_model(model):
        if reasoning_mode == 'deep':
            return {'thinking': {'type': 'enabled', 'budget_tokens': 8000}}
        if reasoning_mode == 'fast':
            return {'thinking': {'type': 'disabled'}}
        return {}   # auto: 不传, 由模型默认

    # OpenAI o1/o3: reasoning_effort
    if protocol == 'openai' and re.match(r'^o[13]', model):
        if reasoning_mode == 'deep': return {'reasoning_effort': 'high'}
        if reasoning_mode == 'fast': return {'reasoning_effort': 'low'}
        return {'reasoning_effort': 'medium'}

    return {}   # 其他模型不传 extras, 由 reasoningInstruction 提示词代偿
```

#### 5.2 ChatRequest 字段更名

[chat.py ChatRequest](backend/app/api/chat.py#L30) 把 `reasoning: bool | None` 改为 `reasoning_mode: Literal['auto','fast','deep'] = 'auto'`。

**兼容性**：本应用前后端同包打包同进程通信，前后端版本始终一致。Pydantic 对未知字段默认 ignore，不需保留旧 `reasoning` 字段。

前端 [chat.js:374-375](frontend/src/stores/chat.js#L374-L375) 同步改：

```js
body.reasoning_mode = aiSettings.reasoningMode   // 'auto' | 'fast' | 'deep'
body.protocol       = aiSettings.providerMeta().protocol
```

`_reasoningForRequest()` 函数删除。

#### 5.3 UI 控件

[AssistantPanel.vue:286 工具栏](frontend/src/ide/AssistantPanel.vue#L286) 在导学按钮和模型 select 之间加 reasoning radio：

```vue
<el-radio-group
  :model-value="aiSettings.reasoningMode"
  size="small"
  class="reasoning-group"
  :disabled="chat.streaming"
  @change="aiSettings.setReasoningMode"
>
  <el-radio-button label="auto" title="自动 — 由模型默认决定">🤖</el-radio-button>
  <el-radio-button label="fast" title="快速 — 不思考直接回答">⚡</el-radio-button>
  <el-radio-button
    label="deep"
    :disabled="deepDisabled"
    :title="deepDisabled ? deepDisabledTooltip : '深度 — 充分思考'"
  >🧠</el-radio-button>
</el-radio-group>
```

```js
const deepDisabled = computed(() =>
  capabilityOf(aiSettings.provider, aiSettings.model).reasoning !== 'native')

const deepDisabledTooltip = computed(() =>
  `当前模型 (${aiSettings.model}) 不支持原生推理；如需思考请用「快速/自动」+ 提示词`)
```

#### 5.4 自动降级

`reasoningMode = 'deep'` 从 localStorage 恢复且当前模型不支持时，watch 切到 `'auto'` 并 toast 一次。

---

### §6 图片上传（📎 按钮 + 拖拽）

#### 6.1 UX

输入框工具栏 thinking 控件右边加 📎。状态规则：

| vision 状态 | 📎 状态 |
| --- | --- |
| `true` | 启用 + 强调色，点开 file dialog |
| `false` | disabled + title「当前模型不支持图像 ({model})」 |
| `undefined` | loading 小圆点，title「正在检测视觉能力…」；底层异步在 probe |

输入区域整体监听 `dragover/drop`，drop 时按相同规则处理。

**图片预览条**：选中的图显示在 textarea 上方（absolute 浮层；textarea padding-top 让空间），每张：缩略图 48×48 + 文件名 + 大小 + ✕。

#### 6.2 chat store 数据流

[chat.js](frontend/src/stores/chat.js) 加：

```js
const pendingAttachments = ref([])
// 单元: { id, name, size, mimeType, base64DataUrl, thumbDataUrl }

function addAttachment(file)   { /* FileReader → base64; canvas 缩到 max 200px → thumb */ }
function removeAttachment(id)  { ... }
function clearAttachments()    { ... }
```

`sendMessage(text)`：

```js
const attachments = [...pendingAttachments.value]
const userMsg = {
  role: 'user',
  content: attachments.length === 0
    ? text                                          // 文本: 维持 string
    : [                                             // 多模态: OpenAI 数组形式
        { type: 'text', text },
        ...attachments.map((a) => ({
          type: 'image_url',
          image_url: { url: a.base64DataUrl },
        })),
      ],
  _attachments: attachments,                        // 前端展示用; 不发后端
}
```

#### 6.3 关键 helper 适配

[chat.js:715-718 构建 apiMessages](frontend/src/stores/chat.js#L715-L718) 改为：

```js
const historyMsgs = visibleMessages.value.map((m) => ({
  role: m.role,
  content: m.role === 'assistant'
    ? stripToolCalls(contentTextOf(m))            // assistant 永远是 string
    : (m.content ?? contentTextOf(m)),            // user: 数组形态原样传, string 保持
}))
```

[chat.js contentTextOf/activeChunksOf](frontend/src/stores/chat.js) 扩展：content 是数组时拼接所有 `type==='text'` 段。

#### 6.4 user 消息渲染

[AssistantPanel.vue:194-199](frontend/src/ide/AssistantPanel.vue#L194-L199) 当前是 6 行纯文本气泡。改为：

```vue
<div v-else class="msg-body user-msg">
  <div class="msg-content">
    <div v-if="msg._attachments?.length" class="msg-attachments">
      <img v-for="a in msg._attachments" :key="a.id" :src="a.thumbDataUrl" :alt="a.name"
           class="msg-attachment-thumb" @click="openImagePreview(a.base64DataUrl)" />
    </div>
    <pre class="user-text">{{ contentText(msg) }}</pre>
  </div>
</div>
```

#### 6.5 边界

- 单图 ≤ 5 MB；超过弹错
- 缩略图 max 200×200，只存前端用；原图 base64 才发后端
- MIME 仅 `image/png|jpeg|webp|gif`
- 单条消息 ≤ 5 张

---

### §7 后端协议分层（chat.py 多协议改造）

#### 7.1 现状 → 目标结构

```text
chat_completions(req)
  ├─ protocol = req.protocol            # 'openai' | 'anthropic'
  ├─ extras  = _build_request_extras(protocol, model, reasoning_mode)
  └─ if protocol == 'anthropic':
        client = _get_anthropic_client(req.api_key)
        stream = _stream_anthropic(client, messages, model, max_tokens, extras)
     else:
        client = _get_async_client(req.base_url, req.api_key)
        stream = _stream_openai(client, messages, model, max_tokens, extras)
     return StreamingResponse(stream, media_type='text/event-stream')
```

**两个 stream 函数发出完全相同的 SSE 帧**：`{delta}` / `{reasoning}` / `{error}` / `[DONE]`。前端 chat.js 不感知协议差异。

#### 7.2 _stream_openai

重命名自当前 `_stream_chat`，逻辑保持。

#### 7.3 _stream_anthropic

```python
async def _stream_anthropic(client, messages, model, max_tokens, extras):
    system_text, ua_msgs = _split_system(messages)
    anthropic_msgs = [_openai_msg_to_anthropic(m) for m in ua_msgs]

    try:
        async with client.messages.stream(
            model=model, max_tokens=max_tokens,
            system=system_text or None,
            messages=anthropic_msgs,
            **extras,
        ) as stream:
            async for event in stream:
                if event.type == 'content_block_delta':
                    d = event.delta
                    if d.type == 'thinking_delta':
                        yield f"data: {json.dumps({'reasoning': d.thinking}, ensure_ascii=False)}\n\n"
                    elif d.type == 'text_delta':
                        yield f"data: {json.dumps({'delta': d.text}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
```

#### 7.4 _openai_msg_to_anthropic

```python
def _split_system(messages):
    sys_parts = [m['content'] for m in messages if m['role'] == 'system' and isinstance(m['content'], str)]
    ua = [m for m in messages if m['role'] != 'system']
    return ('\n\n'.join(sys_parts), ua)

def _openai_msg_to_anthropic(msg):
    content = msg['content']
    if isinstance(content, str):
        return {"role": msg['role'], "content": content}
    parts = []
    for p in content:
        if p['type'] == 'text':
            parts.append({"type": "text", "text": p['text']})
        elif p['type'] == 'image_url':
            url = p['image_url']['url']
            if url.startswith('data:'):
                media_type = url.split(';')[0].split(':')[1]
                b64 = url.split(',', 1)[1]
                parts.append({"type": "image",
                              "source": {"type": "base64",
                                         "media_type": media_type, "data": b64}})
            else:
                parts.append({"type": "image",
                              "source": {"type": "url", "url": url}})
    return {"role": msg['role'], "content": parts}
```

#### 7.5 工具调用循环（与其他厂商对等）

KMatch 的工具调用是**提示词协议**（让模型输出 `<tool_call>{json}</tool_call>` 文本，前端切片解析；见 [chat.js:660-720](frontend/src/stores/chat.js#L660-L720)），**不是 OpenAI native tools**。

因此 Anthropic 模型同样能跑工具循环 — Claude 4+ 对结构化提示词遵循度好。**本期不为 Anthropic 做工具循环降级**。

唯一要确认的是实测时 Claude 对 `<tool_call>` 指令的遵循度；如不达标，再单独 spec 补 fallback。

#### 7.6 其他改动

- [backend/requirements.txt](backend/requirements.txt) 加 `anthropic>=0.40.0`
- `_resolve_client` 拆为 `_resolve_openai_client` + `_resolve_anthropic_client`
- ChatRequest 加 `protocol: Literal['openai','anthropic'] = 'openai'`、`reasoning_mode: Literal['auto','fast','deep'] = 'auto'`

---

## 4. 测试策略

### 4.1 前端单测（Vitest）

- `customProviders-store.test.js`：CRUD（add/update/remove/get）+ autoFetchModels（mock window.api.http）
- `modelCapabilities.test.js`：每条 PROVIDERS × 每个 fallbackModel 跑 capabilityOf
- `modelVision-store.test.js`：probe / hasVision 三态 / clearAll / clearForBaseUrl
- `aiSettings-store.test.js` 扩展：
  - 旧 customBaseUrl 迁移到 customProviders 列表（id=default）
  - `provider='custom:default'` 形态下 getBaseUrl/providerMeta
  - reasoningMode='deep' 在不支持模型上自动降级到 'auto'
  - **修改旧断言**：Claude → `'native'` 而非 `'native-when-supported-by-backend'`
- `chat-attachments.test.js`：addAttachment 压缩缩略图、sendMessage 用 OpenAI 数组 content、`_attachments` 不发后端
- `chat-ai-settings.test.js` 扩展：`reasoning_mode` + `protocol` 字段正确传出

### 4.2 后端单测（pytest）

- `test_chat_models.py`：protocol=openai 透传 / protocol=anthropic 返回硬编码列表
- `test_probe_vision.py`：cache 命中 / auth 错不写缓存 / 普通错写 False / DELETE 清空
- `test_build_request_extras.py`：DeepSeek-V4 / o1/o3 / Anthropic / 其他模型 × auto/fast/deep 九宫格
- `test_stream_openai_anthropic_frame_parity.py`：两个 stream 函数发出 SSE 帧形状一致
- `test_openai_msg_to_anthropic.py`：text-only / image_url(data:) / image_url(url) / system 拆分

### 4.3 手测（CDP）

[scripts/cdp_probe.py](scripts/cdp_probe.py) 注入：

- 切换厂商 → 模型列表更新 + reasoning 按钮 enable 状态变化
- 选中 vision 模型 → 探测起飞 → 📎 按钮亮
- DeepSeek-V4 切 deep/fast → 后端真实请求 `extra_body.thinking` 值正确
- Anthropic 模型 + 图片 → 模型回包
- Anthropic 模型 + 工具调用（read_file）→ 提示词协议生效

---

## 5. 影响面 / 文件清单

### 新增

- [frontend/src/stores/customProviders.js](frontend/src/stores/customProviders.js)
- [frontend/src/stores/modelVision.js](frontend/src/stores/modelVision.js)
- [frontend/src/services/llm/modelCapabilities.js](frontend/src/services/llm/modelCapabilities.js)
- `frontend/src/assets/icons/llm_providers/*.svg` — 8 个，从 Apix 复制

### 修改

- [frontend/src/stores/aiSettings.js](frontend/src/stores/aiSettings.js)
  - PROVIDERS 扩 8 项 + `protocol`/`iconKey`/`fallbackModels`
  - provider 值域扩 `custom:<uuid>`（本期 uuid 固定为 'default'）
  - 删除 customBaseUrl（迁移到 customProviders）
  - providerApiKeys 字典加（按 provider 切换 apiKey）
  - modelReasoningSupport 内部委托 capabilityOf；签名保留
- [frontend/src/stores/chat.js](frontend/src/stores/chat.js)
  - pendingAttachments + sendMessage 多模态 content
  - contentTextOf/activeChunksOf 支持数组 content
  - 构建 apiMessages 时 user 消息原样传
  - body 字段：`reasoning_mode` + `protocol`，删除 `_reasoningForRequest`
- [frontend/src/ide/AssistantPanel.vue](frontend/src/ide/AssistantPanel.vue)
  - 工具栏加 reasoning radio 三态、📎 按钮 + 拖拽、预览条
  - 厂商下拉用 icon
  - 模型 hint 换成 select + badge
  - 🔑 弹窗保留（自定义 base URL 写到 customProviders[id=default]）
  - user 消息渲染加 `_attachments` 块
- [backend/app/api/chat.py](backend/app/api/chat.py)
  - ChatRequest 加 protocol/reasoning_mode
  - `_resolve_client` 拆双
  - `_stream_chat` → `_stream_openai` + `_stream_anthropic`
  - `_build_extra_body` → `_build_request_extras`
  - +`/probe-vision`、+DELETE `/probe-vision/cache`、`_load_vision_cache`/`_save_vision_cache`
  - +`ANTHROPIC_MODELS` 常量
- [backend/requirements.txt](backend/requirements.txt) +`anthropic>=0.40.0`

---

## 6. 实施顺序（PR 分包）

1. **PR-1 厂商注册表 + customProviders schema**：§1 + §2 store 改造 + §3.1 fetchModels。无 vision、无 UI 大改，最稳。
2. **PR-2 模型能力 metadata + reasoning UI**：§3.2 + §3.3 + §5 完整（含灰提示自动降级）。
3. **PR-3 Anthropic 协议**：§7 + requirements.txt。覆盖纯对话 + 提示词工具循环。
4. **PR-4 Vision 探测**：§4 完整（后端 endpoint + 前端 store + 触发时机）。
5. **PR-5 图片上传**：§6 完整。

每个 PR 独立可 merge；依赖按顺序。

---

## 7. 风险清单

- ⚠️ `el-radio-button` 单项 disabled 样式：Element Plus 2.8 部分版本灰色态对比度低，落地时肉眼验证，必要时加 custom CSS。
- ⚠️ Anthropic SDK 国内默认 endpoint 不通：用户配代理后才能用。安装包不内置代理。
- ⚠️ vision probe 烧用户 token：本期没有批量探测，单次切模型 1 次 × 100 tokens ≈ ¥0.001 量级。可忽略。
- ⚠️ Anthropic 模型对 `<tool_call>` 标签遵循度：实测验证 Claude 4+；如不达标单独 spec 加 fallback。
- ⚠️ `provider='custom:<uuid>'` 字符串解析散落：aiSettings 内集中提供 `isCustomProvider(p)` 和 `customProviderUuid(p)` helper，禁止其他文件自行 split。
