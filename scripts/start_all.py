"""KMatch 桌面版一键启动脚本。

编排: Docker Neo4j → 等就绪 → 首次自动导入知识库 → 提示起后端/Electron。
开发期用: python scripts/start_all.py

设计: Neo4j 用 Docker(图谱引擎不重写, 保赛题后端资产); 后端 uvicorn; 前端 vite。
安全: subprocess 只用字面量参数列表 (shell=False), 命令不拼接任何变量;
     Neo4j 密码从环境变量/.env 读取 (cp .env.example .env), 经容器环境变量
     透传 (-e NAME), 不出现在命令行参数里。
"""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
DATA = ROOT / "data"

NEO4J_CONTAINER = "kmatch-desktop-neo4j"


def neo4j_password():
    """从环境变量或仓库 .env 读取 Neo4j 密码 (与 backend/app/config.py 同一真相源)。"""
    pw = os.getenv("NEO4J_PASSWORD")
    if pw:
        return pw
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("NEO4J_PASSWORD="):
                return line.split("=", 1)[1].strip()
    return None


def docker_available():
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def neo4j_running():
    r = subprocess.run(
        ["docker", "ps", "--filter", "name=kmatch-desktop-neo4j", "--format", "{{.Status}}"],
        capture_output=True, text=True,
    )
    return "Up" in r.stdout


def start_neo4j(password):
    if neo4j_running():
        print(f"[OK] Neo4j 容器 {NEO4J_CONTAINER} 已在运行")
        return
    r = subprocess.run(["docker", "start", NEO4J_CONTAINER], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[INFO] 创建 Neo4j 容器 {NEO4J_CONTAINER}...")
        # -e NEO4J_AUTH (只写变量名) 由 docker 从本进程环境取值, 密码不进命令行
        subprocess.run(
            [
                "docker", "run", "-d", "--name", NEO4J_CONTAINER,
                "-p", "7474:7474", "-p", "7687:7687",
                "-e", "NEO4J_AUTH",
                "-v", str(DATA / "knowledge_base") + ":/import/knowledge_base:ro",
                "neo4j:5-community",
            ],
            check=True,
            env={**os.environ, "NEO4J_AUTH": "neo4j/" + password},
        )


def _cypher(password, query, timeout=None):
    """docker exec 执行 cypher: 密码经 -e NEO4J_PASSWORD 环境变量透传 (cypher-shell 原生支持)。"""
    return subprocess.run(
        ["docker", "exec", "-e", "NEO4J_PASSWORD", NEO4J_CONTAINER,
         "cypher-shell", "-u", "neo4j", "--format", "plain", query],
        capture_output=True, text=True, timeout=timeout,
        env={**os.environ, "NEO4J_PASSWORD": password},
    )


def wait_neo4j_ready(password, timeout=60):
    print("[INFO] 等待 Neo4j 就绪...", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = _cypher(password, "RETURN 1")
        except subprocess.TimeoutExpired:
            r = None
        if r is not None and r.returncode == 0:
            print(" OK")
            return True
        print(".", end="", flush=True)
        time.sleep(2)
    print(" 超时!")
    return False


def neo4j_has_data(password):
    r = _cypher(password, "MATCH (n:KnowledgeNode) RETURN count(n) AS c")
    for line in (r.stdout or "").split("\n"):
        s = line.strip()
        if s.isdigit() and int(s) > 0:
            return True
    return False


def main():
    print("=" * 50)
    print("KMatch 桌面版 一键启动")
    print("=" * 50)

    password = neo4j_password()
    if not password:
        print("[FAIL] 未找到 NEO4J_PASSWORD。请先: cp .env.example .env (或 set NEO4J_PASSWORD=...)")
        sys.exit(1)

    if not docker_available():
        print("[FAIL] Docker 未运行。请先启动 Docker Desktop。")
        sys.exit(1)

    start_neo4j(password)
    if not wait_neo4j_ready(password):
        print(f"[FAIL] Neo4j 启动超时, 请检查 docker logs {NEO4J_CONTAINER}")
        sys.exit(1)

    if neo4j_has_data(password):
        print("[OK] Neo4j 已有知识库数据, 跳过导入")
    else:
        print("[INFO] 首次启动, 需导入知识库:")
        print("  cd backend && python scripts/import_knowledge_base.py ../data/knowledge_base/")

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
