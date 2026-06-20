"""KMatch 桌面版一键启动脚本。

编排: Docker Neo4j → 等就绪 → 首次自动导入知识库 → 提示起后端/Electron。
开发期用: python scripts/start_all.py

设计: Neo4j 用 Docker(图谱引擎不重写, 保赛题后端资产); 后端 uvicorn; 前端 vite。
"""

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
DATA = ROOT / "data"

NEO4J_CONTAINER = "kmatch-desktop-neo4j"
NEO4J_PASSWORD = "kmatch2026"


def run(cmd, check=True):
    print(f"$ {cmd}")
    return subprocess.run(cmd, shell=True, check=check)


def docker_available():
    return subprocess.run("docker info", shell=True, capture_output=True).returncode == 0


def neo4j_running():
    r = subprocess.run(
        f'docker ps --filter name={NEO4J_CONTAINER} --format {{{{.Status}}}}',
        shell=True, capture_output=True, text=True,
    )
    return "Up" in r.stdout


def start_neo4j():
    if neo4j_running():
        print(f"[OK] Neo4j 容器 {NEO4J_CONTAINER} 已在运行")
        return
    r = subprocess.run(f"docker start {NEO4J_CONTAINER}", shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[INFO] 创建 Neo4j 容器 {NEO4J_CONTAINER}...")
        run(
            f'docker run -d --name {NEO4J_CONTAINER} '
            f'-p 7474:7474 -p 7687:7687 '
            f'-e NEO4J_AUTH=neo4j/{NEO4J_PASSWORD} '
            f'-v "{DATA}/knowledge_base:/import/knowledge_base:ro" '
            f'neo4j:5-community'
        )


def wait_neo4j_ready(timeout=60):
    print("[INFO] 等待 Neo4j 就绪...", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        r = subprocess.run(
            f'docker exec {NEO4J_CONTAINER} cypher-shell -u neo4j -p {NEO4J_PASSWORD} "RETURN 1"',
            shell=True, capture_output=True, text=True,
        )
        if r.returncode == 0:
            print(" OK")
            return True
        print(".", end="", flush=True)
        time.sleep(2)
    print(" 超时!")
    return False


def neo4j_has_data():
    r = subprocess.run(
        f'docker exec {NEO4J_CONTAINER} cypher-shell -u neo4j -p {NEO4J_PASSWORD} '
        f'"MATCH (n:KnowledgeNode) RETURN count(n) AS c"',
        shell=True, capture_output=True, text=True,
    )
    for line in r.stdout.split("\n"):
        s = line.strip()
        if s.isdigit() and int(s) > 0:
            return True
    return False


def main():
    print("=" * 50)
    print("KMatch 桌面版 一键启动")
    print("=" * 50)

    if not docker_available():
        print("[FAIL] Docker 未运行。请先启动 Docker Desktop。")
        sys.exit(1)

    start_neo4j()
    if not wait_neo4j_ready():
        print(f"[FAIL] Neo4j 启动超时, 请检查 docker logs {NEO4J_CONTAINER}")
        sys.exit(1)

    if neo4j_has_data():
        print("[OK] Neo4j 已有知识库数据, 跳过导入")
    else:
        print("[INFO] 首次启动, 需导入知识库:")
        print(f"  cd backend && python scripts/import_knowledge_base.py ../data/knowledge_base/")

    print()
    print("=" * 50)
    print("[OK] Neo4j 就绪 (7474/7687)")
    print()
    print("下一步 (新终端):")
    print("  1. 起后端:  cd backend && uvicorn app.main:app --port 8000")
    print("  2. 起前端+Electron: npm run electron:dev")
    print("     (或分别: cd frontend && npm run dev; npm start)")
    print("=" * 50)


if __name__ == "__main__":
    main()
