# ============================================================
# setup_docker_mirror.ps1 — 配置 Docker Hub 国内镜像源 (国内网络拉取 neo4j:5-community 提速)
# ============================================================
# 用法: powershell -ExecutionPolicy Bypass -File scripts/setup_docker_mirror.ps1
# 说明: 把 registry-mirrors 写入 Docker Desktop 的 daemon.json 并提示重启生效;
#       幂等 (重复执行只覆盖镜像列表)。如已有其它 daemon.json 配置会被保留。
$ErrorActionPreference = 'Stop'

$daemon = Join-Path $env:ProgramData 'Docker\config\daemon.json'
$mirrors = @(
  'https://docker.m.daocloud.io',
  'https://docker.1panel.live',
  'https://hub.rat.dev'
)

if (-not (Test-Path $daemon)) {
  New-Item -ItemType Directory -Force -Path (Split-Path $daemon) | Out-Null
  Set-Content -Path $daemon -Value '{}' -Encoding UTF8
}

$cfg = Get-Content $daemon -Raw | ConvertFrom-Json
if (-not ($cfg.PSObject.Properties.Name -contains 'registry-mirrors')) {
  $cfg | Add-Member -NotePropertyName 'registry-mirrors' -NotePropertyValue $mirrors -Force
} else {
  $cfg.'registry-mirrors' = $mirrors
}

$tmp = "$daemon.tmp"
$cfg | ConvertTo-Json -Depth 8 | Set-Content -Path $tmp -Encoding UTF8
Move-Item -Force $tmp $daemon

Write-Host "[ok] 镜像源已写入 $daemon"
Write-Host "    镜像列表: $($mirrors -join ', ')"
Write-Host "    请重启 Docker Desktop 生效 (托盘图标 → Restart / 或重新打开 Docker Desktop)。"
Write-Host "    重启后验证: docker pull neo4j:5-community"
