"""沙箱解释器解析回归 (#59: 安装包内代码测试缓解)。

打包态优先捆绑便携运行时 resources/backend/runtime-python/python.exe;
开发态回退 sys.executable。
"""

import os
from pathlib import Path

from app.agents import sandbox


def test_dev_mode_uses_sys_executable(monkeypatch):
    monkeypatch.setattr(sandbox.sys, "frozen", False, raising=False)
    assert sandbox._python_executable() == sandbox.sys.executable


def test_frozen_uses_bundled_runtime_when_present(monkeypatch, tmp_path):
    exe = tmp_path / "app" / "KMatchBackend" / "KMatchBackend.exe"
    runtime = tmp_path / "app" / "runtime-python" / "python.exe"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("", encoding="utf-8")  # 仅占位 (is_file 用)
    monkeypatch.setattr(sandbox.sys, "frozen", True, raising=False)
    monkeypatch.setattr(sandbox.sys, "executable", str(exe))
    assert sandbox._python_executable() == str(Path(runtime).resolve())


def test_frozen_falls_back_to_sys_executable_when_missing(monkeypatch, tmp_path):
    exe = tmp_path / "app" / "KMatchBackend" / "KMatchBackend.exe"
    monkeypatch.setattr(sandbox.sys, "frozen", True, raising=False)
    monkeypatch.setattr(sandbox.sys, "executable", str(exe))
    assert sandbox._python_executable() == str(exe)


def test_cmd_uses_resolved_python(monkeypatch, tmp_path):
    """SubprocessSandboxExecutor 的 cmd[0] 走 _python_executable (而非硬编码 sys.executable)。"""
    exe = tmp_path / "app" / "KMatchBackend" / "KMatchBackend.exe"
    runtime = tmp_path / "app" / "runtime-python" / "python.exe"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("", encoding="utf-8")
    monkeypatch.setattr(sandbox.sys, "frozen", True, raising=False)
    monkeypatch.setattr(sandbox.sys, "executable", str(exe))

    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    out = sandbox.SubprocessSandboxExecutor().run(tmp_path / "w", "m", "test_x.py", "m")
    assert captured["cmd"][0] == str(Path(runtime).resolve())  # 用捆绑运行时
    assert "-m" in captured["cmd"] and "pytest" in captured["cmd"]