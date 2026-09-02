"""
KMatch 知识图谱引擎
- Neo4j 连接管理 + 向量索引
- 图遍历查询 + 语义向量检索
- 混合检索 + 学习路径组装
"""

import json
from typing import Optional

from neo4j import GraphDatabase

# 学习路径组装: 弱项补丁覆盖的弱项上限 (entry 收集 + 弱项节点本身统一用此值, BUG B13 一致性)
# M5 覆盖率≥90% 保障: demo 模式下 user_profile 由 LLM 重新生成, weak_topics 数量每次波动 (常 3-5 个),
# 原 3 会导致 4+ 弱项画像只强补前 3 个, 覆盖率掉到 75% (2026-08-12 实测 84.8% → 28/33)。
# 提到 8: 覆盖常见弱项数上限, 路径总数受 max_nodes=20 兜底, 不会显著膨胀。
_WEAK_PATCH_LIMIT = 8

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class KnowledgeGraph:
    """知识图谱引擎：Neo4j 图遍历 + LLM Embedding 语义检索"""

    # ------------------------------------------------------------
    # 构造 & 生命周期
    # ------------------------------------------------------------

    def __init__(
        self,
        uri: str = None,
        user: str = None,
        password: str = None,
        embedding_client=None,
        embedding_model: str = None,
        vector_index_name: str = None,
    ):
        self.uri = uri or settings.NEO4J_URI
        self.user = user or settings.NEO4J_USER
        self.password = password or settings.NEO4J_PASSWORD
        self.embedding_client = embedding_client
        self.embedding_model = embedding_model or settings.EMBEDDING_MODEL
        self.vector_index_name = vector_index_name or settings.VECTOR_INDEX_NAME
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    @classmethod
    def from_settings(cls, embedding_client=None):
        """工厂方法：从全局 settings 创建实例，注入 embedding_client"""
        return cls(embedding_client=embedding_client)

    @staticmethod
    def create_embedding_client():
        """
        根据配置创建 OpenAI 兼容的 embedding client。
        优先使用 EMBEDDING_API_KEY/BASE_URL，未设置则 fallback 到 LLM_* 的值。

        返回 None 表示配置不可用，调用方应降级为纯图模式。
        """
        from openai import OpenAI

        api_key = settings.EMBEDDING_API_KEY
        base_url = settings.EMBEDDING_BASE_URL

        if api_key in ("", "sk-placeholder"):
            return None

        client = OpenAI(api_key=api_key, base_url=base_url)
        try:
            # 快速验证 endpoint 可用
            client.embeddings.create(
                model=settings.EMBEDDING_MODEL, input=["test"]
            )
            return client
        except Exception:
            return None

    def reconfigure_embedding(self, api_key: str, base_url: str = "", model: str = "") -> bool:
        """运行时重建 embedding 客户端 (设置页保存后调用, 治"改 .env 才能换配置")。

        探活成功 → 更新 client (与 model) 返回 True; 失败/未配置 → client 置 None (降级纯图) 返回 False。
        """
        from openai import OpenAI
        if not api_key or api_key == "sk-placeholder":
            self.embedding_client = None
            return False
        client = OpenAI(api_key=api_key, base_url=base_url or settings.EMBEDDING_BASE_URL or settings.LLM_BASE_URL)
        try:
            client.embeddings.create(model=model or self.embedding_model, input=["test"])
        except Exception:
            logger.warning("embedding 重配置探活失败, 降级纯图", exc_info=True)
            self.embedding_client = None
            return False
        self.embedding_client = client
        if model:
            self.embedding_model = model
        return True

    def close(self):
        self.driver.close()

    @property
    def semantic_ready(self) -> bool:
        """语义检索可用性 (Neo4j 后端: 取决于 embedding 客户端)。嵌入式为向量矩阵就绪。

        供 api/graph.py 语义守卫与 health 使用; 两后端同一属性名 (契约保持项 §4.3)。
        """
        return self.embedding_client is not None

    def test_connection(self) -> bool:
        try:
            self.driver.verify_connectivity()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------
    # 向量索引
    # ------------------------------------------------------------

    def setup_vector_index(self):
        """创建 Neo4j 5.x 原生向量索引（幂等，IF NOT EXISTS）"""
        query = f"""
        CREATE VECTOR INDEX {self.vector_index_name} IF NOT EXISTS
        FOR (n:KnowledgeNode) ON (n.embedding)
        OPTIONS {{indexConfig: {{
            `vector.dimensions`: {settings.EMBEDDING_DIMENSIONS},
            `vector.similarity_function`: 'cosine'
        }}}}
        """
        with self.driver.session() as s:
            s.run(query)

    def generate_embeddings(self, nodes: list[dict], batch_size: int = 20):
        """批量为 KnowledgeNode 生成 embedding 并写回 Neo4j"""
        if not self.embedding_client:
            logger.warning("未配置 embedding_client，跳过向量生成")
            return

        # 只处理缺失 embedding 的节点
        texts, node_ids = [], []
        for node in nodes:
            # 兼容两种来源: 图读取节点已由 _node_from_record 统一为 node_id；
            # import 脚本传入的原始 JSON 节点仍用 id。兜底缺一不可，删除会导致
            # 导入路径的 embedding 写回失败（MATCH 找不到节点）。— 命名收口见 C1 备注
            nid = node.get('node_id') or node.get('id')
            if not nid:
                # BUG 优化: 两键都缺 → None, 旧代码 MATCH {id:$id} 会误匹配无 id 属性的
                # 节点并覆盖其 embedding。跳过, 避免脏写。
                logger.warning("节点缺 node_id/id, 跳过 embedding: %s", node.get('name', '?'))
                continue
            texts.append(f"{node['name']}: {node.get('summary', '')}")
            node_ids.append(nid)

        with self.driver.session() as s:
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i : i + batch_size]
                batch_ids = node_ids[i : i + batch_size]

                try:
                    resp = self.embedding_client.embeddings.create(
                        model=self.embedding_model,
                        input=batch_texts,
                    )
                    # UNWIND 批量写回 (优化: 旧实现逐节点 s.run = N 次往返;
                    # UNWIND 一次事务写整批, 92 节点 5 批 vs 92 次往返)。
                    # 按 index 对齐 batch_ids 与 resp.data (OpenAI 兼容 API 保证顺序,
                    # 但 index 对齐更稳健, 防 reorder)。
                    rows = []
                    for idx, emb_data in enumerate(resp.data):
                        if idx < len(batch_ids):
                            rows.append({"id": batch_ids[idx], "emb": emb_data.embedding})
                    if rows:
                        s.run(
                            "UNWIND $rows AS row "
                            "MATCH (n:KnowledgeNode {id: row.id}) "
                            "SET n.embedding = row.emb",
                            rows=rows,
                        )
                    logger.info(
                        "embedding 进度: %d-%d/%d",
                        i + 1, i + len(batch_texts), len(texts),
                    )
                except Exception as e:
                    logger.warning(
                        "向量化失败 [%d:%d]: %s",
                        i, i + len(batch_texts), e,
                    )

    # ------------------------------------------------------------
    # 基础图查询
    # ------------------------------------------------------------

    def _node_from_record(self, record) -> Optional[dict]:
        """从 Neo4j record 中提取节点字典（排除 embedding 字段，统一 id→node_id）"""
        node = dict(record)
        node.pop("embedding", None)  # 向量不返回给调用方
        if "id" in node:
            node["node_id"] = node.pop("id")
        return node

    def _question_from_record(self, record) -> Optional[dict]:
        """从 Neo4j record 提取 :Question 题目字典。

        - options 存原生 list (import 时 choice 题存 list); 兜底空 list
        - 注入 node_id = source_node_id (diagnostics _grade/_build_profile 按 node_id 分组)
        """
        q = dict(record)
        opts = q.get("options")
        if opts is None:
            q["options"] = []
        elif isinstance(opts, str):
            # 防御: 偶发以字符串存
            try:
                parsed = json.loads(opts)
                q["options"] = parsed if isinstance(parsed, list) else []
            except (ValueError, TypeError):
                q["options"] = []
        # node_id 别名 (供 diagnostics 抽题后直接用, 与 _grade 契约一致)
        q["node_id"] = q.get("source_node_id", "")
        return q

    def get_questions(
        self,
        node_id: str,
        types: Optional[list[str]] = None,
        difficulty_min: Optional[int] = None,
        difficulty_max: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """查某知识点的题目,可按题型/难度筛选。

        走 :Question 索引 (source_node_id/type/difficulty)。返回题目 dict 列表,
        每题含 node_id=source_node_id (供 _grade/_build_profile 分组)。
        """
        clauses = ["(n:KnowledgeNode {id: $node_id})-[:HAS_QUESTION]->(q:Question)"]
        params: dict = {"node_id": node_id}
        if types:
            clauses.append("q.type IN $types")
            params["types"] = types
        if difficulty_min is not None:
            clauses.append("q.difficulty >= $dmin")
            params["dmin"] = difficulty_min
        if difficulty_max is not None:
            clauses.append("q.difficulty <= $dmax")
            params["dmax"] = difficulty_max
        where = " WHERE " + " AND ".join(clauses[1:]) if len(clauses) > 1 else ""
        cypher = (
            "MATCH " + clauses[0] + where
            + " RETURN q ORDER BY q.difficulty"
        )
        if limit:
            cypher += f" LIMIT {int(limit)}"
        with self.driver.session() as s:
            result = s.run(cypher, params)
            return [self._question_from_record(r["q"]) for r in result]

    def get_questions_for_nodes(
        self,
        node_ids: list[str],
        types: Optional[list[str]] = None,
        max_per_node: int = 2,
    ) -> list[dict]:
        """批量查多节点题目,每节点最多 max_per_node 道。供 diagnostics 抽题。

        用 UNWIND + per-node limit (collect+slice) 保证每节点配额。
        """
        if not node_ids:
            return []
        params: dict = {"node_ids": node_ids, "max_per_node": max_per_node}
        type_clause = "AND q.type IN $types" if types else ""
        if types:
            params["types"] = types
        cypher = f"""
        MATCH (n:KnowledgeNode)-[:HAS_QUESTION]->(q:Question)
        WHERE n.id IN $node_ids {type_clause}
        WITH n, q ORDER BY q.difficulty
        WITH n, collect(q)[..$max_per_node] AS qs
        UNWIND qs AS q
        RETURN q
        """
        with self.driver.session() as s:
            result = s.run(cypher, params)
            return [self._question_from_record(r["q"]) for r in result]

    def get_node(self, node_id: str) -> Optional[dict]:
        with self.driver.session() as s:
            result = s.run(
                "MATCH (n:KnowledgeNode {id: $id}) RETURN n", id=node_id
            )
            record = result.single()
            return self._node_from_record(record["n"]) if record else None

    def get_by_category(self, category: str) -> list[dict]:
        with self.driver.session() as s:
            result = s.run(
                "MATCH (n:KnowledgeNode {category: $cat}) "
                "RETURN n ORDER BY n.difficulty",
                cat=category,
            )
            return [self._node_from_record(r["n"]) for r in result]

    def get_by_difficulty(self, min_d: int, max_d: int) -> list[dict]:
        with self.driver.session() as s:
            result = s.run(
                "MATCH (n:KnowledgeNode) "
                "WHERE n.difficulty >= $min AND n.difficulty <= $max "
                "RETURN n ORDER BY n.difficulty",
                min=min_d, max=max_d,
            )
            return [self._node_from_record(r["n"]) for r in result]

    def get_by_tags(self, tags: list[str]) -> list[dict]:
        with self.driver.session() as s:
            result = s.run(
                "MATCH (n:KnowledgeNode) "
                "WHERE any(tag IN n.tags WHERE tag IN $tags) "
                "RETURN n ORDER BY n.difficulty",
                tags=tags,
            )
            return [self._node_from_record(r["n"]) for r in result]

    # ------------------------------------------------------------
    # 图遍历
    # ------------------------------------------------------------

    def get_prerequisites(self, node_id: str) -> list[dict]:
        with self.driver.session() as s:
            result = s.run(
                "MATCH (n:KnowledgeNode {id: $id})-[:REQUIRES]->(p:KnowledgeNode) "
                "RETURN p",
                id=node_id,
            )
            return [self._node_from_record(r["p"]) for r in result]

    def get_prerequisites_batch(self, node_ids: list[str]) -> dict[str, list[dict]]:
        """批量前置依赖 (v1.3.3: 图谱视图逐节点请求 N+1 → 单次 UNWIND; 嵌入式同实现)。

        返回 {node_id: [前置节点]}; 不存在的节点值为空列表。按难度升序 (与嵌入式排序一致)。
        """
        ids = [i for i in (node_ids or []) if i]
        if not ids:
            return {}
        out: dict[str, list[dict]] = {}
        with self.driver.session() as s:
            result = s.run(
                "UNWIND $ids AS nid "
                "MATCH (n:KnowledgeNode {id: nid})-[:REQUIRES]->(p:KnowledgeNode) "
                "RETURN nid, p",
                ids=ids,
            )
            for r in result:
                out.setdefault(r["nid"], []).append(self._node_from_record(r["p"]))
        for lst in out.values():
            lst.sort(key=lambda d: int(d.get("difficulty", 1) or 1))
        return out

    def get_dependents(self, node_id: str) -> list[dict]:
        with self.driver.session() as s:
            result = s.run(
                "MATCH (d:KnowledgeNode)-[:REQUIRES]->(n:KnowledgeNode {id: $id}) "
                "RETURN d",
                id=node_id,
            )
            return [self._node_from_record(r["d"]) for r in result]

    def get_reachable(self, known_ids: list[str], max_depth: int = 3) -> list[dict]:
        """从已知节点向外扩散，获取所有可学习的后继节点（即依赖 known 的节点）"""
        if not known_ids:
            return []
        with self.driver.session() as s:
            # REQUIRES 方向: (child)-[:REQUIRES]->(parent)
            # 要找「接下来学什么」需要反向: (parent)<-[:REQUIRES]-(child)
            result = s.run(
                f"""
                MATCH (start:KnowledgeNode)<-[:REQUIRES*1..{max_depth}]-(n:KnowledgeNode)
                WHERE start.id IN $known_ids
                RETURN DISTINCT n
                ORDER BY n.difficulty
                """,
                known_ids=known_ids,
            )
            return [self._node_from_record(r["n"]) for r in result]

    # ------------------------------------------------------------
    # 语义向量检索
    # ------------------------------------------------------------

    def semantic_search(
        self, query: str, top_k: int = 5, difficulty_max: int = None
    ) -> list[dict]:
        """纯向量语义检索：用自然语言查询找到语义最接近的节点"""
        if not self.embedding_client:
            return []

        try:
            resp = self.embedding_client.embeddings.create(
                model=self.embedding_model, input=[query]
            )
            query_embedding = resp.data[0].embedding
        except Exception:
            # 嵌入 API 失败 → 记录错误后降级返回空集
            # 上层 hybrid_retrieve 会检测到此情况并标记结果集降级
            logger.error("Embedding API 调用失败，语义检索不可用", exc_info=True)
            return []

        with self.driver.session() as s:
            # 多取一些，再在 Python 侧过滤难度
            result = s.run(
                f"""
                CALL db.index.vector.queryNodes(
                    '{self.vector_index_name}', $k, $embedding
                )
                YIELD node, score
                RETURN node, score
                ORDER BY score DESC
                """,
                k=top_k * 3, embedding=query_embedding,
            )

            nodes = []
            for r in result:
                node = dict(r["node"])
                node.pop("embedding", None)
                if "id" in node:
                    node["node_id"] = node.pop("id")
                node["_similarity"] = round(r["score"], 4)
                if difficulty_max is not None and node.get("difficulty", 1) > difficulty_max:
                    continue
                nodes.append(node)
                if len(nodes) >= top_k:
                    break
            return nodes

    # ------------------------------------------------------------
    # 混合检索（核心）
    # ------------------------------------------------------------

    def hybrid_retrieve(
        self,
        known_ids: list[str],
        weak_ids: list[str] = None,
        level: int = 3,
        top_k: int = 10,
    ) -> list[dict]:
        """
        图遍历 + 语义向量混合检索。

        1. 图遍历：从 known_ids 向外 2 跳扩散，获得候选集 A
        2. 语义检索：以 weak_ids 的 summary 做向量查询，获得候选集 B
        3. A ∪ B 去重，按 (难度, 语义分数) 排序
        4. 排除已掌握节点，截断到 top_k
        """
        weak_ids = weak_ids or []
        known_set = set(known_ids)
        seen: dict[str, dict] = {}

        # ---- 阶段 1: 图遍历 ----
        if known_ids:
            for node in self.get_reachable(known_ids, max_depth=2):
                nid = node["node_id"]
                if nid not in seen:
                    node["_source"] = "graph"
                    node["_score"] = 1.0
                    seen[nid] = node

        # ---- 阶段 2: 语义向量检索 ----
        if weak_ids and self.embedding_client:
            # 拼接弱项的 summary 作为语义查询
            weak_summaries = []
            for wid in weak_ids[:3]:
                wn = self.get_node(wid)
                if wn:
                    weak_summaries.append(f"{wn['name']}: {wn.get('summary', '')}")

            if weak_summaries:
                try:
                    for node in self.semantic_search(
                        " ".join(weak_summaries),
                        top_k=top_k,
                        difficulty_max=level,
                    ):
                        nid = node["node_id"]
                        if nid not in seen:
                            node["_source"] = "vector"
                            node["_score"] = node.pop("_similarity", 0.5)
                            seen[nid] = node
                except Exception:
                    # 语义检索非预期异常 → 降级为纯图模式
                    # 返回结果中仅含图遍历数据，缺少向量语义匹配
                    logger.error(
                        "⚠️ 混合检索的语义阶段失败，当前结果仅为图遍历数据，"
                        "可能缺少语义相关的知识点推荐",
                        exc_info=True,
                    )

        # ---- 阶段 3: 排序（难度升序，同难度分数降序） ----
        results = sorted(
            seen.values(),
            key=lambda n: (n.get("difficulty", 1), -n.get("_score", 0)),
        )

        # ---- 阶段 4: 排除已掌握 + 截断 ----
        results = [n for n in results if n["node_id"] not in known_set]
        return results[:top_k]

    # ------------------------------------------------------------
    # 学习路径组装
    # ------------------------------------------------------------

    def assemble_learning_path(
        self,
        known_ids: list[str],
        weak_ids: list[str] = None,
        level: int = 2,
        max_nodes: int = 20,
    ) -> list[dict]:
        """
        组装个性化学习路径图谱。

        1. 零基础用户 → 直接返回难度 1 的入口节点
        2. BFS 从 known_ids 向外扩散，按距离分层
        3. 每层内难度升序，层间按距离升序
        4. 弱项节点的前置依赖链优先插入
        """
        weak_ids = weak_ids or []
        known_set = set(known_ids)

        # 零基础用户：返回最低难度入口节点
        if not known_ids and not weak_ids:
            return self.get_by_difficulty(1, 1)[:max_nodes]

        if not known_ids:
            # 只有 weak_ids：从弱项的前置依赖入手
            entry_set = set()
            for wid in weak_ids[:_WEAK_PATCH_LIMIT]:
                for pr in self.get_prerequisites(wid):
                    entry_set.add(pr["node_id"])
            if entry_set:
                known_ids = list(entry_set)
            else:
                return self.get_by_difficulty(1, 1)[:max_nodes]

        with self.driver.session() as s:
            result = s.run(
                """
                MATCH path = (start:KnowledgeNode)<-[:REQUIRES*1..4]-(n:KnowledgeNode)
                WHERE start.id IN $known_ids
                WITH n, min(length(path)) AS distance
                WITH n, min(distance) AS distance
                RETURN n, distance
                ORDER BY distance, n.difficulty
                LIMIT $limit
                """,
                known_ids=known_ids,
                limit=max_nodes * 2,
            )

            nodes_by_dist: dict[int, list[dict]] = {}
            # 实测 (2026-08-15, AI 域 7 入口): 单次 `WITH n, min(length(path))` 在此
            # 模式按 (start, n) 分组不坍缩 — 同节点多入口各出一行 (42 行/9 唯一),
            # LIMIT 会在重复行上浪费名额; 上面的二次聚合才真正坍缩到全局最短距离。
            # seen_ids 兜底防未来查询回归: 前端 G6 graphlib 对重复节点 id 直接抛
            # "Node already exists" → 图谱渲染失败。
            seen_ids: set[str] = set()
            for r in result:
                node = self._node_from_record(r["n"])
                if node["node_id"] in known_set:  # 过滤已掌握（Python 侧，兼容 Neo4j 5.x）
                    continue
                if node["node_id"] in seen_ids:
                    continue
                seen_ids.add(node["node_id"])
                dist = r["distance"]
                nodes_by_dist.setdefault(dist, []).append(node)

        # 展平：距离升序，层内难度升序；按 level 过滤过高难度节点 (F3)
        # level=用户当前理论水平(1-5)，路径节点难度上限 level+2 (允许适度进阶，
        # 零基础 level=1 → 上限难度 3，避免推难度 4-5 的节点)
        difficulty_cap = max(1, min(5, level + 2))
        path = []
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

        # 弱项盲区覆盖补丁 (赛题(2)"精准锚定盲区" + M5 覆盖率≥90%):
        # 1. 弱项的前置依赖 (F8): 优先插入路径头, 保证学弱项前先备基础
        # 2. 弱项节点本身: 必须纳入路径 (覆盖率指标核心), 受 difficulty_cap 保护
        #    (零基础 level=1 不直推难度4-5弱项, 避免挫败; 其前置已先入路径)
        if weak_ids:
            path_ids = {n["node_id"] for n in path}
            prereq_patch = []
            for wid in weak_ids[:_WEAK_PATCH_LIMIT]:
                for pr in self.get_prerequisites(wid):
                    if pr["node_id"] in known_set or pr["node_id"] in path_ids:
                        continue
                    # 受 difficulty_cap 保护 (BUG B1): 零基础 level=1 不直推难度4-5前置,
                    # 与 weak_patch/BFS 展平一致, 避免"前置比弱项本身还难"的挫败。
                    # 超出 cap 的前置跳过 (其更基础的前置通常已在 BFS 路径里)。
                    if pr.get("difficulty", 1) > difficulty_cap:
                        continue
                    prereq_patch.append(pr)
                    path_ids.add(pr["node_id"])
            # 弱项节点本身入路径 (前置已就位, 弱项紧随其后)
            weak_patch = []
            for wid in weak_ids[:_WEAK_PATCH_LIMIT]:
                if wid in known_set or wid in path_ids:
                    continue
                wnode = self.get_node(wid)
                if wnode is None:
                    continue
                if wnode.get("difficulty", 1) > difficulty_cap:
                    # 超出当前水平上限, 跳过 (其前置已在路径, 后续按进度推进)
                    continue
                weak_patch.append(wnode)
                path_ids.add(wid)
            if prereq_patch or weak_patch:
                path = prereq_patch + weak_patch + path

        return path[:max_nodes]

    # ------------------------------------------------------------
    # 状态管理
    # ------------------------------------------------------------

    def update_node_status(self, node_id: str, status: str) -> None:
        valid = {"mastered", "in_progress", "unlearned", "difficult"}
        if status not in valid:
            raise ValueError(f"无效状态 '{status}'，有效值: {valid}")
        with self.driver.session() as s:
            s.run(
                "MATCH (n:KnowledgeNode {id: $id}) SET n.mastery_status = $status",
                id=node_id, status=status,
            )

    def get_node_status(self, node_id: str) -> Optional[str]:
        with self.driver.session() as s:
            result = s.run(
                "MATCH (n:KnowledgeNode {id: $id}) RETURN n.mastery_status AS s",
                id=node_id,
            )
            record = result.single()
            return record["s"] if record and record["s"] else None

    # ============================================================
    # 项目图谱 (W6: 项目框架层 layer2 + 代码实体层 layer3)
    # ------------------------------------------------------------
    # 项目实体统一打 :ProjectEntity 基标签 + kind 子标签 (Module/Class/Function)，
    # 与领域元知识 :KnowledgeNode (PY-xxx) 物理隔离，MATCH (n:ProjectEntity) 不污染领域层。
    # Neo4j 节点属性不支持 list of map，故 params / external_calls 序列化为 JSON 字符串存储。
    # ============================================================

    def write_project_graph(self, project_id: str, entities: list, relations: list) -> None:
        """幂等写入项目图谱: DETACH DELETE 旧实体 → 分 label 三批 CREATE → 建关系。

        Args:
            project_id: 项目 ID (命名空间)
            entities: CodeEntity 列表 (to_neo4j_props 可转 dict)
            relations: CodeRelation 列表
        """
        from datetime import datetime, timezone

        parsed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        def _e2dict(e):
            d = e.to_neo4j_props() if hasattr(e, "to_neo4j_props") else dict(e)
            # list of map 字段序列化为 JSON 字符串 (Neo4j 不支持嵌套 map 属性)
            d["params"] = json.dumps(d.get("params") or [], ensure_ascii=False)
            d["external_calls"] = json.dumps(d.get("external_calls") or [], ensure_ascii=False)
            d["parsed_at"] = parsed_at
            return d

        modules = [_e2dict(e) for e in entities if getattr(e, "kind", None) == "module"]
        classes = [_e2dict(e) for e in entities if getattr(e, "kind", None) == "class"]
        functions = [_e2dict(e) for e in entities if getattr(e, "kind", None) in ("function", "method")]
        contains = [{"source": r.source, "target": r.target} for r in relations if r.type == "CONTAINS"]
        calls = [{"source": r.source, "target": r.target, "line": r.line, "resolved": r.resolved}
                 for r in relations if r.type == "CALLS"]
        inherits = [{"source": r.source, "target": r.target} for r in relations if r.type == "INHERITS"]

        # 单写事务包全部写操作 (BUG B3): 旧实现 7 次 s.run 各自独立 auto-commit,
        # DETACH DELETE 后若中途 CREATE/关系失败 → 旧图谱已删、新数据半残, 无回滚。
        # execute_write 把全部写纳单事务, 任一失败整体回滚, 保留旧图谱不变。
        def _tx_fn(tx):
            # 0. 幂等清理 (DETACH 同时删关系)
            tx.run(
                "MATCH (n:ProjectEntity {project_id: $pid}) DETACH DELETE n",
                pid=project_id,
            )
            # 1-3. 分 label 三批 CREATE (Neo4j 不支持参数化 label)
            if modules:
                tx.run(
                    "UNWIND $rows AS e CREATE (n:ProjectEntity:Module) SET n = e",
                    rows=modules,
                )
            if classes:
                tx.run(
                    "UNWIND $rows AS e CREATE (n:ProjectEntity:Class) SET n = e",
                    rows=classes,
                )
            if functions:
                tx.run(
                    "UNWIND $rows AS e CREATE (n:ProjectEntity:Function) SET n = e",
                    rows=functions,
                )
            # 4. 关系 (三类分别 UNWIND)
            if contains:
                tx.run(
                    "UNWIND $rows AS r MATCH (a:ProjectEntity {entity_id: r.source}), "
                    "(b:ProjectEntity {entity_id: r.target}) CREATE (a)-[:CONTAINS]->(b)",
                    rows=contains,
                )
            if calls:
                tx.run(
                    "UNWIND $rows AS r MATCH (a:ProjectEntity {entity_id: r.source}), "
                    "(b:ProjectEntity {entity_id: r.target}) "
                    "CREATE (a)-[:CALLS {line: r.line, resolved: r.resolved}]->(b)",
                    rows=calls,
                )
            if inherits:
                tx.run(
                    "UNWIND $rows AS r MATCH (a:ProjectEntity {entity_id: r.source}), "
                    "(b:ProjectEntity {entity_id: r.target}) CREATE (a)-[:INHERITS]->(b)",
                    rows=inherits,
                )

        with self.driver.session() as s:
            s.execute_write(_tx_fn)

    def get_project_graph(self, project_id: str) -> Optional[dict]:
        """查询项目全部 ProjectEntity + 内部关系，返回 G6 友好结构。

        Returns:
            {project_id, nodes:[{id,label,group,layer,properties}], edges:[{source,target,label,...}]}
            无实体返回 None。
        """
        with self.driver.session() as s:
            node_result = s.run(
                "MATCH (n:ProjectEntity {project_id: $pid}) RETURN n",
                pid=project_id,
            )
            nodes_raw = [dict(r["n"]) for r in node_result]
            if not nodes_raw:
                return None

            edge_result = s.run(
                "MATCH (a:ProjectEntity {project_id: $pid})-[r]->(b:ProjectEntity {project_id: $pid}) "
                "WHERE r:CONTAINS OR r:CALLS OR r:INHERITS "
                "RETURN a.entity_id AS source, b.entity_id AS target, type(r) AS type, "
                "r.line AS line, r.resolved AS resolved",
                pid=project_id,
            )
            # 必须在 session 块内物化 result，否则 session 关闭后迭代抛 ResultConsumedError
            edges_raw = [dict(r) for r in edge_result]

        nodes = []
        for n in nodes_raw:
            # 还原 JSON 字符串字段
            props = dict(n)
            for k in ("params", "external_calls"):
                v = props.get(k)
                if isinstance(v, str):
                    try:
                        props[k] = json.loads(v)
                    except (ValueError, TypeError):
                        props[k] = []
            nodes.append({
                "id": props.get("entity_id"),
                "label": props.get("name"),
                "group": props.get("kind"),
                "layer": props.get("layer"),
                "properties": props,
            })

        edges = []
        for r in edges_raw:
            edge = {
                "source": r["source"],
                "target": r["target"],
                "label": r["type"],
            }
            if r["type"] == "CALLS":
                edge["line"] = r["line"]
                edge["resolved"] = r["resolved"]
            edges.append(edge)

        return {"project_id": project_id, "nodes": nodes, "edges": edges}

    def delete_project_graph(self, project_id: str) -> int:
        """删除项目图谱，返回删除节点数。"""
        with self.driver.session() as s:
            result = s.run(
                "MATCH (n:ProjectEntity {project_id: $pid}) DETACH DELETE n "
                "RETURN count(n) AS c",
                pid=project_id,
            )
            record = result.single()
            return record["c"] if record else 0

    # --- 下一批 (code_tester / reviewer) 预留接口: 本批已实现 Cypher，供直接调用 ---

    def annotate_risk(self, entity_id: str, risk_level: str, reason: str) -> None:
        """[W6 batch2] code_tester 反向标注风险节点: SET 风险等级/原因。

        Args:
            entity_id: ProjectEntity entity_id
            risk_level: high|medium|low
            reason: 风险原因 (供前端展示 + 学习建议)
        """
        valid_levels = {"high", "medium", "low"}
        if risk_level not in valid_levels:
            raise ValueError(f"risk_level 无效 '{risk_level}' (有效: {valid_levels})")
        from datetime import datetime, timezone
        at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self.driver.session() as s:
            s.run(
                "MATCH (n:ProjectEntity {entity_id: $eid}) "
                "SET n.risk_level = $level, n.risk_reason = $reason, n.risk_annotated_at = $at",
                eid=entity_id, level=risk_level, reason=reason, at=at,
            )

    def link_entity_to_knowledge(self, entity_id: str, knowledge_node_id: str) -> None:
        """[W6 batch2] 代码实体 → 领域知识点 PY-xxx: MERGE RELATED_TO (跨层语义关联)。

        第3层代码实体 → 第1层领域元知识，供 reviewer 图谱校验 / code_tester 风险节点
        反向关联学习资源。
        """
        with self.driver.session() as s:
            s.run(
                "MATCH (e:ProjectEntity {entity_id: $eid}) "
                "MATCH (k:KnowledgeNode {id: $kid}) "
                "MERGE (e)-[:RELATED_TO]->(k)",
                eid=entity_id, kid=knowledge_node_id,
            )

    # ============================================================
    # 知识库 CRUD 写方法 (KB 管理 API 用; JSON 为源, 此处同步 Neo4j)
    # ============================================================

    def upsert_knowledge_node(self, node: dict) -> None:
        """创建或更新知识节点到 Neo4j (幂等 upsert)。

        - MERGE 节点 (按 id) + SET 全属性
        - 重建 REQUIRES 关系 (删旧出边 + 建新, execute_write 单事务原子)
        - 重建 BELONGS_TO (Category 节点 MERGE)
        字段存储对齐 import 脚本: practice_questions 存 JSON 字符串,
        key_points/common_mistakes/tags 原生 list。
        """
        from datetime import datetime, timezone
        nid = node.get("id")
        if not nid:
            raise ValueError("节点缺 id")
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        params = {
            "id": nid,
            "name": node.get("name", ""),
            "difficulty": node.get("difficulty", 1),
            "category": node.get("category", ""),
            "summary": node.get("summary", ""),
            "key_points": node.get("key_points", []),
            "practice_questions": json.dumps(node.get("practice_questions", []), ensure_ascii=False),
            "common_mistakes": node.get("common_mistakes", []),
            "tags": node.get("tags", []),
            "estimated_minutes": node.get("estimated_minutes", 10),
            "created_at": node.get("created_at") or now,
            "updated_at": now,
        }
        prereqs = node.get("prerequisites", []) or []

        def _tx_fn(tx):
            # 1. upsert 节点属性
            tx.run(
                "MERGE (n:KnowledgeNode {id: $id}) "
                "SET n += $props",
                id=nid, props=params,
            )
            # 2. Category + BELONGS_TO
            if params["category"]:
                tx.run("MERGE (c:Category {name: $name})", name=params["category"])
                tx.run(
                    "MATCH (n:KnowledgeNode {id: $id}), (c:Category {name: $cat}) "
                    "MERGE (n)-[:BELONGS_TO]->(c)",
                    id=nid, cat=params["category"],
                )
            # 3. 重建 REQUIRES 出边: 删旧 + 建新 (原子, 参考 write_project_graph B3)
            tx.run(
                "MATCH (n:KnowledgeNode {id: $id})-[r:REQUIRES]->() DELETE r",
                id=nid,
            )
            for parent_id in prereqs:
                tx.run(
                    "MATCH (a:KnowledgeNode {id: $child}), (b:KnowledgeNode {id: $parent}) "
                    "MERGE (a)-[:REQUIRES]->(b)",
                    child=nid, parent=parent_id,
                )

        with self.driver.session() as s:
            s.execute_write(_tx_fn)

    def delete_knowledge_node(self, node_id: str) -> int:
        """删除知识节点 (DETACH DELETE 连带关系)。返回删除节点数 (0=不存在)。"""
        with self.driver.session() as s:
            result = s.run(
                "MATCH (n:KnowledgeNode {id: $id}) DETACH DELETE n RETURN count(n) AS c",
                id=node_id,
            )
            record = result.single()
            return record["c"] if record else 0

    def get_question(self, qid: str) -> Optional[dict]:
        """按 qid 查单题 (CRUD 读用)。无则 None。"""
        with self.driver.session() as s:
            result = s.run(
                "MATCH (q:Question {qid: $qid}) RETURN q",
                qid=qid,
            )
            record = result.single()
            if record is None:
                return None
            return self._question_from_record(record["q"])

    def upsert_question(self, question: dict) -> None:
        """创建或更新题目 (幂等 upsert Question + HAS_QUESTION)。

        options 存原生 list (choice) / 空 list (fill/code)。
        Neo4j :Question 不存 node_id (与 import 一致, engine 读时注入)。
        """
        from datetime import datetime, timezone
        qid = question.get("qid")
        source = question.get("source_node_id")
        if not qid or not source:
            raise ValueError("题目缺 qid 或 source_node_id")
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        opts = question.get("options", [])
        if not isinstance(opts, list):
            opts = []
        params = {
            "qid": qid,
            "source_node_id": source,
            "type": question.get("type", ""),
            "question": question.get("question", ""),
            "options": opts,
            "answer": question.get("answer", ""),
            "difficulty": question.get("difficulty", 1),
            "hint": question.get("hint", ""),
            "explanation": question.get("explanation", ""),
            "created_at": question.get("created_at") or now,
            "updated_at": now,
        }

        def _tx_fn(tx):
            tx.run(
                "MERGE (q:Question {qid: $qid}) SET q += $props",
                qid=qid, props=params,
            )
            tx.run(
                "MATCH (n:KnowledgeNode {id: $source}), (q:Question {qid: $qid}) "
                "MERGE (n)-[:HAS_QUESTION]->(q)",
                source=source, qid=qid,
            )

        with self.driver.session() as s:
            s.execute_write(_tx_fn)

    def delete_question(self, qid: str) -> int:
        """删除题目 (DETACH DELETE)。返回删除数 (0=不存在)。"""
        with self.driver.session() as s:
            result = s.run(
                "MATCH (q:Question {qid: $qid}) DETACH DELETE q RETURN count(q) AS c",
                qid=qid,
            )
            record = result.single()
            return record["c"] if record else 0

    def get_questions_by_node(self, node_id: str) -> list[dict]:
        """查某节点的全部题目 (cascade 删除/查询用, 不限题型)。"""
        with self.driver.session() as s:
            result = s.run(
                "MATCH (n:KnowledgeNode {id: $nid})-[:HAS_QUESTION]->(q:Question) "
                "RETURN q",
                nid=node_id,
            )
            return [self._question_from_record(r["q"]) for r in result]
