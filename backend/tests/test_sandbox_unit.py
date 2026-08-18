"""沙箱执行器 + 结果解析单测 — 纯函数解析 + 真实 subprocess e2e。

覆盖:
  - parse_junit_xml: passed/failed/error/skipped 各类 + summary 计算 + 空文本
  - parse_coverage_json: line/branch/function 覆盖率 (含 num_branches=0、无 entities 回退)
  - SubprocessSandboxExecutor 真实 e2e: def add + test_add, Windows 兼容
  - timeout: hang 测试 → timed_out=True
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

from app.agents.sandbox import (
    DockerSandboxExecutor,
    SubprocessSandboxExecutor,
    docker_available,
    parse_coverage_json,
    parse_junit_xml,
    select_executor,
)


# ============================================================
# parse_junit_xml
# ============================================================

def test_parse_junit_passed():
    xml = '''<?xml version="1.0"?>
<testsuite tests="1" failures="0" errors="0" skipped="0">
  <testcase classname="test_add" name="test_add_happy" />
</testsuite>'''
    summary, cases = parse_junit_xml(xml)
    assert summary == {"total": 1, "passed": 1, "failed": 0, "error": 0, "skipped": 0}
    assert len(cases) == 1
    assert cases[0].status == "passed"
    assert cases[0].test_name == "test_add.test_add_happy"


def test_parse_junit_failed():
    xml = '''<?xml version="1.0"?>
<testsuite tests="2" failures="1" errors="0" skipped="0">
  <testcase classname="t" name="test_ok" />
  <testcase classname="t" name="test_bad">
    <failure type="AssertionError">assert 1 == 2</failure>
  </testcase>
</testsuite>'''
    summary, cases = parse_junit_xml(xml)
    assert summary["failed"] == 1
    assert summary["passed"] == 1
    failed = [c for c in cases if c.status == "failed"]
    assert len(failed) == 1
    assert failed[0].error_type == "AssertionError"
    assert "assert 1 == 2" in (failed[0].message or "")


def test_parse_junit_error():
    xml = '''<?xml version="1.0"?>
<testsuite tests="1" failures="0" errors="1" skipped="0">
  <testcase classname="t" name="test_err">
    <error type="ZeroDivisionError">division by zero</error>
  </testcase>
</testsuite>'''
    summary, cases = parse_junit_xml(xml)
    assert summary["error"] == 1
    assert cases[0].status == "error"
    assert cases[0].error_type == "ZeroDivisionError"


def test_parse_junit_skipped():
    xml = '''<?xml version="1.0"?>
<testsuite tests="1" failures="0" errors="0" skipped="1">
  <testcase classname="t" name="test_skip">
    <skipped />
  </testcase>
</testsuite>'''
    summary, cases = parse_junit_xml(xml)
    assert summary["skipped"] == 1
    assert cases[0].status == "skipped"


def test_parse_junit_empty():
    summary, cases = parse_junit_xml("")
    assert summary == {"total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0}
    assert cases == []


def test_parse_junit_testsuites_root():
    """根是 testsuites (含多个 testsuite)。"""
    xml = '''<?xml version="1.0"?>
<testsuites>
  <testsuite tests="1" failures="0" errors="0" skipped="0">
    <testcase classname="a" name="t1" />
  </testsuite>
  <testsuite tests="1" failures="1" errors="0" skipped="0">
    <testcase classname="b" name="t2"><failure type="AssertionError">x</failure></testcase>
  </testsuite>
</testsuites>'''
    summary, cases = parse_junit_xml(xml)
    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert len(cases) == 2


# ============================================================
# parse_coverage_json
# ============================================================

def _cov_data(covered_lines=10, num_statements=10, covered_branches=4, num_branches=5,
              files=None):
    return {
        "totals": {
            "covered_lines": covered_lines,
            "num_statements": num_statements,
            "covered_branches": covered_branches,
            "num_branches": num_branches,
            "percent_covered": 100.0,
        },
        "files": files or {},
    }


class _FakeEntity:
    """轻量 CodeEntity 替身 (用于覆盖率自算测试)。"""

    def __init__(self, kind, module_name, line_start, line_end):
        self.kind = kind
        self.module_name = module_name
        self.line_start = line_start
        self.line_end = line_end


def test_coverage_line_branch():
    data = _cov_data(covered_lines=8, num_statements=10, covered_branches=3, num_branches=5)
    cov = parse_coverage_json(data, entities=None)
    assert cov["line_coverage"] == 0.8
    assert cov["branch_coverage"] == 0.6


def test_coverage_no_branches():
    """num_branches=0 → branch_coverage=0 (非除零)。"""
    data = _cov_data(covered_lines=10, num_statements=10, covered_branches=0, num_branches=0)
    cov = parse_coverage_json(data, entities=None)
    assert cov["branch_coverage"] == 0.0
    assert cov["line_coverage"] == 1.0


def test_coverage_function_via_entities():
    """函数覆盖率: entities 行号 vs missing_lines 交叉。"""
    # main.py: 函数A 行1-2 全覆盖, 函数B 行4-5 有 missing(行4)
    data = _cov_data(
        covered_lines=3, num_statements=4,
        files={"main.py": {"executed_lines": [1, 2, 5], "missing_lines": [4]}},
    )
    entities = [
        _FakeEntity("function", "main", 1, 2),   # 无 missing → 覆盖
        _FakeEntity("method", "main", 4, 5),     # 行4 missing → 未覆盖
    ]
    cov = parse_coverage_json(data, entities=entities)
    assert cov["function_coverage"] == 0.5


def test_coverage_function_all_covered():
    data = _cov_data(files={"main.py": {"executed_lines": [1, 2], "missing_lines": []}})
    entities = [_FakeEntity("function", "main", 1, 2)]
    cov = parse_coverage_json(data, entities=entities)
    assert cov["function_coverage"] == 1.0


def test_coverage_no_entities_falls_back():
    """无 entities 且 totals 无 num_functions → function_coverage=0。"""
    data = _cov_data()
    cov = parse_coverage_json(data, entities=None)
    assert cov["function_coverage"] == 0.0


# ============================================================
# SubprocessSandboxExecutor 真实 e2e
# ============================================================

def test_subprocess_e2e_add():
    """真实 subprocess 跑 def add + test_add，断言通过 + 覆盖率。"""
    workdir = Path(tempfile.mkdtemp(prefix="kmatch_test_"))
    try:
        (workdir / "calc.py").write_text(
            "def add(a, b):\n    return a + b\n", encoding="utf-8")
        (workdir / "test_calc.py").write_text(
            "from calc import add\n\n"
            "def test_add_happy():\n    assert add(1, 2) == 3\n\n"
            "def test_add_boundary():\n    assert add(0, 0) == 0\n",
            encoding="utf-8")
        executor = SubprocessSandboxExecutor()
        result = executor.run(workdir, "calc", "test_calc.py", cov_module="calc", timeout=30)
        assert result.success
        assert result.summary["passed"] == 2
        assert result.summary["failed"] == 0
        assert result.coverage is not None
        assert result.coverage["line_coverage"] > 0
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)


def test_subprocess_timeout():
    """hang 测试 → timed_out=True。"""
    workdir = Path(tempfile.mkdtemp(prefix="kmatch_test_"))
    try:
        (workdir / "hang.py").write_text("def f():\n    pass\n", encoding="utf-8")
        (workdir / "test_hang.py").write_text(
            "import time\n"
            "def test_hang():\n    time.sleep(30)\n", encoding="utf-8")
        executor = SubprocessSandboxExecutor()
        result = executor.run(workdir, "hang", "test_hang.py", cov_module="hang", timeout=3)
        assert result.timed_out is True
        assert result.success is False
        assert "超时" in (result.error or "")
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)


def test_subprocess_failed_test():
    """有失败用例 → success=True (pytest 跑起来了) + failed 计数。"""
    workdir = Path(tempfile.mkdtemp(prefix="kmatch_test_"))
    try:
        (workdir / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        (workdir / "test_calc.py").write_text(
            "from calc import add\n"
            "def test_fail():\n    assert add(1, 1) == 3\n", encoding="utf-8")
        executor = SubprocessSandboxExecutor()
        result = executor.run(workdir, "calc", "test_calc.py", cov_module="calc", timeout=30)
        assert result.success is True  # pytest 启动成功
        assert result.summary["failed"] == 1
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)


# ============================================================
# issue-46: pytest coverage 参数构造 (纯函数, 免 subprocess)
# ============================================================
def test_cov_args_valid_module_separate_args():
    """合法 module → --cov 分离参数 + branch/report; 不再是 --cov={module} 拼接。"""
    from app.agents.sandbox import _pytest_cov_args
    args = _pytest_cov_args("calc")
    assert "--cov" in args and args[args.index("--cov") + 1] == "calc"
    assert "--cov-branch" in args
    assert "--cov-report=json:coverage.json" in args

def test_cov_args_invalid_or_empty_module_no_cov_args():
    """'-' 前缀 / 非法字符 / 空 → 不注入 coverage 参数 (防 pytest 选项注入)。"""
    from app.agents.sandbox import _pytest_cov_args
    assert _pytest_cov_args("-collect-only") == []
    assert _pytest_cov_args("../../evil") == []
    assert _pytest_cov_args("a b") == []
    assert _pytest_cov_args("") == []


# ============================================================
# 沙箱执行器选择 (F12/#15: SANDBOX_MODE + docker_available)
# ============================================================

def test_select_executor_subprocess_forced(monkeypatch):
    """SANDBOX_MODE=subprocess 强制子进程 (即便 docker 可用)。"""
    from app.config import settings
    import app.agents.sandbox as sb
    monkeypatch.setattr(settings, "SANDBOX_MODE", "subprocess")
    monkeypatch.setattr(sb, "docker_available", lambda: True)  # 即便 docker 在, 也强制子进程
    exe = sb.select_executor()
    assert isinstance(exe, sb.SubprocessSandboxExecutor)


def test_select_executor_docker_forced_unavailable_raises(monkeypatch):
    """SANDBOX_MODE=docker 但 docker 不可用 → ValueError (调用方据此提示用户)。"""
    from app.config import settings
    import app.agents.sandbox as sb
    monkeypatch.setattr(settings, "SANDBOX_MODE", "docker")
    monkeypatch.setattr(sb, "docker_available", lambda: False)
    with pytest.raises(ValueError, match="docker 不可用"):
        sb.select_executor()


def test_select_executor_auto_falls_back_when_no_docker(monkeypatch):
    """auto 模式无 docker → 回退 SubprocessSandboxExecutor (打包后用户无 Docker 的安全默认)。"""
    from app.config import settings
    import app.agents.sandbox as sb
    monkeypatch.setattr(settings, "SANDBOX_MODE", "auto")
    monkeypatch.setattr(sb, "docker_available", lambda: False)
    exe = sb.select_executor()
    assert isinstance(exe, sb.SubprocessSandboxExecutor)


def test_select_executor_auto_uses_docker_when_available(monkeypatch):
    """auto 模式 docker 可用 → DockerSandboxExecutor。"""
    from app.config import settings
    import app.agents.sandbox as sb
    monkeypatch.setattr(settings, "SANDBOX_MODE", "auto")
    monkeypatch.setattr(sb, "docker_available", lambda: True)
    exe = sb.select_executor()
    assert isinstance(exe, sb.DockerSandboxExecutor)


def test_docker_executor_image_config():
    """DockerSandboxExecutor 读 settings 的镜像/内存/CPU 配置。"""
    exe = DockerSandboxExecutor(image="myimg:1", memory="256m", cpus="2")
    assert exe.image == "myimg:1"
    assert exe.memory == "256m"
    assert exe.cpus == "2"


