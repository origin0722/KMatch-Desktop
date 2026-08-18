"""
PyInstaller 打包入口 — 直接启动 uvicorn (非 import app.main:app 字符串)。

PyInstaller 无法用 uvicorn "app.main:app" 字符串定位 app 对象, 故在此显式 import app
并 run。打包后 KMatchBackend.exe 即后端 sidecar, 监听 127.0.0.1:8000。

开发期不需要此文件 (用 uvicorn app.main:app); 仅打包用。
"""
import os
import sys

# 打包后 _internal 在 sys.path; 确保 app 包可导入
if getattr(sys, 'frozen', False):
    base = os.path.dirname(sys.executable)
    sys.path.insert(0, os.path.join(base, '_internal'))
    # data 目录: electron-builder 打入 resources/data, exe 在 resources/backend/KMatchBackend/
    # data 在同级 ../data
    os.environ.setdefault('KMATCH_DATA_DIR', os.path.join(base, '..', '..', 'data'))

import uvicorn
from app.main import app

if __name__ == '__main__':
    # issue-45: 默认只绑本机; 容器部署 KMATCH_HOST=0.0.0.0
    uvicorn.run(app, host=os.getenv('KMATCH_HOST', '127.0.0.1'), port=8000, log_level='info')
