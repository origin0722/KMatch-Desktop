# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — 把 KMatch backend (FastAPI + LangGraph) 打成单目录可执行体。

用法 (在 backend/ 目录下运行):
  pyinstaller KMatchBackend.spec --noconfirm --distpath ../backend-dist --workpath ../build/pyinstaller
产物: ../backend-dist/KMatchBackend/KMatchBackend.exe + _internal/

Electron main (backend-sidecar.js) 生产分支 spawn
  resources/backend/KMatchBackend/KMatchBackend.exe
(electron-builder.yml 把 backend-dist → resources/backend 映射)。
data/ 由 electron-builder.yml extraResources 打入 resources/data, 运行时
经 KMATCH_DATA_DIR 由 config.py 解析 (开发期 fallback repo_root/data)。
Neo4j 仍由用户 Docker 起 (scripts/start_all.py)。

注意:
  - langgraph/langchain/jedi/neo4j 有动态导入, 用 collect_all 收全子模块+二进制+数据
  - scripts.validate_data: kb.py 模块级 import, scripts 无 __init__, 须显式 hiddenimport
  - PyInstaller 6.x 已移除 cipher 参数, 不再用 block_cipher
  - 打包后 code_test 沙箱 (sys.executable -m pytest) 不可用 (exe 非 python 解释器),
    属已知限制 (阶段5 沙箱强化), 不阻断构建
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = ['scripts.validate_data', 'app.main', 'app.agents.orchestrator']

# app 实际仅用 langchain_core + langchain_openai + langgraph (grep 确认无 langchain_community
# / 裸 langchain 导入)。故只收集这三者, 不收 langchain_community (它会拖入 torch/pandas/
# matplotlib/sympy/sqlalchemy/PIL/lxml 等数百 MB 臃肿依赖, app 根本不用)。
for pkg in [
    'langgraph', 'langchain_openai', 'langchain_core',
    'neo4j', 'pydantic', 'pydantic_core',
    'jedi', 'uvicorn', 'jsonschema', 'yaml',
    'openai', 'httpx', 'multipart', 'dotenv',
    # uvicorn[standard] 运行时依赖
    'httptools', 'websockets', 'h11', 'anyio', 'sniffio', 'certifi',
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f'[spec] collect_all({pkg}) skipped: {e}')

# uvicorn 子模块动态导入兜底 (loops/protocols/lifespan auto 选择)
hiddenimports += [
    'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
    'uvicorn.protocols', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan', 'uvicorn.lifespan.on',
]
try:
    hiddenimports += collect_submodules('uvicorn')
except Exception:
    pass

a = Analysis(
    ['run_server.py'],
    pathex=['.'],  # backend/ — 让 app 与 scripts 可作顶层包导入
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'pytest', 'pytest_cov', 'pytest_asyncio',  # 测试依赖不打包
        # langchain_community 拖入的臃肿可选依赖, app 不用 — 兜底排除防意外打入
        'torch', 'torchvision', 'torchaudio',
        'pandas', 'matplotlib', 'sympy', 'sqlalchemy',
        'PIL', 'lxml', 'fsspec', 'pygments', 'chardet',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KMatchBackend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # Windows 上 upx 偶发误报, 关闭
    console=True,  # sidecar 需 stdout/stderr 管道
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='KMatchBackend',
)
