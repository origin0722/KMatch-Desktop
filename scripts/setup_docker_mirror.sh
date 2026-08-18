#!/usr/bin/env bash
# ============================================================
# setup_docker_mirror.sh — 配置 Docker Hub 国内镜像源 (Linux/macOS Docker Engine)
# ============================================================
# 用法: sudo bash scripts/setup_docker_mirror.sh
# 幂等; 已有 /etc/docker/daemon.json 的其它配置保留, 仅覆盖 registry-mirrors。
set -euo pipefail

DAEMON="${DOCKER_DAEMON_JSON:-/etc/docker/daemon.json}"
MIRRORS='["https://docker.m.daocloud.io","https://docker.1panel.live","https://hub.rat.dev"]'

if [ -f "$DAEMON" ]; then
  python3 - "$DAEMON" "$MIRRORS" <<'PY'
import json, sys
path, mirrors = sys.argv[1], json.loads(sys.argv[2])
with open(path, encoding="utf-8") as f:
    cfg = json.load(f)
cfg["registry-mirrors"] = mirrors
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
PY
else
  echo "{\"registry-mirrors\": $MIRRORS}" | sudo tee "$DAEMON" >/dev/null
fi

echo "[ok] 镜像源已写入 $DAEMON"
echo "    请执行: sudo systemctl restart docker"
echo "    验证: docker pull neo4j:5-community"
