"""
LLM 调用封装

统一通过 get_chat_model() 获取 Chat 模型实例，
所有 Agent 节点共用，便于单测 mock 与配置集中管理。

复用 app.config.settings 的 LLM_* 配置（DeepSeek，OpenAI 兼容接口）。
对齐 01_orchestrator_agent.txt 注意事项：LLM 超时最多重试 2 次。

Spec B: per-request LLM overrides 通过 ContextVar 承载。
- 路由层从请求体 llm_overrides 字段提取，用 use_llm_overrides(overrides) 上下文管理器 set。
- 工作流路径：节点用 @with_state_overrides 装饰器自动从 state["llm_overrides"] set/reset。
- content_generator 的 ThreadPoolExecutor 工作线程不继承 ContextVar，用 safe_llm_call 包装。
- 无 override 时 get_default_chat_model() 走 lru_cache 默认实例（行为不变，单测兼容）。
"""

import contextvars
import functools
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Callable, Optional, TypedDict

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
    max_retries: int = 2,
    timeout: Optional[int] = None,
    max_tokens: Optional[int] = None,
) -> ChatOpenAI:
    """创建 Chat 模型实例。

    Args:
        temperature: 生成温度，None 时用 settings.LLM_TEMPERATURE (0.3)
        overrides: 显式覆写（优先于 ContextVar）；None 时读 _current_overrides。
                   字段缺省时回退 settings 默认（部分覆写，不整体替换）。
        max_retries: 超时/5xx 重试次数。默认 2 (对齐 orchestrator prompt「重试 2 次」)；
                     交互等待路径 (判分) 可传 0 快速失败。
        timeout: 单次请求超时秒数；None 用 settings.LLM_TIMEOUT (60)。判分可用更短值(45)
                 让慢/坏的端点快速失败, 而不是长挂被前端掐断。

    Returns:
        ChatOpenAI 实例（OpenAI 兼容）

    Note:
        max_retries=2 对齐 orchestrator prompt「LLM 超时重试 2 次」要求。
        本函数始终返回新实例（override 路径不缓存）；无 override 时由
        get_default_chat_model 的 lru_cache 复用单例。
    """
    ovr = overrides if overrides is not None else _current_overrides.get()
    # 逐字段 strip 兜底: 粘贴带入的首尾空白/换行原样透传会被上游判 401 (key/base_url/model 均不容空白)
    if ovr:
        api_key = (ovr.get("api_key") or "").strip() or (settings.LLM_API_KEY or "").strip()
        base_url = (ovr.get("base_url") or "").strip() or (settings.LLM_BASE_URL or "").strip()
        model = (ovr.get("model") or "").strip() or (settings.LLM_MODEL or "").strip()
    else:
        api_key = (settings.LLM_API_KEY or "").strip()
        base_url = (settings.LLM_BASE_URL or "").strip()
        model = (settings.LLM_MODEL or "").strip()

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
        max_retries=max_retries,
        timeout=timeout if timeout is not None else settings.LLM_TIMEOUT,
        # 统一输出上限: 长讲义/实操/测试题生成不再被厂商默认 8K 拦腰截断 (截断治理①)
        max_tokens=max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS,
    )


@lru_cache(maxsize=1)
def _get_default_chat_model_cached() -> ChatOpenAI:
    """无 override 时的单例实例（lru_cache 缓存，单测通过 cache_clear 清除）。"""
    return get_chat_model()


def get_default_chat_model() -> ChatOpenAI:
    """单例：全流程共享的默认 Chat 模型实例。

    Spec B: 若 ContextVar 已设 overrides，绕过缓存直接构造（按需实例）——
    必须在查 lru_cache 之前判断，否则已缓存的默认实例会被直接返回
    （lru_cache 命中时不执行函数体，函数内的 ContextVar 判断无法生效）。
    无 override 时返回缓存的默认实例（单测 monkeypatch 兼容）。
    """
    if _current_overrides.get() is not None:
        # 绕过 lru_cache（缓存键无参，无法区分 overrides；直接构造，不污染缓存）
        return get_chat_model()
    return _get_default_chat_model_cached()


# 单测通过 get_default_chat_model.cache_clear() 清缓存 —— 代理到内部 lru_cache。
get_default_chat_model.cache_clear = _get_default_chat_model_cached.cache_clear


def llm_configured() -> bool:
    """是否配置了真实 LLM API Key（非占位符）。

    Spec B: ContextVar 设了 overrides 且含 api_key 时，视为已配置
    （用户用独立 key 跑 Agent，即便后端 .env 是占位符）。
    """
    ovr = _current_overrides.get()
    if ovr and ovr.get("api_key"):
        return True
    return settings.LLM_API_KEY not in ("", "sk-placeholder")


def is_auth_error(exc: BaseException) -> bool:
    """判断异常是否为 API Key 认证类错误 (401 / invalid key / authentication)。"""
    text = str(exc).lower()
    return any(k in text for k in (
        "401", "authentication", "invalid api key", "unauthorized",
        "incorrect api key", "api key is invalid",
    ))


def _mask_key_tail(key: str) -> str:
    """掩码展示密钥尾号 (只露末 4 位, 供用户核对 key 是否配错, 不泄漏全文)。"""
    if not key:
        return "空"
    return f"…{key[-4:]}" if len(key) >= 4 else "已配置"


def _effective_llm_snapshot() -> dict:
    """当前实际生效的 LLM 配置快照 (overrides → settings 逐字段回退, 与 get_chat_model 同口径)。

    用于 401 友好报错: 让用户直接看到本次请求打到哪个端点/模型/key 尾号,
    立刻区分「key 配错」vs「端点不匹配」vs「粘贴带脏字符」。
    """
    ovr = _current_overrides.get() or {}
    raw_key = ovr.get("api_key") or settings.LLM_API_KEY or ""
    return {
        "api_key": raw_key.strip(),
        "base_url": (ovr.get("base_url") or settings.LLM_BASE_URL or "").strip(),
        "model": (ovr.get("model") or settings.LLM_MODEL or "").strip(),
        "key_has_whitespace": raw_key != raw_key.strip(),
    }


def _is_model_error(exc: BaseException) -> bool:
    """判断异常是否为「模型名不存在/无效」类错误 (厂商返回 400)。"""
    text = str(exc).lower()
    return any(k in text for k in (
        "model not exist", "invalid model", "model_not_exist",
        "model does not exist", "no such model", "model not found",
    ))


def _provider_masked_key(exc: BaseException) -> str | None:
    """从厂商 401 原文提取打码后的 key (厂商只露末几位)。

    该值是「服务商实际收到的 key」的证据:
      - 与我方快照尾号一致 → Key 确实已在服务商侧失效/被删除/复制不完整;
      - 不一致 → 实际发出了别的 Key (配置串位), 与界面所配无关。
    """
    m = re.search(r"api[_ ]?key\s*[:：=]\s*(\*{2,}[\w-]{0,16})", str(exc), re.IGNORECASE)
    return m.group(1) if m else None


def friendly_llm_error(exc: BaseException) -> str:
    """把 LLM 调用异常转为用户可读中文提示。

    - 401/认证类 → 明确的配置引导 + 生效配置快照 (端点/模型/key 尾号, 便于自诊断)
    - 模型不存在类 → 引导「获取模型」自动校正 (key 有效但模型名不对的常见下一站)
    - 其余 → 首行原文 (保留排查线索), 不吞错误
    """
    if is_auth_error(exc):
        snap = _effective_llm_snapshot()
        parts = [
            "学习引擎 API Key 无效（401）。密钥来源优先级：设置 → 学习引擎 独立 Key → "
            "AI 助手 Key（未开启独立配置时自动回退）→ 后端默认密钥。",
            f"本次实际生效：base_url={snap['base_url'] or '(空)'}，model={snap['model'] or '(空)'}，"
            f"key={_mask_key_tail(snap['api_key'])}——请核对 key 尾号与厂商端点是否匹配。",
        ]
        if snap["key_has_whitespace"]:
            parts.append(
                "检测到密钥首尾含空白字符（多为复制粘贴带入），系统已自动去除后重试仍被拒；"
                "请重新完整复制 Key 再试。")
        provider_key = _provider_masked_key(exc)
        if provider_key:
            parts.append(
                f"服务商判定无效的 key：{provider_key}（厂商返回原文，自带打码）。"
                "与上方尾号一致 → 该 Key 已在服务商侧失效/被删除/复制不完整，"
                "请到服务商控制台重新生成后再试；不一致 → 实际发出了别的 Key，请检查是否多处配置。")
        parts.append(
            "端用户无需也无法修改 .env——请到 设置 → AI 助手 或 学习引擎 填入有效 API Key，"
            "点「测试连接」验证后重试。")
        parts.append(
            "若 Key 确认无误仍报 401：请检查本机是否开着系统代理/VPN（Windows 设置 → 网络和 "
            "Internet → 代理）——代理软件异常时会拦截并改写 LLM 请求响应；v1.3.0 起学习引擎"
            "默认绕过系统代理直连厂商，若你的网络必须走代理，请在 设置 → 网络代理 显式配置。")
        return "\n".join(parts)
    if _is_model_error(exc):
        snap = _effective_llm_snapshot()
        return "\n".join([
            "学习引擎模型不可用：当前厂商端点不存在该模型（400），Key 已通过校验。",
            f"本次请求：base_url={snap['base_url'] or '(空)'}，model={snap['model'] or '(空)'}。",
            "请到 设置 → 学习引擎 点「获取模型」拉取厂商真实模型列表自动校正，"
            "或手输正确模型 ID（如 deepseek-chat / deepseek-reasoner）后重试。",
        ])
    text = str(exc)
    return text.splitlines()[0] if text else "LLM 调用失败"


# ============================================================
# Spec B 工作流节点 / 线程池复用 helpers
# ============================================================

def with_state_overrides(fn: Callable) -> Callable:
    """装饰器：从 state["llm_overrides"] set ContextVar，节点退出自动 reset。

    用于 LangGraph 工作流节点的 _node 函数（签名 (state) -> dict）。
    无 overrides 时为 no-op（不设 ContextVar）。
    """
    @functools.wraps(fn)
    def wrapper(state, *args, **kwargs):
        # 透传额外 kwargs (如 progress_cb/cancel_check): LangGraph 仍以 _node(state) 调用不受影响,
        # report 补跑等直调路径可注入进度/取消回调。
        overrides = state.get("llm_overrides")
        token = _current_overrides.set(overrides) if overrides else None
        try:
            return fn(state, *args, **kwargs)
        finally:
            if token is not None:
                _current_overrides.reset(token)
    return wrapper


def safe_llm_call(fn: Callable, *args, overrides: dict = None,
                   logger=None, label: str = "") -> tuple[bool, Optional[dict]]:
    """线程池 worker 包装：在 worker 线程内重设 ContextVar，异常不外抛。

    ContextVar 不跨线程传播；ThreadPoolExecutor 的工作线程需显式 set，
    使 fn 内的 get_default_chat_model() 读到 overrides。

    Returns:
        (ok, result_or_None): 成功返回 (True, result)；失败返回 (False, None)。
    """
    token = _current_overrides.set(overrides) if overrides else None
    try:
        return True, fn(*args)
    except Exception:
        if logger is not None:
            logger.warning("LLM 调用失败 %s", label, exc_info=True)
        return False, None
    finally:
        if token is not None:
            _current_overrides.reset(token)
