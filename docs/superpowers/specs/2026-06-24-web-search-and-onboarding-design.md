# Spec C — 联网搜索 + 资源时效性 + Onboarding 对话式引导

**日期**：2026-06-24
**作者**：origin0722
**借鉴来源**：[Apix](https://github.com/JJJJSTIYYYY/Apix) — `tools/web_search/` 整套
**前置**：Spec A + Spec B 都 merge

> 三 spec 中的最后一个。
>
> - **Spec A**（已写）：聊天框 Apix 化
> - **Spec B**（已写）：设置页 + Agent 独立 key
> - **Spec C（本文件）**：联网搜索 + Onboarding 对话式引导

---

## 1. 背景与目标

赛题 XH-202630 要求"个性化学习资源生成"。当前 [content_generator](backend/app/agents/content_generator.py) 仅依赖训练数据生成 Python 教学资源；Python 3.13 新特性、新框架 (FastAPI 0.137+, Pydantic 3+)、第三方库版本变化 (langchain 1.0+) 都在训练 cutoff 之后。**没有联网搜索 = 资源时效性受限于训练数据**。

赛题 M5 质量指标要求"覆盖率 ≥ 90%"——包括训练数据之外但知识图谱有节点的内容。联网搜索能扩一层"训练外覆盖"。

此外用户首次启动应用时面对三套未配置的 API（AI 助手 / Agent 学习引擎 / 搜索），需要清晰可视的引导，否则会困惑"我该填哪个"。

### 用户故事

- 「我让 AI 助手生成 Python 3.13 的 PEP 657 改进版异常追溯学习资料 —— AI 实时联网查 PEP 657 + Python 官方文档，生成包含**真实链接和发布日期**的资源。」
- 「学情检测识别我对 'asyncio 并发原语' 掌握薄弱 —— 资源生成 agent 联网搜 'asyncio Lock Event Semaphore tutorial 2025'，挑 5 篇高质量博客作为补充阅读。」
- 「首次启动看到聊天式引导卡片，逐步告诉我'第一步：填 Agent 学习引擎 API → 用来跑学情检测 / 生成资源 / 代码审查'，'第二步：填 AI 助手 API → 用来跟你对话'，'第三步：可选 — 填搜索 API → 给资源生成扩展时效'，每步带跳过。」

---

## 2. 范围与不在范围

### 范围

#### C-1 联网搜索后端

- 后端新增 `backend/app/tools/web_search/` 模块（仿 Apix `tools/web_search/`，但本期只 1 个 provider）
- Bing Web Search API 接入（Azure Cognitive Services，免费额度 1000 次/月）
- LangChain `@tool` 装饰器封装为 `search_web_by_keywords` 工具
- content_generator agent 提示词加入：「当遇到知识图谱节点对应的内容属于训练数据 cutoff 之后或细节不确定时，调 `search_web_by_keywords` 工具补充」
- 搜索结果带引用号 `[1][2][3]` 注入资源 markdown；前端渲染时 `[n]` 可点击跳原 URL
- Provider 抽象层支持未来扩展（DuckDuckGo / Bocha / anysearch.com 等）

#### C-2 设置页"联网搜索" Tab

- Spec B 的设置页加第四个段（落在 §3 供应商管理之后）
- 配置项：启用开关、provider 下拉（Bing / 未来加 anysearch 等）、API Key、每次搜索最大结果数（3-10）、是否在资源 markdown 显示引用号
- 同 Spec B 风格用 SettingCard 模板，复用锚点

#### C-3 Onboarding 对话式引导

- 新增 `frontend/src/ide/onboarding/OnboardingView.vue`，装载到 MainArea
- 首次启动检测：所有 key (agentLlm.apiKey + aiSettings.apiKey + searchApi.apiKey) 为空时，`sidebar.activeView = 'onboarding'`
- 4 步聊天式卡片：欢迎 → Agent 学习引擎 API → AI 助手 API → 搜索 API（可选）→ 完成
- 每步显示"为什么需要这个 / 如何获取 / 跳过 / 下一步"
- TitlebarMenu「帮助 → 重新引导」可手动再进

### 不在范围

- 多搜索 provider 同时启用（仅一个 active provider，多 provider 留接口）
- 内容抓取层（Apix 的 jina/crawl4ai 那种 URL → 正文）—— 本期只用 Bing snippet
- 给 reviewer/diagnostics/其他 agent 加联网搜索能力（仅 content_generator）
- 引用源去重 / 内容质量评分
- 多语言搜索结果（仅中文 + 英文混合，跟 Bing 默认相同）

---

## 3. 设计

### §1 联网搜索后端

#### 1.1 模块结构

```text
backend/app/tools/web_search/
├── __init__.py
├── models.py              # UrlResultItem 数据类
├── providers/
│   ├── __init__.py        # PROVIDER_REGISTRY
│   ├── base.py            # BaseSearchProvider abstract
│   └── bing.py            # BingProvider
├── manager.py             # search() 总入口, 选 provider 调用
└── tool.py                # LangChain @tool 装饰封装
```

#### 1.2 数据模型

`backend/app/tools/web_search/models.py`：

```python
from dataclasses import dataclass

@dataclass(slots=True)
class UrlResultItem:
    title: str
    url: str
    snippet: str | None = None       # Bing 返回的摘要
    source: str | None = None        # provider 名称 (用于调试)
    published_at: str | None = None  # ISO 日期, 若 provider 提供
```

#### 1.3 Provider 抽象

`backend/app/tools/web_search/providers/base.py`：

```python
from abc import ABC, abstractmethod
from app.tools.web_search.models import UrlResultItem

class BaseSearchProvider(ABC):
    name: str   # 'bing' / 'anysearch' / ...

    def __init__(self, api_key: str, **kwargs):
        self.api_key = api_key

    @abstractmethod
    async def search(self, query: str, *, count: int = 5,
                     lang: str = 'zh-CN') -> list[UrlResultItem]:
        """关键词搜索, 返回 URL 列表"""
```

`backend/app/tools/web_search/providers/bing.py`：

```python
import httpx
from app.tools.web_search.providers.base import BaseSearchProvider
from app.tools.web_search.models import UrlResultItem

class BingProvider(BaseSearchProvider):
    name = 'bing'
    endpoint = 'https://api.bing.microsoft.com/v7.0/search'

    async def search(self, query, *, count=5, lang='zh-CN'):
        headers = {'Ocp-Apim-Subscription-Key': self.api_key}
        params = {
            'q': query,
            'count': count,
            'mkt': lang,             # zh-CN / en-US
            'responseFilter': 'Webpages',
            'safeSearch': 'Moderate',
        }
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.get(self.endpoint, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

        items = []
        for w in (data.get('webPages', {}).get('value') or [])[:count]:
            items.append(UrlResultItem(
                title=w.get('name', ''),
                url=w.get('url', ''),
                snippet=w.get('snippet', ''),
                source='bing',
                published_at=w.get('dateLastCrawled', ''),
            ))
        return items
```

`backend/app/tools/web_search/providers/__init__.py`：

```python
from .bing import BingProvider

PROVIDER_REGISTRY: dict[str, type] = {
    'bing': BingProvider,
    # 'anysearch': AnysearchProvider,   # 未来
}

def build_provider(name: str, api_key: str):
    cls = PROVIDER_REGISTRY.get(name)
    if not cls:
        raise ValueError(f"Unknown search provider: {name}")
    return cls(api_key=api_key)
```

#### 1.4 manager

`backend/app/tools/web_search/manager.py`：

```python
from app.tools.web_search.providers import build_provider
from app.tools.web_search.models import UrlResultItem

async def search(
    query: str,
    *,
    provider: str,
    api_key: str,
    count: int = 5,
    lang: str = 'zh-CN',
) -> list[UrlResultItem]:
    if not api_key:
        return []   # 未配置 key, 静默返回空, 不抛错 (agent 容错处理)
    p = build_provider(provider, api_key)
    try:
        return await p.search(query, count=count, lang=lang)
    except Exception as exc:
        # 后端日志记录, 不阻断 agent 主流程
        return []
```

#### 1.5 LangChain Tool 封装

`backend/app/tools/web_search/tool.py`：

```python
from langchain.tools import tool
from app.tools.web_search.manager import search
from app.config import settings

SEARCH_TOOL_DESC = """
当需要获取训练数据之后的信息（新版 Python 特性、新框架版本、近期发布的库）
或具体细节不确定时, 调用此工具搜索网络。

参数:
  query: 搜索关键词 (中英文均可), 例如 "Python 3.13 PEP 657" / "FastAPI 0.137 release notes"
  count: 期望结果数 (默认 5, 最大 10)

返回:
  JSON 字符串, 含 results: [{title, url, snippet, published_at}]
  使用搜索结果时, 在生成的内容中用 [1][2][3] 标注引用, 引用号对应 results 索引+1。
"""

async def make_search_tool(provider: str, api_key: str, count: int):
    """工厂函数, 按用户配置构造一个 tool 实例返给 agent。"""

    @tool(description=SEARCH_TOOL_DESC)
    async def search_web_by_keywords(query: str) -> str:
        results = await search(
            query, provider=provider, api_key=api_key,
            count=min(count, 10), lang='zh-CN',
        )
        import json
        return json.dumps({
            'count': len(results),
            'results': [
                {'index': i + 1, 'title': r.title, 'url': r.url,
                 'snippet': r.snippet, 'published_at': r.published_at}
                for i, r in enumerate(results)
            ],
        }, ensure_ascii=False)

    return search_web_by_keywords
```

#### 1.6 content_generator 集成

[backend/app/agents/content_generator.py](backend/app/agents/content_generator.py) 当前流程：knowledge_graph 节点输入 → LLM 生成 markdown 资源 → 返回。

改造：

```python
async def content_generator_node(
    target_concepts: list[str],
    user_profile: dict,
    *,
    llm_overrides: dict | None = None,
    search_config: dict | None = None,   # 新增 {provider, api_key, count, enabled}
):
    model = get_chat_model(overrides=llm_overrides)

    # 构造工具列表
    tools = []
    if search_config and search_config.get('enabled') and search_config.get('api_key'):
        tools.append(await make_search_tool(
            search_config['provider'],
            search_config['api_key'],
            search_config.get('count', 5),
        ))

    # bind_tools 让 langchain ChatOpenAI agent 能调
    if tools:
        model = model.bind_tools(tools)

    # 系统提示词追加联网搜索指导 (仅当 tools 存在)
    sys_prompt = build_sys_prompt(
        target_concepts, user_profile,
        with_search=bool(tools),
    )

    # ... 后续 LLM 调用循环, 处理 tool_calls ...
```

提示词加段（仅在 with_search=True 时拼入）：

```text
## 联网搜索指引

当遇到以下情形,可调 search_web_by_keywords 工具:
1. 知识点涉及 2024 年后的 Python 版本特性 (3.13+)
2. 知识点涉及最近发布的库/框架版本变化
3. 你对某个 API 的最新签名或行为不确定
4. 需要引用官方文档或权威博客作为参考链接

搜索结果用 [1][2][3] 在文中标注引用,文末附上 ## 参考资源 列表 (标题 + URL)。
不要为已掌握的基础知识 (变量/循环/列表推导式等) 搜索,浪费配额。
```

⚠️ langchain 1.0+ `bind_tools` 在 ChatOpenAI 实例可用；DeepSeek/Moonshot 等 OpenAI 兼容 API 支持 OpenAI tools 协议。**Anthropic agent 调用本期不存在（Spec B 限制 Agent 仅 OpenAI 兼容）**，因此 tools 协议问题已规避。

#### 1.7 API 路由

[backend/app/api/diagnostics.py](backend/app/api/diagnostics.py) 等路由请求体补 `search_config` 字段：

```python
class AssessRequest(BaseModel):
    user_profile: dict
    target_concepts: list[str] | None = None
    llm_overrides: dict | None = None
    search_config: dict | None = None   # 新增
```

routes 透传 `search_config` 到 agent。Spec B 的 axios interceptor 同样负责注入 `search_config`（跟 `llm_overrides` 同位置）。

---

### §2 设置页"联网搜索" Tab

Spec B 的设置页 §3 供应商管理之后追加新段：

#### 2.1 store

新增 `frontend/src/stores/searchApi.js`，独立 localStorage key `kmatch-search-api`：

```js
export const useSearchApiStore = defineStore('searchApi', () => {
  const state = ref(loadState())
  // 默认: { enabled: false, provider: 'bing', apiKey: '', count: 5,
  //         showCitations: true }

  function setEnabled(on)    { state.value.enabled = on; persist() }
  function setProvider(p)    { state.value.provider = p; persist() }
  function setApiKey(k)      { state.value.apiKey = k; persist() }
  function setCount(n)       { state.value.count = Math.max(1, Math.min(10, n)); persist() }
  function setShowCitations(on) { state.value.showCitations = on; persist() }

  /** 返回供 axios interceptor 注入的配置;关闭/无 key 时返回 null */
  function buildSearchConfig() {
    if (!state.value.enabled) return null
    if (!state.value.apiKey?.trim()) return null
    return {
      enabled: true,
      provider: state.value.provider,
      api_key: state.value.apiKey,
      count: state.value.count,
    }
  }

  return { state, setEnabled, setProvider, setApiKey, setCount, setShowCitations, buildSearchConfig }
})
```

#### 2.2 axios interceptor 扩展

Spec B §4.2 的 interceptor 同时注入 `search_config`：

```js
import { useAgentLlmStore } from '@/stores/agentLlm'
import { useSearchApiStore } from '@/stores/searchApi'

axiosInstance.interceptors.request.use((config) => {
  const isAgentRoute = AGENT_ROUTES.some((p) => config.url.startsWith(p))
  if (!isAgentRoute) return config

  const overrides = useAgentLlmStore().buildOverrides()
  const searchConfig = useSearchApiStore().buildSearchConfig()
  const extras = {}
  if (overrides)    extras.llm_overrides = overrides
  if (searchConfig) extras.search_config = searchConfig

  if (Object.keys(extras).length === 0) return config

  config.data = { ...(config.data || {}), ...extras }
  return config
})
```

#### 2.3 UI

新增 `frontend/src/ide/settings/SearchSettings.vue`：

```vue
<SettingCard title="启用联网搜索"
             info="生成学习资源时,Agent 可自动调用搜索获取最新 Python/框架信息">
  <el-switch :model-value="searchApi.state.enabled"
             @change="searchApi.setEnabled($event)" />
</SettingCard>

<template v-if="searchApi.state.enabled">
  <SettingCard title="搜索 Provider">
    <el-select :model-value="searchApi.state.provider" @change="searchApi.setProvider">
      <el-option label="Bing Web Search" value="bing" />
      <!-- 未来扩展:
      <el-option label="Anysearch" value="anysearch" />
      <el-option label="DuckDuckGo (免 key)" value="duckduckgo" /> -->
    </el-select>
  </SettingCard>

  <SettingCard title="API Key"
               info="Bing 在 Azure Portal 创建 Cognitive Services Bing Search v7 获取">
    <el-input type="password" show-password
              :model-value="searchApi.state.apiKey"
              @change="searchApi.setApiKey" />
    <el-link href="https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/overview"
             target="_blank">如何获取 Bing API Key →</el-link>
  </SettingCard>

  <SettingCard title="每次搜索返回结果数"
               info="3-10 之间, 默认 5。过多浪费 token 和 API 配额">
    <el-input-number :model-value="searchApi.state.count"
                     :min="3" :max="10"
                     @change="searchApi.setCount" />
  </SettingCard>

  <SettingCard title="在资源中显示引用编号"
               info="资源 markdown 末尾附 ## 参考资源 列表 (推荐开启, 提升可信度)">
    <el-switch :model-value="searchApi.state.showCitations"
               @change="searchApi.setShowCitations($event)" />
  </SettingCard>

  <SettingCard title="测试搜索" info="发一次最小查询验证 key 可用">
    <el-input v-model="testQuery" placeholder="Python 3.13" />
    <el-button type="primary" @click="testSearch" :loading="testing">测试</el-button>
    <div v-if="testResult" class="test-result">
      <div v-for="r in testResult" :key="r.url" class="result-item">
        <a :href="r.url" target="_blank">{{ r.title }}</a>
        <p>{{ r.snippet }}</p>
      </div>
    </div>
  </SettingCard>
</template>
```

"测试搜索"调新端点 `POST /api/web-search/test`：

```python
@router.post("/test")
async def test_search(req: TestSearchRequest):
    results = await search(
        req.query, provider=req.provider, api_key=req.api_key,
        count=3, lang='zh-CN',
    )
    return {'ok': True, 'results': [asdict(r) for r in results]}
```

#### 2.4 资源消息中的引用渲染

content_generator 生成的 markdown 形如：

```markdown
PEP 657 [1] 改进了 Python 3.13 的异常追溯, 现在能精确指出表达式中哪个子部分出错。

## 参考资源
1. [PEP 657 – Include Fine Grained Error Locations](https://peps.python.org/pep-0657/)
2. [Python 3.13 What's New](https://docs.python.org/3/whatsnew/3.13.html)
```

前端 [MarkdownViewer](frontend/src/components/MarkdownViewer.vue)（或对应组件）天然渲染 markdown 链接为可点击。无需特殊改造。

---

### §3 Onboarding 对话式引导

#### 3.1 触发条件

`frontend/src/ide/onboarding/onboardingChecker.js`：

```js
import { useAiSettingsStore } from '@/stores/aiSettings'
import { useAgentLlmStore } from '@/stores/agentLlm'
import { useSearchApiStore } from '@/stores/searchApi'

const ONBOARDING_DONE_KEY = 'kmatch-onboarding-done'

export function shouldShowOnboarding() {
  // 用户已显式跳过/完成 → 不再自动触发
  if (localStorage.getItem(ONBOARDING_DONE_KEY) === 'true') return false

  // 全部 key 都为空时才弹
  const ai = useAiSettingsStore()
  const ag = useAgentLlmStore()
  const sr = useSearchApiStore()

  const aiKey   = (ai.apiKey || '').trim()
  const agKey   = (ag.state.apiKey || '').trim()
  const srKey   = (sr.state.apiKey || '').trim()

  return !aiKey && !agKey && !srKey
}

export function markOnboardingDone() {
  localStorage.setItem(ONBOARDING_DONE_KEY, 'true')
}
```

应用启动时（Workspace.vue 或 App.vue 的 onMounted）：

```js
import { shouldShowOnboarding } from '@/ide/onboarding/onboardingChecker'

onMounted(() => {
  if (shouldShowOnboarding()) {
    sidebar.setView('onboarding')
  }
})
```

`sidebar.activeView` 扩 `'onboarding'`。[MainArea.vue](frontend/src/ide/MainArea.vue) v-if 链加分支：

```vue
<OnboardingView v-if="sidebar.activeView === 'onboarding'" />
```

#### 3.2 OnboardingView 主体

`frontend/src/ide/onboarding/OnboardingView.vue`：

```text
┌────────────────────────────────────────────────┐
│              KMatch·知链 欢迎使用!               │
│                                                  │
│   ┌──────────────────────────────────────────┐ │
│   │  助手  你好! 让我用 4 步帮你完成首次配置   │ │
│   │       (大约 2 分钟, 可随时跳过)           │ │
│   └──────────────────────────────────────────┘ │
│                                                  │
│   ┌──────────────────────────────────────────┐ │
│   │  助手  第一步: Agent 学习引擎 API          │ │
│   │       它负责跑学情检测/生成资源/代码审查/  │ │
│   │       代码测试等后端 Agent 工作。          │ │
│   │       推荐用 DeepSeek (国内访问快、便宜)。 │ │
│   │       [获取 DeepSeek API Key →]            │ │
│   └──────────────────────────────────────────┘ │
│                                                  │
│   ┌──────────────────────────────────────────┐ │
│   │  你  [Provider 下拉] [API Key 输入]       │ │
│   │      [跳过] [下一步 →]                    │ │
│   └──────────────────────────────────────────┘ │
│                                                  │
│   ●─○─○─○                                       │
│   (4 步进度指示器)                              │
└────────────────────────────────────────────────┘
```

4 步内容：

| 步 | 主题 | 引导文字 | 输入控件 | 必填 |
| --- | --- | --- | --- | --- |
| 1 | 欢迎 | 简短介绍 + 4 步预告 | 无 | - |
| 2 | Agent 学习引擎 | 解释用途 + 推荐 DeepSeek + 提供获取链接 | provider 下拉 + apiKey 输入 | 可跳 |
| 3 | AI 助手 | 解释用途 + 推荐"同 Agent / 用另一家" + 链接 | provider 下拉 + apiKey 输入 | 可跳 |
| 4 | 联网搜索 | 解释用途（提升资源时效性）+ 标"可选" + 推荐 Bing | provider 下拉 + apiKey 输入 + 启用开关 | 可跳 |
| 5（完成） | 完成 | 总结所填内容 + "进入应用" | 无 | - |

**输入控件绑定的目标 store**（避免实现时疑问）：

- 步 2 → `agentLlm.state` 的 provider/apiKey（Spec B §4.1 引入）
- 步 3 → `aiSettings` 的 provider/apiKey（Spec A 现状）
- 步 4 → `searchApi.state` 的 provider/apiKey/enabled（Spec C §2.1）

#### 3.3 交互细节

- 每步用 transition-fade-in 进入，类似聊天气泡逐条出现
- 控件用 Spec B 同款 SettingCard 风格（保持视觉一致）
- 「跳过」直接进下一步且当前步不存值
- 「下一步」前若有未填 key 弹 confirm「确认跳过此项？以后可在设置页配置」
- 最后一步「完成」按钮 → markOnboardingDone() + `sidebar.setView('code')`
- 顶部「× 关闭引导」按钮永久跳过

#### 3.4 "重新引导"入口

TitlebarMenu 加菜单项 `帮助 → 重新引导`：

```js
function rerunOnboarding() {
  localStorage.removeItem(ONBOARDING_DONE_KEY)
  sidebar.setView('onboarding')
}
```

---

## 4. 测试策略

### 4.1 前端单测

- `searchApi-store.test.js`：state CRUD、buildSearchConfig 在 enabled=false / apiKey 空时返回 null
- `axios-interceptor-search.test.js`：search_config 注入路径正确、与 llm_overrides 共存不冲突
- `onboarding-checker.test.js`：三 key 全空时 should = true；任一 key 已配置时 = false；done 标记后 = false
- `onboarding-view.test.js`：4 步可前进 / 后退 / 跳过；最后 markOnboardingDone() 被调

### 4.2 后端单测

- `test_bing_provider.py`：mock httpx response → 解析 webPages 正确成 UrlResultItem
- `test_web_search_manager.py`：build_provider 路由正确；未知 provider 抛错；空 key 返回空列表（不抛错）
- `test_search_tool.py`：tool 调用返回 JSON 含 results、count；空 key 返回 count=0
- `test_content_generator_with_search.py`：search_config 启用时 model.bind_tools 被调；提示词含联网搜索指引；未启用时 tools=[]
- `test_routes_search_config.py`：search_config 字段从 body 透传到 content_generator

### 4.3 手测（真实 Bing key）

- 进设置页填 Bing key + 启用 → 测试搜索"Python 3.13" → 看返回 3 条 + snippet
- 跑场景一学情测评（包含资源生成）→ 后端日志看 tool_calls 调到 search_web_by_keywords → 生成的 markdown 含 `[1][2]` 引用 + 末尾参考资源列表
- 清 localStorage 重启 → MainArea 自动进 Onboarding → 4 步走完 → 进 code 视图
- 菜单"帮助 → 重新引导"→ 再进 Onboarding

---

## 5. 影响面 / 文件清单

### 新增

- `backend/app/tools/web_search/__init__.py`
- `backend/app/tools/web_search/models.py`
- `backend/app/tools/web_search/providers/__init__.py`
- `backend/app/tools/web_search/providers/base.py`
- `backend/app/tools/web_search/providers/bing.py`
- `backend/app/tools/web_search/manager.py`
- `backend/app/tools/web_search/tool.py`
- `backend/app/api/web_search.py` — `POST /api/web-search/test` 端点
- `frontend/src/stores/searchApi.js`
- `frontend/src/ide/settings/SearchSettings.vue`
- `frontend/src/ide/onboarding/OnboardingView.vue`
- `frontend/src/ide/onboarding/onboardingChecker.js`
- `frontend/src/ide/onboarding/StepCard.vue` — onboarding 步骤气泡卡片

### 修改

- [backend/app/agents/content_generator.py](backend/app/agents/content_generator.py)
  - content_generator_node 签名加 `search_config: dict | None`
  - 启用时 model.bind_tools(make_search_tool(...))
  - 提示词构造加 with_search 参数
- [backend/app/api/diagnostics.py](backend/app/api/diagnostics.py) + [learning.py](backend/app/api/learning.py)
  - 请求体加 `search_config` 字段
  - 透传到 content_generator_node
- [backend/requirements.txt](backend/requirements.txt) — 加 `httpx>=0.27.0`（如未有；多半已在）
- [frontend/src/api/index.js](frontend/src/api/index.js) — interceptor 同时注入 search_config
- [frontend/src/stores/sidebar.js](frontend/src/stores/sidebar.js) — activeView 扩 `'onboarding'`
- [frontend/src/ide/MainArea.vue](frontend/src/ide/MainArea.vue) — v-if 链加 OnboardingView
- [frontend/src/ide/TitlebarMenu.vue](frontend/src/ide/TitlebarMenu.vue) — 加"帮助 → 重新引导"
- [frontend/src/ide/settings/SettingsView.vue](frontend/src/ide/settings/SettingsView.vue) — 加 §4 联网搜索 section + 锚点
- 启动入口（Workspace.vue 或 App.vue onMounted）— shouldShowOnboarding 判断

---

## 6. 实施顺序（PR 分包）

1. **PR-1 联网搜索骨架**：§1.1-1.5 后端 web_search 模块 + Bing provider + LangChain tool 封装 + 单测 + `POST /api/web-search/test` 端点
2. **PR-2 content_generator 集成**：§1.6 + §1.7 — agent 加 search_config 参数、提示词补充、路由透传
3. **PR-3 设置页联网搜索 Tab**：§2 — searchApi store + axios interceptor 扩展 + SearchSettings.vue
4. **PR-4 OnboardingView**：§3 — checker + view + 4 步流程 + TitlebarMenu 重新引导
5. **PR-5 Onboarding 触发联动**：启动检测 + sidebar/MainArea 集成

---

## 7. 风险清单

- ⚠️ Bing API 在 Azure 创建：用户首次拿 key 流程复杂（需 Azure 账号 + 创建 Cognitive Services 资源），onboarding 里给清晰链接 + 截图教程（短期截图、不放仓库）
- ⚠️ Bing API 国内访问：测试时务必验证；如需代理，复用 Spec B §5.3 的 proxy 注入路径（搜索走 sidecar，sidecar 已有 HTTP_PROXY）
- ⚠️ LangChain `bind_tools` 在 DeepSeek/Moonshot 兼容性：DeepSeek-V3+/Moonshot k2 支持 OpenAI tools；deepseek-reasoner 不支持 tools (官方文档明确)。提示词加段：「reasoner 模型不支持工具调用，请用 v3/v4-pro」
- ⚠️ Anthropic Agent 调用本期不支持（Spec B 限制）→ 联网搜索自然也不在 Anthropic 路径上。一致
- ⚠️ Onboarding"必填 key"边界：实际三个 key 全可跳过（不阻断进应用），但跳过后 AI 助手发对话会 fail；用户友好的做法是聊天框头部加红色徽章「未配置 API Key → 进设置」。这条留给 Spec B 实现时一起做（不在 Spec C 范围）
- ⚠️ 引用号 [n] 在历史消息中保持有效：当前不持久化 chat history (Spec A §8.5 已确认)，刷新后引用列表与文中数字仍匹配 (markdown 自带)。无需额外处理
- ⚠️ Bing API 配额：免费 1000 次/月。若用户激进调用，单次场景一测评 → 5-10 个知识点 × 1 次搜索 = 单次 5-10 配额。设置页"每次返回 N 条"已限。后期可加日配额警告 (本期不做)
- ⚠️ anysearch.com 待用户提供文档：本期不接，但 PROVIDER_REGISTRY 已留接口；下一期收到具体 API 文档后实现一个 AnysearchProvider 类即可，零核心改动

---

## 8. 未来扩展

- DuckDuckGo（免 key、隐私优先）作为第二个 provider
- anysearch.com / Bocha（中国友好）按用户实际可用性补
- 内容抓取层（Jina Reader / Crawl4ai）：搜索结果 URL 进一步抓正文，给 LLM 更深上下文（当前只用 snippet）
- 联网搜索给 reviewer agent（验证生成资源中事实性引用正确）
- 多语言（mkt 参数动态切换 zh-CN/en-US）
- 搜索结果缓存（同 query 24h 内复用，省配额）
