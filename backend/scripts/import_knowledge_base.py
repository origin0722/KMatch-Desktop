#!/usr/bin/env python3
"""
KMatch 元知识库 Neo4j 导入脚本 v2
用法: python import_knowledge_base.py <knowledge_base_dir>
功能:
  1. 加载所有知识节点 JSON
  2. 连接 Neo4j 并导入
  3. 创建 KNOWLEDGE_NODE 节点及 REQUIRES 关系
  4. 创建 BELONGS_TO 分类关系
  5. 输出导入统计
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

# 确保 backend/ 在 sys.path 中（脚本直接运行时也能导入 app 模块）
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from neo4j import GraphDatabase, exceptions
except ImportError:
    print("❌ 请先安装 neo4j 驱动: pip install neo4j")
    sys.exit(1)


# ============================================================
# 配置
# ============================================================

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "kmatch2026")


# ============================================================
# 数据加载
# ============================================================

def load_json_files(base_dir: Path) -> list[dict]:
    """递归加载所有 JSON 文件中的节点 (排除 schema.json 和 questions/ 题目文件)"""
    nodes = []
    schema_file = base_dir / "schema.json"
    questions_dir = base_dir / "questions"
    for file_path in base_dir.glob("**/*.json"):
        if file_path == schema_file:
            continue
        # 题目独立文件 (questions/<node_id>.json) 不作为知识节点加载
        if questions_dir in file_path.parents:
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                nodes.extend(data)
            elif isinstance(data, dict) and "id" in data:
                nodes.append(data)
        except json.JSONDecodeError as e:
            print(f"⚠️  跳过无效 JSON: {file_path} ({e})")
    return nodes


def load_questions(base_dir: Path) -> list[dict]:
    """加载 questions/ 目录下所有题目 (独立 :Question 节点数据源)

    递归 rglob: 支持分域子目录 (questions/ML|DA|WD|DB/EN/)。
    兼容 list(一文件多题, PY 惯例) 与单 dict(一文件一题, ML 惯例) 两种形态。
    """
    questions_dir = base_dir / "questions"
    if not questions_dir.is_dir():
        return []
    all_q = []
    for file_path in sorted(questions_dir.rglob("*.json")):
        # 跳过 questions/schema.json (题目结构规范文档, 非题目数据)
        if file_path.name == "schema.json":
            continue
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                all_q.extend(data)
            elif isinstance(data, dict) and "qid" in data:
                all_q.append(data)
        except Exception as e:
            print(f"⚠️  跳过题目文件 {file_path}: {e}")
    return all_q


# ============================================================
# Cypher 查询
# ============================================================

CONSTRAINTS = [
    "CREATE CONSTRAINT kb_unique_id IF NOT EXISTS FOR (n:KnowledgeNode) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT kb_cat_name IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT q_unique_id IF NOT EXISTS FOR (q:Question) REQUIRE q.qid IS UNIQUE",
    # Question 索引: 支撑按 source_node_id/type/difficulty 高效检索 (题库驱动出题)
    "CREATE INDEX q_source IF NOT EXISTS FOR (q:Question) ON (q.source_node_id)",
    "CREATE INDEX q_type IF NOT EXISTS FOR (q:Question) ON (q.type)",
    "CREATE INDEX q_difficulty IF NOT EXISTS FOR (q:Question) ON (q.difficulty)",
]

# 清知识节点 + 题目节点 (DETACH DELETE 一并清关系)
CLEAR_ALL = "MATCH (n) WHERE n:KnowledgeNode OR n:Question DETACH DELETE n"

CREATE_NODE = """
CREATE (n:KnowledgeNode {
    id: $id,
    name: $name,
    difficulty: $difficulty,
    category: $category,
    summary: $summary,
    key_points: $key_points,
    practice_questions: $practice_questions,
    common_mistakes: $common_mistakes,
    tags: $tags,
    estimated_minutes: $estimated_minutes,
    created_at: $created_at
})
RETURN n
"""

CREATE_QUESTION = """
CREATE (q:Question {
    qid: $qid,
    source_node_id: $source_node_id,
    type: $type,
    question: $question,
    options: $options,
    answer: $answer,
    difficulty: $difficulty,
    hint: $hint,
    explanation: $explanation,
    created_at: $created_at
})
RETURN q
"""

LINK_QUESTION = """
MATCH (n:KnowledgeNode {id: $source_node_id})
MATCH (q:Question {qid: $qid})
MERGE (n)-[:HAS_QUESTION]->(q)
"""

CREATE_PREREQ = """
MATCH (a:KnowledgeNode {id: $child_id})
MATCH (b:KnowledgeNode {id: $parent_id})
MERGE (a)-[:REQUIRES]->(b)
"""

CREATE_BELONGS = """
MATCH (n:KnowledgeNode {id: $id})
MATCH (c:Category {name: $category})
MERGE (n)-[:BELONGS_TO]->(c)
"""

CREATE_CATEGORY = """
MERGE (c:Category {name: $name})
RETURN c
"""


class Neo4jImporter:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def test(self) -> bool:
        try:
            self.driver.verify_connectivity()
            return True
        except Exception as e:
            print(f"❌ Neo4j 连接失败: {e}")
            return False

    def clear(self):
        print("🗑️  清空已有 KnowledgeNode 节点...")
        with self.driver.session() as s:
            s.run(CLEAR_ALL)
        print("   已清空")

    def setup_constraints(self):
        print("🔧 创建约束...")
        with self.driver.session() as s:
            for q in CONSTRAINTS:
                s.run(q)
        print("   就绪")

    def import_nodes(self, nodes: list[dict]) -> dict:
        stats = {"success": 0, "failed": 0, "categories": set()}
        created_at = datetime.now().isoformat()

        with self.driver.session() as s:
            for node in nodes:
                try:
                    nid = node["id"]
                    params = {
                        "id": nid,
                        "name": node["name"],
                        "difficulty": node.get("difficulty", 1),
                        "category": node.get("category", ""),
                        "summary": node.get("summary", ""),
                        "key_points": node.get("key_points", []),
                        "practice_questions": json.dumps(
                            node.get("practice_questions", []),
                            ensure_ascii=False,
                        ),
                        # common_mistakes 原生 list (Neo4j 支持 list[str])，5处运行时消费点直接 .get 拿 list
                        "common_mistakes": node.get("common_mistakes", []),
                        "tags": node.get("tags", []),
                        "estimated_minutes": node.get("estimated_minutes", 10),
                        "created_at": created_at,
                    }

                    s.run(CREATE_NODE, params)
                    s.run(CREATE_CATEGORY, {"name": node["category"]})
                    s.run(CREATE_BELONGS, {"id": nid, "category": node["category"]})
                    stats["categories"].add(node["category"])
                    stats["success"] += 1
                    print(f"   ✅ {nid}: {node['name']}")

                except exceptions.ConstraintError:
                    print(f"   ⚠️  {node.get('id', '?')}: 已存在，跳过")
                    stats["failed"] += 1
                except Exception as e:
                    print(f"   ❌ {node.get('id', '?')}: {e}")
                    stats["failed"] += 1

        return stats

    def import_relationships(self, nodes: list[dict]) -> int:
        count = 0
        with self.driver.session() as s:
            for node in nodes:
                nid = node.get("id")
                for prereq_id in node.get("prerequisites", []):
                    try:
                        s.run(CREATE_PREREQ, {"child_id": nid, "parent_id": prereq_id})
                        count += 1
                        print(f"   🔗 {nid} -[:REQUIRES]-> {prereq_id}")
                    except Exception as e:
                        print(f"   ⚠️  关系失败 {nid}->{prereq_id}: {e}")
        return count

    def import_questions(self, questions: list[dict]) -> dict:
        """导入题目为独立 :Question 节点 + :HAS_QUESTION 关系。

        options 存原生 list (choice 题); common_mistakes 类似,Neo4j 支持 list[str]。
        """
        stats = {"success": 0, "failed": 0}
        created_at = datetime.now().isoformat()
        with self.driver.session() as s:
            for q in questions:
                try:
                    qid = q["qid"]
                    params = {
                        "qid": qid,
                        "source_node_id": q.get("source_node_id", ""),
                        "type": q.get("type", ""),
                        "question": q.get("question", ""),
                        # options 原生 list (choice); 非 choice 题存空 list
                        "options": q.get("options", []) if isinstance(q.get("options"), list) else [],
                        "answer": q.get("answer", ""),
                        "difficulty": q.get("difficulty", 1),
                        "hint": q.get("hint", ""),
                        "explanation": q.get("explanation", ""),
                        "created_at": created_at,
                    }
                    s.run(CREATE_QUESTION, params)
                    s.run(LINK_QUESTION, {"source_node_id": params["source_node_id"], "qid": qid})
                    stats["success"] += 1
                except Exception as e:
                    print(f"   ❌ 题目 {q.get('qid', '?')}: {e}")
                    stats["failed"] += 1
        return stats

    def verify(self, expected: int) -> bool:
        with self.driver.session() as s:
            result = s.run("MATCH (n:KnowledgeNode) RETURN count(n) AS cnt")
            actual = result.single()["cnt"]
            print(f"\n🔍 验证: 数据库 {actual} 节点 (期望 {expected})")
            return actual == expected


# ============================================================
# 主流程
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("用法: python import_knowledge_base.py <knowledge_base_dir>")
        sys.exit(1)

    base_dir = Path(sys.argv[1])
    if not base_dir.exists():
        print(f"❌ 目录不存在: {base_dir}")
        sys.exit(1)

    print("=" * 60)
    print("  KMatch 元知识库 → Neo4j 导入 v2")
    print("=" * 60)
    print(f"\n📂 {base_dir}")
    print(f"🔗 {NEO4J_URI}")

    nodes = load_json_files(base_dir)
    if not nodes:
        print("❌ 未找到任何节点！")
        sys.exit(1)
    print(f"📥 加载 {len(nodes)} 个节点")

    importer = Neo4jImporter(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    if not importer.test():
        print("\n💡 请确保 Neo4j 已启动: docker-compose up -d neo4j")
        sys.exit(1)
    print("✅ Neo4j 已连接")

    importer.clear()
    importer.setup_constraints()

    print(f"\n📤 导入节点...")
    stats = importer.import_nodes(nodes)

    print(f"\n🔗 导入依赖关系...")
    rel_count = importer.import_relationships(nodes)

    # 导入题目 (独立 :Question 节点 + :HAS_QUESTION 关系)
    questions = load_questions(base_dir)
    q_stats = {"success": 0, "failed": 0}
    if questions:
        print(f"\n📝 导入题目 ({len(questions)} 道)...")
        q_stats = importer.import_questions(questions)

    importer.verify(stats["success"])

    print(f"\n{'=' * 60}")
    print(f"  导入完成！")
    print(f"  节点: {stats['success']} 成功 / {stats['failed']} 失败")
    print(f"  关系: {rel_count} 条")
    print(f"  题目: {q_stats['success']} 成功 / {q_stats['failed']} 失败")
    print(f"  分类: {len(stats['categories'])} 个 — {', '.join(sorted(stats['categories']))}")
    print(f"{'=' * 60}")

    # --- 向量索引 & embedding ---
    print(f"\n🔧 初始化向量索引...")
    try:
        from app.graph.engine import KnowledgeGraph

        kg = KnowledgeGraph(
            uri=NEO4J_URI,
            user=NEO4J_USER,
            password=NEO4J_PASSWORD,
        )

        kg.setup_vector_index()

        emb_client = KnowledgeGraph.create_embedding_client()
        if emb_client:
            kg.embedding_client = emb_client
            print(f"📊 生成知识节点 embedding（模型: {kg.embedding_model}）...")
            kg.generate_embeddings(nodes)
        else:
            print("⚠️  Embedding 未配置或不可用，跳过向量生成（语义检索将降级为纯图模式）")

        kg.close()

    except ImportError as e:
        print(f"⚠️  缺少依赖，跳过向量步骤: {e}")
    except Exception as e:
        print(f"⚠️  向量初始化异常（非阻塞）: {e}")

    importer.close()
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
