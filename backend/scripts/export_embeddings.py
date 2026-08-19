"""
导出 Neo4j 中的节点 embedding 为离线种子 data/local/embeddings.json (ADR-0008 §4.4 可选增强)。

价值: 安装包打上离线种子后, 端用户首跑即语义检索可用 (省去首次自动回填 222+ 节点的 token 与等待;
注意: 每次查询仍用云端 embedding 编码 query, 见 embedded.semantic_ready 诚实语义注释)。

用法 (需 Neo4j 已导入并已向量化, 先 GRAPH_STORE=neo4j 跑 import + generate_embeddings):
    python scripts/export_embeddings.py [output.json]
    # 默认写到 settings.LOCAL_DIR/embeddings.json (打包前运行, electron-builder 会把 data/local 打进 resources)
"""

import json
import os
import sys
from pathlib import Path

from neo4j import GraphDatabase

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def fetch_embeddings(uri: str, user: str, password: str) -> dict:
    """从 Neo4j 读取全部 KnowledgeNode 的 embedding → {node_id: [..]} (仅含向量的节点)。"""
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
        with driver.session() as s:
            result = s.run(
                "MATCH (n:KnowledgeNode) WHERE n.embedding IS NOT NULL "
                "RETURN n.id AS id, n.embedding AS emb"
            )
            return {r["id"]: r["emb"] for r in result}
    finally:
        driver.close()


def write_seed(items: dict, out: Path, model: str = None) -> Path:
    """原子写种子文件 (临时文件 + os.replace, 与 embedded._atomic_write 一致)。"""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {"model": model or settings.EMBEDDING_MODEL, "items": items}
    tmp = out.with_name(f".{out.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, out)
    return out


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else settings.LOCAL_DIR / "embeddings.json"
    items = fetch_embeddings(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    if not items:
        print("⚠️ 未从 Neo4j 找到带 embedding 的节点 — 请先 import_knowledge_base.py 导入并 generate_embeddings")
        sys.exit(1)
    write_seed(items, out)
    print(f"✅ 导出 {len(items)} 个节点向量 → {out}")
