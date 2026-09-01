"""
KMatch 后端全局配置
从环境变量和 .env 文件加载
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载项目根目录的 .env
load_dotenv(Path(__file__).parent.parent.parent / ".env")


class Settings:
    # --- 应用 ---
    APP_NAME: str = "KMatch·知链 API"
    APP_VERSION: str = "1.3.1"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # --- Neo4j ---
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "kmatch2026")

    # --- 图存储后端 (端用户免 Docker, 见 架构与设计/轻量化改造方案_免Docker_嵌入式存储.md) ---
    # neo4j   : 现有 Neo4j 后端 (开发/演示默认, 保测试零漂移)
    # embedded: 进程内 JSON 存储 (无 Docker/JVM/端口, 安装包端用户默认; run_server frozen 态翻此值)
    # auto    : 探测 Neo4j 可达用 neo4j, 否则 embedded (零配置开发)
    GRAPH_STORE: str = os.getenv("GRAPH_STORE", "neo4j")

    # --- LLM ---
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "sk-placeholder")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-v4-pro")
    # Agent 生成统一输出上限 (长讲义/实操/测试题不再被厂商默认 8K 拦腰截断)
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "16384"))

    # --- 独立裁判 LLM (M5 质检升级: 与主 LLM 不同源, 提升指标可信度) ---
    # 留空则回退主 LLM (报告标注 same_source=True 诚实降级)
    JUDGE_LLM_API_KEY: str = os.getenv("JUDGE_LLM_API_KEY", "")
    JUDGE_LLM_BASE_URL: str = os.getenv("JUDGE_LLM_BASE_URL", "")
    JUDGE_LLM_MODEL: str = os.getenv("JUDGE_LLM_MODEL", "")

    # --- Embedding ---
    # 独立配置，如未设置则 fallback 到 LLM_* 的值
    EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", "") or os.getenv("LLM_API_KEY", "sk-placeholder")
    EMBEDDING_BASE_URL: str = os.getenv("EMBEDDING_BASE_URL", "") or os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v2")
    EMBEDDING_DIMENSIONS: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
    VECTOR_INDEX_NAME: str = os.getenv("VECTOR_INDEX_NAME", "knowledge_embeddings")

    # --- Agent ---
    MAX_RETRY_ROUNDS: int = 3
    LLM_TIMEOUT: int = 60
    LLM_TEMPERATURE: float = 0.3
    REVIEW_PASS_THRESHOLD: float = float(os.getenv("REVIEW_PASS_THRESHOLD", "0.85"))
    CONTENT_GEN_CONCURRENCY: int = int(os.getenv("CONTENT_GEN_CONCURRENCY", "5"))

    # --- 联网搜索 (Tavily, 学情反馈搜薄弱知识点相关网站) ---
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

    # --- 沙箱 (code_test) ---
    # sandbox=auto: Docker 可用则用 DockerSandboxExecutor (--network=none --memory 限内存),
    # 否则回退 SubprocessSandboxExecutor (诚实限制: 无法禁网/限内存, 仅 env 白名单 + AST 预检)。
    # sandbox=subprocess 强制子进程; sandbox=docker 强制 Docker (不可用则报错)。
    SANDBOX_MODE: str = os.getenv("SANDBOX_MODE", "auto")
    SANDBOX_DOCKER_IMAGE: str = os.getenv("SANDBOX_DOCKER_IMAGE", "kmatch-sandbox:latest")
    SANDBOX_MEMORY: str = os.getenv("SANDBOX_MEMORY", "512m")
    SANDBOX_CPUS: str = os.getenv("SANDBOX_CPUS", "1")

    # --- CORS ---
    CORS_ORIGINS: list = [
        o.strip() for o in
        os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
        if o.strip()
    ]

    # --- Paths ---
    # 打包后由 run_server.py 设 KMATCH_DATA_DIR 指向 resources/data (extraResources);
    # 开发期 fallback 到 repo_root/data (config.py 在 backend/app/)。
    _data_dir_env = os.getenv("KMATCH_DATA_DIR")
    DATA_DIR: Path = Path(_data_dir_env) if _data_dir_env else Path(__file__).parent.parent.parent / "data"
    KB_DIR: Path = DATA_DIR / "knowledge_base"  # 供 scripts/ 引用知识库路径

    # 嵌入式存储可变数据 (掌握状态/项目图谱/向量缓存) 目录 — ADR-0008
    # 安装包 resources/data 只读, 打包态由 Electron sidecar 注入 KMATCH_LOCAL_DIR 到用户
    # appData 可写目录; 开发态 fallback 到 DATA_DIR/local.
    _local_env = os.getenv("KMATCH_LOCAL_DIR")
    LOCAL_DIR: Path = Path(_local_env) if _local_env else DATA_DIR / "local"


settings = Settings()
