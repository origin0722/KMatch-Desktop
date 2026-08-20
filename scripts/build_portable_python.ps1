# Build portable Python runtime for the installer (#59: code-test in packaged app).
# Output: <root>/backend-dist/runtime-python  (electron-builder maps backend-dist -> resources/backend,
# so within the installer it resolves to resources/backend/runtime-python/python.exe).
# SubprocessSandboxExecutor prefers this runtime when frozen, so scenario-2 "code test"
# works on end-user machines without Docker or a system Python.
#
# Usage:
#   powershell -File scripts/build_portable_python.ps1                 # Python 3.12.8 amd64
#   powershell -File scripts/build_portable_python.ps1 -PythonVersion 3.12.8 -Output build/runtime-python
param(
  [string]$PythonVersion = '3.12.8',
  [string]$Arch = 'amd64',
  [string]$Output = '',
  [switch]$SkipDownload
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$build = Join-Path $root 'build'
$stage = Join-Path $build ("portable-python-$PythonVersion")
$zip = Join-Path $build ("python-$PythonVersion-embed-$Arch.zip")
$url = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-$Arch.zip"
if (-not $Output) { $Output = Join-Path $root 'backend-dist/runtime-python' }

New-Item -ItemType Directory -Force -Path $build | Out-Null

Write-Host "[portable-python] 1/6 download $url"
if ((Test-Path $zip) -and -not $SkipDownload) { Remove-Item $zip -Force }
if (-not (Test-Path $zip)) {
  Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
}

Write-Host "[portable-python] 2/6 extract to $stage"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $stage -Force

Write-Host "[portable-python] 3/6 enable site-packages"
$pth = Get-ChildItem $stage -Filter 'python*._pth' | Select-Object -First 1
if (-not $pth) { throw '._pth not found (python layout changed?)' }
$content = Get-Content $pth.FullName
$content = $content -replace '^#import site', 'import site'
Set-Content -Path $pth.FullName -Value $content -Encoding ASCII

Write-Host "[portable-python] 4/6 bootstrap pip (get-pip.py)"
$getpip = Join-Path $build 'get-pip.py'
if (-not (Test-Path $getpip)) {
  Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile $getpip -UseBasicParsing
}
& (Join-Path $stage 'python.exe') $getpip --no-warn-script-location -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) { throw 'get-pip failed' }

Write-Host "[portable-python] 5/6 install pytest + pytest-cov"
& (Join-Path $stage 'python.exe') -m pip install -q --no-warn-script-location -i https://pypi.tuna.tsinghua.edu.cn/simple pytest pytest-cov
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

Write-Host "[portable-python] 6/6 verify and copy to $Output"
$pytestVer = & (Join-Path $stage 'python.exe') -m pytest --version 2>&1
Write-Host ("  " + ($pytestVer -join ' '))
if (($pytestVer -join ' ') -notmatch 'pytest') { throw 'pytest verification failed' }

New-Item -ItemType Directory -Force -Path (Split-Path $Output -Parent) | Out-Null
if (Test-Path $Output) { Remove-Item $Output -Recurse -Force }
Copy-Item -Recurse $stage $Output
Write-Host "[portable-python] done -> $Output"