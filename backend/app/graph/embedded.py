"""
嵌入式知识图谱存储后端 (EmbeddedGraphStore)

端用户免 Docker 的核心 (方案: docs/架构与设计/轻量化改造方案_免Docker_嵌入式存储.md):
以 data/knowledge_base JSON 为真相源 (与 kb_store 共享, "JSON 为源, Neo4j 为派生缓存"),
进程内载入节点/题目/邻接表索引, 查询零网络往返; 可变数据 (掌握状态/项目图谱/风险标注/向量)
落 data/local/, 原子写 (临时文件 + os.replace) + per-file 锁。

方法签名与 Neo4j 后端 KnowledgeGraph 完全一致, 返回形状逐字段镜像:
- node: id→node_id 归一, prerequisites 以边不注入返回, practice_questions 以 JSON 字符串返回
- question: options list 兜底, node_id=source_node_id 注入
- property: embedding_client (供 domain_bootstrap 守卫), semantic_ready (三态语义可用性)

模式开关: GRAPH_STORE=neo4j|embedded|auto (config)。打包态由 run_server.py 强制 embedded。
"""

from __future__ import annotations

import json
import os
import re
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import settings
from app.data import kb_store
from app.graph.engine import _WEAK_PATCH_LIMIT  # 单源: 与 Neo4j 后端共享弱项补丁上限
from app.utils.logging import get_logger

logger = get_logger(__name__)

# 掌握状态合法值 (与 engine.update_node_status 对齐)
_VALID_STATUSES = {"mastered", "in_progress", "unlearned", "difficult"}

# 自动回填 embedding 的批量大小 (与 engine.generate_embeddings 一致)
_EMBED_BATCH = 20

# project_id 白名单 (防路径穿越: 只允许 [A-Za-z0-9_-], 长度≤64; API 输入自由字符串)
_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write(path: Path, text: str) -> None:
    """临时文件 + os.replace 原子写: 写入中断不产生半残文件, 旧文件保留 (B3 事务语义)。"""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp = parent / f".{path.name}.tmp"
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class EmbeddedGraphStore:
    """嵌入式知识图谱存储：进程内 JSON 加载 + 本地可变数据落盘。"""

    kind = "embedded"

    # ------------------------------------------------------------
    # 构造 & 生命周期
    # ------------------------------------------------------------

    def __init__(
        self,
        kb_dir: Optional[Path] = None,
        local_dir: Optional[Path] = None,
        embedding_model: str = None,
        embedding_client=None,
    ):
        self.kb_dir = Path(kb_dir) if kb_dir else settings.KB_DIR
        self.local_dir = Path(local_dir) if local_dir else settings.LOCAL_DIR
        self.embedding_model = embedding_model or settings.EMBEDDING_MODEL
        self.embedding_client = embedding_client  # 属性语义与 Neo4j 后端一致 (可为 None)

        # --- 内存索引 (惰性载入) ---
        self._nodes: dict[str, dict] = {}                 # id -> raw JSON node
        self._parents: dict[str, list[str]] = {}          # node_id -> prerequisites ids
        self._children: dict[str, set] = defaultdict(set)  # parent_id -> {child ids}
        self._by_category: dict[str, list[str]] = defaultdict(list)   # cat -> node ids (按难度排序)
        self._by_difficulty: dict[int, list[str]] = defaultdict(list)
        self._by_tag: dict[str, set] = defaultdict(set)   # tag -> {node ids}
        self._questions_by_node: dict[str, list[dict]] = defaultdict(list)
        self._qid_index: dict[str, dict] = {}

        # --- 向量 (semantic_ready 三态) ---
        self._embeddings: dict[str, list] = {}            # node_id -> vector
        self._semantic_ready = False

        # --- 并发/生命周期 ---
        self._load_lock = threading.Lock()
        self._vector_lock = threading.Lock()  # embeddings 读改写互斥 (自动回填 vs 单节点回填并发)
        self._loaded = False
        self._file_locks: dict[Path, threading.Lock] = defaultdict(threading.Lock)
        self._backfill_thread: Optional[threading.Thread] = None

    def reconfigure_embedding(self, api_key: str, base_url: str = "", model: str = "") -> bool:
        """运行时重建 embedding 客户端 (设置页保存后调用; 影响后续向量回填)。

        与 Neo4j 引擎同契约: 探活成功返回 True, 失败/未配置置 None 返回 False。
        """
        from openai import OpenAI
        if not api_key or api_key == "sk-placeholder":
            self.embedding_client = None
            return False
        client = OpenAI(api_key=api_key, base_url=base_url or settings.LLM_BASE_URL)
        try:
            client.embeddings.create(model=model or self.embedding_model, input=["test"])
        except Exception:
            logger.warning("嵌入式 embedding 重配置探活失败", exc_info=True)
            self.embedding_client = None
            return False
        self.embedding_client = client
        if model:
            self.embedding_model = model
        return True

    # ------------------------------------------------------------
    # 载入
    # ------------------------------------------------------------

    def _lock_for(self, path: Path) -> threading.Lock:
        return self._file_locks[path]

    def _node_out(self, node: dict) -> dict:
        """镜像 Neo4j 导入后节点属性形状: prerequisites 为边不注入, practice_questions 落 JSON 字符串。"""
        out = {
            "node_id": node["id"],
            "name": node.get("name", ""),
            "difficulty": node.get("difficulty", 1),
            "category": node.get("category", ""),
            "summary": node.get("summary", ""),
            "key_points": node.get("key_points", []),
            "practice_questions": json.dumps(
                node.get("practice_questions", []), ensure_ascii=False,
            ),
            "common_mistakes": node.get("common_mistakes", []),
            "tags": node.get("tags", []),
            "estimated_minutes": node.get("estimated_minutes", 10),
        }
        if "created_at" in node:
            out["created_at"] = node["created_at"]
        return out

    def _question_out(self, q: dict) -> dict:
        """镜像 engine._question_from_record: options list 兜底 + node_id=source_node_id 注入。"""
        q = dict(q)
        opts = q.get("options")
        if opts is None:
            q["options"] = []
        elif isinstance(opts, str):
            try:
                parsed = json.loads(opts)
                q["options"] = parsed if isinstance(parsed, list) else []
            except (ValueError, TypeError):
                q["options"] = []
        q["node_id"] = q.get("source_node_id", "")
        return q

    def _reload_all(self) -> None:
        """从 kb_dir JSON 全量重建内存索引 (启动/失效重建)。"""
        self._nodes = {}
        self._parents = {}
        self._children = defaultdict(set)
        self._by_category = defaultdict(list)
        self._by_difficulty = defaultdict(list)
        self._by_tag = defaultdict(set)
        self._questions_by_node = defaultdict(list)
        self._qid_index = {}

        # --- 节点 ---
        seen: dict[str, str] = {}
        for fpath in kb_store._iter_node_files(self.kb_dir):  # noqa: SLF001 (同包内部复用)
            try:
                nodes = kb_store._load_json_list(fpath)  # noqa: SLF001
            except Exception:
                logger.warning("节点文件解析失败, 跳过: %s", fpath, exc_info=True)
                continue
            for n in nodes:
                if not isinstance(n, dict) or not n.get("id"):
                    continue
                nid = n["id"]
                # 同 id 多文件: 后写覆盖前写 (贴近 MERGE upsert 语义); 记录去重提示
                mark = seen.get(nid)
                if mark is not None and mark != str(fpath):
                    logger.info("节点 %s 重复定义(先 %s, 现 %s), 以后者为准", nid, mark, fpath)
                seen[nid] = str(fpath)
                self._nodes[nid] = n

        # --- 邻接 + 索引 ---
        for nid, node in self._nodes.items():
            prereqs = [p for p in (node.get("prerequisites") or []) if p in self._nodes]
            # 只保留已存在的目标 (缺失前置视作边不存在, 避免悬挂)
            self._parents[nid] = prereqs
            for p in prereqs:
                self._children[p].add(nid)
            cat = node.get("category", "")
            if cat:
                self._by_category[cat].append(nid)
            diff = int(node.get("difficulty", 1))
            self._by_difficulty[diff].append(nid)
            for tag in node.get("tags", []) or []:
                self._by_tag[tag].add(nid)

        # category/difficulty 列表按难度排序 (对齐 Cypher ORDER BY n.difficulty)
        for ids in self._by_category.values():
            ids.sort(key=lambda i: int(self._nodes[i].get("difficulty", 1)))
        for ids in self._by_difficulty.values():
            ids.sort(key=lambda i: int(self._nodes[i].get("difficulty", 1)))

        # --- 题目 ---
        qdir = self.kb_dir / "questions"
        if qdir.is_dir():
            # 递归: 真实题库含嵌套子目录 (DA/DB/WD/... 每域一夹), 只扫顶层会漏 → 题库为空 (BUG 回归)
            for fpath in sorted(qdir.glob("**/*.json")):
                if fpath.name == "schema.json":
                    continue
                try:
                    qs = kb_store._load_json_list(fpath)  # noqa: SLF001
                except Exception:
                    logger.warning("题目文件解析失败, 跳过: %s", fpath, exc_info=True)
                    continue
                for q in qs:
                    if not isinstance(q, dict) or not q.get("qid"):
                        continue
                    self._qid_index[q["qid"]] = q
                    src = q.get("source_node_id") or ""
                    if src:
                        self._questions_by_node[src].append(q)
        # 每节点题目按难度排序 (对齐 Cypher ORDER BY q.difficulty)
        for qs in self._questions_by_node.values():
            qs.sort(key=lambda q: int(q.get("difficulty", 1)))

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._load_lock:
            if self._loaded:
                return
            self._reload_all()
            self._loaded = True
            self._load_vectors_from_disk()
            self._maybe_start_backfill()

    def close(self) -> None:
        """嵌入式无外部连接, no-op (与 Neo4j 后端接口对齐)。"""
        self._loaded = False

    def test_connection(self) -> bool:
        """本地就绪: 恒 True (与 Neo4j 后端接口对齐)。"""
        self._ensure_loaded()
        return True

    # ------------------------------------------------------------
    # 基础图查询
    # ------------------------------------------------------------

    def get_node(self, node_id: str) -> Optional[dict]:
        self._ensure_loaded()
        node = self._nodes.get(node_id)
        return self._node_out(node) if node else None

    def get_by_category(self, category: str) -> list[dict]:
        self._ensure_loaded()
        return [self._node_out(self._nodes[i]) for i in self._by_category.get(category, [])]

    def get_by_difficulty(self, min_d: int, max_d: int) -> list[dict]:
        self._ensure_loaded()
        result = []
        for diff in range(min_d, max_d + 1):
            for i in self._by_difficulty.get(diff, []):
                result.append(self._node_out(self._nodes[i]))
        return result

    def get_by_tags(self, tags: list[str]) -> list[dict]:
        self._ensure_loaded()
        wanted = set(tags)
        matched = set()
        for t in wanted:
            matched |= self._by_tag.get(t, set())
        # 按难度升序 (对齐 Cypher ORDER BY n.difficulty)
        ordered = sorted(matched, key=lambda i: int(self._nodes[i].get("difficulty", 1)))
        return [self._node_out(self._nodes[i]) for i in ordered]

    # ------------------------------------------------------------
    # 图遍历
    # ------------------------------------------------------------

    def get_prerequisites(self, node_id: str) -> list[dict]:
        self._ensure_loaded()
        prereqs = self._parents.get(node_id, [])
        # 确定性排序 (Neo4j 无序; 这里按难度升序保证稳定)
        ordered = sorted(prereqs, key=lambda i: int(self._nodes[i].get("difficulty", 1)))
        return [self._node_out(self._nodes[i]) for i in ordered]

    def get_prerequisites_batch(self, node_ids: list[str]) -> dict[str, list[dict]]:
        """批量前置依赖 (v1.3.3: 与 engine.get_prerequisites_batch 同契约, 内存遍历零网络往返)。"""
        self._ensure_loaded()
        out: dict[str, list[dict]] = {}
        for nid in node_ids or []:
            if not nid:
                continue
            ordered = sorted(self._parents.get(nid, []),
                             key=lambda i: int(self._nodes[i].get("difficulty", 1)))
            out[nid] = [self._node_out(self._nodes[i]) for i in ordered]
        return out

    def get_dependents(self, node_id: str) -> list[dict]:
        self._ensure_loaded()
        deps = self._children.get(node_id, set())
        ordered = sorted(deps, key=lambda i: int(self._nodes[i].get("difficulty", 1)))
        return [self._node_out(self._nodes[i]) for i in ordered]

    def get_reachable(self, known_ids: list[str], max_depth: int = 3) -> list[dict]:
        """反向 BFS 等价 [:REQUIRES*1..max_depth]: 从已知节点向外扩散取后继, 去重按难度排序。

        REQUIRES 方向: (child)-[:REQUIRES]->(parent)。要找「接下来学什么」需反向:
        沿 parent→children 邻接扩散 (与 Neo4j 后端一致)。
        """
        self._ensure_loaded()
        if not known_ids:
            return []
        reached: dict[str, int] = {}
        frontier = list(known_ids)
        for depth in range(1, max_depth + 1):
            nxt: list[str] = []
            for nid in frontier:
                for child in self._children.get(nid, ()):
                    if child not in reached:
                        reached[child] = depth
                        nxt.append(child)
            frontier = nxt
            if not frontier:
                break
        ordered = sorted(reached, key=lambda i: int(self._nodes[i].get("difficulty", 1)))
        return [self._node_out(self._nodes[i]) for i in ordered]

    # ------------------------------------------------------------
    # 题目
    # ------------------------------------------------------------

    def get_questions(
        self,
        node_id: str,
        types: Optional[list[str]] = None,
        difficulty_min: Optional[int] = None,
        difficulty_max: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        self._ensure_loaded()
        result = []
        for q in self._questions_by_node.get(node_id, []):
            if types and q.get("type") not in types:
                continue
            if difficulty_min is not None and int(q.get("difficulty", 1)) < difficulty_min:
                continue
            if difficulty_max is not None and int(q.get("difficulty", 1)) > difficulty_max:
                continue
            result.append(self._question_out(q))
        # 已按难度排序 (载入时排)
        if limit is not None:
            result = result[: int(limit)]
        return result

    def get_questions_for_nodes(
        self,
        node_ids: list[str],
        types: Optional[list[str]] = None,
        max_per_node: int = 2,
    ) -> list[dict]:
        """每节点最多 max_per_node 道, 等价 Cypher collect+slice。"""
        self._ensure_loaded()
        if not node_ids:
            return []
        result = []
        for nid in node_ids:
            picked = self.get_questions(nid, types=types, limit=max_per_node)
            result.extend(picked)
        return result

    def get_question(self, qid: str) -> Optional[dict]:
        self._ensure_loaded()
        q = self._qid_index.get(qid)
        return self._question_out(q) if q else None

    def get_questions_by_node(self, node_id: str) -> list[dict]:
        self._ensure_loaded()
        return [self._question_out(q) for q in self._questions_by_node.get(node_id, [])]

    # ------------------------------------------------------------
    # 语义向量检索 (P4: 载入 + numpy 余弦 + 自动回填 + 降级)
    # ------------------------------------------------------------

    @property
    def semantic_ready(self) -> bool:
        """语义检索可用性三态: 向量矩阵就绪 且 有 embedding 客户端 才可回答查询。

        注: 每次查询仍需云端 embedding 编码 query (节点向量本地缓存省的是节点侧重复编码),
        故无客户端时即使有缓存向量也降级纯图 (诚实语义, 与 Neo4j 后端一致)。
        """
        self._ensure_loaded()
        return self._semantic_ready and self.embedding_client is not None

    def _load_vectors_from_disk(self) -> None:
        path = self.local_dir / "embeddings.json"
        if not path.is_file():
            return
        try:
            with self._lock_for(path):
                data = json.loads(path.read_text(encoding="utf-8"))
            items = data.get("items", {}) if isinstance(data, dict) else {}
            keep = {k: v for k, v in items.items() if k in self._nodes and isinstance(v, list)}
            self._embeddings = keep
            if keep:
                self._semantic_ready = True
                logger.info("✅ 嵌入式向量已载入 (%d 节点), 语义检索可用", len(keep))
        except Exception:
            logger.warning("embeddings.json 解析失败, 语义检索走纯图降级", exc_info=True)

    def _write_embeddings(self, items: dict) -> None:
        if not items:
            return
        with self._vector_lock:  # 读改写互斥, 防并发回填丢条目
            merged = dict(self._embeddings)
            merged.update(items)
            self._embeddings = merged
        path = self.local_dir / "embeddings.json"
        with self._lock_for(path):
            _atomic_write(
                path,
                json.dumps({"model": self.embedding_model, "items": merged}, ensure_ascii=False),
            )
        self._semantic_ready = True

    def _maybe_start_backfill(self) -> None:
        """无向量 且 配了 embedding API → 后台 daemon 自动回填 (不阻塞启动, 失败降级)。"""
        if self._semantic_ready or self.embedding_client is None:
            return
        if not self._nodes:
            return
        self._backfill_thread = threading.Thread(target=self._backfill_all, daemon=True)
        self._backfill_thread.start()
        logger.info("⏳ 无本地向量, 已启动后台自动回填 (%d 节点)...", len(self._nodes))

    def _backfill_all(self) -> None:
        try:
            items: dict[str, list] = {}
            texts: list[str] = []
            ids: list[str] = []
            for nid, node in self._nodes.items():
                texts.append(f"{node.get('name', '')}: {node.get('summary', '')}")
                ids.append(nid)
            for i in range(0, len(texts), _EMBED_BATCH):
                resp = self.embedding_client.embeddings.create(
                    model=self.embedding_model,
                    input=texts[i : i + _EMBED_BATCH],
                )
                for idx, emb in enumerate(resp.data):
                    if idx < len(ids[i : i + _EMBED_BATCH]):
                        items[ids[i + idx]] = emb.embedding
            self._write_embeddings(items)
            logger.info("✅ embedding 自动回填完成 (%d 节点), 语义检索已就绪", len(items))
        except Exception:
            logger.warning(
                "⚠️ embedding 自动回填失败, 语义检索降级纯图 (不影响主流程)", exc_info=True,
            )

    def generate_embeddings(self, nodes: list[dict], batch_size: int = _EMBED_BATCH) -> None:
        """为缺失向量节点生成 embedding 并写回本地缓存 (对齐 Neo4j 后端入口)。"""
        self._ensure_loaded()
        if not self.embedding_client:
            logger.warning("未配置 embedding_client, 跳过向量生成")
            return
        texts: list[str] = []
        ids: list[str] = []
        for node in nodes:
            nid = node.get("node_id") or node.get("id")
            if not nid or nid in self._embeddings:
                continue
            texts.append(f"{node.get('name', '')}: {node.get('summary', '')}")
            ids.append(nid)
        if not ids:
            return
        items: dict[str, list] = {}
        for i in range(0, len(texts), batch_size):
            try:
                resp = self.embedding_client.embeddings.create(
                    model=self.embedding_model,
                    input=texts[i : i + batch_size],
                )
                for idx, emb in enumerate(resp.data):
                    if idx < len(ids[i : i + batch_size]):
                        items[ids[i + idx]] = emb.embedding
            except Exception as e:
                logger.warning("向量化失败 [%d:%d]: %s", i, i + len(texts), e)
        if items:
            self._write_embeddings(items)

    def _cosine_topk(self, qvec: list, top_k: int, difficulty_max: Optional[int]) -> list[tuple[str, float]]:
        """numpy 优先的余弦 top-k; 无 numpy 时纯 Python 降级 (300 节点仍 <20ms)。"""
        ids = list(self._embeddings.keys())
        if not ids:
            return []
        qlen = (sum(v * v for v in qvec) ** 0.5) or 1.0
        try:
            import numpy as np

            matrix = np.asarray([self._embeddings[i] for i in ids], dtype=np.float64)
            q = np.asarray(qvec, dtype=np.float64)
            norms = np.linalg.norm(matrix, axis=1)
            denom = np.where(norms == 0, 1.0, norms) * qlen
            scores = (matrix @ q) / denom
            order = np.argsort(-scores)
            scored = []
            for idx in order:
                nid = ids[int(idx)]
                diff = int(self._nodes[nid].get("difficulty", 1))
                if difficulty_max is not None and diff > difficulty_max:
                    continue
                scored.append((nid, round(float(scores[int(idx)]), 4)))
                if len(scored) >= top_k:
                    break
            return scored
        except ImportError:
            scored = []
            for nid in ids:
                vec = self._embeddings[nid]
                vlen = (sum(v * v for v in vec) ** 0.5) or 1.0
                denom = vlen * qlen
                s = (sum(a * b for a, b in zip(qvec, vec))) / denom
                scored.append((nid, round(s, 4)))
            scored.sort(key=lambda t: -t[1])
            out = []
            for nid, s in scored:
                diff = int(self._nodes[nid].get("difficulty", 1))
                if difficulty_max is not None and diff > difficulty_max:
                    continue
                out.append((nid, s))
                if len(out) >= top_k:
                    break
            return out

    def semantic_search(
        self, query: str, top_k: int = 5, difficulty_max: int = None
    ) -> list[dict]:
        """纯向量语义检索: 本地余弦 (Neo4j 向量索引的进程内等价)。无向量/无客户端 → 降级 []。"""
        self._ensure_loaded()
        if not self._semantic_ready or not self.embedding_client:
            return []
        try:
            resp = self.embedding_client.embeddings.create(
                model=self.embedding_model, input=[query]
            )
            qvec = resp.data[0].embedding
        except Exception:
            logger.error("Embedding API 调用失败，语义检索不可用", exc_info=True)
            return []
        scored = self._cosine_topk(qvec, top_k, difficulty_max)
        return [self._node_with_similarity(nid, s) for nid, s in scored]

    def _node_with_similarity(self, nid: str, score: float) -> dict:
        node = self._node_out(self._nodes[nid])
        node["_similarity"] = score
        return node

    # ------------------------------------------------------------
    # 混合检索 + 学习路径组装 (P2: 逐段复刻 Neo4j 后端)
    # ------------------------------------------------------------

    def hybrid_retrieve(
        self,
        known_ids: list[str],
        weak_ids: list[str] = None,
        level: int = 3,
        top_k: int = 10,
    ) -> list[dict]:
        weak_ids = weak_ids or []
        known_set = set(known_ids)
        seen: dict[str, dict] = {}

        # 阶段 1: 图遍历
        if known_ids:
            for node in self.get_reachable(known_ids, max_depth=2):
                nid = node["node_id"]
                if nid not in seen:
                    node["_source"] = "graph"
                    node["_score"] = 1.0
                    seen[nid] = node

        # 阶段 2: 语义向量
        if weak_ids and self.embedding_client:
            weak_summaries = []
            for wid in weak_ids[:3]:
                wn = self.get_node(wid)
                if wn:
                    weak_summaries.append(f"{wn['name']}: {wn.get('summary', '')}")
            if weak_summaries:
                try:
                    for node in self.semantic_search(
                        " ".join(weak_summaries), top_k=top_k, difficulty_max=level,
                    ):
                        nid = node["node_id"]
                        if nid not in seen:
                            node["_source"] = "vector"
                            node["_score"] = node.pop("_similarity", 0.5)
                            seen[nid] = node
                except Exception:
                    logger.error(
                        "⚠️ 混合检索的语义阶段失败，当前结果仅为图遍历数据", exc_info=True,
                    )

        # 阶段 3/4: 排序 + 排除已知 + 截断
        results = sorted(
            seen.values(),
            key=lambda n: (n.get("difficulty", 1), -n.get("_score", 0)),
        )
        results = [n for n in results if n["node_id"] not in known_set]
        return results[:top_k]

    def assemble_learning_path(
        self,
        known_ids: list[str],
        weak_ids: list[str] = None,
        level: int = 2,
        max_nodes: int = 20,
    ) -> list[dict]:
        """组装个性化学习路径 — 逐段复刻 engine.assemble_learning_path (BFS 等价 Cypher 两次聚合)。

        - BFS 逐层记录距离天然等价 Cypher 的 min(length(path)) 全局最短距离
        - _WEAK_PATCH_LIMIT / difficulty_cap 常量与 Neo4j 后端单源对齐, 保 M5 覆盖率口径
        """
        self._ensure_loaded()
        weak_ids = weak_ids or []
        known_set = set(known_ids)

        # 零基础: 直接返回难度 1 入口
        if not known_ids and not weak_ids:
            return self.get_by_difficulty(1, 1)[:max_nodes]

        if not known_ids:
            entry_set = set()
            for wid in weak_ids[:_WEAK_PATCH_LIMIT]:
                for pr in self.get_prerequisites(wid):
                    entry_set.add(pr["node_id"])
            if entry_set:
                known_ids = list(entry_set)
            else:
                return self.get_by_difficulty(1, 1)[:max_nodes]

        # BFS 分层 (深度 1..4), 与 Cypher *1..4 一致
        nodes_by_dist: dict[int, list[dict]] = {}
        visited: set[str] = set()
        frontier = list(known_ids)
        for depth in range(1, 5):
            nxt: list[str] = []
            for nid in frontier:
                for child in self._children.get(nid, ()):
                    if child in visited or child in frontier:
                        continue
                    visited.add(child)
                    nxt.append(child)
                    node = self._node_out(self._nodes[child])
                    if node["node_id"] in known_set:  # 过滤已掌握 (与 Neo4j 后端一致)
                        continue
                    nodes_by_dist.setdefault(depth, []).append(node)
            frontier = nxt
            if not frontier:
                break

        difficulty_cap = max(1, min(5, level + 2))
        path: list[dict] = []
        for dist in sorted(nodes_by_dist):
            nodes_by_dist[dist].sort(key=lambda n: n.get("difficulty", 1))
            for node in nodes_by_dist[dist]:
                if len(path) >= max_nodes:
                    break
                if node.get("difficulty", 1) > difficulty_cap:
                    continue
                path.append(node)
            if len(path) >= max_nodes:
                break

        # 弱项盲区覆盖补丁 (赛题(2)精准锚定盲区 + M5 覆盖率≥90%)
        if weak_ids:
            path_ids = {n["node_id"] for n in path}
            prereq_patch = []
            for wid in weak_ids[:_WEAK_PATCH_LIMIT]:
                for pr in self.get_prerequisites(wid):
                    if pr["node_id"] in known_set or pr["node_id"] in path_ids:
                        continue
                    if pr.get("difficulty", 1) > difficulty_cap:
                        continue
                    prereq_patch.append(pr)
                    path_ids.add(pr["node_id"])
            weak_patch = []
            for wid in weak_ids[:_WEAK_PATCH_LIMIT]:
                if wid in known_set or wid in path_ids:
                    continue
                wnode = self.get_node(wid)
                if wnode is None:
                    continue
                if wnode.get("difficulty", 1) > difficulty_cap:
                    continue
                weak_patch.append(wnode)
                path_ids.add(wid)
            if prereq_patch or weak_patch:
                path = prereq_patch + weak_patch + path

        return path[:max_nodes]

    # ------------------------------------------------------------
    # 状态管理
    # ------------------------------------------------------------

    def _status_path(self) -> Path:
        return self.local_dir / "mastery_status.json"

    def _read_status(self) -> dict:
        """读状态文件 (不加锁): 锁由调用方 update_node_status 持有。

        切勿在此再加 _lock_for(path) — 与 update_node_status 外层同一把非可重入锁
        嵌套获取会**自锁死锁**(第二次写状态时文件已存在即触发, 扫描实测 PUT status 超时)。
        """
        path = self._status_path()
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def update_node_status(self, node_id: str, status: str) -> None:
        if status not in _VALID_STATUSES:
            raise ValueError(f"无效状态 '{status}'，有效值: {sorted(_VALID_STATUSES)}")
        path = self._status_path()
        with self._lock_for(path):  # 唯一持锁点: 读-改-写整体串行化
            data = self._read_status()
            data[node_id] = status
            _atomic_write(path, json.dumps(data, ensure_ascii=False))

    def get_node_status(self, node_id: str) -> Optional[str]:
        return self._read_status().get(node_id)

    # ------------------------------------------------------------
    # 项目图谱 (P3: 可变数据落盘, G6 形状逐字段对齐)
    # ------------------------------------------------------------

    def _project_path(self, project_id: str) -> Path:
        """项目图落盘路径。project_id 白名单校验 — 防路径穿越 (API 输入为自由字符串)。"""
        if not _PROJECT_ID_RE.fullmatch(project_id or ""):
            raise ValueError(
                f"非法 project_id: {project_id!r} (仅允许字母/数字/下划线/连字符, 长度≤64)")
        return self.local_dir / "projects" / f"{project_id}.json"

    def _project_files(self):
        d = self.local_dir / "projects"
        return sorted(d.glob("*.json")) if d.is_dir() else []

    def write_project_graph(self, project_id: str, entities: list, relations: list) -> None:
        """幂等写入项目图谱: 原子替换本地 JSON (等价 DETACH DELETE + CREATE 单事务语义)。"""
        parsed_at = _utc_now_iso()

        def e2dict(e):
            d = e.to_neo4j_props() if hasattr(e, "to_neo4j_props") else dict(e)
            d["params"] = json.dumps(d.get("params") or [], ensure_ascii=False)
            d["external_calls"] = json.dumps(d.get("external_calls") or [], ensure_ascii=False)
            d["parsed_at"] = parsed_at
            return d

        stored_entities = [e2dict(e) for e in entities]
        stored_relations = []
        for r in relations:
            rec = {"type": r.type, "source": r.source, "target": r.target}
            if r.type == "CALLS":
                rec["line"] = r.line
                rec["resolved"] = r.resolved
            stored_relations.append(rec)

        path = self._project_path(project_id)
        data = {
            "project_id": project_id,
            "parsed_at": parsed_at,
            "entities": stored_entities,
            "relations": stored_relations,
        }
        with self._lock_for(path):
            _atomic_write(path, json.dumps(data, ensure_ascii=False))

    def get_project_graph(self, project_id: str) -> Optional[dict]:
        """读项目图谱, 归一 G6 友好结构 {project_id, nodes, edges}。"""
        path = self._project_path(project_id)
        if not path.is_file():
            return None
        try:
            with self._lock_for(path):
                data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("项目图解析失败: %s", path, exc_info=True)
            return None
        entities = data.get("entities", []) if isinstance(data, dict) else []
        if not entities:
            return None

        nodes = []
        for props in entities:
            p = dict(props)
            for k in ("params", "external_calls"):
                v = p.get(k)
                if isinstance(v, str):
                    try:
                        p[k] = json.loads(v)
                    except (ValueError, TypeError):
                        p[k] = []
            nodes.append({
                "id": p.get("entity_id"),
                "label": p.get("name"),
                "group": p.get("kind"),
                "layer": p.get("layer"),
                "properties": p,
            })

        edges = []
        for r in data.get("relations", []):
            edge = {"source": r.get("source"), "target": r.get("target"), "label": r.get("type")}
            if r.get("type") == "CALLS":
                edge["line"] = r.get("line")
                edge["resolved"] = r.get("resolved")
            edges.append(edge)

        return {"project_id": project_id, "nodes": nodes, "edges": edges}

    def delete_project_graph(self, project_id: str) -> int:
        path = self._project_path(project_id)
        if not path.is_file():
            return 0
        try:
            with self._lock_for(path):
                data = json.loads(path.read_text(encoding="utf-8"))
            count = len(data.get("entities", [])) if isinstance(data, dict) else 0
        except Exception:
            count = 0
        with self._lock_for(path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        return count

    def _find_entity(self, entity_id: str):
        """全项目扫描定位 entity_id → (project_path, data, idx)。稀疏索引:(项目量小, 直接扫描足够)。"""
        for fpath in self._project_files():
            try:
                with self._lock_for(fpath):
                    data = json.loads(fpath.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            for i, e in enumerate(data.get("entities", []) or []):
                if isinstance(e, dict) and e.get("entity_id") == entity_id:
                    return fpath, data, i
        return None, None, -1

    def annotate_risk(self, entity_id: str, risk_level: str, reason: str) -> None:
        valid = {"high", "medium", "low"}
        if risk_level not in valid:
            raise ValueError(f"risk_level 无效 '{risk_level}' (有效: {sorted(valid)})")
        fpath, data, idx = self._find_entity(entity_id)
        if fpath is None:
            return
        if data.get("entities") is None:
            data["entities"] = []
        data["entities"][idx]["risk_level"] = risk_level
        data["entities"][idx]["risk_reason"] = reason
        data["entities"][idx]["risk_annotated_at"] = _utc_now_iso()
        with self._lock_for(fpath):
            _atomic_write(fpath, json.dumps(data, ensure_ascii=False))

    def link_entity_to_knowledge(self, entity_id: str, knowledge_node_id: str) -> None:
        fpath, data, idx = self._find_entity(entity_id)
        if fpath is None:
            return
        if data.get("entities") is None:
            data["entities"] = []
        related = data["entities"][idx].get("related_to") or []
        if knowledge_node_id not in related:
            related.append(knowledge_node_id)
        data["entities"][idx]["related_to"] = related
        with self._lock_for(fpath):
            _atomic_write(fpath, json.dumps(data, ensure_ascii=False))

    # ------------------------------------------------------------
    # 知识库 CRUD 同步 (JSON 即库: 刷新内存索引即可)
    # ------------------------------------------------------------

    def _refresh_node(self, node_id: str) -> None:
        """kb_store 已写 JSON → 刷新单个节点到内存 (邻接/索引/题目重建)。"""
        node = kb_store.load_node(self.kb_dir, node_id)
        if node is None:
            self._drop_node(node_id)
            return
        self._drop_node(node_id, keep_questions=True)
        self._nodes[node_id] = node
        prereqs = [p for p in (node.get("prerequisites") or []) if p in self._nodes]
        self._parents[node_id] = prereqs
        for p in prereqs:
            self._children[p].add(node_id)
        cat = node.get("category", "")
        if cat:
            ids = self._by_category.setdefault(cat, [])
            if node_id not in ids:
                ids.append(node_id)
                ids.sort(key=lambda i: int(self._nodes[i].get("difficulty", 1)))
        diff = int(node.get("difficulty", 1))
        ids = self._by_difficulty.setdefault(diff, [])
        if node_id not in ids:
            ids.append(node_id)
            ids.sort(key=lambda i: int(self._nodes[i].get("difficulty", 1)))
        for tag in node.get("tags", []) or []:
            self._by_tag[tag].add(node_id)

    def _drop_node(self, node_id: str, keep_questions: bool = False) -> None:
        """从内存移除节点 + 邻接出/入边 + 索引 (题目按需保留)。"""
        if node_id in self._nodes:
            del self._nodes[node_id]
        for child in self._children.pop(node_id, ()):
            pass
        for p in self._parents.pop(node_id, []):
            self._children[p].discard(node_id)
        for cat_ids in self._by_category.values():
            if node_id in cat_ids:
                cat_ids.remove(node_id)
        for diff_ids in self._by_difficulty.values():
            if node_id in diff_ids:
                diff_ids.remove(node_id)
        for tag_set in self._by_tag.values():
            tag_set.discard(node_id)
        if not keep_questions:
            for q in self._questions_by_node.pop(node_id, []):
                self._qid_index.pop(q.get("qid"), None)
        self._embeddings.pop(node_id, None)

    def _refresh_questions(self, source_node_id: Optional[str] = None) -> None:
        """从磁盘重建题目索引 (单节点或全量)。"""
        if source_node_id is not None:
            for q in self._questions_by_node.pop(source_node_id, []):
                self._qid_index.pop(q.get("qid"), None)
            qs = kb_store.load_questions_for_node(self.kb_dir, source_node_id)
            self._questions_by_node[source_node_id] = qs
            for q in qs:
                self._qid_index[q.get("qid")] = q
            self._questions_by_node[source_node_id].sort(
                key=lambda q: int(q.get("difficulty", 1))
            )
            return
        # 全量重建
        new_q = defaultdict(list)
        new_idx = {}
        qdir = self.kb_dir / "questions"
        if qdir.is_dir():
            for fpath in sorted(qdir.glob("**/*.json")):  # 递归含嵌套域目录
                if fpath.name == "schema.json":
                    continue
                try:
                    qs = kb_store._load_json_list(fpath)  # noqa: SLF001
                except Exception:
                    continue
                for q in qs:
                    if not isinstance(q, dict) or not q.get("qid"):
                        continue
                    new_idx[q["qid"]] = q
                    src = q.get("source_node_id") or ""
                    if src:
                        new_q[src].append(q)
        self._questions_by_node = defaultdict(list)
        for k, v in new_q.items():
            v.sort(key=lambda q: int(q.get("difficulty", 1)))
            self._questions_by_node[k] = v
        self._qid_index = new_idx

    def upsert_knowledge_node(self, node: dict) -> None:
        """JSON 即库 (与 Neo4j 后端等价: 自持持久化): 先落盘 kb_store 再刷新内存索引。

        kb.py/domain_bootstrap 的"先 save_node 再 upsert"双写幂等兼容; 直接调用本方法也能持久化。
        """
        self._ensure_loaded()
        nid = node.get("id") or node.get("node_id")
        if not nid:
            raise ValueError("节点缺 id")
        disk_node = dict(node)
        if "id" not in disk_node and "node_id" in disk_node:
            disk_node["id"] = disk_node.pop("node_id")
        kb_store.save_node(self.kb_dir, disk_node)
        with self._load_lock:
            self._refresh_node(nid)

    def delete_knowledge_node(self, node_id: str) -> int:
        self._ensure_loaded()
        existed = node_id in self._nodes
        if existed:
            kb_store.delete_node(self.kb_dir, node_id)
        with self._load_lock:
            self._drop_node(node_id)
        return 1 if existed else 0

    def upsert_question(self, question: dict) -> None:
        self._ensure_loaded()
        source = question.get("source_node_id")
        if not source:
            raise ValueError("题目缺 source_node_id")
        kb_store.save_question(self.kb_dir, question)
        with self._load_lock:
            self._refresh_questions(source)

    def delete_question(self, qid: str) -> int:
        self._ensure_loaded()
        existed = qid in self._qid_index
        src = self._qid_index.get(qid, {}).get("source_node_id")
        if existed:
            kb_store.delete_question(self.kb_dir, qid)
        with self._load_lock:
            self._qid_index.pop(qid, None)
            if src:
                self._questions_by_node[src] = [
                    q for q in self._questions_by_node.get(src, []) if q.get("qid") != qid
                ]
        return 1 if existed else 0

    # 对齐 Neo4j 后端接口 (嵌入式无动作)
    def setup_vector_index(self) -> None:
        pass
