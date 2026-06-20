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
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # --- Neo4j ---
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "kmatch2026")

    # --- LLM ---
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "sk-placeholder")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-v4-pro")

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


settings = Settings()
