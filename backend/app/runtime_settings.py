"""
运行时设置 (W?): 治"端用户被迫改 .env"的产品缺口。

Embedding / 异源裁判等引擎级配置此前只能 .env 配置; 对安装包端用户而言,
"打开安装目录改环境变量文件"是产品失误。本模块提供 LOCAL_DIR 下的
backend_settings.json 持久化 + 进程内即时生效, 供 /api/settings 读写:

  优先级: 运行时文件 > .env 默认 (用户显式留空 = 回落 env, 保证已配 .env 的开发态不破坏)

安全边界: 文件含 key 明文, 仅落本机 LOCAL_DIR (打包态为用户 appData, dev 为 data/local),
不经任何网络上传; API 回读时 key 只回 configured 布尔 + 尾 4 位, 不回明文。
"""

import json
import os
import tempfile
from threading import RLock

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# RLock: save() 持锁内调用 load() — 普通 Lock 会自死锁
_LOCK = RLock()

# 合法字段 (白名单, 防任意键写入)
_EMBEDDING_KEYS = ("api_key", "base_url", "model")
_JUDGE_KEYS = ("enabled", "api_key", "base_url", "model")


def _file_path():
    return settings.LOCAL_DIR / "backend_settings.json"


def _defaults() -> dict:
    return {
        "embedding": {k: "" for k in _EMBEDDING_KEYS},
        "judge": {"enabled": False, **{k: "" for k in _JUDGE_KEYS if k != "enabled"}},
    }


def _sanitize(section: dict, keys) -> dict:
    out = {}
    for k in keys:
        v = section.get(k)
        if k == "enabled":
            out[k] = bool(v)
        else:
            out[k] = str(v).strip() if v is not None else ""
    return out


def load() -> dict:
    """读运行时设置 (坏文件/缺键回落默认, 不抛)。"""
    with _LOCK:
        data = _defaults()
        try:
            raw = _file_path()
            if raw.exists():
                parsed = json.loads(raw.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    if isinstance(parsed.get("embedding"), dict):
                        data["embedding"] = _sanitize(parsed["embedding"], _EMBEDDING_KEYS)
                    if isinstance(parsed.get("judge"), dict):
                        data["judge"] = _sanitize(parsed["judge"], _JUDGE_KEYS)
        except Exception as e:  # noqa: BLE001 设置文件损坏不应崩服务
            logger.warning("backend_settings.json 读取失败, 使用默认: %s", e)
        return data


def save(patch: dict) -> dict:
    """合并保存 (patch 中 None = 该键保持不变, "" = 显式清空), 原子写。返回保存后的完整配置。"""
    with _LOCK:
        current = load()
        for name, keys in (("embedding", _EMBEDDING_KEYS), ("judge", _JUDGE_KEYS)):
            section = patch.get(name)
            if not isinstance(section, dict):
                continue
            merged = dict(current[name])
            for k in keys:
                if k not in section:
                    continue
                v = section[k]
                if k == "enabled":
                    merged[k] = bool(v)
                elif v is None:
                    continue  # 未提供 → 保持
                else:
                    merged[k] = str(v).strip()
            current[name] = merged
        path = _file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    logger.info("运行时设置已保存: %s", path)
    return current


def _pick(file_val: str, env_val: str) -> tuple:
    """单字段生效值: 运行时文件显式配置 > env。返回 (值, 来源)。"""
    if file_val:
        return file_val, "runtime"
    if env_val and env_val != "sk-placeholder":
        return env_val, "env"
    return "", "unset"


def effective_embedding() -> dict:
    """Embedding 生效配置: 文件 > EMBEDDING_* env > LLM_* 回退 (与引擎 create 逻辑一致)。"""
    f = load().get("embedding", {})
    api_key, key_src = _pick(f.get("api_key"), settings.EMBEDDING_API_KEY)
    base_url, url_src = _pick(f.get("base_url"), settings.EMBEDDING_BASE_URL)
    model, model_src = _pick(f.get("model"), settings.EMBEDDING_MODEL)
    if not base_url:
        base_url = settings.LLM_BASE_URL
        url_src = "env" if settings.LLM_BASE_URL else "unset"
    if not model:
        # env 未配模型时与 config 默认一致 (text-embedding-v2)
        model, model_src = settings.EMBEDDING_MODEL, "default"
    return {
        "api_key": api_key, "key_source": key_src if api_key else "unset",
        "base_url": base_url, "model": model,
        "model_source": model_src, "url_source": url_src,
    }


def effective_judge() -> dict:
    """裁判生效配置: 运行时文件(需 enabled) > JUDGE_LLM_* env > 同源回退。"""
    f = load().get("judge", {})
    if f.get("enabled") and f.get("api_key"):
        return {
            "enabled": True, "source": "runtime",
            "api_key": f["api_key"],
            "base_url": f.get("base_url") or settings.LLM_BASE_URL,
            "model": f.get("model") or settings.LLM_MODEL,
            "same_source": False,
        }
    if settings.JUDGE_LLM_API_KEY:
        return {
            "enabled": True, "source": "env",
            "api_key": settings.JUDGE_LLM_API_KEY,
            "base_url": settings.JUDGE_LLM_BASE_URL or settings.LLM_BASE_URL,
            "model": settings.JUDGE_LLM_MODEL or settings.LLM_MODEL,
            "same_source": False,
        }
    return {"enabled": False, "source": "unset", "same_source": True}


def masked(key: str) -> dict:
    """key 脱敏回显: 只回 configured 布尔 + 尾 4 位, 不回明文。"""
    if not key:
        return {"configured": False, "tail": ""}
    return {"configured": True, "tail": key[-4:] if len(key) > 4 else "****"}
