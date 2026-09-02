"""耐久 run 记录 (Phase 1) — 借鉴 dsh_workflow 的持久 run 图思路。

把一次学情/协同执行 (demo 全流程 / interactive submit) 落盘到:

    data/workflow_runs/<session_id>/
      run.json      # 原子写入: 请求 meta + 汇总 + 完整结构化事件 + 原始日志 (复盘/续跑单一来源)
      events.jsonl  # append-only: 每次保存追加 {seq, ts, ...event} 事件时间线 (审计)

用途:
  - 复盘: 前端 loadRun(session_id) 回灌 orchestrationEvents, Agent 协同面板可重放
  - 续跑: run.json 保存请求 meta (target_direction/scene/mode/max_retries), 一键重跑
  - 审计: 结构化事件 + 原始日志永久保留

安全: session_id 归一化 (仅安全字符) 防路径穿越; run.json 用临时文件 + os.replace 原子替换。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from app.utils.logging import get_logger
from app.utils.redaction import redact_keys, should_redact

logger = get_logger(__name__)

RUNS_DIR_NAME = "workflow_runs"
# session_id 必须安全 (uuid 风格): 字母/数字/连字符/下划线/点
_SAFE_RE = re.compile(r"^[A-Za-z0-9._\-]+$")


def _runs_dir() -> Path:
    return settings.DATA_DIR / RUNS_DIR_NAME


def _safe_session_id(session_id: str) -> str:
    """归一化 session_id 防路径穿越; 非法/空值回落占位。"""
    sid = (session_id or "").strip()
    if not sid or not _SAFE_RE.match(sid) or sid in {".", ".."}:
        logger.warning("run_store: 非法 session_id=%r → fallback 'unknown'", session_id)
        return "unknown"
    return sid


def _run_dir(session_id: str) -> Path:
    return _runs_dir() / _safe_session_id(session_id)


def _atomic_write_json(path: Path, data: dict) -> None:
    """临时文件 + os.replace 原子写, 避免并发/中断产生半截 run.json。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_run(
    *,
    session_id: str,
    mode: str,
    request: Optional[dict] = None,
    events: Optional[list] = None,
    log: Optional[list] = None,
    summary: Optional[dict] = None,
    workflow: Optional[dict] = None,
) -> str:
    """持久化一次 run (可重复调用, 覆盖 run.json + 追加 events.jsonl)。

    workflow: Phase 2 流程定义快照 (provenance, 复盘可知当时跑的拓扑)。
    返回安全 session_id。
    """
    sid = _safe_session_id(session_id)
    d = _run_dir(sid)
    d.mkdir(parents=True, exist_ok=True)
    now = datetime.utcnow().isoformat()

    # 交互日志脱敏 (赛题(5)): 开关默认关 — 关闭时 request 原样保留, 与旧行为完全一致;
    # 开启 (PRIVACY_REDACT_INTERACTION_LOGS=1) 时, 对 request 内敏感键名
    # (answers/explanation/practical_evidence/api_key/learner_key/email/phone/name)
    # 打码后再落盘 run.json/events.jsonl。
    if should_redact():
        request = redact_keys(request) if isinstance(request, dict) else request

    # append-only 事件时间线: 带递增 seq, 每次保存续写
    evs = events or []
    # 读现有 seq 基线 (解析 events.jsonl 最末条目的 seq)，下次追加从其后继续
    jsonl = d / "events.jsonl"
    base_seq = 0
    if jsonl.exists():
        try:
            with open(jsonl, encoding="utf-8") as f:
                last_ev = None
                for line in f:
                    if line.strip():
                        last_ev = json.loads(line)
                if last_ev is not None:
                    base_seq = int(last_ev.get("seq", 0)) + 1
        except (json.JSONDecodeError, ValueError):
            base_seq = 0
    with open(jsonl, "a", encoding="utf-8") as f:
        for idx, ev in enumerate(evs):
            rec = {"seq": base_seq + idx, "ts": now, **ev}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # run.json 原子重写 (最新一次为完整真相源)
    payload = {
        "session_id": sid,
        "mode": mode,
        "request": request or {},
        "summary": summary or {},
        "workflow": workflow or {},
        "created_at": _read_meta(d).get("created_at", now),
        "updated_at": now,
        "orchestration_events": evs,
        "orchestration_log": log or [],
    }
    _atomic_write_json(d / "run.json", payload)
    logger.info("run_store: saved run=%s mode=%s events=%d", sid, mode, len(evs))
    return sid


def _read_meta(run_dir: Path) -> dict:
    """读现有 run.json 的元信息 (若无则空), 供 created_at 保持首次时间。"""
    try:
        with open(run_dir / "run.json", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def load_run(session_id: str) -> Optional[dict]:
    """读取一次 run 的完整记录 {run, events}；不存在返回 None。"""
    d = _run_dir(session_id)
    if not (d / "run.json").is_file():
        return None
    try:
        with open(d / "run.json", encoding="utf-8") as f:
            run = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("run_store: run.json 解析失败 session=%s err=%s", session_id, e)
        return None
    events = []
    try:
        with open(d / "events.jsonl", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("run_store: events.jsonl 解析失败 session=%s err=%s", session_id, e)
    return {"run": run, "events": events}


def _run_list_item(meta: dict, fallback_id: str) -> dict:
    """将耐久 run 投影为历史列表所需的最小展示摘要。

    ``run.json`` 包含便于续跑和复盘的完整 request，不能随着列表接口下发；
    前端列表仅依赖本函数显式列出的标题、场景和轻量汇总字段。
    """
    request = meta.get("request") if isinstance(meta.get("request"), dict) else {}
    summary = meta.get("summary") if isinstance(meta.get("summary"), dict) else {}
    scene = request.get("scene") or summary.get("scene") or ""
    target = request.get("target_direction") or summary.get("target_direction") or ""
    project_name = request.get("project_name") or summary.get("project_name") or ""
    # pipeline run 实际落盘的是 filename (如 a.py); project_name 仅为兼容预留, 现网无写入方
    filename = request.get("filename") or summary.get("filename") or ""
    is_project = scene == "with_project" or meta.get("mode") == "pipeline"

    if is_project:
        name = project_name or filename.removesuffix(".py") or target or "未命名项目"
        display_title = f"{name} · 项目质量流水线"
        scene_label = "有项目二次开发"
    else:
        display_title = f"学习 · {target or '未命名目标'}"
        scene_label = "无项目技能学习"

    return {
        "session_id": meta.get("session_id", fallback_id),
        "mode": meta.get("mode"),
        "display_title": display_title,
        "scene": scene,
        "scene_label": scene_label,
        "target_direction": target or None,
        "project_name": project_name or None,
        "status": summary.get("status") or "completed",
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
        "summary": summary,
    }


def list_runs(limit: int = 20) -> list:
    """按 updated_at 倒序列出最近 run 摘要 (供历史运行入口)。"""
    base = _runs_dir()
    items = []
    if not base.is_dir():
        return items
    for entry in base.iterdir():
        if not entry.is_dir():
            continue
        try:
            meta = _read_meta(entry)
        except Exception:  # noqa: BLE001
            continue
        if not meta:
            continue
        items.append(_run_list_item(meta, entry.name))
    items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return items[: max(1, int(limit))]


def delete_run(session_id: str) -> bool:
    """删除一次 run 记录 (issue-83): 安全归一化 session_id 后删除目录。

    返回是否删除成功 (不存在/已删除返回 False, 便于 API 层映射 404)。
    删除失败 (残留) 也返回 False, 由调用方提示。
    """
    import shutil

    sid = _safe_session_id(session_id)
    if sid == "unknown":
        return False
    d = _run_dir(sid)
    if not d.is_dir():
        return False
    try:
        shutil.rmtree(d)
    except OSError:
        logger.warning("run_store: 删除失败 session=%s", sid, exc_info=True)
        return False
    logger.info("run_store: deleted run=%s", sid)
    return not d.exists()
