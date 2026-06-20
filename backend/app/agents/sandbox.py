"""
代码测试沙箱执行器 + 结果解析

职责:
  - 可插拔沙箱接口 SandboxExecutor (默认 SubprocessSandboxExecutor，预留 DockerSandboxExecutor)
  - SubprocessSandboxExecutor: subprocess 调 pytest --cov --junitxml 执行用户测试
  - parse_junit_xml: 解析 pytest junit XML → 测试用例结果 + summary
  - parse_coverage_json: 解析 pytest-cov coverage.json → line/branch/function 覆盖率

安全性 (分层沙箱第一层在此之外，由 code_tester 调 hard_check_code_safety 完成 AST 预检):
  subprocess 方案诚实限制 (无法满足 06 prompt 全部硬约束):
    - 禁网络: 做不到 (Docker --network=none 才可)，仅剔除代理 env 微缓解
    - 512MB 内存: 做不到 (Windows 无 resource.setrlimit)
    - 单测 5s 超时: 用整套 subprocess timeout 近似 (精确需 pytest-timeout，未引入)
    - 文件系统限 /tmp: cwd 限临时目录，无 OS 级隔离
  第一层 AST 预检 (复用 code_reviewer.hard_check_code_safety) 完全满足 prompt 的
  "所有代码先经过 AST 安全检查"，是可演示的核心安全能力。
"""

from __future__ import annotations

import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ============================================================
# 结果数据结构
# ============================================================

@dataclass
class TestCaseResult:
    """单个测试用例结果。"""

    __test__ = False  # 防 pytest 误当测试类收集 (类名以 Test 开头)

    test_name: str            # f"{classname}.{name}" 或 name
    classname: str
    status: str               # passed|failed|error|skipped
    error_type: Optional[str] = None   # failure.type，如 AssertionError
    message: Optional[str] = None      # 失败消息/traceback 摘要


@dataclass
class TestRunResult:
    """一次 pytest 执行的完整结果。"""

    __test__ = False  # 防 pytest 误当测试类收集

    success: bool             # pytest 是否成功启动执行 (与用例 pass/fail 无关)
    exit_code: int
    summary: dict = field(default_factory=lambda: {
        "total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0,
    })
    cases: list[TestCaseResult] = field(default_factory=list)
    coverage: Optional[dict] = None   # {line_coverage, branch_coverage, function_coverage, files}
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    error: Optional[str] = None       # 沙箱级错误 (timeout/importerror 等)


# ============================================================
# 沙箱接口
# ============================================================

class SandboxExecutor(ABC):
    """可插拔沙箱执行器接口。"""

    @abstractmethod
    def run(
        self,
        workdir: Path,
        module_name: str,
        test_filename: str,
        cov_module: str,
        timeout: int = 30,
    ) -> TestRunResult:
        """在 workdir 执行 test_filename，覆盖率统计 cov_module。"""
        raise NotImplementedError


# 网络代理相关 env 变量 (subprocess 无法真正禁网，仅剔除代理作微缓解)
_PROXY_ENV_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
    "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy",
)


def _sandbox_env() -> dict:
    """构造沙箱环境变量: 复制当前 env 但剔除代理 (诚实声明: 无法真正禁网)。"""
    env = os.environ.copy()
    for k in _PROXY_ENV_KEYS:
        env.pop(k, None)
    return env


class SubprocessSandboxExecutor(SandboxExecutor):
    """默认执行器: subprocess 调 sys.executable -m pytest --cov --junitxml。

    诚实限制见模块 docstring。第一层 AST 预检由调用方 (code_tester) 在执行前完成。
    """

    def run(self, workdir, module_name, test_filename, cov_module, timeout=30):
        cmd = [
            sys.executable, "-m", "pytest",
            f"--rootdir={workdir}",
            "-p", "no:cacheprovider",       # 不污染全局缓存
            "-o", "addopts=",               # 清掉用户 conftest 的 addopts
            "--tb=short",
            "-q",
            "--junitxml=junit.xml",
            f"--cov={cov_module}",
            "--cov-branch",
            "--cov-report=json:coverage.json",
            test_filename,
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(workdir),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=_sandbox_env(),
            )
        except subprocess.TimeoutExpired as e:
            return TestRunResult(
                success=False,
                exit_code=-1,
                timed_out=True,
                error=f"测试执行超时 ({timeout}s)",
                stdout=e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""),
                stderr=e.stderr.decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or ""),
            )
        except FileNotFoundError as e:
            return TestRunResult(
                success=False, exit_code=-1, error=f"pytest 未找到: {e}",
            )
        except Exception as e:
            return TestRunResult(
                success=False, exit_code=-1, error=f"沙箱执行异常: {e}",
            )

        # pytest 退出码: 0=全过, 1=有失败/错误, 2=收集错误 → 均视为成功启动
        success = proc.returncode in (0, 1, 2)

        # 解析 junit.xml
        junit_path = workdir / "junit.xml"
        junit_text = junit_path.read_text(encoding="utf-8") if junit_path.exists() else ""
        summary, cases = parse_junit_xml(junit_text)

        # 解析 coverage.json
        cov_path = workdir / "coverage.json"
        coverage = None
        if cov_path.exists():
            try:
                import json
                coverage = parse_coverage_json(
                    json.loads(cov_path.read_text(encoding="utf-8")), entities=None,
                )
            except Exception:
                coverage = None

        return TestRunResult(
            success=success,
            exit_code=proc.returncode,
            summary=summary,
            cases=cases,
            coverage=coverage,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )


class DockerSandboxExecutor(SandboxExecutor):
    """预留: docker run --rm --network=none --memory=512m --cpus=1
    -v {workdir}:/work -w /work {image} python -m pytest ...

    冲刺期如需完全满足 06 prompt 沙箱要求 (禁网络/限内存) 再切换实现。
    切换零改动 code_tester (接口已统一)。
    """

    def run(self, *args, **kwargs) -> TestRunResult:
        raise NotImplementedError("Docker 沙箱未实现，使用 SubprocessSandboxExecutor")


# ============================================================
# JUnit XML 解析
# ============================================================

def parse_junit_xml(xml_text: str) -> tuple[dict, list[TestCaseResult]]:
    """解析 pytest junit XML → (summary, cases)。

    summary: {total, passed, failed, error, skipped}
    cases: [TestCaseResult]

    空文本 → 零 summary + 空 cases。
    """
    summary = {"total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0}
    cases: list[TestCaseResult] = []
    if not xml_text or not xml_text.strip():
        return summary, cases

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return summary, cases

    # 根可能是 testsuites 或 testsuite
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]
    for ts in suites:
        t = ts.get("tests", "0")
        f = ts.get("failures", "0")
        e = ts.get("errors", "0")
        s = ts.get("skipped", "0")
        total = _to_int(t)
        failed = _to_int(f)
        error = _to_int(e)
        skipped = _to_int(s)
        summary["total"] += total
        summary["failed"] += failed
        summary["error"] += error
        summary["skipped"] += skipped
        summary["passed"] += max(0, total - failed - error - skipped)

        for tc in ts.findall("testcase"):
            classname = tc.get("classname", "")
            name = tc.get("name", "")
            test_name = f"{classname}.{name}" if classname and name else name

            failure = tc.find("failure")
            err = tc.find("error")
            skipped = tc.find("skipped")

            if failure is not None:
                cases.append(TestCaseResult(
                    test_name=test_name, classname=classname, status="failed",
                    error_type=failure.get("type"),
                    message=(failure.text or "").strip() or None,
                ))
            elif err is not None:
                cases.append(TestCaseResult(
                    test_name=test_name, classname=classname, status="error",
                    error_type=err.get("type"),
                    message=(err.text or "").strip() or None,
                ))
            elif skipped is not None:
                cases.append(TestCaseResult(
                    test_name=test_name, classname=classname, status="skipped",
                    message=(skipped.text or "").strip() or None,
                ))
            else:
                cases.append(TestCaseResult(
                    test_name=test_name, classname=classname, status="passed",
                ))

    return summary, cases


# ============================================================
# Coverage JSON 解析
# ============================================================

def parse_coverage_json(data: dict, entities: Optional[list] = None) -> dict:
    """解析 pytest-cov (coverage.py) JSON → {line_coverage, branch_coverage, function_coverage, files}。

    Args:
        data: coverage.json 解析后的 dict
        entities: CodeEntity 列表 (含 line_start/line_end/kind)，用于自算 function_coverage。
                  为 None 时 function_coverage 回退到 coverage.py 的 totals (若无则 0)。

    Returns:
        全部 0-1 浮点。
    """
    totals = data.get("totals", {}) if isinstance(data, dict) else {}
    files = data.get("files", {}) if isinstance(data, dict) else {}

    # line coverage
    num_stmts = _to_float(totals.get("num_statements", 0))
    covered_lines = _to_float(totals.get("covered_lines", 0))
    if num_stmts > 0:
        line_cov = covered_lines / num_stmts
    else:
        line_cov = _to_float(totals.get("percent_covered", 0)) / 100.0

    # branch coverage
    num_branches = _to_float(totals.get("num_branches", 0))
    covered_branches = _to_float(totals.get("covered_branches", 0))
    if num_branches > 0:
        branch_cov = covered_branches / num_branches
    else:
        branch_cov = _to_float(totals.get("percent_covered_branches", 0)) / 100.0

    # function coverage: 优先用 entities 行号交叉自算 (coverage.py JSON 不直接给函数级)
    func_cov = _compute_function_coverage(entities, files)
    if func_cov is None:
        # 回退: coverage.py 的 covered_functions / num_functions (新版有，可能缺失)
        num_funcs = _to_float(totals.get("num_functions", 0))
        covered_funcs = _to_float(totals.get("covered_functions", 0))
        func_cov = (covered_funcs / num_funcs) if num_funcs > 0 else 0.0

    return {
        "line_coverage": round(line_cov, 4),
        "branch_coverage": round(branch_cov, 4),
        "function_coverage": round(func_cov, 4),
        "files": _summarize_files(files),
    }


def _compute_function_coverage(entities: Optional[list], files: dict) -> Optional[float]:
    """用 CodeEntity 行号区间 vs 各文件 missing_lines 交叉算函数覆盖率。

    每个函数/method: 其 [line_start, line_end] 区间内若无 missing_lines → 视为覆盖。
    无 entities → 返回 None (回退到 totals)。
    """
    if not entities:
        return None

    # 收集每个文件的 missing_lines
    file_missing: dict[str, set[int]] = {}
    for fname, fdata in (files or {}).items():
        missing = fdata.get("missing_lines", []) if isinstance(fdata, dict) else []
        stem = Path(fname).stem
        file_missing[stem] = set(missing) if isinstance(missing, list) else set()

    total_funcs = 0
    covered_funcs = 0
    for e in entities:
        kind = getattr(e, "kind", None)
        if kind not in ("function", "method"):
            continue
        total_funcs += 1
        line_start = getattr(e, "line_start", 0) or 0
        line_end = getattr(e, "line_end", 0) or 0
        module_name = getattr(e, "module_name", "")
        missing = file_missing.get(module_name, set())
        # 函数区间内是否有缺失行
        func_lines = set(range(line_start, line_end + 1))
        if not (func_lines & missing):
            covered_funcs += 1

    if total_funcs == 0:
        return None
    return covered_funcs / total_funcs


def _summarize_files(files: dict) -> dict:
    """简化 files 结构供报告 (保留每模块 executed/missing 行数)。"""
    result = {}
    for fname, fdata in (files or {}).items():
        if not isinstance(fdata, dict):
            continue
        result[fname] = {
            "executed_lines": len(fdata.get("executed_lines", []) or []),
            "missing_lines": len(fdata.get("missing_lines", []) or []),
        }
    return result


# ============================================================
# 辅助
# ============================================================

def _to_int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0
