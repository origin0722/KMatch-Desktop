# KMatch code_test 沙箱镜像 (#15 DockerSandboxExecutor)
#
# 用途: code_test 工具在隔离容器内跑用户代码的 pytest (--network=none --memory 限内存/禁网)。
# 构建镜像后设 SANDBOX_DOCKER_IMAGE=kmatch-sandbox:latest (或自定义), SANDBOX_MODE=auto/docker。
#
# 构建 (在本目录):
#   docker build -t kmatch-sandbox:latest .
#
# 镜像只含 python + pytest + pytest-cov, 无网络访问 (--network=none), 不含任何项目密钥。

FROM python:3.12-slim

# pytest + 覆盖率 (沙箱内执行用户测试所需)
RUN pip install --no-cache-dir "pytest>=8.0" "pytest-cov>=4.1"

# 工作目录由 DockerSandboxExecutor 以 -v workdir:/work -w /work 挂载, 镜像内不预置代码
WORKDIR /work

# 容器内默认入口由 executor 显式传 python -m pytest ... 覆盖
CMD ["python", "-m", "pytest"]
