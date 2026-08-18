# ============================================================
# KMatch·知链 — FastAPI 后端镜像 (docker-compose backend 服务)
# ============================================================
# 构建: docker build -t kmatch-backend ./backend
# 运行态依赖 Neo4j (compose 里 neo4j 服务 + depends_on healthy), 环境变量见 docker-compose.yml
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    # 容器内必须绑 0.0.0.0 才能经 -p 端口映射对外;
    # 本地/桌面 sidecar 仍默认 127.0.0.1 (issue-45 安全默认)
    KMATCH_HOST=0.0.0.0

WORKDIR /app

# 依赖层 (利用构建缓存)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 源码层
COPY . .

EXPOSE 8000

# 数据目录缺省 /data (compose 挂载 ./data:/data:ro)
ENV KMATCH_DATA_DIR=/data

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
