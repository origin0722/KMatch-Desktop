"""
KMatch 后端 FastAPI 入口

第1周: 骨架版 — 验证 FastAPI + LangGraph + Neo4j 集成
第2—4周: 逐步填充 Agent 节点和业务路由
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

# 将 backend 加入路径（方便脚本单独运行时导入）
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.graph.engine import KnowledgeGraph
from app.agents.orchestrator import build_workflow
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _build_store(embedding_client=None):
    """按 GRAPH_STORE 选择图存储后端 (端用户免 Docker: embedded 进程内 JSON 存储)。

    模式: embedded(安装包默认, 无 Docker/JVM/端口) / neo4j(开发/演示默认, 保测试零漂移)
          / auto(探测 Neo4j 可达则 neo4j, 否则 embedded)。
    """
    from app.graph.embedded import EmbeddedGraphStore

    mode = settings.GRAPH_STORE
    if mode == "embedded":
        logger.info("✅ 图存储: 嵌入式后端已就绪 (无 Docker/JVM/端口)")
        return EmbeddedGraphStore(embedding_client=embedding_client)
    if mode == "neo4j":
        store = KnowledgeGraph.from_settings(embedding_client=embedding_client)
        if store.test_connection():
            logger.info("✅ 图存储: Neo4j 已连接")
            return store
        logger.warning("⚠️ Neo4j 不可达，知识图谱引擎未就绪，业务路由将返回 503")
        store.close()
        return None
    # auto: Neo4j 可达 → neo4j, 否则嵌入式
    probe = KnowledgeGraph.from_settings(embedding_client=embedding_client)
    if probe.test_connection():
        logger.info("✅ 图存储: Neo4j 已连接 (auto)")
        return probe
    probe.close()
    logger.info("✅ 图存储: Neo4j 不可达，已切换嵌入式后端 (auto)")
    return EmbeddedGraphStore(embedding_client=embedding_client)

# ============================================================
# Lifespan: 全局 KnowledgeGraph 单例 (BUG-011 修复)
# ============================================================
# 第1周 health check 每次请求都新建 Neo4j 连接。引入 lifespan 在启动时创建
# 全局 KG 单例，health check 与业务路由共享，避免反复建连。


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期: 启动时创建全局单例 (KG + OpenAI)，关闭时释放连接。"""
    # --- 图存储后端单例 (Neo4j / 嵌入式, 按 GRAPH_STORE) ---
    # 接入 embedding 客户端：未配置或探测失败时返回 None（语义检索降级为纯图模式）
    embedding_client = KnowledgeGraph.create_embedding_client()
    if embedding_client is not None:
        logger.info("✅ Embedding 客户端已创建（%s），向量检索可用", settings.EMBEDDING_MODEL)
    else:
        logger.warning("⚠️ Embedding 客户端未就绪，语义/混合检索将降级为纯图模式")

    kg = _build_store(embedding_client)
    app.state.kg = kg

    # --- OpenAI 客户端单例 (BUG-011 同类: 避免 health check 反复建连) ---
    if settings.LLM_API_KEY not in ("", "sk-placeholder"):
        from openai import OpenAI
        app.state.openai_client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
        logger.info("✅ OpenAI 客户端已创建 (%s)", settings.LLM_MODEL)
    else:
        app.state.openai_client = None
        logger.warning("⚠️ LLM API Key 未配置，OpenAI 客户端未就绪")

    # --- LangGraph Workflow 单例 (避免每次 API 请求重复编译图 + MemorySaver 可跨请求复用) ---
    if app.state.kg is not None:
        app.state.workflow = build_workflow(app.state.kg)
        logger.info("✅ LangGraph 多 Agent 工作流已编译（MemorySaver checkpointer）")
    else:
        app.state.workflow = None
        logger.warning("⚠️ KG 未就绪，工作流跳过编译")

    yield

    # 关闭连接
    if app.state.kg is not None:
        app.state.kg.close()
        logger.info("KnowledgeGraph 连接已关闭")
    # OpenAI 客户端由 urllib3 连接池自动管理，无需显式 close()


# ============================================================
# FastAPI 应用初始化
# ============================================================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="知识图谱驱动的多智能体协同个性化学习平台",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# --- CORS 配置 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 健康检查
# ============================================================

@app.get("/api/health", tags=["System"])
async def health_check():
    """系统健康检查 — 复用全局 KnowledgeGraph 单例 (BUG-011)"""
    checks = {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }

    # Neo4j/嵌入式连通性检查（复用 lifespan 创建的全局单例，不再每次新建连接）
    kg = getattr(app.state, "kg", None)
    if kg is not None and kg.test_connection():
        checks["neo4j"] = "connected"
        checks["graph_store"] = getattr(kg, "kind", "neo4j")
        checks["semantic_search"] = "ready" if getattr(kg, "semantic_ready", False) else "degraded"
    else:
        checks["neo4j"] = "unavailable (global singleton not ready)"
        checks["graph_store"] = "none"
        checks["semantic_search"] = "unavailable"

    # LLM API 连通性检查（复用 lifespan 创建的全局 OpenAI 客户端，不再每次建连 — BUG-011 同类）
    openai_client = getattr(app.state, "openai_client", None)
    if openai_client is not None:
        try:
            # 轻量测试: 列出模型
            openai_client.models.list()
            checks["llm_api"] = f"connected ({settings.LLM_MODEL})"
        except Exception as e:
            checks["llm_api"] = f"unavailable: {str(e)[:100]}"
    else:
        checks["llm_api"] = "not configured (sk-placeholder)"

    return checks


# ============================================================
# Router 注册（逐周添加）
# ============================================================

# 第1周: 骨架路由
@app.get("/api/version", tags=["System"])
async def get_version():
    import langgraph
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "langgraph": getattr(langgraph, "__version__", "unknown"),
        "neo4j": "5.x",
    }


# 第2周: 学情检测→审核局部流程
from app.api import diagnostics  # noqa: E402

app.include_router(diagnostics.router, prefix="/api/diagnostics", tags=["Diagnostics"])

# 第3周: 知识图谱查询 + 学习路径组装
from app.api import graph  # noqa: E402

app.include_router(graph.router, prefix="/api/graph", tags=["Graph"])

# 第6周: 项目代码解析 + 项目图谱 (四层图谱第2/3层)
from app.api import project  # noqa: E402

app.include_router(project.router, prefix="/api/project", tags=["Project"])

# W7②: 可视化报告 (interactive 补跑路径+内容+审核，返回三类可视化数据)
from app.api import learning  # noqa: E402

app.include_router(learning.router, prefix="/api/learning", tags=["Learning"])

# W7③: 知识库管理 CRUD (节点 + 题目; JSON 为源写后同步 Neo4j)
from app.api import kb  # noqa: E402

app.include_router(kb.router, prefix="/api/kb", tags=["知识库管理"])

# 阶段2: AI 助手对话 (SSE 流式, 复用 OpenAI 客户端单例)
from app.api import chat  # noqa: E402

app.include_router(chat.router, prefix="/api/chat", tags=["AI 助手"])

# Spec B: Agent 学习引擎 (测试连接 ping)
from app.api import agents  # noqa: E402

app.include_router(agents.router, prefix="/api/agents", tags=["Agent 学习引擎"])

# 联网搜索 (Tavily, AI 助手 web_search 工具调用, 结果落学习资源模块)
from app.api import search  # noqa: E402

app.include_router(search.router, prefix="/api/search", tags=["Search"])


# ============================================================
# 直接运行入口
# ============================================================

if __name__ == "__main__":
    import os
    import uvicorn
    print(f"🚀 启动 {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"   📖 API 文档: http://localhost:8000/api/docs")
    print(f"   ❤️  健康检查: http://localhost:8000/api/health")
    # issue-45: 默认只绑本机 (127.0.0.1), 防局域网被当开放代理;
    # 容器/需要被外部访问时设 KMATCH_HOST=0.0.0.0
    uvicorn.run(
        "app.main:app",
        host=os.getenv("KMATCH_HOST", "127.0.0.1"),
        port=8000,
        reload=settings.DEBUG,
    )
