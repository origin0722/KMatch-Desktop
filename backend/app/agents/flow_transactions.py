"""流程定义事务 (Phase 3b) — 借鉴 dsh-deepseek-flow 的"拓扑提交事务"。

画布/面板编辑先落到草稿 (draft)，不算提交；显式"应用修改/提交发布"才走:

    本地校验 (validate_definition 严格) → (记录审查 note/reviewedBy) →
    原子 revision 保存 → 成为 list_workflows 可发现定义

内置流程不可被覆盖；想改内置 = 以新 id 提交"衍生副本"。

存储:
    data/workflows/<id>.json                  # 已提交定义 (发现源)
    data/workflows/.revisions/<id>/<ts>.json  # 幂等 revision (可回滚)
    data/workflows-drafts/<id>.json           # 未提交草稿 (保留用户编辑)

所有 IO 均原子 (临时文件 + os.replace) / 幂等; 失败返回结构化结果, 不抛给调用方。
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
from app.agents.workflow_def import BUILTIN_WORKFLOWS, validate_definition

logger = get_logger(__name__)

_SAFE_RE = re.compile(r"^[A-Za-z0-9._\-]+$")


def _workflows_dir() -> Path:
    return settings.DATA_DIR / "workflows"


def _drafts_dir() -> Path:
    return settings.DATA_DIR / "workflows-drafts"


def _safe_id(workflow_id: str) -> str:
    sid = (workflow_id or "").strip()
    if not sid or not _SAFE_RE.match(sid) or sid in {".", ".."}:
        raise ValueError(f"非法流程 id: {workflow_id!r}")
    return sid


def _atomic_write(path: Path, data: dict) -> None:
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


def _now_ts() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")


def save_draft(definition: Any) -> dict:
    """存草稿 (WIP 允许未过严格校验, 返回 warnings 提示)。"""
    if not isinstance(definition, dict) or not definition.get("id"):
        return {"ok": False, "errors": ["草稿必须是对象且含 id"]}
    try:
        sid = _safe_id(definition["id"])
    except ValueError as e:
        return {"ok": False, "errors": [str(e)]}
    warnings = validate_definition(definition)
    _atomic_write(_drafts_dir() / f"{sid}.json", definition)
    return {"ok": True, "id": sid, "warnings": warnings, "valid": not warnings}


def commit_definition(definition: Any, *, note: str = "", reviewed_by: str = "") -> dict:
    """严格校验后原子提交为可发现定义 (revision 化)。内置 id 拒绝。"""
    if not isinstance(definition, dict) or not definition.get("id"):
        return {"ok": False, "errors": ["定义必须是对象且含 id"], "revision": None}
    try:
        sid = _safe_id(definition["id"])
    except ValueError as e:
        return {"ok": False, "errors": [str(e)], "revision": None}
    if sid in BUILTIN_WORKFLOWS:
        return {"ok": False, "errors": [f"内置流程不可覆盖: {sid} (请以新 id 提交衍生副本)"], "revision": None}
    errs = validate_definition(definition)
    if errs:
        return {"ok": False, "errors": errs, "revision": None}

    d = _workflows_dir()
    # revision 备份当前已发布版本
    revisions_dir = d / ".revisions" / sid
    revisions_dir.mkdir(parents=True, exist_ok=True)
    current = d / f"{sid}.json"
    rev_ts = _now_ts()
    if current.is_file():
        try:
            prev = json.loads(current.read_text(encoding="utf-8"))
            _atomic_write(revisions_dir / f"{rev_ts}_before.json", prev)
        except (OSError, json.JSONDecodeError):
            logger.warning("flow_tx: 读取旧定义失败, 仅存档新版本 id=%s", sid)

    payload = {
        "format": definition.get("format"),
        "version": definition.get("version"),
        "id": sid,
        "name": definition.get("name"),
        "description": definition.get("description"),
        "stages": definition.get("stages"),
        "inputs": definition.get("inputs"),
        "decisions": definition.get("decisions"),
        # 事务元数据 (非定义 schema 字段, 供审计/回滚; 只进 revision 文件, 不污染主定义)
        "_tx": {
            "rev": rev_ts,
            "committed_at": datetime.utcnow().isoformat(),
            "note": (note or "").strip(),
            "reviewed_by": (reviewed_by or "").strip(),
        },
    }
    # 主定义文件保持 schema 干净 (无 _tx), 保证 workflow_def 校验/发现不受影响
    clean = {k: v for k, v in payload.items() if not k.startswith("_")}
    _atomic_write(current, clean)
    _atomic_write(revisions_dir / f"{rev_ts}.json", payload)
    logger.info("flow_tx: commit id=%s rev=%s note=%r", sid, rev_ts, note)
    return {"ok": True, "id": sid, "revision": rev_ts, "committed": payload}


def list_revisions(workflow_id: str) -> list:
    """按时间列出 revision (仅"提交"条目; *_before 安全备份不当作可回滚 revision)。"""
    try:
        sid = _safe_id(workflow_id)
    except ValueError:
        return []
    rev_dir = _workflows_dir() / ".revisions" / sid
    items = []
    if rev_dir.is_dir():
        for p in sorted(rev_dir.glob("*.json")):
            if p.stem.endswith("_before"):  # 备份非提交, 不进回滚列表
                continue
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            items.append({
                "revision": p.stem,
                "id": meta.get("id", sid),
                "name": meta.get("name"),
                "_tx": meta.get("_tx", {}),
            })
    return items


def restore_revision(workflow_id: str, revision: str) -> dict:
    """回滚到指定 revision (校验合法后原子写回为当前定义)。"""
    try:
        sid = _safe_id(workflow_id)
        rev = _safe_id(revision)
    except ValueError as e:
        return {"ok": False, "errors": [str(e)]}
    p = _workflows_dir() / ".revisions" / sid / f"{rev}.json"
    if not p.is_file():
        return {"ok": False, "errors": [f"revision 不存在: {revision}"]}
    try:
        defn = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"ok": False, "errors": [f"读取 revision 失败: {e}"]}
    # 先校验, 坏 revision 不写回
    body = {k: v for k, v in defn.items() if not k.startswith("_")}
    errs = validate_definition(body)
    if errs:
        return {"ok": False, "errors": errs}
    _atomic_write(_workflows_dir() / f"{sid}.json", body)
    return {"ok": True, "id": sid, "restored": revision, "definition": body}


def get_definition(workflow_id: str) -> Optional[dict]:
    """读已提交定义 (不含事务元数据)。"""
    try:
        sid = _safe_id(workflow_id)
    except ValueError:
        return None
    body = {}
    if sid in BUILTIN_WORKFLOWS:
        body = dict(BUILTIN_WORKFLOWS[sid])
    p = _workflows_dir() / f"{sid}.json"
    if p.is_file():
        try:
            body = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("flow_tx: 读取 %s 失败 err=%s", p, e)
            return None
    return {k: v for k, v in body.items() if not k.startswith("_")} if body else None
