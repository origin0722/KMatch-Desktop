"""画像档案 (跨次累积/进化) — 让画像从"每次测评都是新快照"变成"持续进化的档案"。

针对短板: 每次 `_build_profile` 都生成全新 profile_id、不读历史、不合并。
本模块提供:
  - merge_profiles(prev, new): 纯函数加权合并掌握度 + 生成版本 diff (进化核心, 可单测)
  - save_profile / load_profile: 耐久存储 (data/profile_archive/<key>/latest.json + history.jsonl)

约定 (v1 文档化取舍):
  - 有历史时复用 prev.profile_id (同一学习者一份持续档案); 首次则用 new 的 id。
  - 合并只覆盖 known_topics / weak_topics (掌握度真相源, 跨次进化目标);
    weakness_areas / recommended_path / 等级 仍以本次 (new) 为权威 —— 它们是"本轮的
    诊断结论", 而 known/weak 是"到目前累计的掌握度档案"。
  - learning_history 逐次追加; 未在本轮重测的旧节点原样结转 (快照语义, 不做遗忘衰减 v1)。
安全: learner key 归一化 (安全字符), 防路径穿越。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_SAFE_RE = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")


def safe_key(key: str) -> str:
    s = (key or "").strip()
    if not s or not _SAFE_RE.match(s):
        raise ValueError(f"非法学习者 key: {key!r}")
    return s


def _archive_dir() -> Path:
    return settings.DATA_DIR / "profile_archive"


_MASTERY_BOUND = 0.8
# 遗忘/时效: known 超该天数未重测 → 标 recheck_due (待重验)
STALE_AFTER_DAYS = 30


def _entry_map(profile) -> tuple[dict, dict]:
    """(node_id → entry) from known/weak, and kind map node_id → 'known'|'weak'."""
    def _norm(items):
        out = {}
        for it in items or []:
            if isinstance(it, dict) and it.get("node_id"):
                out[it["node_id"]] = it
        return out
    known = _norm(profile.get("known_topics"))
    weak = _norm(profile.get("weak_topics"))
    kind = {nid: "known" for nid in known}
    kind.update({nid: "weak" for nid in weak})
    master = {nid: it.get("mastery", 0) for nid, it in known.items()}
    master.update({nid: it.get("mastery", 0) for nid, it in weak.items()})
    return master, kind


def _classify(mastery: float) -> str:
    return "known" if mastery >= _MASTERY_BOUND else "weak"


def merge_profiles(prev: Optional[dict], new: dict,
                   now: Optional[datetime] = None) -> tuple[dict, Optional[dict]]:
    """纯函数：加权合并 prev 与 new 的掌握度，返回 (evolved, diff)。

    - prev 为空 → 首次: 原样返回 new, diff=None
    - 规则: 本轮重测节点 merged=0.4*prev_m + 0.6*new_m (多轮更相信近期);
            未重测旧节点原样结转; 阈值 0.8 分段 known/weak。
    - 时效(②): 本轮实测条目记 last_test_at；结转的 known 若超 STALE_AFTER_DAYS
      未验证 → 标 recheck_due (待重验), UI 层提示复习/重测。
    - diff: recovered(旧薄弱→已掌握) / newly_known(首见→已掌握) /
            regressed(旧掌握→薄弱) / newly_weak(首见→薄弱)
    """
    now = now or datetime.utcnow()
    now_iso = now.isoformat() + "Z"
    if prev is None:
        return dict(new), None
    new_master, new_kind = _entry_map(new)
    prev_master, prev_kind = _entry_map(prev)
    run_nodes = list(new_master.keys())  # 本轮实际测过的节点

    # 知识点名称映射 (node_id → name): 合并条目时结转名称,
    # 前端 Dashboard/盲区图按名称展示, 缺名会回退成 PY-xxx 编号 (混显问题根因)。
    def _names(profile):
        out = {}
        for section in ("known_topics", "weak_topics"):
            for it in profile.get(section) or []:
                if isinstance(it, dict) and it.get("node_id") and it.get("name"):
                    out.setdefault(it["node_id"], it["name"])
        return out

    prev_names = _names(prev)
    new_names = _names(new)

    merged: dict[str, dict] = {}
    for nid in run_nodes:
        m_new = new_master[nid]
        m_prev = prev_master.get(nid)
        # 近次优先平滑 (0.6 本次 / 0.4 历史)
        m = round(0.6 * m_new + 0.4 * (m_prev if m_prev is not None else m_new), 2)
        m = min(m, 1.0)
        # 跨类边界以"本次实测"为准: 本次高分(≥0.8)→视为已掌握(恢复可达),
        # 本次失手(<0.8)→视为未达(回落可达); 同类内再做数值平滑。
        if m_new >= _MASTERY_BOUND:
            m = max(m, _MASTERY_BOUND)
        else:
            m = min(m, _MASTERY_BOUND - 0.01)
        entry = {"node_id": nid, "mastery": m, "last_test_at": now_iso}
        topic_name = new_names.get(nid) or prev_names.get(nid)
        if topic_name:
            entry["name"] = topic_name
        kind = _classify(m)
        if kind == "weak":
            patterns = set()
            for src in (prev.get("weak_topics"), new.get("weak_topics")):
                for it in src or []:
                    if isinstance(it, dict) and it.get("node_id") == nid:
                        patterns.update(it.get("error_patterns") or [])
            if patterns:
                entry["error_patterns"] = sorted(patterns)
        else:
            entry["last_test_score"] = round(m * 10, 1)
        merged[nid] = entry

    # 未重测旧节点结转
    for nid, it in prev_master.items():
        if nid not in merged:
            src = (prev.get("known_topics") or prev.get("weak_topics") or [])
            old = next((x for x in src if isinstance(x, dict) and x.get("node_id") == nid), {})
            merged[nid] = dict(old)
            # 时效降级(②): 未重测 known 超过 STALE_AFTER_DAYS → 标待重验
            last_at = merged[nid].get("last_test_at")
            if last_at:
                try:
                    dt = datetime.fromisoformat(last_at.replace("Z", "+00:00"))
                    dt = dt.replace(tzinfo=None)
                    if (now - dt).days > STALE_AFTER_DAYS and _classify(merged[nid]["mastery"]) == "known":
                        merged[nid]["recheck_due"] = True
                except (ValueError, TypeError):
                    pass

    evolved_known = [merged[n] for n in merged if _classify(merged[n]["mastery"]) == "known"]
    evolved_weak = [merged[n] for n in merged if _classify(merged[n]["mastery"]) == "weak"]

    prev_known = {n for n, k in prev_kind.items() if k == "known"}
    prev_weak = {n for n, k in prev_kind.items() if k == "weak"}
    ev_known = {e["node_id"] for e in evolved_known}
    ev_weak = {e["node_id"] for e in evolved_weak}

    recovered = {n for n in prev_weak if n in ev_known}
    regressed = {n for n in prev_known if n in ev_weak}
    newly_known = {n for n in ev_known if n not in prev_known and n not in prev_weak}
    newly_weak = {n for n in ev_weak if n not in prev_known and n not in prev_weak}
    diff = {
        "recovered": sorted(recovered, key=lambda x: merged[x]["mastery"], reverse=True),
        "newly_known": sorted(newly_known),
        "newly_weak": sorted(newly_weak),
        "regressed": sorted(regressed),
        "summary": {
            "recovered": len(recovered),
            "newly_known": len(newly_known),
            "newly_weak": len(newly_weak),
            "regressed": len(regressed),
        },
    }

    evolved = dict(new)
    evolved["profile_id"] = prev.get("profile_id", new.get("profile_id"))
    evolved["known_topics"] = evolved_known
    evolved["weak_topics"] = evolved_weak
    evolved["learning_history"] = prev.get("learning_history", []) + [{
        "ts": datetime.utcnow().isoformat() + "Z",
        "theory_level": new.get("theory_level"),
        "known": len(evolved_known),
        "weak": len(evolved_weak),
        "diff": diff["summary"],
        "target_direction": new.get("target_direction"),
    }]
    return evolved, diff


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


def save_profile(key: str, profile: dict) -> str:
    sid = safe_key(key)
    d = _archive_dir() / sid
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"profile_id": profile.get("profile_id"),
                            "ts": datetime.utcnow().isoformat() + "Z",
                            "theory_level": profile.get("theory_level")}, ensure_ascii=False) + "\n")
    _atomic_write(d / "latest.json", profile)
    return sid


def load_profile(key: str) -> Optional[dict]:
    try:
        sid = safe_key(key)
    except ValueError:
        return None
    p = _archive_dir() / sid / "latest.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("profile_store: 读取 %s 失败 err=%s", p, e)
        return None
