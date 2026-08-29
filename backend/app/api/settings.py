"""
运行时设置 API 路由 (W?: 治"端用户被迫改 .env")

  GET  /api/settings/backend    当前生效配置 (key 脱敏: configured + 尾4位) + 存储/数据状态
  POST /api/settings/backend    保存并即时生效:
                                 - embedding: 重建引擎 embedding 客户端 (探活失败降级纯图)
                                 - judge: 下次裁判调用生效 (get_judge_llm 每次读生效配置)
  POST /api/settings/test-judge 用生效裁判配置做一次 1-token 探活 (设置页"测试连接")

key 更新协议: api_key=null=不变 / ""=清除 / 非空=更新 (GET 不回明文, 前端留空即不变)。
优先级: 运行时文件 > .env 默认 (详见 app/runtime_settings.py)。
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import runtime_settings
from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class EmbeddingPatch(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    clear_api_key: bool = False


class JudgePatch(BaseModel):
    enabled: bool | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    clear_api_key: bool = False


class BackendSettingsPatch(BaseModel):
    embedding: EmbeddingPatch | None = None
    judge: JudgePatch | None = None


def _get_store(request: Request):
    return getattr(request.app.state, "kg", None)


@router.get("/backend", summary="当前运行时设置 (key 脱敏) + 存储/数据状态")
def get_backend_settings(request: Request):
    kg = _get_store(request)
    emb = runtime_settings.effective_embedding()
    judge = runtime_settings.effective_judge()
    masked_emb = runtime_settings.masked(emb["api_key"])
    masked_judge = runtime_settings.masked(judge.get("api_key", ""))
    return {
        "embedding": {
            "configured": masked_emb["configured"],
            "key_tail": masked_emb["tail"],
            "base_url": emb["base_url"],
            "model": emb["model"],
            "source": emb["key_source"],
        },
        "judge": {
            "enabled": judge["enabled"],
            "source": judge["source"],
            "same_source": judge["same_source"],
            "base_url": judge.get("base_url", ""),
            "model": judge.get("model", ""),
            "key_tail": masked_judge["tail"],
        },
        "store": {
            "kind": getattr(kg, "kind", None),
            "semantic_ready": bool(kg.semantic_ready) if kg else False,
        },
        "data": {"local_dir": str(settings.LOCAL_DIR)},
    }


@router.post("/backend", summary="保存运行时设置并即时生效")
def save_backend_settings(patch: BackendSettingsPatch, request: Request):
    # ① 持久化 (patch → 文件; clear_api_key 显式置空, api_key=None 保持不变)
    raw = {}
    if patch.embedding is not None:
        sec = {"api_key": patch.embedding.api_key, "base_url": patch.embedding.base_url,
               "model": patch.embedding.model}
        if patch.embedding.clear_api_key:
            sec["api_key"] = ""
        raw["embedding"] = sec
    if patch.judge is not None:
        sec = {"enabled": patch.judge.enabled, "api_key": patch.judge.api_key,
               "base_url": patch.judge.base_url, "model": patch.judge.model}
        if patch.judge.clear_api_key:
            sec["api_key"] = ""
        raw["judge"] = sec
    try:
        runtime_settings.save(raw)
    except Exception as e:
        logger.error("运行时设置保存失败", exc_info=True)
        raise HTTPException(status_code=500, detail=f"设置保存失败: {e}")

    # ② embedding 即时生效 (探活; judge 由 get_judge_llm 每次读生效配置, 无需重建)
    applied = None
    kg = _get_store(request)
    if patch.embedding is not None and kg is not None and hasattr(kg, "reconfigure_embedding"):
        emb = runtime_settings.effective_embedding()
        try:
            ok = kg.reconfigure_embedding(emb["api_key"], emb["base_url"], emb["model"])
            applied = {"ok": ok, "semantic_ready": bool(getattr(kg, "semantic_ready", False))}
        except Exception as e:
            logger.warning("embedding 重配置异常", exc_info=True)
            applied = {"ok": False, "reason": str(e)}

    return {"saved": True, "embedding_applied": applied}


@router.post("/test-judge", summary="用生效裁判配置做一次 1-token 探活")
def test_judge():
    """设置页「测试连接」: 按当前生效配置实例化裁判并做最小调用。"""
    from app.agents.quality_judge import get_judge_llm
    try:
        judge, same_source = get_judge_llm()
        resp = judge.invoke("回复一个字: 好")
        text = getattr(resp, "content", "") or ""
        return {"ok": bool(text.strip()), "same_source": same_source,
                "detail": text.strip()[:20] or "(空响应)"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"裁判探活失败: {e}")
