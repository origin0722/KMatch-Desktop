"""学习流程定义 (Phase 2) — 借鉴 dsh_workflow 的 capsule 思路: 流程即数据。

把一次"协同执行"的拓扑、阶段、Agent 归属与输入契约描述为纯数据定义:

    {
      "format": "kmatch.workflow",
      "version": 1,
      "id": "scene1-loop",
      "name": "场景一·学情闭环",
      "description": "学情检测→画像审核→图谱组装→内容生成→内容审核→交付",
      "stages": [
        {"id": "diagnostics", "label": "学情检测", "agents": ["diagnostics"], "dependencies": []},
        {"id": "review-profile", "label": "画像审核", "agents": ["reviewer"], "dependencies": ["diagnostics"]},
        ...
      ],
      "inputs": {"schema": {...}, "required": ["target_direction"]}
    }

- 内置默认 (代码兜底, 永不被遮蔽); 可选 `data/workflows/*.json` 追加自定义流程
- validate(preflight): 必填字段/未知字段/阶段引用/依赖环/Agent 已知/输入契约
- 用途: run 记录 provenance; demo SSE 进度阶段化; Phase 3 流程画布的数据底座
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from app.agents import log_events
from app.utils.logging import get_logger

logger = get_logger(__name__)

WORKFLOW_FORMAT = "kmatch.workflow"
WORKFLOW_VERSION = 1
_WF_DIR_NAME = "workflows"

_KNOWN_AGENTS = set(log_events.AGENT_KEYS)
_STAGE_FIELDS = {"id", "label", "agents", "dependencies"}
_TOP_FIELDS = {"format", "version", "id", "name", "description", "stages", "inputs"}


# ============================================================
# 内置默认流程 (代码兜底; data/workflows/*.json 追加自定义)
# ============================================================
# 阶段顺序即执行序; 校验保证依赖 id 必须指向更早阶段 (无环)。
def _scene1_stages():
    return [
        {"id": "diagnostics", "label": "学情检测", "agents": ["diagnostics"], "dependencies": []},
        {"id": "review-profile", "label": "画像审核", "agents": ["reviewer"], "dependencies": ["diagnostics"]},
        {"id": "graph", "label": "图谱组装", "agents": ["graph_controller"], "dependencies": ["review-profile"]},
        {"id": "content", "label": "内容生成", "agents": ["content_generator"], "dependencies": ["graph"]},
        {"id": "review-content", "label": "内容审核", "agents": ["reviewer"], "dependencies": ["content"]},
    ]


def _interactive_stages():
    return [
        {"id": "diagnostics", "label": "学情检测", "agents": ["diagnostics"], "dependencies": []},
        {"id": "graph", "label": "图谱组装", "agents": ["graph_controller"], "dependencies": ["diagnostics"]},
    ]


BUILTIN_WORKFLOWS: dict[str, dict] = {
    "scene1-loop": {
        "format": WORKFLOW_FORMAT,
        "version": WORKFLOW_VERSION,
        "id": "scene1-loop",
        "name": "场景一·学情闭环",
        "description": "学情检测→画像审核→图谱组装→内容生成→内容审核→交付",
        "stages": _scene1_stages(),
        "inputs": {"required": ["target_direction"], "schema": {"target_direction": "string", "scene": "string"}},
    },
    "scene1-interactive": {
        "format": WORKFLOW_FORMAT,
        "version": WORKFLOW_VERSION,
        "id": "scene1-interactive",
        "name": "场景一·交互测评",
        "description": "interactive 出题→判分→专属路径组装",
        "stages": _interactive_stages(),
        "inputs": {"required": ["target_direction"], "schema": {"target_direction": "string"}},
    },
    "scene2-project": {
        "format": WORKFLOW_FORMAT,
        "version": WORKFLOW_VERSION,
        "id": "scene2-project",
        "name": "场景二·项目二次开发",
        "description": "代码解析→项目图谱→代码审查→代码测试 (挂载在场景一图谱之上)",
        "stages": [
            {"id": "parse", "label": "代码解析", "agents": ["diagnostics"], "dependencies": []},
            {"id": "project-graph", "label": "项目图谱", "agents": ["graph_controller"], "dependencies": ["parse"]},
            {"id": "code-review", "label": "代码审查", "agents": ["reviewer"], "dependencies": ["project-graph"]},
            {"id": "code-test", "label": "代码测试", "agents": ["reviewer"], "dependencies": ["code-review"]},
        ],
        "inputs": {"required": ["target_direction"], "schema": {"target_direction": "string", "scene": "string"}},
    },
}


def workflow_for(mode: str, scene: str = "no_project") -> str:
    """按模式/场景解析默认流程 id (Run 模态 → 流程资产)。"""
    if mode == "interactive":
        return "scene1-interactive"
    if scene == "with_project":
        return "scene2-project"
    return "scene1-loop"


# ============================================================
# 发现 (内置 + data/workflows/*.json 追加)
# ============================================================
def _wf_dir() -> Path:
    from app.config import settings
    return settings.DATA_DIR / _WF_DIR_NAME


def validate_definition(defn: Any) -> list:
    """校验一份流程定义, 返回错误列表 (空 = 合法)。未知字段/未知 Agent/依赖环均拒绝。"""
    errors: list = []
    if not isinstance(defn, dict):
        return ["flow 定义必须是对象"]
    for field in defn:
        if field not in _TOP_FIELDS:
            errors.append(f"未知顶级字段: {field}")
    if defn.get("format") != WORKFLOW_FORMAT:
        errors.append(f"format 必须为 {WORKFLOW_FORMAT}")
    if defn.get("version") != WORKFLOW_VERSION:
        errors.append(f"version 必须为 {WORKFLOW_VERSION}")
    wf_id = defn.get("id")
    if not wf_id or not isinstance(wf_id, str):
        errors.append("缺 id (字符串)")
    if not defn.get("name"):
        errors.append("缺 name")
    stages = defn.get("stages")
    if not isinstance(stages, list) or not stages:
        errors.append("stages 必须为非空数组")
        return errors
    seen: dict[str, int] = {}
    for idx, stage in enumerate(stages):
        if not isinstance(stage, dict):
            errors.append(f"stage[{idx}] 不是对象")
            continue
        for f in stage:
            if f not in _STAGE_FIELDS:
                errors.append(f"stage[{idx}] 未知字段: {f}")
        sid = stage.get("id")
        if not sid or not isinstance(sid, str):
            errors.append(f"stage[{idx}] 缺 id")
            continue
        if sid in seen:
            errors.append(f"stage id 重复: {sid}")
        seen[sid] = idx
        agents = stage.get("agents", [])
        if not isinstance(agents, list) or not agents:
            errors.append(f"stage[{sid}] agents 必须为非空列表")
        for a in agents:
            if a not in _KNOWN_AGENTS:
                errors.append(f"stage[{sid}] 未知 Agent: {a}")
        deps = stage.get("dependencies", [])
        if not isinstance(deps, list):
            errors.append(f"stage[{sid}] dependencies 必须为列表")
            continue
        for d in deps:
            if d == sid:
                errors.append(f"stage[{sid}] 不能依赖自身")
            elif d not in seen:  # 依赖必须指向更早阶段 (顺序即拓扑, 天然无环)
                errors.append(f"stage[{sid}] 依赖未知/乱序: {d}")
    return errors


def list_workflows() -> list:
    """内置 + data/workflows 自定义 (校验失败跳过并告警, 不致命)。"""
    out = [dict(w) for w in BUILTIN_WORKFLOWS.values()]
    d = _wf_dir()
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.json")):
        try:
            defn = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("workflow_def: 无法解析 %s err=%s", p, e)
            continue
        errs = validate_definition(defn)
        if errs:
            logger.warning("workflow_def: %s 校验失败: %s", p, errs)
            continue
        wid = defn.get("id")
        if wid in BUILTIN_WORKFLOWS:
            continue  # 内置不可被遮蔽
        out.append(defn)
    return out


def get_workflow(workflow_id: str) -> Optional[dict]:
    """按 id 取流程定义 (内置优先, 再查 data/workflows 文件)。"""
    if workflow_id in BUILTIN_WORKFLOWS:
        return dict(BUILTIN_WORKFLOWS[workflow_id])
    d = _wf_dir()
    if d.is_dir():
        p = d / f"{workflow_id}.json"
        if p.is_file():
            try:
                defn = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("workflow_def: 读取 %s 失败 err=%s", p, e)
                return None
            if validate_definition(defn):
                logger.warning("workflow_def: %s 校验失败", p)
                return None
            return defn
    return None


# ============================================================
# Preflight (运行前校验: 定义合法 + 请求契约满足)
# ============================================================
def preflight(workflow_id: str, *, target_direction: str, scene: str = "no_project",
              max_retries: int = 3) -> tuple[bool, list]:
    """对一次拟运行的请求做运行前校验, 返回 (ok, errors)。坏定义/坏请求在启动前被拒。"""
    errors: list = []
    wf = get_workflow(workflow_id)
    if wf is None:
        return False, [f"流程定义不存在: {workflow_id}"]
    errs = validate_definition(wf)
    if errs:
        errors += [f"流程定义不合法 ({workflow_id}): {e}" for e in errs]
    if not target_direction or not str(target_direction).strip():
        errors.append("输入契约: 缺少 target_direction")
    req = wf.get("inputs", {}).get("required", [])
    if "target_direction" in req and not target_direction:
        errors.append("输入契约: 必须提供 target_direction")
    if not (1 <= int(max_retries) <= 5):
        errors.append("max_retries 必须在 1..5")
    if scene not in ("no_project", "with_project"):
        errors.append(f"未知 scene: {scene}")
    return (not errors), errors
