# Spec B — 设置页 + Agent 学习引擎独立 key + 盘活孤儿 store 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 Apix 线性式设置页（三段：AI 助手 / Agent 学习引擎 / 供应商管理），让 Agent 学习引擎能用与 AI 助手独立的 LLM key 运行，并盘活 `toolPermissions` / `memories` / `proxy` 三个有数据无 UI 的孤儿 store 字段。

**Architecture:** 后端用 `contextvars.ContextVar` 承载 per-request 的 `llm_overrides`——`get_default_chat_model()` 读 ContextVar，9 处 LLM 调用点零改动。工作流路径（demo 全流程）在 LangGraph 节点入口从 `state["llm_overrides"]` set/reset ContextVar；content_generator 的 ThreadPoolExecutor 工作线程通过闭包捕获的 overrides 在 `_safe_generate` 内重新 set（子线程不继承 ContextVar）。直调路径（submit/feedback/learning report/project review/test）在路由层用 `with use_llm_overrides(...)` 上下文管理器包裹。前端不依赖 axios interceptor（agent 路由分走 axios `/api/diagnostics` 与直 IPC `window.api.http` SSE/project 两条路，interceptor 漏注入），改用显式 `withOverrides(body)` helper 在 6 个调用点注入 `llm_overrides`。proxy 配置经 IPC 落 `proxy-cache.json`，main 进程 spawn sidecar 时注入 `HTTP_PROXY`/`HTTPS_PROXY` env。

**Tech Stack:** FastAPI + LangGraph + langchain_openai（后端）; Vue3 + Pinia + Element Plus + Vitest + @vue/test-utils（前端）; Electron main + IPC（proxy env 注入）。复用 Spec A 已落地的 `customProviders` / `modelVision` store / `PROVIDERS` protocol / `/api/chat/probe-vision` / `modelCapabilities`。

---

## 关键设计决策（实现时务必遵守）

1. **ContextVar 而非参数透传。** Spec 原文设想「7 agent 函数加 `llm_overrides` 参数透传」，但实测 9 处 LLM 调用全在深层 helper（`_grade`/`_demo_answer`/`_generate_one`/`_llm_review` 等），参数透传需改 9 处签名 + 全链路上游 + 所有 monkeypatch `get_default_chat_model` 的单测。改用 ContextVar：`get_default_chat_model()` 内部读 `overrides = _current_overrides.get()`，无 override 时走 `settings` 默认（行为不变），单测无需改。

2. **ContextVar 跨线程不自动传播。** `content_generator_node` 用 `ThreadPoolExecutor` 并发调 `_generate_one`（`backend/app/agents/content_generator.py:206`）。Python ContextVar 不跨线程传递。解法：`_safe_generate` 闭包捕获 `overrides`，在工作线程内 `token = _current_overrides.set(overrides)` → 调用 → `finally: _current_overrides.reset(token)`。这是唯一需要特殊处理的并发点（grep 确认其余 agent 无线程池）。

3. **前端注入走显式 helper，不走 axios interceptor。** Agent 路由前端调用分两条路：
   - axios 实例：`/api/diagnostics/assess` `/submit` `/feedback`（`frontend/src/api/diagnostics.js`）
   - 直 IPC `window.api.http`：`/api/diagnostics/assess/stream`（SSE，`assessment.js`）、`/api/project/review` `/test`（`chat.js _delegate`）
   axios interceptor 漏注 SSE + project 两条直 IPC 路。改为在 6 个调用点用 `withOverrides(body)` helper 统一注入，覆盖完整。

4. **`/api/learning/report` 前端无调用方**（grep 确认），仍加 overrides 透传以对齐契约（后端补跑 graph_controller/content_generator/reviewer），但前端不需注入点。

5. **Agent 本期仅 OpenAI 协议。** `agentLlm` store `protocol` 固定 `'openai'`；UI 厂商下拉把 anthropic 选项 disabled + tooltip。`buildOverrides()` 不含 protocol 分支（始终 openai）。

6. **lru_cache 单例保留。** Spec 说「移除 `get_default_chat_model` 的 lru_cache」。但 ContextVar 方案下，`get_default_chat_model()` 每次 read ContextVar 后 `get_chat_model(overrides=...)` 按需构造——lru_cache 缓存的是「无 override 时的默认实例」，与 per-request override 互不冲突。保留 lru_cache 维持 `test_default_chat_model_is_singleton` 通过；override 路径不进缓存（`get_chat_model` 直接返回新实例）。⚠️ 任务 1 实现见精确代码。

7. **proxy 是唯一需落盘的配置。** main 进程启动早于 renderer，无法从 localStorage 读 proxy；落 `app.getPath('userData')/proxy-cache.json`。其余设置（apiKey/model/...）只 renderer 用，不落盘到 main。

8. **TitlebarMenu 已有 `view.<id>` 自动路由。** `TitlebarMenu.vue:80` 的 `runCommand` 已对 `view.` 前缀命令调 `sidebar.setView(id)`，且已有 `view.ai-settings` 占位 stub（75-79 行）。新增设置菜单项只需 `command: 'view.settings'`，删掉 stub 提示。

---

## File Structure

### 新增

| 文件 | 职责 |
| --- | --- |
| `frontend/src/stores/agentLlm.js` | Agent 独立 LLM 配置 store（useOverrides/provider/apiKey/baseUrl/model + buildOverrides） |
| `frontend/src/services/llm/overrides.js` | `withOverrides(body)` helper —— 注入 agentLlm.buildOverrides() 到请求 body |
| `frontend/src/ide/settings/SettingsView.vue` | 设置页主壳（线性滚动 + sticky 锚点侧栏 + IntersectionObserver） |
| `frontend/src/ide/settings/SettingCard.vue` | 公共卡片 slot 组件（title/info/control） |
| `frontend/src/ide/settings/AssistantSettings.vue` | §1 AI 助手段（厂商/模型/key 表单 + 思考模式 + 工具权限 + 记忆 + 清聊天历史） |
| `frontend/src/ide/settings/AgentSettings.vue` | §2 Agent 学习引擎段（开关 + key/baseUrl/model + 测试连接） |
| `frontend/src/ide/settings/ProvidersSettings.vue` | §3 供应商管理段（customProviders CRUD + 批量 vision + 清缓存 + 网络代理） |
| `frontend/src/ide/settings/ProviderEditDialog.vue` | 新建/编辑自定义厂商对话框 |
| `backend/app/api/agents.py` | `POST /api/agents/ping` —— 用 overrides 构造 ChatOpenAI 发 ping 验证可用 |
| `electron/main/proxy-cache.js` | proxy 配置落盘读写（userData/proxy-cache.json） |

### 修改

| 文件 | 改动 |
| --- | --- |
| `backend/app/agents/llm.py` | 加 ContextVar `_current_overrides` + `use_llm_overrides` 上下文管理器；`get_chat_model` 加 `overrides` 参数；`get_default_chat_model` 读 ContextVar |
| `backend/app/agents/state.py` | `AgentState` 加 `llm_overrides: dict` 字段；`make_initial_state` 加 `llm_overrides` 参数 |
| `backend/app/agents/diagnostics.py` | `diagnostics_node._node` 入口 set/reset ContextVar from state |
| `backend/app/agents/content_generator.py` | `content_generator_node._node` 入口 set；`_safe_generate` 工作线程内 set/reset |
| `backend/app/agents/reviewer.py` | `reviewer_node._node` 入口 set/reset |
| `backend/app/agents/code_reviewer.py` | `llm_review_code` 入口参数加 overrides + set/reset（直调函数） |
| `backend/app/agents/code_tester.py` | `llm_generate_tests` 入口参数加 overrides + set/reset（直调函数） |
| `backend/app/api/diagnostics.py` | AssessRequest/SubmitRequest/FeedbackRequest 加 `llm_overrides`；3 路由透传到 make_initial_state / _grade / _build_profile / regenerate_for_feedback |
| `backend/app/api/learning.py` | LearningReportRequest 加 `llm_overrides`；路由用 `use_llm_overrides` 包裹补跑管线 |
| `backend/app/api/project.py` | ReviewRequest/TestRequest 加 `llm_overrides`；2 路由透传到 review_code / run_tests |
| `backend/app/main.py` | 注册 `agents.router`（prefix `/api/agents`） |
| `frontend/src/api/diagnostics.js` | 4 函数 body 经 `withOverrides()` 注入 |
| `frontend/src/stores/chat.js` | project review/test body 经 `withOverrides()` 注入；加 `clearMessages()` 方法 |
| `frontend/src/stores/sidebar.js` | `activeView` 注释扩 `'settings'`（值域已任意字符串，无需改逻辑） |
| `frontend/src/ide/ActivityBar.vue` | 底部加齿轮按钮 → `sidebar.setView('settings')` |
| `frontend/src/ide/TitlebarMenu.vue` | 工具菜单加「设置」项 `command: 'view.settings'`；删 `view.ai-settings` stub |
| `frontend/src/ide/MainArea.vue` | v-if 链加 `<SettingsView v-if="sidebar.activeView === 'settings'" />` |
| `electron/preload/index.js` | 暴露 `window.api.setProxyConfig` / `getProxyConfig` / `restartBackend` |
| `electron/main/backend-sidecar.js` | `spawnBackend` env 注入 proxy；导出 `restartBackend` |
| `electron/main/ipc/proxy.js` | 新增 IPC handler：setProxyConfig/getProxyConfig/restartBackend |
| `electron/main/index.js` | 注册 proxy IPC + 启动握手 |

---

## PR 分包（对齐 spec §6）

- **PR-1 设置视图骨架**：Task 1-7（sidebar 注释 + ActivityBar 齿轮 + TitlebarMenu + MainArea + SettingCard + SettingsView 空壳 + 锚点导航）
- **PR-2 Tab 1 AI 助手**：Task 8-12（AssistantSettings：厂商/模型/key 表单 + 思考模式 + 工具权限 + 记忆 + 清聊天历史 + chat.clearMessages）
- **PR-3 Tab 2 Agent 独立 key（后端）**：Task 13-19（ContextVar + state 字段 + 5 agent + 8 路由透传 + /agents/ping）
- **PR-3 Tab 2 Agent 独立 key（前端）**：Task 20-23（agentLlm store + withOverrides + 6 注入点 + AgentSettings UI）
- **PR-4 Tab 3 供应商管理**：Task 24-25（ProvidersSettings CRUD + ProviderEditDialog）
- **PR-5 Vision 批量 + 清缓存**：Task 26（批量探测 UI）
- **PR-6 网络代理**：Task 27-30（proxy UI + IPC + sidecar env 注入 + proxy-cache 落盘）

---

## Task 1: 后端 ContextVar 基础设施

**Files:**
- Modify: `backend/app/agents/llm.py`
- Test: `backend/tests/test_llm.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_llm.py`:

```python
from app.agents.llm import get_chat_model, llm_configured, use_llm_overrides, _current_overrides


def test_get_chat_model_with_overrides():
    """overrides 应覆盖 settings 默认配置。"""
    overrides = {
        "api_key": "sk-override",
        "base_url": "https://override.example.com/v1",
        "model": "override-model",
    }
    model = get_chat_model(overrides=overrides)
    assert model.model_name == "override-model"
    assert model.openai_api_key.get_secret_value() == "sk-override"
    assert model.openai_api_base == "https://override.example.com/v1"


def test_get_default_chat_model_reads_contextvar():
    """ContextVar 设置后，get_default_chat_model 用 overrides 构造（不走 lru_cache 默认实例）。"""
    overrides = {"api_key": "sk-ctx", "base_url": "https://ctx.example.com/v1", "model": "ctx-model"}
    with use_llm_overrides(overrides):
        model = get_default_chat_model()
        assert model.model_name == "ctx-model"
        assert model.openai_api_key.get_secret_value() == "sk-ctx"
    # 退出上下文后回到 settings 默认
    llm_module.get_default_chat_model.cache_clear()
    assert get_default_chat_model().model_name == settings.LLM_MODEL


def test_use_llm_overrides_none_is_noop():
    """use_llm_overrides(None) 不设 ContextVar，get_default_chat_model 走默认。"""
    llm_module.get_default_chat_model.cache_clear()
    with use_llm_overrides(None):
        assert _current_overrides.get() is None
        assert get_default_chat_model().model_name == settings.LLM_MODEL


def test_use_llm_overrides_partial_overrides_merge_settings():
    """部分字段 overrides 时，缺省字段回退 settings（不整体替换）。"""
    overrides = {"model": "partial-model"}  # 无 api_key/base_url
    model = get_chat_model(overrides=overrides)
    assert model.model_name == "partial-model"
    assert model.openai_api_key.get_secret_value() == settings.LLM_API_KEY
    assert model.openai_api_base == settings.LLM_BASE_URL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm.py -v`
Expected: FAIL — `ImportError: cannot import name 'use_llm_overrides'` / `get_chat_model() got unexpected keyword 'overrides'`

- [ ] **Step 3: Implement the ContextVar infra**

Replace the entire contents of `backend/app/agents/llm.py` with:

```python
"""
LLM 调用封装

统一通过 get_chat_model() 获取 Chat 模型实例，
所有 Agent 节点共用，便于单测 mock 与配置集中管理。

复用 app.config.settings 的 LLM_* 配置（DeepSeek，OpenAI 兼容接口）。
对齐 01_orchestrator_agent.txt 注意事项：LLM 超时最多重试 2 次。

Spec B: per-request LLM overrides 通过 ContextVar 承载。
- 路由层从请求体 llm_overrides 字段提取，用 use_llm_overrides(overrides) 上下文管理器 set。
- 工作流路径：节点入口从 state["llm_overrides"] set/reset。
- content_generator 的 ThreadPoolExecutor 工作线程不继承 ContextVar，需在 _safe_generate 内重新 set。
- 无 override 时 get_default_chat_model() 走 lru_cache 默认实例（行为不变，单测兼容）。
"""

import contextvars
from functools import lru_cache
from typing import Optional, TypedDict

from langchain_openai import ChatOpenAI

from app.config import settings


class LlmOverrides(TypedDict, total=False):
    """Per-request LLM 覆写（来自请求体 llm_overrides 字段）。"""
    api_key: str
    base_url: str
    model: str
    protocol: str  # 本期仅 'openai'，预留


# ContextVar: 当前请求的 overrides；None 时走 settings 默认。
_current_overrides: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "kmatch_llm_overrides", default=None
)


class use_llm_overrides:
    """上下文管理器：在 with 块内设置当前 overrides，退出时 reset。

    overrides=None 时为 no-op（不设 ContextVar）。
    用于路由层直调路径（submit/feedback/learning report/project review/test）。
    """

    def __init__(self, overrides: Optional[dict]):
        self.overrides = overrides
        self.token = None

    def __enter__(self):
        if self.overrides is not None:
            self.token = _current_overrides.set(self.overrides)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.token is not None:
            _current_overrides.reset(self.token)
        return False


def get_chat_model(
    temperature: float = None,
    overrides: Optional[dict] = None,
) -> ChatOpenAI:
    """创建 Chat 模型实例。

    Args:
        temperature: 生成温度，None 时用 settings.LLM_TEMPERATURE (0.3)
        overrides: 显式覆写（优先于 ContextVar）；None 时读 _current_overrides。
                   字段缺省时回退 settings 默认（部分覆写，不整体替换）。

    Returns:
        ChatOpenAI 实例（OpenAI 兼容）

    Note:
        max_retries=2 对齐 orchestrator prompt「LLM 超时重试 2 次」要求。
        本函数始终返回新实例（override 路径不缓存）；无 override 时由
        get_default_chat_model 的 lru_cache 复用单例。
    """
    ovr = overrides if overrides is not None else _current_overrides.get()
    if ovr:
        api_key = ovr.get("api_key") or settings.LLM_API_KEY
        base_url = ovr.get("base_url") or settings.LLM_BASE_URL
        model = ovr.get("model") or settings.LLM_MODEL
    else:
        api_key = settings.LLM_API_KEY
        base_url = settings.LLM_BASE_URL
        model = settings.LLM_MODEL

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
        max_retries=2,
        timeout=settings.LLM_TIMEOUT,
    )


@lru_cache(maxsize=1)
def get_default_chat_model() -> ChatOpenAI:
    """单例：全流程共享的默认 Chat 模型实例。

    Spec B: 若 ContextVar 已设 overrides，绕过缓存直接构造（按需实例）。
    无 override 时返回缓存的默认实例（单测 monkeypatch 兼容）。
    """
    if _current_overrides.get() is not None:
        # 绕过 lru_cache（缓存键无参，无法区分 overrides；直接构造）
        return get_chat_model()
    return get_chat_model()


def llm_configured() -> bool:
    """是否配置了真实 LLM API Key（非占位符）。

    Spec B: ContextVar 设了 overrides 且含 api_key 时，视为已配置
    （用户用独立 key 跑 Agent，即便后端 .env 是占位符）。
    """
    ovr = _current_overrides.get()
    if ovr and ovr.get("api_key"):
        return True
    return settings.LLM_API_KEY not in ("", "sk-placeholder")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_llm.py -v`
Expected: PASS — all 8 tests (4 existing + 4 new)

- [ ] **Step 5: Run existing agent unit tests to confirm no regression**

Run: `cd backend && python -m pytest tests/test_diagnostics_unit.py tests/test_content_generator_unit.py -v`
Expected: PASS — existing tests monkeypatch `get_default_chat_model` by name; ContextVar default is None so behavior unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/llm.py backend/tests/test_llm.py
git commit -m "feat(llm): ContextVar 承载 per-request llm_overrides + use_llm_overrides 上下文管理器"
```

---

## Task 2: AgentState 加 llm_overrides 字段

**Files:**
- Modify: `backend/app/agents/state.py`
- Test: `backend/tests/test_state_overrides.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_state_overrides.py`:

```python
"""AgentState llm_overrides 字段 + make_initial_state 透传单测。"""
from app.agents.state import make_initial_state, AgentState


def test_make_initial_state_defaults_no_overrides():
    """无 llm_overrides 参数时 state 不含该字段（total=False）。"""
    state = make_initial_state(target_direction="Python 入门")
    assert "llm_overrides" not in state or state.get("llm_overrides") is None
    assert state["target_direction"] == "Python 入门"


def test_make_initial_state_with_overrides():
    """llm_overrides 参数透传进 state。"""
    overrides = {"api_key": "sk-x", "base_url": "https://x/v1", "model": "m"}
    state = make_initial_state(target_direction="Python 入门", llm_overrides=overrides)
    assert state["llm_overrides"] == overrides


def test_agentstate_accepts_llm_overrides():
    """AgentState TypedDict 接受 llm_overrides 键（total=False，运行时不强校验）。"""
    state = AgentState(session_id="s1", llm_overrides={"model": "m"})
    assert state["llm_overrides"] == {"model": "m"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_state_overrides.py -v`
Expected: FAIL — `TypeError: make_initial_state() got an unexpected keyword argument 'llm_overrides'`

- [ ] **Step 3: Add the field and parameter**

In `backend/app/agents/state.py`, add `llm_overrides` to the `AgentState` TypedDict. Insert after the `orchestration_log` field (before the closing of the class, after line 79 `orchestration_log: Annotated[list, _append_log]`):

```python
    # --- Spec B: per-request LLM 覆写 (Agent 学习引擎独立 key) ---
    # 路由层从请求体 llm_overrides 提取后塞入 initial state；节点入口读它 set ContextVar。
    # 工作流路径用此字段传递；直调路径（submit/feedback/review/test）用 use_llm_overrides。
    llm_overrides: dict
```

Then modify `make_initial_state` signature and body. Replace the function (lines 82-104) with:

```python
def make_initial_state(
    target_direction: str,
    mode: str = "demo",
    known_topics: list = None,
    scene: str = "no_project",
    max_retries: int = 3,
    llm_overrides: dict = None,
) -> AgentState:
    """构造初始状态。学情检测节点将填充 user_profile / assessment。

    Spec B: llm_overrides 非空时随 state 下传，节点入口 set 进 ContextVar。
    """
    import uuid

    state = AgentState(
        session_id=str(uuid.uuid4()),
        scene=scene,
        target_direction=target_direction,
        mode=mode,
        known_topics=known_topics or [],
        user_profile={},
        assessment={},
        review_results={"passed": False},
        retry_count=0,
        max_retries=max_retries,
        orchestration_log=[],
    )
    if llm_overrides:
        state["llm_overrides"] = llm_overrides
    return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_state_overrides.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/state.py backend/tests/test_state_overrides.py
git commit -m "feat(state): AgentState 加 llm_overrides 字段 + make_initial_state 透传"
```

---

## Task 3: 工作流节点入口 set ContextVar（diagnostics / reviewer / content_generator）

> 这 3 个节点是 demo 全流程（`workflow.invoke/stream`）的 LLM 调用节点。入口从 `state["llm_overrides"]` set ContextVar，退出 reset。graph_controller 不调 LLM（纯图谱遍历），无需改。

**Files:**
- Modify: `backend/app/agents/diagnostics.py:486` (`diagnostics_node._node`)
- Modify: `backend/app/agents/reviewer.py:254` (`reviewer_node._node`)
- Modify: `backend/app/agents/content_generator.py:149` + `:188` (`content_generator_node._node` + `_safe_generate`)
- Test: `backend/tests/test_node_overrides_propagation.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_node_overrides_propagation.py`:

```python
"""验证工作流节点入口从 state.llm_overrides set ContextVar，深层 LLM helper 用到 overrides。

用 monkeypatch 拦截 get_chat_model，断言它被调用时 _current_overrides 已 set 为 state 里的值。
"""
import app.agents.llm as llm_module
from app.agents.llm import _current_overrides


def _make_fake_kg():
    """返回一个不触网的假 KG（节点函数早期会 return，不真正调 LLM）。"""
    class FakeKg:
        def get_node(self, nid):
            return None
    return FakeKg()


def test_diagnostics_node_sets_contextvar_from_state():
    """diagnostics_node 入口把 state.llm_overrides set 进 ContextVar，退出 reset。"""
    overrides = {"api_key": "sk-agent", "base_url": "https://x/v1", "model": "m"}
    from app.agents.diagnostics import diagnostics_node
    node = diagnostics_node(_make_fake_kg())
    state = {"target_direction": "x", "mode": "demo", "known_topics": [],
             "llm_overrides": overrides}

    # 节点外 ContextVar 应为 None
    assert _current_overrides.get() is None
    try:
        node(state)
    except Exception:
        pass  # 假 kg 可能抛，只关心 ContextVar 是否被 set 且退出后 reset
    # 节点退出后 ContextVar 必须 reset 回 None
    assert _current_overrides.get() is None, "节点退出后 ContextVar 未 reset"


def test_reviewer_node_resets_contextvar_after_exit():
    from app.agents.reviewer import reviewer_node
    node = reviewer_node(_make_fake_kg())
    # 空 profile → 早返（不调 LLM），但 set/reset 仍应平衡
    state = {"user_profile": {}, "assessment": {}, "retry_count": 0,
             "llm_overrides": {"api_key": "sk-x", "model": "m"}}
    assert _current_overrides.get() is None
    node(state)
    assert _current_overrides.get() is None


def test_content_generator_safe_generate_sets_contextvar_in_worker_thread():
    """_safe_generate 在 ThreadPoolExecutor 工作线程内重新 set ContextVar。

    ContextVar 不跨线程传播；验证 worker 线程内 _current_overrides.get() == overrides。
    """
    from app.agents.content_generator import content_generator_node
    captured = []
    import app.agents.content_generator as cg

    def fake_generate_one(node, theory_level, content_type):
        captured.append(_current_overrides.get())
        return {}

    original = cg._generate_one
    cg._generate_one = fake_generate_one
    try:
        overrides = {"api_key": "sk-w", "model": "wm"}
        node = content_generator_node(_make_fake_kg())
        state = {
            "user_profile": {"theory_level": 2},
            "knowledge_graph": {"learning_path": [{"node_id": "N1", "difficulty": 1}]},
            "llm_overrides": overrides,
        }
        node(state)
    finally:
        cg._generate_one = original

    assert len(captured) > 0, "worker 未执行"
    for ctx_val in captured:
        assert ctx_val == overrides, f"worker 线程内 ContextVar 未 set: {ctx_val}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_node_overrides_propagation.py -v`
Expected: FAIL — ContextVar 在节点内仍为 None（未 set）；worker 线程内为 None

- [ ] **Step 3: Add imports + set/reset in `diagnostics_node._node`**

In `backend/app/agents/diagnostics.py`, update the import line 25 to also import the ContextVar:

```python
from app.agents.llm import get_default_chat_model, llm_configured, _current_overrides
```

Then restructure `_node` inside `diagnostics_node` (line 489 `def _node(state) -> dict:`). Replace lines 489-493:

```python
    def _node(state) -> dict:
        target = state.get("target_direction", "Python 基础入门")
        known = state.get("known_topics", [])
        mode = state.get("mode", "demo")
        log = [f"[{datetime.utcnow().isoformat()}] 🔧 学情检测: 开始 (mode={mode})"]
```

with:

```python
    def _node(state) -> dict:
        target = state.get("target_direction", "Python 基础入门")
        known = state.get("known_topics", [])
        mode = state.get("mode", "demo")
        log = [f"[{datetime.utcnow().isoformat()}] 🔧 学情检测: 开始 (mode={mode})"]

        # Spec B: 工作流路径从 state.llm_overrides set ContextVar（节点退出 reset）
        overrides = state.get("llm_overrides")
        ctx_token = _current_overrides.set(overrides) if overrides else None
        try:
            return _node_body(state, target, known, mode, log)
        finally:
            if ctx_token is not None:
                _current_overrides.reset(ctx_token)

    def _node_body(state, target, known, mode, log) -> dict:
```

⚠️ 把原 `_node` 函数体（从 `if not llm_configured():` 到该函数最后的 `return {...}`，即 `return _node` 之前）整体作为 `_node_body` 的函数体——即原实现代码移进 `_node_body`，`_node` 只负责 set/reset + 委托。`_node_body` 内部代码缩进不变（它取代了原 `_node` 在闭包里的位置）。文件末尾的 `return _node` 保持不变。

- [ ] **Step 4: Add set/reset in `reviewer_node._node`**

In `backend/app/agents/reviewer.py`, update import line 23:

```python
from app.agents.llm import get_default_chat_model, llm_configured, _current_overrides
```

Modify `_node` inside `reviewer_node` (line 257 `def _node(state) -> dict:`). Replace lines 257-261:

```python
    def _node(state) -> dict:
        profile = state.get("user_profile", {})
        assessment = state.get("assessment", {})
        retry = state.get("retry_count", 0)
        log = [f"[{datetime.utcnow().isoformat()}] 🔍 内容审核: 开始审画像 (第{retry+1}轮)"]
```

with:

```python
    def _node(state) -> dict:
        profile = state.get("user_profile", {})
        assessment = state.get("assessment", {})
        retry = state.get("retry_count", 0)
        log = [f"[{datetime.utcnow().isoformat()}] 🔍 内容审核: 开始审画像 (第{retry+1}轮)"]

        overrides = state.get("llm_overrides")
        ctx_token = _current_overrides.set(overrides) if overrides else None
        try:
            return _node_body(state, profile, assessment, retry, log)
        finally:
            if ctx_token is not None:
                _current_overrides.reset(ctx_token)

    def _node_body(state, profile, assessment, retry, log) -> dict:
```

同 Step 3：原 `_node` 实现（`if not profile:` 起）整体移进 `_node_body`。

- [ ] **Step 5: Add set/reset in `content_generator_node._node` + worker thread re-set**

In `backend/app/agents/content_generator.py`, update import line 25:

```python
from app.agents.llm import get_default_chat_model, llm_configured, _current_overrides
```

Modify `_node` inside `content_generator_node` (line 152 `def _node(state) -> dict:`). Replace lines 152-155:

```python
    def _node(state) -> dict:
        profile = state.get("user_profile", {})
        kg_state = state.get("knowledge_graph", {}) or {}
        log = [f"[{datetime.utcnow().isoformat()}] 📚 领域知识生成: 开始"]
```

with:

```python
    def _node(state) -> dict:
        profile = state.get("user_profile", {})
        kg_state = state.get("knowledge_graph", {}) or {}
        log = [f"[{datetime.utcnow().isoformat()}] 📚 领域知识生成: 开始"]

        # Spec B: 工作流路径 set ContextVar；content_generator 的 ThreadPoolExecutor
        # 工作线程不继承 ContextVar，_safe_generate 内闭包捕获 overrides 重新 set。
        overrides = state.get("llm_overrides")
        ctx_token = _current_overrides.set(overrides) if overrides else None
        try:
            return _node_body(state, profile, kg_state, log, overrides)
        finally:
            if ctx_token is not None:
                _current_overrides.reset(ctx_token)

    def _node_body(state, profile, kg_state, log, overrides) -> dict:
```

同前：原 `_node` 实现移进 `_node_body`。然后修改 `_safe_generate`（line 188）使其在工作线程内重新 set ContextVar。Replace lines 188-195:

```python
        def _safe_generate(node, ctype):
            """单任务包装: 返回 (ok, result_or_None)。异常不外抛，避免 ThreadPool 终止其他任务。"""
            try:
                return True, _generate_one(node, theory_level, ctype)
            except Exception:
                logger.warning("生成失败 node=%s type=%s",
                               node.get("node_id"), ctype, exc_info=True)
                return False, None
```

with:

```python
        def _safe_generate(node, ctype):
            """单任务包装: 返回 (ok, result_or_None)。异常不外抛，避免 ThreadPool 终止其他任务。

            Spec B: ContextVar 不跨线程传播；工作线程内闭包捕获 overrides 重新 set，
            使 _generate_one → get_default_chat_model() 读到 overrides。
            """
            wtoken = _current_overrides.set(overrides) if overrides else None
            try:
                return True, _generate_one(node, theory_level, ctype)
            except Exception:
                logger.warning("生成失败 node=%s type=%s",
                               node.get("node_id"), ctype, exc_info=True)
                return False, None
            finally:
                if wtoken is not None:
                    _current_overrides.reset(wtoken)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_node_overrides_propagation.py -v`
Expected: PASS — 3 tests

- [ ] **Step 7: Run full agent test suite for regression**

Run: `cd backend && python -m pytest tests/test_diagnostics_unit.py tests/test_content_generator_unit.py -v 2>&1 | tail -20`
Expected: PASS — existing monkeypatch tests still green (ContextVar default None → unchanged behavior)

- [ ] **Step 8: Commit**

```bash
git add backend/app/agents/diagnostics.py backend/app/agents/reviewer.py backend/app/agents/content_generator.py backend/tests/test_node_overrides_propagation.py
git commit -m "feat(agents): 工作流节点入口从 state.llm_overrides set ContextVar + worker 线程重 set"
```

---

## Task 4: 直调 Agent 函数加 overrides 参数（code_reviewer / code_tester）

> 这两个是直调函数（不经 workflow）：`llm_review_code` / `llm_generate_tests` 被 `review_code` / `run_tests` 调用，再被 project 路由调。overrides 由路由透传进来，函数内用 `use_llm_overrides` 包裹。

**Files:**
- Modify: `backend/app/agents/code_reviewer.py:95` (`llm_review_code`) + `review_code` wrapper
- Modify: `backend/app/agents/code_tester.py:135` (`llm_generate_tests`) + `run_tests` wrapper
- Test: `backend/tests/test_direct_call_overrides.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_direct_call_overrides.py`:

```python
"""验证直调 agent 函数的 overrides 透传（拦截 get_default_chat_model 断言 ContextVar）。"""
import app.agents.code_reviewer as cr_module
import app.agents.code_tester as ct_module
from app.agents.llm import _current_overrides


def test_llm_review_code_sets_overrides_in_contextvar(monkeypatch):
    captured = {}

    class FakeModel:
        def invoke(self, messages):
            captured["ctx"] = _current_overrides.get()
            class Resp:
                content = ('{"logic_correctness":{"score":1,"issues":[]},'
                           '"security":{"score":1,"issues":[]},'
                           '"code_quality":{"score":1,"issues":[]},'
                           '"domain_compliance":{"score":1,"issues":[]}}')
            return Resp()

    monkeypatch.setattr(cr_module, "get_default_chat_model", lambda: FakeModel())

    overrides = {"api_key": "sk-r", "model": "rm"}
    cr_module.llm_review_code(
        code="x=1", target_direction="t", knowledge_nodes=[], llm_overrides=overrides,
    )
    assert captured.get("ctx") == overrides
    # 退出函数后 ContextVar reset
    assert _current_overrides.get() is None


def test_llm_generate_tests_sets_overrides_in_contextvar(monkeypatch):
    captured = {}

    class FakeModel:
        def invoke(self, messages):
            captured["ctx"] = _current_overrides.get()
            class Resp:
                content = "```python\ndef test_a(): assert 1\n```\n```json\n[]\n```"
            return Resp()

    monkeypatch.setattr(ct_module, "get_default_chat_model", lambda: FakeModel())

    overrides = {"api_key": "sk-t", "model": "tm"}
    try:
        ct_module.llm_generate_tests(
            entities=[], knowledge_nodes=[], target_direction="t",
            module_name="main", llm_overrides=overrides,
        )
    except Exception:
        pass
    assert captured.get("ctx") == overrides
    assert _current_overrides.get() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_direct_call_overrides.py -v`
Expected: FAIL — `TypeError: llm_review_code() got an unexpected keyword argument 'llm_overrides'`

- [ ] **Step 3: Add overrides param to `llm_review_code`**

In `backend/app/agents/code_reviewer.py`, update import line 33 to add `use_llm_overrides`:

```python
from app.agents.llm import get_default_chat_model, llm_configured, use_llm_overrides
```

Modify the `llm_review_code` signature (line 95) and wrap the body. Replace lines 95-104:

```python
def llm_review_code(code: str, target_direction: str, knowledge_nodes: list[dict]) -> dict:
    """LLM 对照领域规范审查代码，返回四维度评分。

    对照领域元知识 key_points/common_mistakes + 开发目标，检查:
      - logic_correctness: 逻辑错误、边界、类型、控制流
      - security: 安全隐患 (注入/敏感信息/危险操作)
      - code_quality: 命名/结构/可读性/重复
      - domain_compliance: 是否符合领域规范 (key_points/common_mistakes)
    """
    model = get_default_chat_model()
```

with:

```python
def llm_review_code(code: str, target_direction: str, knowledge_nodes: list[dict],
                    llm_overrides: dict = None) -> dict:
    """LLM 对照领域规范审查代码，返回四维度评分。

    对照领域元知识 key_points/common_mistakes + 开发目标，检查:
      - logic_correctness: 逻辑错误、边界、类型、控制流
      - security: 安全隐患 (注入/敏感信息/危险操作)
      - code_quality: 命名/结构/可读性/重复
      - domain_compliance: 是否符合领域规范 (key_points/common_mistakes)

    Spec B: llm_overrides 非空时用独立 key（Agent 学习引擎配置）。
    """
    with use_llm_overrides(llm_overrides):
        model = get_default_chat_model()
```

⚠️ Then indent the rest of the original `llm_review_code` body (from the `system = SystemMessage(...)` line through the function's final `return`) one level deeper, into the `with` block.

- [ ] **Step 4: Propagate overrides through `review_code` wrapper**

Find `review_code` in `code_reviewer.py` (the public function called by the project route). Run to locate it:

Run: `cd backend && grep -n "def review_code\|llm_review_code(" app/agents/code_reviewer.py`

Add `llm_overrides: dict = None` to the `review_code` signature, and change its `llm_review_code(...)` call site to pass `llm_overrides=llm_overrides`.

- [ ] **Step 5: Add overrides param to `llm_generate_tests`**

In `backend/app/agents/code_tester.py`, update import line 41 to add `use_llm_overrides`:

```python
from app.agents.llm import get_default_chat_model, llm_configured, use_llm_overrides
```

Modify `llm_generate_tests` signature (line 135) and wrap the body. Replace lines 135-142:

```python
def llm_generate_tests(entities: list[CodeEntity], knowledge_nodes: list[dict],
                       target_direction: str, module_name: str) -> tuple[str, list[dict]]:
    """LLM 据图谱函数签名 + common_mistakes 生成 pytest 代码 + 元数据。

    Returns:
        (test_code, test_metadata[]) — metadata: {test_name, related_node, related_keypoint, scenario}
    """
    model = get_default_chat_model()
```

with:

```python
def llm_generate_tests(entities: list[CodeEntity], knowledge_nodes: list[dict],
                       target_direction: str, module_name: str,
                       llm_overrides: dict = None) -> tuple[str, list[dict]]:
    """LLM 据图谱函数签名 + common_mistakes 生成 pytest 代码 + 元数据。

    Returns:
        (test_code, test_metadata[]) — metadata: {test_name, related_node, related_keypoint, scenario}

    Spec B: llm_overrides 非空时用独立 key。
    """
    with use_llm_overrides(llm_overrides):
        model = get_default_chat_model()
```

Then indent the rest of the original body (line 143 onward through the final `return`) one level into the `with` block.

- [ ] **Step 6: Propagate overrides through `run_tests` wrapper**

Run to locate: `cd backend && grep -n "def run_tests\|llm_generate_tests(" app/agents/code_tester.py`

Add `llm_overrides: dict = None` to the `run_tests` signature, and change its `llm_generate_tests(...)` call site to pass `llm_overrides=llm_overrides`.

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_direct_call_overrides.py -v`
Expected: PASS — 2 tests

- [ ] **Step 8: Commit**

```bash
git add backend/app/agents/code_reviewer.py backend/app/agents/code_tester.py backend/tests/test_direct_call_overrides.py
git commit -m "feat(agents): code_reviewer/code_tester 直调函数加 llm_overrides 透传"
```

---

## Task 5: diagnostics 路由透传 llm_overrides

> `/assess`（demo 走 workflow，透传到 `make_initial_state`）、`/assess/stream`（同）、`/submit`（直调 `_grade`/`_build_profile`，用 `use_llm_overrides` 包裹）、`/feedback`（直调 `regenerate_for_feedback`，用 `use_llm_overrides` 包裹）。

**Files:**
- Modify: `backend/app/api/diagnostics.py`
- Test: `backend/tests/test_routes_llm_overrides.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_routes_llm_overrides.py`:

```python
"""验证 4 个 diagnostics 路由从请求体读 llm_overrides 并下传。

用 monkeypatch 拦截 make_initial_state / _grade / _build_profile / regenerate_for_feedback，
断言它们收到 overrides。KG 用假对象避免 Neo4j。
"""
import app.api.diagnostics as api_diag
from app.api.diagnostics import AssessRequest, SubmitRequest, FeedbackRequest


class FakeKg:
    def test_connection(self):
        return True
    def get_node(self, nid):
        return None
    def assemble_learning_path(self, **kw):
        return []
    def get_by_difficulty(self, *a, **kw):
        return []


def _patch_appstate_kg(monkeypatch):
    from app.main import app
    app.state.kg = FakeKg()
    app.state.workflow = None


def test_assess_request_model_accepts_llm_overrides():
    req = AssessRequest(target_direction="x", llm_overrides={"api_key": "k"})
    assert req.llm_overrides == {"api_key": "k"}


def test_assess_demo_passes_overrides_to_initial_state(monkeypatch):
    _patch_appstate_kg(monkeypatch)
    captured = {}

    class FakeWorkflow:
        def invoke(self, initial, config):
            captured["overrides"] = initial.get("llm_overrides")
            return {"user_profile": {}, "assessment": {}, "review_results": {},
                    "knowledge_graph": {}, "generated_content": {}, "orchestration_log": []}

    from app.main import app
    app.state.workflow = FakeWorkflow()

    from fastapi.testclient import TestClient
    client = TestClient(app)
    overrides = {"api_key": "sk-a", "model": "am"}
    r = client.post("/api/diagnostics/assess",
                    json={"target_direction": "x", "mode": "demo",
                          "llm_overrides": overrides})
    assert r.status_code == 200, r.text
    assert captured["overrides"] == overrides


def test_submit_passes_overrides_to_grade(monkeypatch):
    """submit 直调 _grade；用 use_llm_overrides 包裹，_grade 内 get_default_chat_model 读到。"""
    import app.agents.diagnostics as ag
    from app.agents.llm import _current_overrides

    seen = {}

    def fake_grade(questions, answers):
        seen["ctx"] = _current_overrides.get()
        return {"per_node": {}, "correct_count": 0, "total_count": len(questions)}

    def fake_build_profile(target, nodes, grading, questions=None):
        return {"theory_level": 1}

    monkeypatch.setattr(ag, "_grade", fake_grade)
    monkeypatch.setattr(ag, "_build_profile", fake_build_profile)

    # 预置 interactive 会话缓存
    api_diag._INTERACTIVE_SESSIONS["s1"] = {
        "questions": [{"node_id": "N1", "question": "q", "answer": "a"}],
        "nodes": [{"node_id": "N1"}], "target_direction": "x", "known_topics": [],
        "created_at": "2026-01-01T00:00:00",
    }

    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    overrides = {"api_key": "sk-s", "model": "sm"}
    r = client.post("/api/diagnostics/submit",
                    json={"session_id": "s1", "answers": ["a"], "llm_overrides": overrides})
    assert r.status_code == 200, r.text
    assert seen["ctx"] == overrides
    # 路由退出后 ContextVar reset
    assert _current_overrides.get() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_routes_llm_overrides.py -v`
Expected: FAIL — `AssessRequest` 无 `llm_overrides` 字段 / 422 validation error

- [ ] **Step 3: Add llm_overrides field to the 3 request models**

In `backend/app/api/diagnostics.py`, add a field to each of `AssessRequest`, `SubmitRequest`, `FeedbackRequest`. Append this line as the last field of each model (after their existing last field):

For `AssessRequest` (after `max_retries` line 58):
```python
    llm_overrides: dict = Field(default=None, description="Spec B: Agent 学习引擎独立 key 覆写")
```

For `SubmitRequest` (after `answers` line 84):
```python
    llm_overrides: dict = Field(default=None, description="Spec B: Agent 学习引擎独立 key 覆写")
```

For `FeedbackRequest` (after `profile` line 101):
```python
    llm_overrides: dict = Field(default=None, description="Spec B: Agent 学习引擎独立 key 覆写")
```

- [ ] **Step 4: Pass overrides through `/assess` demo path**

In `assess()` (line 130), the demo branch builds `initial = make_initial_state(...)`. Modify the call (lines 177-183) to pass `llm_overrides`:

```python
    initial = make_initial_state(
        target_direction=req.target_direction,
        mode=req.mode,
        known_topics=req.known_topics,
        scene=req.scene,
        max_retries=req.max_retries,
        llm_overrides=req.llm_overrides,
    )
```

- [ ] **Step 5: Pass overrides through `/assess/stream`**

In `assess_stream()` (line 237), modify its `make_initial_state` call (lines 261-267) the same way — append `llm_overrides=req.llm_overrides,`.

- [ ] **Step 6: Wrap `/submit` with use_llm_overrides**

In `submit()` (line 335), the LLM calls (`_grade`, `_build_profile`) happen in the try block (lines 360-363). Import `use_llm_overrides` at top of file. Add to the existing import line 28:

```python
from app.agents.llm import llm_configured, use_llm_overrides
```

Then wrap the grading try block. Replace lines 360-366:

```python
    try:
        grading = _grade(questions, answers)
        profile = _build_profile(target, nodes, grading, questions=questions)
        feedback = decide_feedback(grading["correct_count"], grading["total_count"])
    except Exception as e:
        logger.error("答题判分失败 session=%s", req.session_id, exc_info=True)
        raise HTTPException(status_code=500, detail=f"判分失败: {e}")
```

with:

```python
    try:
        with use_llm_overrides(req.llm_overrides):
            grading = _grade(questions, answers)
            profile = _build_profile(target, nodes, grading, questions=questions)
        feedback = decide_feedback(grading["correct_count"], grading["total_count"])
    except Exception as e:
        logger.error("答题判分失败 session=%s", req.session_id, exc_info=True)
        raise HTTPException(status_code=500, detail=f"判分失败: {e}")
```

- [ ] **Step 7: Wrap `/feedback` with use_llm_overrides**

In `feedback()` (line 389), the LLM call is `regenerate_for_feedback(...)` (line 414). Wrap it. Replace lines 413-417:

```python
    try:
        result = regenerate_for_feedback(req.strategy, req.profile, learning_path, kg)
    except Exception as e:
        logger.error("feedback 再生失败 session=%s", req.session_id, exc_info=True)
        raise HTTPException(status_code=500, detail=f"内容再生失败: {e}")
```

with:

```python
    try:
        with use_llm_overrides(req.llm_overrides):
            result = regenerate_for_feedback(req.strategy, req.profile, learning_path, kg)
    except Exception as e:
        logger.error("feedback 再生失败 session=%s", req.session_id, exc_info=True)
        raise HTTPException(status_code=500, detail=f"内容再生失败: {e}")
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_routes_llm_overrides.py -v`
Expected: PASS — 4 tests

- [ ] **Step 9: Commit**

```bash
git add backend/app/api/diagnostics.py backend/tests/test_routes_llm_overrides.py
git commit -m "feat(api): diagnostics 4 路由透传 llm_overrides (assess/stream/submit/feedback)"
```

---

## Task 6: learning + project 路由透传 llm_overrides

**Files:**
- Modify: `backend/app/api/learning.py`
- Modify: `backend/app/api/project.py`
- Test: `backend/tests/test_routes_llm_overrides.py` (extend)

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_routes_llm_overrides.py`:

```python
def test_learning_report_request_accepts_llm_overrides():
    from app.api.learning import LearningReportRequest
    req = LearningReportRequest(session_id="s1", llm_overrides={"api_key": "k"})
    assert req.llm_overrides == {"api_key": "k"}


def test_project_review_request_accepts_llm_overrides():
    from app.api.project import ReviewRequest, TestRequest
    assert ReviewRequest(code="x", target_direction="t", llm_overrides={"api_key": "k"}).llm_overrides == {"api_key": "k"}
    assert TestRequest(target_direction="t", llm_overrides={"api_key": "k"}).llm_overrides == {"api_key": "k"}


def test_project_review_passes_overrides_to_review_code(monkeypatch):
    import app.agents.code_reviewer as cr
    from app.agents.llm import _current_overrides
    seen = {}
    monkeypatch.setattr(cr, "review_code", lambda kg, code, td, kn, llm_overrides=None: (
        seen.update(ctx=_current_overrides.get(), arg=llm_overrides) or {"passed": True}
    ))
    from fastapi.testclient import TestClient
    from app.main import app
    app.state.kg = FakeKg()
    client = TestClient(app)
    overrides = {"api_key": "sk-r", "model": "rm"}
    r = client.post("/api/project/review",
                    json={"code": "x=1", "target_direction": "t", "llm_overrides": overrides})
    assert r.status_code == 200, r.text
    assert seen["arg"] == overrides
    assert _current_overrides.get() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_routes_llm_overrides.py -v -k "learning or project"`
Expected: FAIL — models 无字段 / review_code 不接受 llm_overrides

- [ ] **Step 3: learning.py — add field + wrap pipeline**

In `backend/app/api/learning.py`, add field to `LearningReportRequest` (after `session_id` line 35):

```python
    llm_overrides: dict = Field(default=None, description="Spec B: Agent 独立 key 覆写")
```

Import `use_llm_overrides` (add to line 21 import):
```python
from app.agents.llm import llm_configured, use_llm_overrides
```

In `learning_report()` (line 103), the pipeline runs at line 150 `state = _run_report_pipeline(profile, kg)`. Wrap it. Replace lines 149-153:

```python
    # ⑤ 补跑
    try:
        state = _run_report_pipeline(profile, kg)
    except Exception as e:
        logger.error("学习报告补跑失败 session=%s", req.session_id, exc_info=True)
        raise HTTPException(status_code=500, detail=f"报告补跑失败: {e}")
```

with:

```python
    # ⑤ 补跑 (Spec B: 用 use_llm_overrides 包裹，graph_controller/content_generator/reviewer 内 get_default_chat_model 读到)
    try:
        with use_llm_overrides(req.llm_overrides):
            state = _run_report_pipeline(profile, kg)
    except Exception as e:
        logger.error("学习报告补跑失败 session=%s", req.session_id, exc_info=True)
        raise HTTPException(status_code=500, detail=f"报告补跑失败: {e}")
```

- [ ] **Step 4: project.py — add fields + pass through**

In `backend/app/api/project.py`, add `llm_overrides` field to `ReviewRequest` (after `knowledge_node_ids` line 143) and `TestRequest` (after `project_id` line 179):

```python
    llm_overrides: dict = None  # Spec B: Agent 独立 key 覆写
```

In `review_project_code_api()` (line 147), change the `review_code(...)` call (line 160) to pass overrides:

```python
        result = review_code(kg, req.code, req.target_direction, req.knowledge_node_ids,
                             llm_overrides=req.llm_overrides)
```

In `test_project_code_api()` (line 183), change the `run_tests(...)` call (lines 219-223) to pass overrides — add `llm_overrides=req.llm_overrides,` as the last keyword arg:

```python
        result = run_tests(
            kg, sources, req.target_direction, req.knowledge_node_ids,
            mode=req.mode, project_id=req.project_id, module_name=module_name,
            example_name=example_name, llm_overrides=req.llm_overrides,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_routes_llm_overrides.py -v`
Expected: PASS — all tests

- [ ] **Step 6: Run full backend test suite for regression**

Run: `cd backend && python -m pytest -q 2>&1 | tail -15`
Expected: PASS — no regressions

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/learning.py backend/app/api/project.py backend/tests/test_routes_llm_overrides.py
git commit -m "feat(api): learning + project 路由透传 llm_overrides"
```

---

## Task 7: /api/agents/ping 端点

**Files:**
- Create: `backend/app/api/agents.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_agents_ping.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_agents_ping.py`:

```python
"""POST /api/agents/ping — 用 overrides 构造 ChatOpenAI 发 ping 验证可用。"""
from fastapi.testclient import TestClient


def test_agents_ping_ok_with_overrides(monkeypatch):
    """overrides 合法时，ping 调 model.invoke 返回 ok=True。"""
    import app.api.agents as agents_api
    import app.agents.llm as llm_module

    class FakeModel:
        def invoke(self, prompt):
            class Resp:
                content = "pong"
            return Resp()

    monkeypatch.setattr(llm_module, "get_chat_model", lambda temperature=None, overrides=None: FakeModel())
    from app.main import app
    client = TestClient(app)
    r = client.post("/api/agents/ping",
                    json={"llm_overrides": {"api_key": "sk", "model": "m", "base_url": "u"}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "pong" in body["content"]


def test_agents_ping_failure_returns_ok_false(monkeypatch):
    """model.invoke 抛异常时返回 ok=False + error。"""
    import app.agents.llm as llm_module

    def boom_model(*a, **kw):
        class M:
            def invoke(self, p):
                raise RuntimeError("invalid api key")
        return M()

    monkeypatch.setattr(llm_module, "get_chat_model", boom_model)
    from app.main import app
    client = TestClient(app)
    r = client.post("/api/agents/ping",
                    json={"llm_overrides": {"api_key": "bad", "model": "m", "base_url": "u"}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "invalid api key" in body["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_agents_ping.py -v`
Expected: FAIL — 404 (route not registered)

- [ ] **Step 3: Create the route file**

Create `backend/app/api/agents.py`:

```python
"""
Agent 学习引擎 API 路由 (Spec B)

POST /api/agents/ping
  用请求体 llm_overrides 构造 ChatOpenAI 发一句 "ping"，验证 key/baseUrl/model 可用。
  供设置页「测试连接」按钮调用。不依赖 Neo4j / workflow。
"""

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents.llm import get_chat_model
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class PingRequest(BaseModel):
    """测试连接请求：Agent 独立 LLM 配置覆写。"""
    llm_overrides: dict = Field(..., description="api_key/base_url/model 覆写")


@router.post("/ping", summary="测试 Agent 独立 LLM 配置连通性")
async def agents_ping(req: PingRequest):
    """用 req.llm_overrides 构造 ChatOpenAI 发一句 'ping'，验证可用。

    ChatOpenAI.invoke 是同步阻塞调用，用 asyncio.to_thread 包裹避免阻塞事件循环。
    """
    overrides = req.llm_overrides or {}
    try:
        model = get_chat_model(overrides=overrides)
        resp = await asyncio.to_thread(model.invoke, "ping")
        content = getattr(resp, "content", "") or ""
        return {"ok": True, "content": str(content)[:100]}
    except Exception as exc:
        logger.warning("agent ping 失败: %s", exc)
        return {"ok": False, "error": str(exc)}
```

- [ ] **Step 4: Register the router in main.py**

In `backend/app/main.py`, after the chat router registration (line 189), add:

```python
# Spec B: Agent 学习引擎 (测试连接 ping)
from app.api import agents  # noqa: E402

app.include_router(agents.router, prefix="/api/agents", tags=["Agent 学习引擎"])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_agents_ping.py -v`
Expected: PASS — 2 tests

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/agents.py backend/app/main.py backend/tests/test_agents_ping.py
git commit -m "feat(api): /api/agents/ping 端点 — Agent 独立 key 连通性测试"
```

---

## Task 8: 设置视图入口 — sidebar 注释 + ActivityBar 齿轮 + TitlebarMenu + MainArea 装载

> sidebar `activeView` 值域已是任意字符串（`ref('code')` + `setView(id)`），无需改逻辑，仅更新注释。TitlebarMenu 的 `runCommand` 已自动处理 `view.<id>` 前缀命令调 `setView`。

**Files:**
- Modify: `frontend/src/stores/sidebar.js`
- Modify: `frontend/src/ide/ActivityBar.vue`
- Modify: `frontend/src/ide/TitlebarMenu.vue`
- Modify: `frontend/src/ide/MainArea.vue`

- [ ] **Step 1: Update sidebar.js comment**

In `frontend/src/stores/sidebar.js`, update the `ACTIVITY_ITEMS` / activeView comment (lines 4, 10) to include `settings`. Change line 4:

```js
 * 活动栏指示同一时间只亮一个 = activeView (code/learning-session/graph/learning/dashboard)
```

to:

```js
 * 活动栏指示同一时间只亮一个 = activeView (code/learning-session/graph/learning/dashboard/settings)
```

(No logic change — `settings` is a bottom-pinned entry, not in `ACTIVITY_ITEMS` top list.)

- [ ] **Step 2: Add settings gear to ActivityBar bottom**

In `frontend/src/ide/ActivityBar.vue`, add a settings button in the bottom group (after the theme toggle, before `</div>` close of `.activity-bar`). Insert before the closing `</template>` tag's last button. Replace the theme-toggle block + closing (lines 27-37):

```vue
    <!-- 主题切换 -->
    <div
      class="activity-item"
      :title="themeMode === 'dark' ? '切换到亮色' : '切换到暗色'"
      @click="toggleTheme"
    >
      <el-icon :size="22">
        <Sunny v-if="themeMode === 'dark'" />
        <Moon v-else />
      </el-icon>
    </div>
  </div>
```

with:

```vue
    <!-- 主题切换 -->
    <div
      class="activity-item"
      :title="themeMode === 'dark' ? '切换到亮色' : '切换到暗色'"
      @click="toggleTheme"
    >
      <el-icon :size="22">
        <Sunny v-if="themeMode === 'dark'" />
        <Moon v-else />
      </el-icon>
    </div>

    <!-- 设置 (Spec B: 底部齿轮, 仿 VS Code 左下角) -->
    <div
      class="activity-item"
      :class="{ active: sidebar.activeView === 'settings' }"
      title="设置"
      @click="sidebar.setView('settings')"
    >
      <el-icon :size="22"><Setting /></el-icon>
    </div>
  </div>
```

Then register the `Setting` icon import. In `<script setup>` (line 41-43), add `Setting` to the auto-imported icons. Element Plus icons are globally registered via `@element-plus/icons-vue` in main.js; verify by running:

Run: `cd frontend && grep -n "icons-vue" src/main.js`
If icons are globally registered (a `for...of` loop over `* as icons`), no import needed. If not, add to ActivityBar script:
```js
import { Setting } from '@element-plus/icons-vue'
```
and reference in template. Check the existing `Sunny`/`Moon`/`ChatDotRound` usage — they're used without local import, so `Setting` works the same way (globally registered).

- [ ] **Step 3: Add settings menu item to TitlebarMenu + remove stub**

In `frontend/src/ide/TitlebarMenu.vue`, add a settings item to the `tools` group. In `menuGroups` computed (line 58-63), change the tools group:

```js
  {
    id: 'tools',
    label: '工具',
    items: [
      { command: 'assistant.toggle', label: sidebar.aiPanelVisible ? '隐藏 AI 助手' : '显示 AI 助手' },
      { command: 'theme.toggle', label: theme.mode === 'dark' ? '切换到亮色' : '切换到暗色' },
      { command: 'view.settings', label: '设置', divided: true },
      { command: 'window.devtools', label: '打开开发者工具', divided: true },
    ],
  },
```

Then remove the `view.ai-settings` stub. In `runCommand` (lines 75-84), delete the stub block:

```js
  if (command.startsWith('view.ai-settings')) {
    if (!sidebar.aiPanelVisible) sidebar.toggleAiPanel()
    ElMessage.info('AI 设置视图将在下一步启用；当前可在右侧 AI 助手底部设置模型/API Key。')
    return
  }
```

The existing `if (command.startsWith('view.'))` block (line 80) now handles `view.settings` automatically → `sidebar.setView('settings')`.

- [ ] **Step 4: Add SettingsView to MainArea**

In `frontend/src/ide/MainArea.vue`, add a branch in the v-if chain and the import. In template (line 19-23), add settings before learning-session:

```vue
        <SettingsView v-if="sidebar.activeView === 'settings'" />
        <LearningSession v-else-if="sidebar.activeView === 'learning-session'" />
```

In `<script setup>` imports (after line 35), add:

```js
import SettingsView from '@/ide/settings/SettingsView.vue'
```

⚠️ `SettingsView.vue` doesn't exist yet — it's created in Task 10. This task's commit must come after Task 10 (or do Task 10 first). **Reorder: implement Task 9 (SettingCard) → Task 10 (SettingsView shell) → then this Task 8.** See Task 8 note below.

- [ ] **Step 5: Commit (after Task 9-10 land)**

```bash
git add frontend/src/stores/sidebar.js frontend/src/ide/ActivityBar.vue frontend/src/ide/TitlebarMenu.vue frontend/src/ide/MainArea.vue
git commit -m "feat(ide): 设置视图入口 — ActivityBar 齿轮 + TitlebarMenu 菜单项 + MainArea 装载"
```

---

## Task 9: SettingCard 公共组件

**Files:**
- Create: `frontend/src/ide/settings/SettingCard.vue`
- Test: `frontend/src/__tests__/setting-card.test.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/setting-card.test.js`:

```js
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SettingCard from '@/ide/settings/SettingCard.vue'

describe('SettingCard', () => {
  it('renders title and info', () => {
    const w = mount(SettingCard, {
      props: { title: 'API Key', info: '用于鉴权' },
      slots: { default: '<input />' },
    })
    expect(w.text()).toContain('API Key')
    expect(w.text()).toContain('用于鉴权')
    expect(w.find('input').exists()).toBe(true)
  })

  it('hides info when not provided', () => {
    const w = mount(SettingCard, { props: { title: 'X' }, slots: { default: '<div class="c"/>' } })
    expect(w.find('.setting-info').exists()).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/setting-card.test.js`
Expected: FAIL — module not found

- [ ] **Step 3: Create the component**

Create `frontend/src/ide/settings/SettingCard.vue`:

```vue
<template>
  <div class="setting-card">
    <div class="setting-head">
      <div class="setting-title">{{ title }}</div>
      <div v-if="info" class="setting-info">{{ info }}</div>
    </div>
    <div class="setting-control"><slot /></div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  info: { type: String, default: '' },
})
</script>

<style scoped>
.setting-card {
  background: var(--km-bg-layer-2);
  border: 1px solid var(--km-border-light);
  border-radius: var(--km-radius-lg);
  padding: 14px 16px;
  margin-bottom: 12px;
  transition: box-shadow 0.18s var(--km-ease), border-color 0.18s var(--km-ease);
}
.setting-card:hover {
  box-shadow: var(--km-shadow-sm);
  border-color: var(--km-primary-light);
}
.setting-head { margin-bottom: 10px; }
.setting-title { font-size: 13.5px; font-weight: 600; color: var(--km-gray-800); }
.setting-info { font-size: 12px; color: var(--km-gray-500); margin-top: 2px; line-height: 1.5; }
.setting-control { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/__tests__/setting-card.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/ide/settings/SettingCard.vue frontend/src/__tests__/setting-card.test.js
git commit -m "feat(settings): SettingCard 公共卡片组件"
```

---

## Task 10: SettingsView 主壳 + 锚点导航（空三段占位）

**Files:**
- Create: `frontend/src/ide/settings/SettingsView.vue`
- Test: `frontend/src/__tests__/settings-view.test.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/settings-view.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SettingsView from '@/ide/settings/SettingsView.vue'

describe('SettingsView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    globalThis.window = globalThis.window || {}
    window.api = window.api || {}
  })

  it('renders three section titles + three anchors', () => {
    const w = mount(SettingsView, { global: { stubs: ['AssistantSettings', 'AgentSettings', 'ProvidersSettings'] } })
    const text = w.text()
    expect(text).toContain('AI 助手')
    expect(text).toContain('Agent 学习引擎')
    expect(text).toContain('供应商管理')
    expect(w.findAll('.settings-anchor')).toHaveLength(3)
  })

  it('clicking anchor sets active anchor', async () => {
    const w = mount(SettingsView, { global: { stubs: ['AssistantSettings', 'AgentSettings', 'ProvidersSettings'] } })
    await w.findAll('.settings-anchor')[1].trigger('click')
    expect(w.vm.activeAnchor).toBe('sec-agent')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/settings-view.test.js`
Expected: FAIL — module not found

- [ ] **Step 3: Create SettingsView**

Create `frontend/src/ide/settings/SettingsView.vue`:

```vue
<template>
  <div class="settings-view">
    <div ref="mainEl" class="settings-main" @scroll="onScroll">
      <div class="settings-content">
        <section id="sec-assistant" ref="secAssistant" class="settings-section">
          <h2 class="section-title">AI 助手</h2>
          <AssistantSettings />
        </section>
        <section id="sec-agent" ref="secAgent" class="settings-section">
          <h2 class="section-title">Agent 学习引擎</h2>
          <AgentSettings />
        </section>
        <section id="sec-providers" ref="secProviders" class="settings-section">
          <h2 class="section-title">供应商管理</h2>
          <ProvidersSettings />
        </section>
      </div>
    </div>
    <aside class="settings-anchors">
      <a
        v-for="a in anchors"
        :key="a.id"
        class="settings-anchor"
        :class="{ active: activeAnchor === a.id }"
        @click="scrollTo(a.id)"
      >{{ a.label }}</a>
    </aside>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import AssistantSettings from './AssistantSettings.vue'
import AgentSettings from './AgentSettings.vue'
import ProvidersSettings from './ProvidersSettings.vue'

const anchors = [
  { id: 'sec-assistant', label: 'AI 助手' },
  { id: 'sec-agent', label: 'Agent 学习引擎' },
  { id: 'sec-providers', label: '供应商管理' },
]

const mainEl = ref(null)
const activeAnchor = ref('sec-assistant')
let observer = null

function scrollTo(id) {
  activeAnchor.value = id
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function onScroll() {
  // 兜底: IntersectionObserver 在某些环境不触发时, 按滚动位置近似
  if (!mainEl.value) return
  const tops = anchors.map((a) => {
    const el = document.getElementById(a.id)
    return { id: a.id, top: el ? el.getBoundingClientRect().top : Infinity }
  })
  // 选 top 最接近 0 且 >= 负高度一半的段
  const visible = tops.filter((t) => t.top < 120)
  if (visible.length) activeAnchor.value = visible[visible.length - 1].id
}

onMounted(async () => {
  await nextTick()
  if (!('IntersectionObserver' in window) || !mainEl.value) return
  observer = new IntersectionObserver(
    (entries) => {
      const entering = entries.filter((e) => e.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (entering[0]) activeAnchor.value = entering[0].target.id
    },
    { root: mainEl.value, rootMargin: '-20% 0px -70% 0px', threshold: 0 },
  )
  anchors.forEach((a) => {
    const el = document.getElementById(a.id)
    if (el) observer.observe(el)
  })
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<style scoped>
.settings-view {
  display: flex;
  height: 100%;
  min-height: 0;
  background: var(--km-bg-layer-1);
}
.settings-main {
  flex: 1;
  overflow-y: auto;
  scroll-behavior: smooth;
}
.settings-content {
  max-width: 760px;
  margin: 0 auto;
  padding: 24px 28px 60px;
}
.settings-section { margin-bottom: 8px; scroll-margin-top: 16px; }
.section-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--km-gray-800);
  margin: 20px 0 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--km-border-light);
}
.settings-anchors {
  width: 160px;
  flex-shrink: 0;
  padding: 28px 16px;
  border-left: 1px solid var(--km-border-light);
  position: sticky;
  top: 0;
  align-self: flex-start;
}
.settings-anchor {
  display: block;
  padding: 6px 10px;
  margin-bottom: 4px;
  font-size: 12.5px;
  color: var(--km-gray-500);
  border-radius: var(--km-radius-sm);
  cursor: pointer;
  border-left: 2px solid transparent;
  transition: color 0.16s var(--km-ease), background 0.16s var(--km-ease), border-color 0.16s var(--km-ease);
}
.settings-anchor:hover { color: var(--km-gray-700); background: var(--km-gray-100); }
.settings-anchor.active {
  color: var(--km-primary-active);
  border-left-color: var(--km-primary-active);
  background: var(--km-primary-light);
}
</style>
```

⚠️ The three child components (`AssistantSettings`/`AgentSettings`/`ProvidersSettings`) don't exist yet. Create minimal placeholder stubs so SettingsView mounts — Task 11/12/13 fill them. Create these three stub files now with a single empty `<template><div></div></template>` each, to be replaced in their respective tasks:

Create `frontend/src/ide/settings/AssistantSettings.vue`:
```vue
<template><div class="assistant-settings"></div></template>
<script setup></script>
```
Create `frontend/src/ide/settings/AgentSettings.vue`:
```vue
<template><div class="agent-settings"></div></template>
<script setup></script>
```
Create `frontend/src/ide/settings/ProvidersSettings.vue`:
```vue
<template><div class="providers-settings"></div></template>
<script setup></script>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/__tests__/settings-view.test.js`
Expected: PASS

- [ ] **Step 5: Now complete Task 8 (entry points) and commit both together**

Now that SettingsView + stubs exist, implement Task 8 Steps 1-4, then commit:

```bash
git add frontend/src/ide/settings/ frontend/src/__tests__/settings-view.test.js frontend/src/stores/sidebar.js frontend/src/ide/ActivityBar.vue frontend/src/ide/TitlebarMenu.vue frontend/src/ide/MainArea.vue
git commit -m "feat(settings): SettingsView 主壳 + 锚点导航 + 三段占位 + 入口装载"
```

---

## Task 11: AssistantSettings — AI 助手段（厂商/模型/key 表单 + 思考模式 + 工具权限 + 记忆 + 清聊天历史）

> 聚合 Spec A 已落地的 aiSettings store 状态为完整表单视图。盘活 `toolPermissions`（6 工具 × 3 态）+ `memories`（CRUD）。清聊天历史调已有 `chat.clearMessages()`（chat.js:865，无需新增）。

**Files:**
- Modify: `frontend/src/ide/settings/AssistantSettings.vue` (replace stub)
- Test: `frontend/src/__tests__/assistant-settings.test.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/assistant-settings.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AssistantSettings from '@/ide/settings/AssistantSettings.vue'
import { useAiSettingsStore } from '@/stores/aiSettings'
import { useChatStore } from '@/stores/chat'

describe('AssistantSettings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    globalThis.window = globalThis.window || {}
    window.api = window.api || {}
    window.api.http = { request: vi.fn() }
  })

  it('renders tool permission rows for all 6 tools', () => {
    const w = mount(AssistantSettings, { global: { stubs: ['el-icon'] } })
    expect(w.findAll('.tool-perm-row')).toHaveLength(6)
  })

  it('changing a tool permission calls setToolPermission', async () => {
    const ai = useAiSettingsStore()
    const w = mount(AssistantSettings, { global: { stubs: ['el-icon'] } })
    const radio = w.findAll('.tool-perm-row .el-radio-group')[0]
    await radio.vm.$emit('change', 'deny')
    expect(ai.permissionFor('read_file')).toBe('deny')
  })

  it('add memory button calls addMemory', async () => {
    const ai = useAiSettingsStore()
    const before = ai.memories.length
    const w = mount(AssistantSettings, { global: { stubs: ['el-icon'] } })
    await w.find('[data-test="add-memory"]').trigger('click')
    // addMemory with empty title/content returns null (不保存空记忆)
    expect(ai.memories.length).toBe(before)
  })

  it('clear history button calls chat.clearMessages', async () => {
    const chat = useChatStore()
    chat.messages = [{ role: 'user', id: '1', versions: [{ chunks: [] }], activeVersion: 0 }]
    const spy = vi.spyOn(chat, 'clearMessages')
    const w = mount(AssistantSettings, { global: { stubs: ['el-icon'] } })
    await w.find('[data-test="clear-history"]').trigger('click')
    expect(spy).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/assistant-settings.test.js`
Expected: FAIL — stub has no `.tool-perm-row` / `[data-test=...]`

- [ ] **Step 3: Implement AssistantSettings**

Replace `frontend/src/ide/settings/AssistantSettings.vue` with:

```vue
<template>
  <div class="assistant-settings">
    <!-- 厂商 / API Key / Base URL / 模型 -->
    <SettingCard title="厂商" info="AI 助手对话使用的模型供应商">
      <el-select :model-value="ai.provider" size="small" style="width: 220px" @change="onProviderChange">
        <template #prefix>
          <img :src="iconUrlOf(ai.providerMeta().iconKey)" class="provider-icon" alt="" />
        </template>
        <el-option v-for="p in PROVIDERS" :key="p.id" :label="p.label" :value="p.id">
          <span class="provider-row"><img :src="iconUrlOf(p.iconKey)" class="provider-icon" alt="" /><span>{{ p.label }}</span></span>
        </el-option>
      </el-select>
    </SettingCard>

    <SettingCard title="API Key" info="用于鉴权；仅本地存储，不上传">
      <el-input :model-value="ai.apiKey" type="password" show-password size="small" style="width: 320px"
                placeholder="sk-..." @change="ai.setApiKey" />
    </SettingCard>

    <SettingCard v-if="isCustomProvider(ai.provider)" title="Base URL" info="自定义厂商的 OpenAI 兼容端点">
      <el-input :model-value="customBaseUrl" size="small" style="width: 320px"
                placeholder="https://your-endpoint/v1" @change="onCustomBaseUrlChange" />
    </SettingCard>

    <SettingCard title="模型" info="带能力徽章（👁 vision / 🧠 reasoning / 上下文）">
      <el-select :model-value="ai.model" size="small" style="width: 280px" @change="ai.setModel">
        <el-option v-for="m in ai.models" :key="m" :label="m" :value="m">
          <span class="model-row">
            <span>{{ m }}</span>
            <el-tag v-if="capOf(m).reasoning === 'native'" size="small" type="warning" effect="plain">🧠</el-tag>
            <el-tag v-if="capOf(m).context" size="small" type="info" effect="plain">{{ formatContext(capOf(m).context) }}</el-tag>
          </span>
        </el-option>
      </el-select>
    </SettingCard>

    <!-- 思考模式 -->
    <SettingCard title="思考模式" info="控制 AI 推理深度；深度模式仅原生 reasoning 模型可用">
      <el-radio-group :model-value="ai.reasoningMode" size="small" @change="ai.setReasoningMode">
        <el-radio-button label="auto">自动</el-radio-button>
        <el-radio-button label="fast">快速</el-radio-button>
        <el-radio-button label="deep" :disabled="deepDisabled"
          :title="deepDisabled ? deepDisabledTooltip : ''">深度</el-radio-button>
      </el-radio-group>
    </SettingCard>

    <!-- 工具权限 -->
    <SettingCard title="工具权限" info="AI 助手调用工具时的默认行为">
      <div v-for="tool in TOOLS" :key="tool.name" class="tool-perm-row">
        <div class="tool-info">
          <span class="tool-name">{{ tool.name }}</span>
          <span class="tool-desc">{{ tool.description }}</span>
        </div>
        <el-radio-group :model-value="ai.permissionFor(tool.name)" size="small"
                        @change="ai.setToolPermission(tool.name, $event)">
          <el-radio-button label="allow">允许</el-radio-button>
          <el-radio-button label="ask">询问</el-radio-button>
          <el-radio-button label="deny">禁用</el-radio-button>
        </el-radio-group>
      </div>
    </SettingCard>

    <!-- 个人记忆 -->
    <SettingCard title="个人记忆" info="AI 对话时自动附加的偏好/事实，避免每次手动告知">
      <div class="memory-list">
        <div v-for="m in ai.memories" :key="m.id" class="memory-item">
          <el-switch :model-value="m.enabled" @change="ai.updateMemory(m.id, { enabled: $event })" />
          <el-input :model-value="m.title" size="small" style="width: 160px" placeholder="标题"
                    @change="ai.updateMemory(m.id, { title: $event })" />
          <el-input :model-value="m.content" type="textarea" :rows="2" style="flex:1" placeholder="内容"
                    @change="ai.updateMemory(m.id, { content: $event })" />
          <el-button type="danger" link @click="ai.removeMemory(m.id)">删除</el-button>
        </div>
      </div>
      <el-button type="primary" plain size="small" data-test="add-memory"
                 @click="ai.addMemory({ title: '', content: '', type: 'preference' })">+ 添加记忆</el-button>
    </SettingCard>

    <!-- 清除聊天历史 -->
    <SettingCard title="清除聊天历史" info="清空当前 AI 助手对话记录（不可恢复）">
      <el-button type="danger" plain size="small" data-test="clear-history" @click="onClearHistory">清除</el-button>
    </SettingCard>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useAiSettingsStore, isCustomProvider } from '@/stores/aiSettings'
import { useCustomProvidersStore } from '@/stores/customProviders'
import { useChatStore } from '@/stores/chat'
import { useModelVisionStore } from '@/stores/modelVision'
import { PROVIDERS } from '@/stores/aiSettings'
import { TOOLS } from '@/ide/tools/registry'
import { capabilityOf, formatContext } from '@/services/llm/modelCapabilities'
import { iconUrlOf } from '@/services/llm/icons'
import SettingCard from './SettingCard.vue'

const ai = useAiSettingsStore()
const chat = useChatStore()
const customProviders = useCustomProvidersStore()
const modelVision = useModelVisionStore()

const customBaseUrl = computed(() => {
  if (!isCustomProvider(ai.provider)) return ''
  const uuid = ai.provider.slice('custom:'.length)
  return customProviders.get(uuid)?.baseUrl || ''
})

function onProviderChange(pid) {
  if (pid === 'custom') return ai.setProvider('custom:default')
  ai.setProvider(pid)
}

function onCustomBaseUrlChange(url) {
  const uuid = ai.provider.slice('custom:'.length)
  customProviders.update(uuid, { baseUrl: url })
  ai.fetchModels()
}

function capOf(m) {
  const base = capabilityOf(ai.provider, m)
  const baseUrl = ai.getBaseUrl()
  return { ...base, vision: modelVision.hasVision(baseUrl, m) }
}

const deepDisabled = computed(() => capabilityOf(ai.provider, ai.model).reasoning !== 'native')
const deepDisabledTooltip = computed(() => `当前模型 (${ai.model}) 不支持原生推理；如需思考请用「快速/自动」`)

async function onClearHistory() {
  try {
    await ElMessageBox.confirm('确定清空所有 AI 助手对话记录？此操作不可恢复。', '清除聊天历史', {
      type: 'warning', confirmButtonText: '清除', cancelButtonText: '取消',
    })
    chat.clearMessages()
  } catch { /* 用户取消 */ }
}
</script>

<style scoped>
.provider-icon { width: 14px; height: 14px; vertical-align: middle; margin-right: 4px; }
.provider-row { display: inline-flex; align-items: center; gap: 4px; }
.model-row { display: inline-flex; align-items: center; gap: 6px; }
.tool-perm-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 0; border-bottom: 1px solid var(--km-border-light);
}
.tool-perm-row:last-child { border-bottom: 0; }
.tool-info { display: flex; flex-direction: column; min-width: 0; }
.tool-name { font-size: 13px; font-weight: 600; color: var(--km-gray-800); }
.tool-desc { font-size: 11.5px; color: var(--km-gray-500); margin-top: 2px; }
.memory-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; width: 100%; }
.memory-item { display: flex; align-items: center; gap: 8px; width: 100%; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/__tests__/assistant-settings.test.js`
Expected: PASS — 4 tests

- [ ] **Step 5: Commit**

```bash
git add frontend/src/ide/settings/AssistantSettings.vue frontend/src/__tests__/assistant-settings.test.js
git commit -m "feat(settings): AssistantSettings — 厂商/模型/key + 思考模式 + 工具权限 + 记忆 + 清历史"
```

---

## Task 12: agentLlm store + withOverrides helper

> Agent 独立 LLM 配置 store（localStorage `kmatch-agent-llm`）+ 显式注入 helper。

**Files:**
- Create: `frontend/src/stores/agentLlm.js`
- Create: `frontend/src/services/llm/overrides.js`
- Test: `frontend/src/__tests__/agentLlm-store.test.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/agentLlm-store.test.js`:

```js
import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAgentLlmStore, withOverrides } from '@/stores/agentLlm'

describe('agentLlm store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('defaults to useOverrides=false + empty key', () => {
    const s = useAgentLlmStore()
    expect(s.state.useOverrides).toBe(false)
    expect(s.state.apiKey).toBe('')
  })

  it('buildOverrides returns null when disabled', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(false)
    expect(s.buildOverrides()).toBeNull()
  })

  it('buildOverrides returns null when enabled but no apiKey', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(true)
    s.setProvider('deepseek')
    s.setModel('deepseek-v4-pro')
    expect(s.buildOverrides()).toBeNull()
  })

  it('buildOverrides returns overrides when enabled + key set', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(true)
    s.setProvider('deepseek')
    s.setApiKey('sk-x')
    s.setBaseUrl('https://api.deepseek.com/v1')
    s.setModel('deepseek-v4-pro')
    expect(s.buildOverrides()).toEqual({
      api_key: 'sk-x',
      base_url: 'https://api.deepseek.com/v1',
      model: 'deepseek-v4-pro',
      protocol: 'openai',
    })
  })

  it('withOverrides injects llm_overrides when enabled', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(true)
    s.setApiKey('sk-x')
    s.setProvider('deepseek')
    s.setModel('m')
    const body = withOverrides({ target_direction: 'x' })
    expect(body.llm_overrides).toBeDefined()
    expect(body.target_direction).toBe('x')
  })

  it('withOverrides is no-op when disabled', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(false)
    const body = withOverrides({ target_direction: 'x' })
    expect(body.llm_overrides).toBeUndefined()
  })

  it('persists across store instances', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(true)
    s.setApiKey('sk-persist')
    setActivePinia(createPinia())
    const s2 = useAgentLlmStore()
    expect(s2.state.useOverrides).toBe(true)
    expect(s2.state.apiKey).toBe('sk-persist')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/agentLlm-store.test.js`
Expected: FAIL — module not found

- [ ] **Step 3: Create agentLlm store**

Create `frontend/src/stores/agentLlm.js`:

```js
/**
 * Agent 学习引擎独立 LLM 配置 store (Spec B)
 *
 * 与 AI 助手 (aiSettings) 解耦：Agent 链（学情检测/资源生成/代码审查/测试）可用独立 key。
 * 本期 protocol 固定 'openai'（Anthropic 接入留后续 spec）。
 *
 * buildOverrides() 返回供 axios body 注入的 llm_overrides；关闭或无 key 时返回 null（走后端 .env）。
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'
import { PROVIDERS, isCustomProvider, customProviderUuid } from './aiSettings'
import { useCustomProvidersStore } from './customProviders'

const STORAGE_KEY = 'kmatch-agent-llm'

function providerBaseUrl(pid) {
  if (isCustomProvider(pid)) {
    const cp = useCustomProvidersStore().get(customProviderUuid(pid))
    return cp?.baseUrl || ''
  }
  const meta = PROVIDERS.find((p) => p.id === pid)
  return meta?.baseUrl || ''
}

function defaultState() {
  return {
    useOverrides: false,
    provider: 'deepseek',
    apiKey: '',
    baseUrl: providerBaseUrl('deepseek'),
    model: 'deepseek-v4-pro',
    protocol: 'openai',
  }
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return defaultState()
    const s = JSON.parse(raw)
    return { ...defaultState(), ...s }
  } catch {
    return defaultState()
  }
}

function saveState(state) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)) } catch { /* quota / private */ }
}

export const useAgentLlmStore = defineStore('agentLlm', () => {
  const state = ref(loadState())

  function persist() { saveState(state.value) }

  function setUseOverrides(on) { state.value.useOverrides = !!on; persist() }
  function setProvider(pid) {
    state.value.provider = pid
    state.value.baseUrl = providerBaseUrl(pid)
    if (isCustomProvider(pid)) {
      const cp = useCustomProvidersStore().get(customProviderUuid(pid))
      state.value.apiKey = cp?.apiKey || ''
    }
    persist()
  }
  function setApiKey(key) { state.value.apiKey = key; persist() }
  function setBaseUrl(url) { state.value.baseUrl = url; persist() }
  function setModel(m) { state.value.model = m; persist() }

  /** 返回供请求体注入的 overrides；关闭/无 key 时返回 null（走后端 .env 默认）。 */
  function buildOverrides() {
    if (!state.value.useOverrides) return null
    if (!state.value.apiKey?.trim()) return null
    return {
      api_key: state.value.apiKey,
      base_url: state.value.baseUrl,
      model: state.value.model,
      protocol: state.value.protocol,   // 本期固定 'openai'
    }
  }

  return { state, setUseOverrides, setProvider, setApiKey, setBaseUrl, setModel, buildOverrides }
})

/**
 * 显式注入 helper：把 agentLlm.buildOverrides() 注入请求 body。
 * Agent 路由（assess/submit/feedback/stream/project review/test）调用点用它。
 * 关闭或无 key 时原样返回 body（走后端 .env）。
 */
export function withOverrides(body) {
  const overrides = useAgentLlmStore().buildOverrides()
  if (!overrides) return body
  return { ...(body || {}), llm_overrides: overrides }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/__tests__/agentLlm-store.test.js`
Expected: PASS — 7 tests

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/agentLlm.js frontend/src/__tests__/agentLlm-store.test.js
git commit -m "feat(stores): agentLlm store + withOverrides 注入 helper"
```

---

## Task 13: 前端 6 注入点接 withOverrides

> `api/diagnostics.js` 4 函数 + `chat.js` SSE stream body + `chat.js` project review/test body。

**Files:**
- Modify: `frontend/src/api/diagnostics.js`
- Modify: `frontend/src/stores/assessment.js`（SSE stream body）
- Modify: `frontend/src/stores/chat.js`（project review/test body）
- Test: `frontend/src/__tests__/agent-overrides-injection.test.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/agent-overrides-injection.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAgentLlmStore } from '@/stores/agentLlm'

// 用 mock http adapter 拦截 axios，断言 body 含 llm_overrides
describe('agent overrides injection into diagnostics API', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    globalThis.window = globalThis.window || {}
    window.api = window.api || {}
  })

  it('submitAssessment injects llm_overrides when agent overrides enabled', async () => {
    const agent = useAgentLlmStore()
    agent.setUseOverrides(true)
    agent.setApiKey('sk-agent')
    agent.setProvider('deepseek')
    agent.setModel('dm')

    const captured = {}
    window.api.http.request = vi.fn(async (method, url, body) => {
      captured.body = body
      return { ok: true, status: 200, body: { session_id: 's', profile: {}, review_results: {}, assessment: {}, knowledge_graph: {}, generated_content: {}, learning_report: {}, orchestration_log: [] } }
    })

    const { submitAssessment } = await import('@/api/diagnostics')
    await submitAssessment({ targetDirection: 'x' })
    expect(captured.body.llm_overrides).toEqual(expect.objectContaining({ api_key: 'sk-agent', model: 'dm' }))
  })

  it('submitAssessment does NOT inject when agent overrides disabled', async () => {
    const agent = useAgentLlmStore()
    agent.setUseOverrides(false)
    const captured = {}
    window.api.http.request = vi.fn(async (method, url, body) => {
      captured.body = body
      return { ok: true, status: 200, body: { session_id: 's', profile: {}, review_results: {}, assessment: {}, knowledge_graph: {}, generated_content: {}, learning_report: {}, orchestration_log: [] } }
    })
    const { submitAssessment } = await import('@/api/diagnostics')
    await submitAssessment({ targetDirection: 'x' })
    expect(captured.body.llm_overrides).toBeUndefined()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/agent-overrides-injection.test.js`
Expected: FAIL — body has no `llm_overrides`

- [ ] **Step 3: Inject into diagnostics.js (4 functions)**

In `frontend/src/api/diagnostics.js`, import `withOverrides` at top (after line 11 `import http from './index'`):

```js
import { withOverrides } from '@/stores/agentLlm'
```

Then wrap each of the 4 request bodies. For `submitAssessment` (line 37-43), change the `http.post` body to `withOverrides({...})`:

```js
  return http.post('/api/diagnostics/assess', withOverrides({
    target_direction: targetDirection,
    mode,
    known_topics: knownTopics,
    scene,
    max_retries: maxRetries,
  }), signal ? { signal } : undefined)
```

For `submitAnswers` (line 83-86):

```js
  return http.post('/api/diagnostics/submit', withOverrides({
    session_id: sessionId,
    answers,
  }), signal ? { signal } : undefined)
```

For `requestFeedback` (line 106-110):

```js
  return http.post('/api/diagnostics/feedback', withOverrides({
    session_id: sessionId,
    strategy,
    profile,
  }), signal ? { signal } : undefined)
```

For `startAssessmentStream` (line 133-138), the SSE body:

```js
  const body = withOverrides({
    target_direction: payload.targetDirection,
    mode: 'demo',
    scene: payload.scene || 'no_project',
    max_retries: payload.maxRetries ?? 3,
  })
```

- [ ] **Step 4: Inject into chat.js project review/test bodies**

In `frontend/src/stores/chat.js`, import `withOverrides` (add after line 20 `import { streamChat }...`):

```js
import { withOverrides } from '@/stores/agentLlm'
```

For `code_review` tool body (line 614-618):

```js
        const body = withOverrides({
          code: src.code,
          target_direction: call.target_direction,
          knowledge_node_ids: call.knowledge_node_ids || null,
        })
```

For `code_test` tool body (line 627-634):

```js
        const body = withOverrides({
          source_type: 'text',
          code: src.code,
          filename: call.filename || 'main.py',
          target_direction: call.target_direction,
          knowledge_node_ids: call.knowledge_node_ids || null,
          mode: call.mode || 'generate',
        })
```

⚠️ `withOverrides` 调用 `useAgentLlmStore()`，需在 Pinia 上下文内。`chat.js` 已是 store（setup 内），子调用栈内 Pinia 已激活，安全。但若 `withOverrides` 在 store 初始化时被过早调用会报错——此处都在 action 运行期调用，安全。

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/__tests__/agent-overrides-injection.test.js`
Expected: PASS — 2 tests

- [ ] **Step 6: Run full frontend test suite for regression**

Run: `cd frontend && npx vitest run 2>&1 | tail -25`
Expected: PASS — no regressions in existing diagnostics/chat tests

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/diagnostics.js frontend/src/stores/chat.js frontend/src/__tests__/agent-overrides-injection.test.js
git commit -m "feat(api): 6 agent 路由调用点接 withOverrides 注入 llm_overrides"
```

---

## Task 14: AgentSettings — Agent 学习引擎段 UI

> 开关 + 厂商（anthropic disabled）/key/baseUrl/model + 测试连接（调 `/api/agents/ping`）。

**Files:**
- Modify: `frontend/src/ide/settings/AgentSettings.vue` (replace stub)
- Test: `frontend/src/__tests__/agent-settings.test.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/agent-settings.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AgentSettings from '@/ide/settings/AgentSettings.vue'
import { useAgentLlmStore } from '@/stores/agentLlm'

describe('AgentSettings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    globalThis.window = globalThis.window || {}
    window.api = window.api || {}
    window.api.http = { request: vi.fn() }
  })

  it('hides config when useOverrides off', () => {
    const w = mount(AgentSettings, { global: { stubs: ['el-icon'] } })
    expect(w.find('[data-test="agent-provider"]').exists()).toBe(false)
  })

  it('shows config when useOverrides on', async () => {
    const agent = useAgentLlmStore()
    agent.setUseOverrides(true)
    const w = mount(AgentSettings, { global: { stubs: ['el-icon'] } })
    expect(w.find('[data-test="agent-provider"]').exists()).toBe(true)
  })

  it('anthropic provider option is disabled', async () => {
    const agent = useAgentLlmStore()
    agent.setUseOverrides(true)
    const w = mount(AgentSettings, { global: { stubs: ['el-icon'] } })
    // el-option 的 disabled prop — 找 anthropic option
    const options = w.findAllComponents({ name: 'ElOption' })
    const anthropic = options.find((o) => o.props('value') === 'anthropic')
    expect(anthropic?.props('disabled')).toBe(true)
  })

  it('test connection calls /api/agents/ping with overrides', async () => {
    const agent = useAgentLlmStore()
    agent.setUseOverrides(true)
    agent.setApiKey('sk-x')
    agent.setProvider('deepseek')
    agent.setModel('m')
    window.api.http.request.mockResolvedValueOnce({ ok: true, status: 200, body: { ok: true, content: 'pong' } })
    const w = mount(AgentSettings, { global: { stubs: ['el-icon'] } })
    await w.find('[data-test="test-conn"]').trigger('click')
    await flushPromises()
    expect(window.api.http.request).toHaveBeenCalledWith('POST', '/api/agents/ping',
      expect.objectContaining({ llm_overrides: expect.objectContaining({ api_key: 'sk-x' }) }))
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/agent-settings.test.js`
Expected: FAIL — stub has no `[data-test=...]`

- [ ] **Step 3: Implement AgentSettings**

Replace `frontend/src/ide/settings/AgentSettings.vue` with:

```vue
<template>
  <div class="agent-settings">
    <SettingCard title="启用 Agent 独立配置"
                 info="开启后，学情检测/资源生成/代码审查等 Agent 使用下方配置；关闭则走后端默认 .env">
      <el-switch :model-value="agent.state.useOverrides" @change="agent.setUseOverrides" />
    </SettingCard>

    <template v-if="agent.state.useOverrides">
      <SettingCard title="厂商" info="Agent 本期仅支持 OpenAI 兼容协议（Anthropic 暂不支持）">
        <el-select data-test="agent-provider" :model-value="agent.state.provider" size="small" style="width: 220px"
                   @change="agent.setProvider">
          <el-option v-for="p in PROVIDERS" :key="p.id" :label="p.label" :value="p.id"
                     :disabled="p.protocol === 'anthropic'"
                     :title="p.protocol === 'anthropic' ? 'Agent 本期仅支持 OpenAI 兼容协议' : ''" />
        </el-select>
      </SettingCard>

      <SettingCard title="API Key" info="Agent 学习引擎独立 key；仅本地存储">
        <el-input :model-value="agent.state.apiKey" type="password" show-password size="small" style="width: 320px"
                  placeholder="sk-..." @change="agent.setApiKey" />
      </SettingCard>

      <SettingCard v-if="isCustomProvider(agent.state.provider)" title="Base URL" info="自定义厂商端点">
        <el-input :model-value="agent.state.baseUrl" size="small" style="width: 320px"
                  placeholder="https://your-endpoint/v1" @change="agent.setBaseUrl" />
      </SettingCard>

      <SettingCard title="模型">
        <el-input :model-value="agent.state.model" size="small" style="width: 280px" placeholder="模型 ID"
                  @change="agent.setModel" />
      </SettingCard>

      <SettingCard title="测试连接" info="调一次 /api/agents/ping 验证 key/baseUrl/model 可用">
        <el-button type="primary" size="small" data-test="test-conn" :loading="testing" @click="testConn">测试</el-button>
        <span v-if="testResult" :class="testResult.ok ? 'conn-ok' : 'conn-err'">{{ testResult.message }}</span>
      </SettingCard>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useAgentLlmStore } from '@/stores/agentLlm'
import { PROVIDERS, isCustomProvider } from '@/stores/aiSettings'
import SettingCard from './SettingCard.vue'

const agent = useAgentLlmStore()
const testing = ref(false)
const testResult = ref(null)

async function testConn() {
  const overrides = agent.buildOverrides()
  if (!overrides) {
    testResult.value = { ok: false, message: '请先填写 API Key' }
    return
  }
  testing.value = true
  testResult.value = null
  try {
    const res = await window.api.http.request('POST', '/api/agents/ping', { llm_overrides: overrides })
    const data = res.body || {}
    if (res.ok && data.ok) {
      testResult.value = { ok: true, message: `✓ 连接成功（${(data.content || '').slice(0, 40)}）` }
    } else {
      testResult.value = { ok: false, message: `✗ ${data.error || '连接失败'}` }
    }
  } catch (e) {
    testResult.value = { ok: false, message: `✗ ${e.message || '请求失败'}` }
  } finally {
    testing.value = false
  }
}
</script>

<style scoped>
.conn-ok { color: var(--km-success, #67c23a); margin-left: 8px; font-size: 12.5px; }
.conn-err { color: var(--km-danger, #f56c6c); margin-left: 8px; font-size: 12.5px; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/__tests__/agent-settings.test.js`
Expected: PASS — 4 tests

- [ ] **Step 5: Commit**

```bash
git add frontend/src/ide/settings/AgentSettings.vue frontend/src/__tests__/agent-settings.test.js
git commit -m "feat(settings): AgentSettings — 独立 key 表单 + anthropic disabled + 测试连接"
```

---

## Task 15: ProvidersSettings — 自定义厂商 CRUD + ProviderEditDialog

> 盘活 `customProviders` store 多组 schema（Spec A 已落地，本期补 UI）。

**Files:**
- Create: `frontend/src/ide/settings/ProviderEditDialog.vue`
- Modify: `frontend/src/ide/settings/ProvidersSettings.vue` (replace stub)
- Test: `frontend/src/__tests__/providers-settings-crud.test.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/providers-settings-crud.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ProvidersSettings from '@/ide/settings/ProvidersSettings.vue'
import { useCustomProvidersStore } from '@/stores/customProviders'

describe('ProvidersSettings CRUD', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    globalThis.window = globalThis.window || {}
    window.api = window.api || {}
    window.api.http = { request: vi.fn() }
  })

  it('renders list of custom providers', async () => {
    const cps = useCustomProvidersStore()
    cps.add({ name: 'OpenRouter', baseUrl: 'https://openrouter.ai/v1', apiKey: 'k', models: ['m1'] })
    const w = mount(ProvidersSettings, { global: { stubs: ['el-icon'] } })
    await flushPromises()
    expect(w.text()).toContain('OpenRouter')
    expect(w.findAll('.cp-item')).toHaveLength(1)
  })

  it('delete button removes provider', async () => {
    const cps = useCustomProvidersStore()
    const cp = cps.add({ name: 'X', baseUrl: 'u' })
    const w = mount(ProvidersSettings, { global: { stubs: ['el-icon'] } })
    await flushPromises()
    await w.find('[data-test="cp-delete"]').trigger('click')
    expect(cps.list).toHaveLength(0)
  })

  it('new provider button opens dialog', async () => {
    const w = mount(ProvidersSettings, { global: { stubs: ['el-icon'] } })
    await w.find('[data-test="cp-new"]').trigger('click')
    expect(w.findComponent({ name: 'ProviderEditDialog' }).exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/providers-settings-crud.test.js`
Expected: FAIL — stub has no `.cp-item`

- [ ] **Step 3: Create ProviderEditDialog**

Create `frontend/src/ide/settings/ProviderEditDialog.vue`:

```vue
<template>
  <el-dialog :model-value="modelValue" title="自定义厂商" width="480px" @update:model-value="$emit('update:modelValue', $event)">
    <el-form label-width="90px" size="small">
      <el-form-item label="名称">
        <el-input :model-value="form.name" placeholder="如 OpenRouter" @input="form.name = $event" />
      </el-form-item>
      <el-form-item label="Base URL">
        <el-input :model-value="form.baseUrl" placeholder="https://.../v1" @input="form.baseUrl = $event" />
      </el-form-item>
      <el-form-item label="API Key">
        <el-input :model-value="form.apiKey" type="password" show-password placeholder="sk-..." @input="form.apiKey = $event" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input :model-value="form.description" @input="form.description = $event" />
      </el-form-item>
      <el-form-item label="模型">
        <el-input :model-value="modelsText" type="textarea" :rows="2"
                  placeholder="自动获取或每行一个" @input="onModelsInput" />
        <el-button link size="small" :loading="fetching" @click="autoFetch">自动获取</el-button>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { useCustomProvidersStore } from '@/stores/customProviders'

const props = defineProps({
  modelValue: Boolean,
  provider: { type: Object, default: null }, // 编辑时传入；新建时 null
})
const emit = defineEmits(['update:modelValue', 'save'])

const cps = useCustomProvidersStore()
const form = ref({ name: '', baseUrl: '', apiKey: '', description: '', models: [] })
const fetching = ref(false)

watch(() => props.modelValue, (open) => {
  if (open) {
    form.value = props.provider
      ? { ...props.provider, models: [...(props.provider.models || [])] }
      : { name: '', baseUrl: '', apiKey: '', description: '', models: [] }
  }
}, { immediate: true })

const modelsText = computed(() => (form.value.models || []).join('\n'))
function onModelsInput(v) { form.value.models = v.split('\n').map((s) => s.trim()).filter(Boolean) }

async function autoFetch() {
  if (!form.value.baseUrl) return
  fetching.value = true
  // 临时存一个再 fetch；或直接调 /api/chat/models
  const tmp = cps.add({ name: form.value.name || 'tmp', baseUrl: form.value.baseUrl, apiKey: form.value.apiKey })
  const r = await cps.autoFetchModels(tmp.id)
  fetching.value = false
  if (r.ok) form.value.models = r.models
}

function save() {
  const payload = { ...form.value }
  emit('save', payload)
  emit('update:modelValue', false)
}
</script>
```

- [ ] **Step 4: Implement ProvidersSettings**

Replace `frontend/src/ide/settings/ProvidersSettings.vue` with:

```vue
<template>
  <div class="providers-settings">
    <SettingCard title="自定义厂商" info="新增 OpenRouter / 内部代理 / 302.ai 等自定义厂商，各自模型列表+key 独立">
      <div class="cp-list" style="width: 100%">
        <div v-for="cp in cps.list" :key="cp.id" class="cp-item">
          <div class="cp-info">
            <span class="cp-name">{{ cp.name }}</span>
            <span class="cp-baseurl">{{ cp.baseUrl }}</span>
            <span class="cp-models">{{ (cp.models || []).length }} 个模型</span>
          </div>
          <el-button-group>
            <el-button size="small" @click="editProvider(cp)">编辑</el-button>
            <el-button size="small" type="danger" data-test="cp-delete" @click="removeProvider(cp.id)">删除</el-button>
          </el-button-group>
        </div>
      </div>
      <el-button type="primary" plain size="small" data-test="cp-new" @click="openNew">+ 新建厂商</el-button>
    </SettingCard>

    <ProviderEditDialog v-model="dialogVisible" :provider="editing" @save="onSave" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useCustomProvidersStore } from '@/stores/customProviders'
import SettingCard from './SettingCard.vue'
import ProviderEditDialog from './ProviderEditDialog.vue'

const cps = useCustomProvidersStore()
const dialogVisible = ref(false)
const editing = ref(null)

function openNew() { editing.value = null; dialogVisible.value = true }
function editProvider(cp) { editing.value = cp; dialogVisible.value = true }

function onSave(payload) {
  if (editing.value) cps.update(editing.value.id, payload)
  else cps.add(payload)
}

async function removeProvider(id) {
  try {
    await ElMessageBox.confirm('确定删除该自定义厂商？', '删除', { type: 'warning' })
    cps.remove(id)
  } catch { /* cancel */ }
}
</script>

<style scoped>
.cp-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
.cp-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; border: 1px solid var(--km-border-light); border-radius: var(--km-radius-md);
}
.cp-info { display: flex; flex-direction: column; min-width: 0; }
.cp-name { font-size: 13px; font-weight: 600; color: var(--km-gray-800); }
.cp-baseurl { font-size: 11.5px; color: var(--km-gray-500); }
.cp-models { font-size: 11.5px; color: var(--km-gray-400); }
</style>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/__tests__/providers-settings-crud.test.js`
Expected: PASS — 3 tests

- [ ] **Step 6: Commit**

```bash
git add frontend/src/ide/settings/ProvidersSettings.vue frontend/src/ide/settings/ProviderEditDialog.vue frontend/src/__tests__/providers-settings-crud.test.js
git commit -m "feat(settings): ProvidersSettings 自定义厂商 CRUD + ProviderEditDialog"
```

---

## Task 16: 批量 vision 探测 + 清缓存 UI

> 复用 Spec A 的 `/api/chat/probe-vision` + `modelVision` store。串行探测所有 customProviders 未知模型，进度 + 取消。

**Files:**
- Modify: `frontend/src/ide/settings/ProvidersSettings.vue`
- Test: `frontend/src/__tests__/providers-vision-batch.test.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/providers-vision-batch.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ProvidersSettings from '@/ide/settings/ProvidersSettings.vue'
import { useCustomProvidersStore } from '@/stores/customProviders'

describe('ProvidersSettings vision batch', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    globalThis.window = globalThis.window || {}
    window.api = window.api || {}
    window.api.http = { request: vi.fn(async () => ({ ok: true, status: 200, body: { vision: true } })) }
  })

  it('batch probe button exists with count', async () => {
    const cps = useCustomProvidersStore()
    cps.add({ name: 'X', baseUrl: 'u', apiKey: 'k', models: ['m1', 'm2'] })
    const w = mount(ProvidersSettings, { global: { stubs: ['el-icon'] } })
    await flushPromises()
    expect(w.find('[data-test="vision-batch"]').exists()).toBe(true)
    expect(w.text()).toContain('2')
  })

  it('clear cache button calls modelVision.clearAll', async () => {
    const w = mount(ProvidersSettings, { global: { stubs: ['el-icon'] } })
    await flushPromises()
    await w.find('[data-test="vision-clear"]').trigger('click')
    await flushPromises()
    // DELETE /api/chat/probe-vision/cache 被调
    expect(window.api.http.request).toHaveBeenCalledWith('DELETE', '/api/chat/probe-vision/cache')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/providers-vision-batch.test.js`
Expected: FAIL — no `[data-test="vision-batch"]`

- [ ] **Step 3: Add vision batch + clear to ProvidersSettings**

In `frontend/src/ide/settings/ProvidersSettings.vue`, add a SettingCard after the custom-providers card (before `<ProviderEditDialog>`), and import `useModelVisionStore`. Add import in script:

```js
import { useModelVisionStore } from '@/stores/modelVision'
```

Add `const modelVision = useModelVisionStore()` and batch state:

```js
const probing = ref(false)
const probeProgress = ref({ done: 0, total: 0 })
let probeCancelled = false

const allModels = computed(() => {
  const out = []
  cps.list.forEach((cp) => {
    (cp.models || []).forEach((m) => out.push({ baseUrl: cp.baseUrl, apiKey: cp.apiKey, model: m, name: cp.name }))
  })
  return out
})

async function batchProbeVision() {
  const targets = allModels.value
  if (!targets.length) return
  try {
    await ElMessageBox.confirm(`即将探测 ${targets.length} 个模型的视觉能力，约消耗少量 token，继续？`, '批量探测', { type: 'info' })
  } catch { return }
  probing.value = true
  probeCancelled = false
  probeProgress.value = { done: 0, total: targets.length }
  for (const t of targets) {
    if (probeCancelled) break
    await modelVision.probe(t.baseUrl, t.apiKey, t.model, 'openai')
    probeProgress.value.done++
  }
  probing.value = false
}

async function clearVisionCache() {
  await modelVision.clearAll()
}
```

Add `computed` to imports: `import { ref, computed } from 'vue'`.

Add the card in template (after the custom-providers `SettingCard`, before `<ProviderEditDialog>`):

```vue
    <SettingCard title="视觉能力探测" info="逐个探测每个模型是否支持图像输入，结果缓存；消耗少量 token">
      <el-button size="small" data-test="vision-batch" :loading="probing" @click="batchProbeVision">
        👁 批量检测（{{ probeProgress.done }}/{{ probeProgress.total || allModels.length }}）
      </el-button>
      <el-button v-if="probing" size="small" @click="probeCancelled = true">取消</el-button>
      <el-button size="small" type="danger" plain data-test="vision-clear" @click="clearVisionCache">🗑 清除视觉缓存</el-button>
    </SettingCard>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/__tests__/providers-vision-batch.test.js`
Expected: PASS — 2 tests

- [ ] **Step 5: Commit**

```bash
git add frontend/src/ide/settings/ProvidersSettings.vue frontend/src/__tests__/providers-vision-batch.test.js
git commit -m "feat(settings): 批量 vision 探测 + 清缓存 UI"
```

---

## Task 17: 网络代理 UI（盘活 proxy store 字段）

> 盘活 `aiSettings.proxy`（{enabled,type,url,scope}）。UI 改 store；proxy 落盘 + sidecar env 注入在 Task 18-19。

**Files:**
- Modify: `frontend/src/ide/settings/ProvidersSettings.vue`
- Test: `frontend/src/__tests__/proxy-settings.test.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/proxy-settings.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ProvidersSettings from '@/ide/settings/ProvidersSettings.vue'
import { useAiSettingsStore } from '@/stores/aiSettings'

describe('proxy settings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    globalThis.window = globalThis.window || {}
    window.api = window.api || {}
    window.api.http = { request: vi.fn() }
    window.api.setProxyConfig = vi.fn()
  })

  it('toggling proxy enabled calls setProxy', async () => {
    const ai = useAiSettingsStore()
    const w = mount(ProvidersSettings, { global: { stubs: ['el-icon'] } })
    await flushPromises()
    const sw = w.find('[data-test="proxy-enabled"]')
    await sw.vm.$emit('change', true)
    expect(ai.proxy.enabled).toBe(true)
  })

  it('url input calls setProxy', async () => {
    const ai = useAiSettingsStore()
    ai.setProxy({ enabled: true })
    const w = mount(ProvidersSettings, { global: { stubs: ['el-icon'] } })
    await flushPromises()
    await w.find('[data-test="proxy-url"]').vm.$emit('change', 'http://127.0.0.1:7890')
    expect(ai.proxy.url).toBe('http://127.0.0.1:7890')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/proxy-settings.test.js`
Expected: FAIL — no `[data-test="proxy-enabled"]`

- [ ] **Step 3: Add proxy card to ProvidersSettings**

In `frontend/src/ide/settings/ProvidersSettings.vue`, import `useAiSettingsStore`:

```js
import { useAiSettingsStore } from '@/stores/aiSettings'
```

Add `const ai = useAiSettingsStore()`. Add the proxy card in template (after the vision card, before `<ProviderEditDialog>`):

```vue
    <SettingCard title="网络代理" info="所有 LLM 出站请求通过此代理（影响后端 sidecar 进程）；改后需重启后端生效">
      <el-switch :model-value="ai.proxy.enabled" data-test="proxy-enabled"
                 @change="onProxyChange({ enabled: $event })" />
      <template v-if="ai.proxy.enabled">
        <el-input :model-value="ai.proxy.url" size="small" style="width: 240px"
                  placeholder="http://127.0.0.1:7890" data-test="proxy-url"
                  @change="onProxyChange({ url: $event })" />
        <el-select :model-value="ai.proxy.type" size="small" style="width: 110px"
                   @change="onProxyChange({ type: $event })">
          <el-option label="HTTP" value="http" />
          <el-option label="SOCKS5" value="socks5" />
        </el-select>
        <el-button size="small" type="primary" @click="restartBackend" :loading="restarting">重启后端</el-button>
      </template>
    </SettingCard>
```

Add the handlers in script:

```js
const restarting = ref(false)

function onProxyChange(patch) {
  ai.setProxy(patch)
  // 通知 main 进程落盘 + 准备下次 spawn 注入
  window.api?.setProxyConfig?.(ai.proxy)
}

async function restartBackend() {
  restarting.value = true
  try { await window.api?.restartBackend?.() } finally { restarting.value = false }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/__tests__/proxy-settings.test.js`
Expected: PASS — 2 tests

- [ ] **Step 5: Commit**

```bash
git add frontend/src/ide/settings/ProvidersSettings.vue frontend/src/__tests__/proxy-settings.test.js
git commit -m "feat(settings): 网络代理 UI — 盘活 proxy store + 落盘/重启触发"
```

---

## Task 18: Electron proxy 落盘 + IPC（proxy-cache.js + ipc/proxy.js + preload）

**Files:**
- Create: `electron/main/proxy-cache.js`
- Create: `electron/main/ipc/proxy.js`
- Modify: `electron/preload/index.js`
- Test: manual (Electron IPC; covered by integration check)

- [ ] **Step 1: Create proxy-cache.js**

Create `electron/main/proxy-cache.js`:

```js
/**
 * proxy 配置落盘 (Spec B) — 唯一需要 main 进程感知的配置。
 * main 启动早于 renderer，无法读 localStorage；落 userData/proxy-cache.json。
 */
import path from 'path'
import fs from 'fs'
import { app } from 'electron'

let cached = null

function cachePath() {
  return path.join(app.getPath('userData'), 'proxy-cache.json')
}

export function loadProxyCache() {
  try {
    const raw = fs.readFileSync(cachePath(), 'utf-8')
    cached = JSON.parse(raw)
  } catch {
    cached = null
  }
  return cached
}

export function saveProxyCache(proxy) {
  cached = proxy || null
  try {
    fs.writeFileSync(cachePath(), JSON.stringify(proxy || {}))
  } catch (e) {
    console.error('[proxy-cache] 写入失败', e)
  }
  return cached
}

export function getProxyCache() {
  return cached
}

/** 构造 spawn sidecar 时注入的 env（enabled 时才有 HTTP_PROXY/HTTPS_PROXY）。 */
export function proxyEnv() {
  const p = getProxyCache()
  if (!p || !p.enabled || !p.url) return {}
  const url = p.type === 'socks5' ? p.url.replace(/^socks5:\/\//, 'socks5://') : p.url
  return {
    HTTP_PROXY: url,
    HTTPS_PROXY: url,
    NO_PROXY: 'localhost,127.0.0.1',
  }
}
```

- [ ] **Step 2: Create ipc/proxy.js**

Create `electron/main/ipc/proxy.js`:

```js
/**
 * proxy IPC (Spec B) — setProxyConfig/getProxyConfig/restartBackend
 */
import { ipcMain } from 'electron'
import { saveProxyCache, getProxyCache } from '../proxy-cache.js'
import { restartBackend } from '../backend-sidecar.js'

export function registerProxyIpc() {
  ipcMain.handle('proxy:set', (_e, proxy) => {
    saveProxyCache(proxy)
    return getProxyCache()
  })
  ipcMain.handle('proxy:get', () => getProxyCache())
  ipcMain.handle('backend:restart', async () => {
    await restartBackend()
    return { ok: true }
  })
}
```

- [ ] **Step 3: Expose in preload**

In `electron/preload/index.js`, add a `proxy` namespace inside the `contextBridge.exposeInMainWorld('api', {...})` object (after the `window` block, before the closing `}`):

```js
  proxy: {
    setProxyConfig: (proxy) => ipcRenderer.invoke('proxy:set', proxy),
    getProxyConfig: () => ipcRenderer.invoke('proxy:get'),
    restartBackend: () => ipcRenderer.invoke('backend:restart'),
  },
```

- [ ] **Step 4: Commit**

```bash
git add electron/main/proxy-cache.js electron/main/ipc/proxy.js electron/preload/index.js
git commit -m "feat(electron): proxy-cache 落盘 + IPC (set/get/restartBackend) + preload 暴露"
```

---

## Task 19: sidecar spawn 注入 proxy env + restartBackend 导出 + main 启动握手

**Files:**
- Modify: `electron/main/backend-sidecar.js`
- Modify: `electron/main/index.js`

- [ ] **Step 1: Inject proxy env into spawnBackend + export restartBackend**

In `electron/main/backend-sidecar.js`, import `proxyEnv` at top (after line 11 `import { app } from 'electron'`):

```js
import { proxyEnv, loadProxyCache } from './proxy-cache.js'
```

Modify `spawnBackend()` to merge proxy env. In the dev branch (line 67-74) and packaged branch (line 53-62), add `env` with proxy. For the dev branch, change:

```js
  const proc = spawn(process.env.PYTHON || 'python', [
    '-m', 'uvicorn', 'app.main:app',
    '--host', '127.0.0.1', '--port', '8000',
  ], { cwd, stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, ...proxyEnv() } })
```

For the packaged branch (line 54-58), change the `env` line:

```js
      env: { ...process.env, ...proxyEnv() },
```

Then export `restartBackend` (after `stopBackend`, before `getBackendHealth`). Add:

```js
export async function restartBackend() {
  await stopBackend()
  // 重新 spawn（attach 优先；若旧的已停则 spawn 新的）
  if (await fetchHealth()) {
    console.log('[backend] 重启: 检测到已有后端, attach 复用')
    return
  }
  console.log('[backend] 重启 sidecar...')
  backendProc = spawnBackend()
  await waitForReady()
}
```

- [ ] **Step 2: Register proxy IPC + load cache at startup in main/index.js**

In `electron/main/index.js`, find where other IPC is registered and the app `whenReady` / before `startBackend()`. Add at startup (load cache before sidecar spawn):

Locate the `startBackend()` call in the ready handler. Before it, add:

```js
import { loadProxyCache } from './proxy-cache.js'
import { registerProxyIpc } from './ipc/proxy.js'
```

In the ready handler, before `startBackend()`:

```js
  loadProxyCache()           // 启动时读 proxy-cache.json，供 spawnBackend env 注入
  registerProxyIpc()
```

Run to find the exact location: `cd d:/Origin_jerry/KMatch-Desktop && grep -n "startBackend\|whenReady\|registerIpc\|import.*ipc" electron/main/index.js`

- [ ] **Step 3: Verify dev build loads**

Run: `cd d:/Origin_jerry/KMatch-Desktop && npm run build 2>&1 | tail -15`
Expected: build succeeds (Electron main bundles without import errors). If `proxyEnv` import path wrong, fix relative path.

- [ ] **Step 4: Commit**

```bash
git add electron/main/backend-sidecar.js electron/main/index.js
git commit -m "feat(electron): sidecar spawn 注入 proxy env + restartBackend 导出 + 启动握手"
```

---

## Task 20: 全量测试 + 收尾

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && python -m pytest -q 2>&1 | tail -20`
Expected: PASS — all green (existing 430+ + new override tests)

- [ ] **Step 2: Run full frontend test suite**

Run: `cd frontend && npx vitest run 2>&1 | tail -30`
Expected: PASS — all green (existing 195+ + new settings tests)

- [ ] **Step 3: Manual smoke (CDP + dev mode)**

⚠️ This step requires the desktop app running with a real LLM key; if the executing agent can't run the GUI, defer to the user.

Start dev (mind the env pollution note — see memory `project-tech-decisions`):

```bash
env -u ELECTRON_RUN_AS_NODE -u ELECTRON_FORCE_IS_PACKAGED npm run dev
```

Then verify via `scripts/cdp_probe.py` (port 9222):
1. ActivityBar 底部齿轮 → 进设置页，三段 + 锚点高亮正常
2. AI 助手段：改工具权限 → 回聊天 → AI 行为受影响
3. Agent 学习引擎：开关 → 填 DeepSeek key → 测试连接 → 跑场景一学情测评 → 后端日志确认用此 key
4. 供应商管理：新建厂商 → 自动获取模型 → 批量探测 vision
5. 网络代理：启用 → 填 URL → 重启后端 → 后端日志看 HTTP_PROXY 注入

- [ ] **Step 4: Update devlog + CLAUDE.md**

Add `docs/devlogs/Desktop_阶段12_SpecB.md` summarizing PRs landed. Update `CLAUDE.md` 关键文件索引 to add `frontend/src/ide/settings/` + `agentLlm.js` + `backend/app/api/agents.py`.

- [ ] **Step 5: Commit docs**

```bash
git add docs/devlogs/Desktop_阶段12_SpecB.md CLAUDE.md
git commit -m "docs: 阶段12 Spec B 收官 — 设置页 + Agent 独立 key + 孤儿 store 盘活"
```

- [ ] **Step 6: Final cross-task review**

Run `/code-review` on the full branch diff. Address any High/Medium findings, then merge `feature/settings` → main.

---

## 自检（Self-Review 记录）

**Spec 覆盖核查（spec §1-§7）：**
- §1 设置视图装载 → Task 8（sidebar + ActivityBar + TitlebarMenu + MainArea）✓
- §2 设置页主体（线性 + 锚点 + SettingCard）→ Task 9 + 10 ✓
- §3.1 厂商/模型/key 表单 → Task 11 ✓
- §3.2 思考模式三态 → Task 11 ✓
- §3.3 工具权限 → Task 11 ✓
- §3.4 个人记忆 → Task 11 ✓
- §3.5 清除聊天历史 → Task 11（复用已有 clearMessages）✓
- §4.1 agentLlm store → Task 12 ✓
- §4.2 前端注入 → Task 13（withOverrides 而非 interceptor，决策 3）✓
- §4.3 后端 get_chat_model overrides → Task 1（ContextVar 决策 1）✓
- §4.3 后端 7 agent + 8 路由透传 → Task 2-7 ✓
- §4.3 orchestrator 透传 → 经 state.llm_overrides（Task 2）+ 节点 set（Task 3）✓
- §4.4 Agent UI + 测试连接 + /agents/ping → Task 7 + 14 ✓
- §5.1 自定义厂商 CRUD → Task 15 ✓
- §5.2 批量 vision + 清缓存 → Task 16 ✓
- §5.3 网络代理 + sidecar env → Task 17 + 18 + 19 ✓

**偏离 spec 的决策（已记录在「关键设计决策」）：**
- ContextVar 替代参数透传（决策 1）— 更少改动，单测兼容
- 前端 withOverrides 替代 axios interceptor（决策 3）— 覆盖 SSE + project 直 IPC
- lru_cache 保留（决策 6）— 与 ContextVar 不冲突
- llm_overrides 经 AgentState 而非 orchestrator 参数（工作流是 graph.invoke，无 agent 函数直调点）

**待执行者注意：** Task 8 与 Task 9/10 有依赖（MainArea 引用 SettingsView），按计划先 9→10→8。Task 3/4 的「整体移进 _node_body / with 块并缩进」需仔细，是易错点。
