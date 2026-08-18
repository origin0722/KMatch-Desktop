"""动态建域 Agent (Domain Bootstrap)

学习目标不命中既有知识域 (6 内置域 PY/DA/DB/EN/WD/ML + 已建动态域) 时的兜底链路:
Tavily 联网检索 → LLM 生成迷你知识域 (~10 节点 + 前置依赖 + 每节点 2 题)
→ 代码级校验 → 走 KB CRUD 同通道落库 (JSON 真相源 _manual_nodes.json
+ Neo4j 同步 + 批量 embedding)。落库后全链路 (测评/学习路径/内容生成/
审核/图谱可视化) 对动态节点自动复用。

节点标记: category="动态领域" + source="llm_generated" + domain_label=<领域名>
(schema 已扩字段)。质量口径: 动态域事实基准来自 LLM (Tavily 检索缓解),
不纳入 M5 质检指标 (见 docs/质量与验收/质量检测报告.md 固定画像口径)。

对齐 data/prompts/08_domain_bootstrap_agent.txt。
"""

import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import get_default_chat_model, llm_configured
from app.config import settings
from app.data import kb_store
from app.utils.json_utils import parse_llm_json
from app.utils.logging import get_logger
from app.utils.web_search import search_web

logger = get_logger(__name__)

# 内置 6 域注册表 (对齐 schema.json id 描述 + 知识库前缀)
BUILTIN_DOMAINS = {
    "PY": "Python 编程",
    "DA": "数据分析与可视化",
    "DB": "数据库与缓存",
    "EN": "工程化实践",
    "WD": "Web 后端开发",
    "ML": "机器学习",
}
DYNAMIC_CATEGORY = "动态领域"
DYNAMIC_NODES = 10              # 每个动态域的节点数
QUESTIONS_PER_NODE = 2          # 每节点 choice/fill 题数
_QUESTION_BATCH_NODES = 4       # 每次出题 LLM 调用携带的节点数
_LLM_CONCURRENCY = 5            # 出题并发 (对齐 content_generator CONTENT_GEN_CONCURRENCY)
_MAX_ATTEMPTS = 2               # 生成→校验整轮重试上限
_HIT_MIN_NODES = 3              # 命中域的候选节点下限, 不足回退全域节点
_SEMANTIC_HIT_THRESHOLD = 0.55  # 向量启发式命中阈值 (LLM 未配置时的次选判据)


def _kb_base() -> Path:
    """知识库根目录 (对齐 api/kb.py 的 KB_BASE; 函数化便于测试 monkeypatch)。"""
    return Path(settings.DATA_DIR) / "knowledge_base"


# ============================================================
# 域注册表 & 命中判定
# ============================================================

def _iter_nodes_from_json(base: Path):
    """遍历 JSON 真相源中的全部节点 dict (排除 questions/ 与 schema.json)。"""
    for path in base.glob("**/*.json"):
        if path.name == "schema.json":
            continue
        if (base / "questions") in path.parents:
            continue
        try:
            data = path.read_text(encoding="utf-8")
            import json as _json
            parsed = _json.loads(data)
        except Exception:
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if isinstance(item, dict) and item.get("id"):
                yield item


def _dynamic_domains(base: Path) -> dict[str, str]:
    """扫描 JSON 真相源, 收集已建动态域 {前缀: 领域名} (供二次学习复用)。"""
    domains: dict[str, str] = {}
    for node in _iter_nodes_from_json(base):
        if node.get("source") != "llm_generated":
            continue
        nid = str(node.get("id", ""))
        if len(nid) >= 3 and nid[2] == "-":
            prefix = nid[:2]
            domains.setdefault(prefix, node.get("domain_label") or prefix)
    return domains


def _dynamic_domain_samples(base: Path = None, limit: int = 4) -> dict[str, list[str]]:
    """动态域节点名样例 {前缀: [节点名]} — 供域分类器对照重合度。

    宽泛伞形域名 (如「人工智能」) 会吸收其子领域目标 ("agent 开发" 被误判命中),
    注册表标签不足以判断, 附节点名样例让 LLM 看到域的实际内容再做判定。
    """
    base = base or _kb_base()
    samples: dict[str, list[str]] = {}
    for node in _iter_nodes_from_json(base):
        if node.get("source") != "llm_generated":
            continue
        nid = str(node.get("id", ""))
        if len(nid) >= 3 and nid[2] == "-" and node.get("name"):
            prefix = nid[:2]
            if len(samples.setdefault(prefix, [])) < limit:
                samples[prefix].append(str(node["name"]))
    return samples


def domain_registry(base: Path = None) -> dict[str, str]:
    """完整域注册表: 内置 6 域 + 已建动态域。"""
    base = base or _kb_base()
    registry = dict(BUILTIN_DOMAINS)
    registry.update(_dynamic_domains(base))
    return registry


def _classify_domain(target_direction: str, registry: dict[str, str]) -> tuple[str, str | None]:
    """LLM 单次调用把学习目标分类到域注册表。

    返回 (verdict, prefix): ("new", None)=全新领域 / ("known", 前缀) / ("invalid", None)。
    跨语言目标 (如 Java vs Python) 的向量相似度天然偏高, LLM 判域比纯向量可靠;
    且建域本身依赖 LLM, 主判据与兜底能力保持一致。
    """
    model = get_default_chat_model()
    samples = _dynamic_domain_samples()
    lines = []
    for pfx, label in sorted(registry.items()):
        if pfx in samples:
            lines.append(f"- {pfx}: {label} (已含节点: {'、'.join(samples[pfx])})")
        else:
            lines.append(f"- {pfx}: {label}")
    system = SystemMessage(content=(
        "你是学习领域分类器。判断学习目标属于哪个既有知识领域, 或是未收录的全新领域。\n"
        "既有领域注册表:\n" + "\n".join(lines) + "\n"
        "判据是「学习内容与该域知识点的重合度」, 不是「是否相关」:\n"
        "- 目标与某领域只是相关但核心是另一门技术时选 new (如「学 Java」不是 Python)。\n"
        "- 目标是某域的子领域/专项技术时同样选 new —— 学该专项不等于学该域通识课程\n"
        "  (如「agent 开发」之于「人工智能」通识、「爬虫」之于「Web 后端开发」);\n"
        "  动态域已附节点名样例, 与样例内容重合度低就选 new。\n"
        '严格输出 JSON: {"domain": "<注册表前缀>" 或 "new"}。'
        "不要输出 JSON 以外文字。"
    ))
    user = HumanMessage(content=f"学习目标: {target_direction}")
    try:
        resp = model.invoke([system, user])
    except Exception:
        logger.warning("域分类 LLM 调用失败", exc_info=True)
        return "invalid", None
    data = parse_llm_json(resp.content)
    if not isinstance(data, dict):
        return "invalid", None
    domain = data.get("domain")
    if domain == "new":
        return "new", None
    if isinstance(domain, str) and domain in registry:
        return "known", domain
    return "invalid", None


def _domain_candidate_nodes(kg, prefix: str, target_direction: str, known_ids: set) -> list[dict]:
    """取命中域的出题候选节点: 语义检索优先 (方向相关), 不足回退难度入口, 排除已会。"""
    nodes: list[dict] = []
    try:
        nodes = [n for n in kg.semantic_search(target_direction, top_k=12)
                 if str(n.get("node_id", "")).startswith(f"{prefix}-")]
    except Exception:
        logger.warning("域候选语义检索失败, 回退难度入口", exc_info=True)
    if len(nodes) < _HIT_MIN_NODES:
        fallback = [n for n in kg.get_by_difficulty(1, 3)
                    if str(n.get("node_id", "")).startswith(f"{prefix}-")]
        nodes = fallback[:8] or nodes
    # 剔除用户已会节点; 剔尽才放宽 (有剩余即优先个性化, 题量缺口由 LLM 补题兜底)
    fresh = [n for n in nodes if n.get("node_id") not in known_ids]
    return fresh or nodes[:8]


def resolve_direction(kg, target_direction: str, known_topics: list) -> tuple[str, list[dict]]:
    """把学习目标解析到既有域或判定为新领域。

    返回 (resolution, nodes):
      hit     — 命中既有域 (内置 6 域或已建动态域), nodes 为该域候选节点
      miss    — 未命中任何域, 需动态建域
      unknown — LLM 与向量都不可用无法判定, 调用方回退旧选点行为
    """
    if not target_direction or not str(target_direction).strip():
        return "unknown", []
    registry = domain_registry()
    known_ids = {t.get("node_id") for t in (known_topics or [])
                 if isinstance(t, dict) and t.get("node_id")}

    if llm_configured():
        verdict, prefix = _classify_direction_safe(target_direction, registry)
        if verdict == "new":
            return "miss", []
        if verdict == "known":
            # 语义复核 (伞形域兜底): LLM 可能被宽泛域名误导 ("agent 开发"→「人工智能」),
            # 若目标的语义检索结果中该域节点零出现 → 判定与目标零交集, 降级动态建域。
            # 语义结果为空 (未建索引/检索异常) 时无法复核, 维持 LLM 判定。
            if kg.embedding_client is not None:
                try:
                    sem = kg.semantic_search(target_direction, top_k=12)
                except Exception:
                    sem = None
                    logger.warning("域判定语义复核检索失败, 维持 LLM 判定", exc_info=True)
                if sem and not any(
                    str(n.get("node_id", "")).startswith(f"{prefix}-") for n in sem
                ):
                    logger.info(
                        "域判定复核: 目标「%s」与命中域 %s 语义零交集, 降级动态建域",
                        target_direction, prefix)
                    return "miss", []
            return "hit", _domain_candidate_nodes(kg, prefix, target_direction, known_ids)
        # invalid → 交给向量启发式兜底

    # 向量启发 (LLM 未配置/分类失败时的次选): 检索正常且最高分过阈值视为命中
    if kg.embedding_client is not None:
        nodes = kg.semantic_search(target_direction, top_k=12)
        if nodes and nodes[0].get("_similarity", 0) >= _SEMANTIC_HIT_THRESHOLD:
            fresh = [n for n in nodes if n.get("node_id") not in known_ids]
            return "hit", (fresh or nodes)
        if nodes:
            return "miss", []
    return "unknown", []


def _classify_direction_safe(target_direction: str, registry: dict[str, str]) -> tuple[str, str | None]:
    """_classify_domain 的薄封装: llm_configured 由调用方保证, 此处只隔离解析失败。"""
    try:
        return _classify_domain(target_direction, registry)
    except Exception:
        logger.warning("域分类异常, 回退向量启发式", exc_info=True)
        return "invalid", None


# ============================================================
# 动态建域: 生成 → 校验 → 落库
# ============================================================

def _search_context(direction: str, tavily_key: str | None) -> str:
    """Tavily 检索领域学习资料, 拼装为 LLM 事实锚。无 key/失败返回空串 (纯 LLM 回退)。"""
    key = tavily_key or settings.TAVILY_API_KEY
    if not key:
        return ""
    results = search_web(f"{direction} 学习路线 核心概念 入门", key, max_results=5)
    return "\n\n".join(
        f"[{r.get('title', '')}] {r.get('snippet', '')}" for r in results if r
    )


def _alloc_prefix(proposed, domain_name: str, taken: set[str]) -> str:
    """分配 2 字母节点前缀: LLM 提案优先, 冲突/非法时从领域名推导, 再不行按字母表扫描。"""
    if isinstance(proposed, str) and re.match(r"^[A-Z]{2}$", proposed) and proposed not in taken:
        return proposed
    # 从领域名取首字母启发 (Java→JA), 中文名取拼音首字母不可靠, 直接进字母表扫描
    ascii_letters = [c for c in (domain_name or "").upper() if "A" <= c <= "Z"]
    if len(ascii_letters) >= 2:
        candidate = ascii_letters[0] + ascii_letters[1]
        if candidate not in taken:
            return candidate
    for a in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for b in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            candidate = f"{a}{b}"
            if candidate not in taken:
                return candidate
    raise ValueError("无可用前缀 (不可能到达, 防御)")  # 26*26=676 > 任何现实前缀数


def _generate_domain_spec(direction: str, tavily_context: str) -> dict | None:
    """LLM 生成域蓝图 (节点名/难度/摘要/要点/前置名)。解析失败返回 None。"""
    model = get_default_chat_model()
    grounding = tavily_context.strip() or "(无检索资料, 基于该领域公认常识生成)"
    system = SystemMessage(content=(
        f"你是 KMatch 动态建域 Agent。为学习领域「{direction}」生成迷你知识图谱蓝图。\n"
        "只依据联网检索资料和该领域公认常识, 严禁编造版本号/性能数字/历史沿革等易幻细节。\n"
        f"严格输出 JSON: {{\"domain_name\": \"领域名(短)\", \"prefix\": \"两个大写字母缩写(如 Java→JV)\", "
        "\"nodes\": [{\"name\": \"知识点名\", \"difficulty\": 1-3 的整数, "
        "\"summary\": \"30-500 字概要(2-5 句, 不足 30 字会被校验拒绝)\", "
        "\"key_points\": [\"3-8 条核心要点, 每条一句话\"], "
        "\"common_mistakes\": [\"1-6 条常见误区\"], "
        "\"tags\": [\"1-6 个标签\"], "
        "\"estimated_minutes\": 20-90 的整数, "
        "\"prerequisite_names\": [\"仅可引用本次生成的其他节点 name, 且只能引用排列更早的节点\"]}]}}\n"
        f"nodes 恰好 {DYNAMIC_NODES} 个, 按学习顺序由浅入深排列, 形成无环前置链。"
        "不要输出 JSON 以外文字。"
    ))
    user = HumanMessage(content=(
        f"学习领域: {direction}\n\n联网检索资料:\n{grounding}\n\n请生成蓝图。"
    ))
    try:
        resp = model.invoke([system, user])
    except Exception:
        logger.warning("域蓝图生成 LLM 调用失败", exc_info=True)
        return None
    spec = parse_llm_json(resp.content)
    return spec if isinstance(spec, dict) else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _materialize_nodes(spec: dict, direction: str) -> tuple[list[dict], list[str]]:
    """把域蓝图落成节点 dict: 分配 id/前缀、映射前置名→id (仅保留更早节点, 天然无环)。"""
    base = _kb_base()
    raw_nodes = spec.get("nodes")
    if not isinstance(raw_nodes, list) or len(raw_nodes) < 4:
        return [], ["蓝图 nodes 数量不足"]
    domain_name = str(spec.get("domain_name") or direction)[:40]

    taken = set(BUILTIN_DOMAINS) | {nid[:2] for nid in kb_store.list_all_node_ids(base) if len(nid) >= 3}
    prefix = _alloc_prefix(spec.get("prefix"), domain_name, taken)

    name2id: dict[str, str] = {}
    nodes: list[dict] = []
    # 序号进程内递增: next_node_id 扫描的是磁盘 JSON, 节点落盘前重复调用会返回同一序号
    counter = 0
    kb_store_next = kb_store.next_node_id(base, prefix)  # 起点 (现有最大序号 +1)
    start_num = int(kb_store_next.split("-")[1])
    for i, raw in enumerate(raw_nodes[:DYNAMIC_NODES]):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or f"{domain_name}·知识点{i + 1}")[:60]
        if name in name2id:  # 重名节点丢弃, 防前置映射歧义
            continue
        counter += 1
        nid = f"{prefix}-{start_num + counter - 1:03d}"
        name2id[name] = nid
        nodes.append({
            "id": nid,
            "name": name,
            "difficulty": raw.get("difficulty") if isinstance(raw.get("difficulty"), int) and 1 <= raw.get("difficulty") <= 3 else max(1, min(3, i + 1)),
            "category": DYNAMIC_CATEGORY,
            "summary": str(raw.get("summary") or ""),
            "prerequisites": [],  # 第二遍填 (需全部 id 就位)
            "key_points": [str(k) for k in (raw.get("key_points") or []) if str(k).strip()],
            "practice_questions": [],  # 题目生成后注入 (schema 必填 ≥1)
            "common_mistakes": [str(m) for m in (raw.get("common_mistakes") or []) if str(m).strip()],
            "tags": [str(t) for t in (raw.get("tags") or []) if str(t).strip()] or [domain_name],
            "estimated_minutes": raw.get("estimated_minutes") if isinstance(raw.get("estimated_minutes"), int) and 5 <= raw.get("estimated_minutes") <= 240 else 40,
            "source": "llm_generated",
            "domain_label": domain_name,
            "created_at": _now_iso(),
            # 题目生成阶段读取的原料 (落库前删除)
            "_prereq_names": [str(p) for p in (raw.get("prerequisite_names") or []) if str(p).strip()],
        })

    # 前置映射: 仅保留对更早节点的引用 (LLM 违规引用靠后/未知名称 → 丢弃记日志)
    for idx, node in enumerate(nodes):
        earlier = {n["name"]: n["id"] for n in nodes[:idx]}
        for pname in node.pop("_prereq_names"):
            pid = earlier.get(pname)
            if pid:
                node["prerequisites"].append(pid)
            else:
                logger.info("动态域前置引用被丢弃 (非更早节点/未知名): %s → %s", node["name"], pname)
    if len(nodes) < 4:
        return [], [f"有效节点不足 ({len(nodes)}<4)"]
    return nodes, []


def _question_prompt(direction: str, tavily_context: str, batch: list[dict]) -> list:
    """构造批量出题 prompt: 每节点恰好 QUESTIONS_PER_NODE 道 choice/fill。"""
    facts = "\n".join(
        f"- 节点 {n['id']}《{n['name']}》(难度{n['difficulty']}): "
        f"{'；'.join(n['key_points'][:4])}"
        for n in batch
    )
    system = SystemMessage(content=(
        f"你是 KMatch 出题 Agent。基于知识节点事实为「{direction}」测评出题。\n"
        "只依据节点要点与误区出题, 不引入节点以外的事实。严格输出 JSON 数组, 每元素: "
        '{"node_id": "节点id", "type": "choice|fill", "question": "题干", '
        '"options": ["A...","B...","C...","D..."](仅 choice, 4 项含干扰项), '
        '"answer": "答案(choice 给字母如 A, fill 给文本)", "difficulty": 1-3 的整数, '
        '"explanation": "一句话解析"}。'
        "不要输出 JSON 以外文字。"
    ))
    grounding = f"\n\n领域参考资料 (仅辅助理解, 出题不得引用其外的具体数字):\n{tavily_context}" if tavily_context.strip() else ""
    user = HumanMessage(content=(
        f"学习领域: {direction}\n\n节点事实:\n{facts}{grounding}\n\n"
        f"请为以上每个节点出恰好 {QUESTIONS_PER_NODE} 道题 (choice 与 fill 混合)。"
    ))
    return [system, user]


def _generate_questions(direction: str, tavily_context: str, nodes: list[dict]) -> dict[str, list[dict]]:
    """并发为全部节点生成 choice/fill 题。返回 {node_id: [question, ...]} (已过基础过滤)。"""
    batches = [nodes[i:i + _QUESTION_BATCH_NODES]
               for i in range(0, len(nodes), _QUESTION_BATCH_NODES)]
    valid_ids = {n["id"] for n in nodes}
    results: dict[str, list[dict]] = {n["id"]: [] for n in nodes}

    def _run(batch):
        model = get_default_chat_model()
        resp = model.invoke(_question_prompt(direction, tavily_context, batch))
        data = parse_llm_json(resp.content)
        if not isinstance(data, list):
            return []
        out = []
        for q in data:
            if not isinstance(q, dict) or q.get("node_id") not in valid_ids:
                continue
            if q.get("type") not in ("choice", "fill"):
                continue
            if not q.get("question") or not q.get("answer"):
                continue
            if q.get("type") == "choice" and not (isinstance(q.get("options"), list) and len(q["options"]) >= 2):
                continue
            out.append(q)
        return out

    with ThreadPoolExecutor(max_workers=_LLM_CONCURRENCY) as pool:
        for questions in pool.map(_run, batches):
            for q in questions:
                results[q["node_id"]].append(q)
    return results


def _finalize_nodes_and_questions(nodes: list[dict], qmap: dict[str, list[dict]]):
    """注入 practice_questions + 逐节点/逐题 schema 校验 + 组装独立 :Question。

    返回 (questions, errors)。errors 非空则整轮作废 (调用方重试)。
    """
    base = _kb_base()
    # 校验器与 kb.py 同源 (scripts/validate_data)
    scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from scripts.validate_data import load_schema, validate_node, validate_question

    schema = load_schema(base / "schema.json")
    all_ids = set(kb_store.list_all_node_ids(base)) | {n["id"] for n in nodes}

    questions: list[dict] = []
    for node in nodes:
        node_qs = qmap.get(node["id"], [])
        # practice_questions: 首题原样注入 (schema 必填 ≥1; 字段 type/question/options/answer/difficulty 兼容)
        if node_qs:
            first = dict(node_qs[0])
            first.setdefault("difficulty", node["difficulty"])
            node["practice_questions"] = [first]
        errors = validate_node(node, schema, all_ids)
        if errors:
            return [], [f"节点 {node['id']} 校验失败: {e}" for e in errors]
        for seq, q in enumerate(node_qs[:QUESTIONS_PER_NODE], start=1):
            # qid 由代码按 node_id 推导 (kb_store.next_question_id 未落盘前不递增, 不可用)
            m = re.match(r"^([A-Z]{2})-(\d{3})$", node["id"])
            qid = f"Q-{m.group(1)}{m.group(2)}-{seq:03d}"
            question = {
                "qid": qid,
                "source_node_id": node["id"],
                "type": q["type"],
                "question": q["question"],
                "options": q.get("options") if q["type"] == "choice" else [],
                "answer": str(q["answer"]),
                "difficulty": q["difficulty"] if isinstance(q.get("difficulty"), int) and 1 <= q.get("difficulty") <= 5 else node["difficulty"],
                "hint": q.get("hint") or "",
                "explanation": q.get("explanation") or "",
                "created_at": _now_iso(),
            }
            errors = validate_question(question, qid, known_node_ids=all_ids)
            if errors:
                return [], [f"题目 {qid} 校验失败: {e}" for e in errors]
            questions.append(question)
    if len(questions) < len(nodes):
        return [], ["有效题目数不足以覆盖全部节点 (每节点至少 1 题)"]
    return questions, []


def _persist(kg, nodes: list[dict], questions: list[dict]) -> list[str]:
    """落库: JSON 真相源全量先写, 再同步 Neo4j, 最后批量 embedding (与 kb.py 同策略)。"""
    base = _kb_base()
    warnings: list[str] = []
    for node in nodes:
        kb_store.save_node(base, node)
    for q in questions:
        kb_store.save_question(base, q)
    for node in nodes:
        try:
            kg.upsert_knowledge_node(node)
        except Exception as e:
            logger.warning("动态域节点同步 Neo4j 失败 %s", node["id"], exc_info=True)
            warnings.append(f"Neo4j 同步失败: {node['id']}: {e}")
    for q in questions:
        try:
            kg.upsert_question(q)
        except Exception as e:
            logger.warning("动态域题目同步 Neo4j 失败 %s", q["qid"], exc_info=True)
            warnings.append(f"Neo4j 同步失败: {q['qid']}: {e}")
    try:
        kg.generate_embeddings(nodes)  # 批量 ≤20 (engine 默认 batch), 未配置 client 时内部跳过
    except Exception as e:
        logger.warning("动态域 embedding 生成失败", exc_info=True)
        warnings.append(f"embedding 生成失败: {e} (非阻塞)")
    return warnings


def bootstrap_domain(kg, direction: str, tavily_key: str | None = None) -> list[dict]:
    """为未收录领域动态构建迷你知识域并落库。

    返回按学习顺序 (生成序, 由浅入深) 排列的节点列表: 同时携带 id (持久化形状)
    与 node_id (运行时形状) — submit 链路 _build_profile 直接取 n["node_id"],
    search_weak_topics 按 node_id 建映射, 缺键即 500/溯源失效 (CSS 会话实测 BUG)。
    两轮生成→校验重试后仍不合规抛 ValueError。
    """
    if not llm_configured():
        raise ValueError("LLM 未配置, 无法动态建域; 请在设置中配置 AI 后重试")
    tavily_context = _search_context(direction, tavily_key)
    if tavily_context:
        logger.info("动态建域「%s」: Tavily 检索到 %d 字参考资料", direction, len(tavily_context))
    else:
        logger.info("动态建域「%s」: 无 Tavily 资料, 纯 LLM 生成 (幻觉风险已知)", direction)

    last_errors: list[str] = []
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        spec = _generate_domain_spec(direction, tavily_context)
        if spec is None:
            last_errors = ["域蓝图解析失败"]
            continue
        nodes, errors = _materialize_nodes(spec, direction)
        if errors:
            last_errors = errors
            continue
        qmap = _generate_questions(direction, tavily_context, nodes)
        questions, errors = _finalize_nodes_and_questions(nodes, qmap)
        if errors:
            last_errors = errors
            continue
        warnings = _persist(kg, nodes, questions)
        for w in warnings:
            logger.warning("动态建域落库 warning: %s", w)
        logger.info("动态建域「%s」完成: %d 节点 / %d 题 (第 %d 轮)",
                    direction, len(nodes), len(questions), attempt)
        # 持久化已完成 (JSON 内保持 id 键), 返回时补 node_id 运行时形状
        return [{**n, "node_id": n["id"]} for n in nodes]
    raise ValueError(f"动态建域失败: LLM 产物 {attempt} 轮校验未通过: {last_errors[:5]}")
