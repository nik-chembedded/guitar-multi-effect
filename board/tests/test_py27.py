"""The board side (gme/, gme_hps.py, gme_web.py, tools/gme_hps.py) must run on Python 2.7 and 3.

No Python 2 on the PC: an AST scan rejects Python 3-only syntax and a list of Python 3-only
names; if a python2 interpreter exists, the files are also byte-compiled with it."""
import ast
import glob
import os
import shutil
import subprocess

import pytest

from conftest import BOARD, REPO

FILES = sorted(glob.glob(os.path.join(BOARD, "gme", "*.py"))) + [
    os.path.join(BOARD, "gme_hps.py"), os.path.join(BOARD, "gme_web.py"), os.path.join(BOARD, "gme_smoke.py"),
    os.path.join(REPO, "tools", "gme_hps.py")]

BANNED_NAMES = set("""FileNotFoundError FileExistsError PermissionError ModuleNotFoundError TimeoutError
ConnectionError BrokenPipeError ConnectionResetError NotADirectoryError IsADirectoryError
InterruptedError RecursionError StopAsyncIteration nonlocal breakpoint""".split())
BANNED_ATTRS = set("""monotonic isclose which JSONDecodeError run lru_cache to_bytes from_bytes
isascii casefold removeprefix removesuffix fspath scandir ensure_future""".split())
# attributes that exist in 2.7 although the name looks suspicious


def scan(path):
    src = open(path, "rb").read().decode("utf-8")
    tree = ast.parse(src, path)
    problems = []
    for n in ast.walk(tree):
        line = getattr(n, "lineno", 0)
        kind = n.__class__.__name__
        if kind in ("JoinedStr", "FormattedValue", "AnnAssign", "Nonlocal", "YieldFrom", "AsyncFunctionDef",
                    "AsyncFor", "AsyncWith", "Await", "NamedExpr", "MatMult", "Match", "TryStar"):
            problems.append((line, kind))
        if isinstance(n, (ast.FunctionDef, ast.Lambda)):
            a = n.args
            if a.kwonlyargs or getattr(a, "posonlyargs", []):
                problems.append((line, "keyword-only / positional-only arguments"))
            if isinstance(n, ast.FunctionDef) and n.returns is not None:
                problems.append((line, "return annotation"))
        if isinstance(n, ast.arg) and n.annotation is not None:
            problems.append((line, "argument annotation"))
        if isinstance(n, ast.Raise) and n.cause is not None:
            problems.append((line, "raise ... from"))
        if isinstance(n, ast.Starred) and not isinstance(getattr(n, "ctx", None), ast.Load):
            problems.append((line, "starred assignment target"))
        if isinstance(n, ast.Call):
            if any(isinstance(a, ast.Starred) for a in n.args[:-1]) or \
               sum(isinstance(a, ast.Starred) for a in n.args) > 1:
                problems.append((line, "several * unpackings in a call"))
            if isinstance(n.func, ast.Name) and n.func.id == "super" and not n.args:
                problems.append((line, "zero-argument super()"))
            for kw in n.keywords:
                if kw.arg in ("exist_ok", "encoding", "newline", "capture_output", "text", "flush") \
                        and not (isinstance(n.func, ast.Attribute) and n.func.attr == "write"):
                    problems.append((line, "Python 3-only keyword argument %s" % kw.arg))
        if isinstance(n, ast.Name) and n.id in BANNED_NAMES:
            problems.append((line, "Python 3-only name %s" % n.id))
        if isinstance(n, ast.Attribute) and n.attr in BANNED_ATTRS:
            problems.append((line, "Python 3-only attribute %s" % n.attr))
        if isinstance(n, ast.Dict) and any(k is None for k in n.keys):
            problems.append((line, "dict unpacking {**x}"))
    header = [x for x in tree.body if isinstance(x, ast.ImportFrom) and x.module == "__future__"]
    names = set(a.name for h in header for a in h.names)
    if "print_function" not in names:
        problems.append((1, "missing 'from __future__ import print_function'"))
    if "division" not in names and os.path.basename(path) not in ("__init__.py",):
        if os.path.basename(path) != "gme_hps.py" or "tools" not in path:
            problems.append((1, "missing 'from __future__ import division'"))
    return problems


@pytest.mark.parametrize("path", FILES, ids=lambda p: os.path.relpath(p, REPO))
def test_python27_syntax(path):
    problems = scan(path)
    assert not problems, "\n".join("%s:%d %s" % (os.path.basename(path), l, w) for l, w in problems)


def test_scan_detects_python3_only_code(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("from __future__ import print_function, division\n"
                   "def f(a, *, b=1) -> int:\n    x: int = 1\n    return f'{a}'\n"
                   "def g():\n    yield from f()\n    nonlocal_ = 1\n")
    got = " ".join(w for _, w in scan(str(bad)))
    for expect in ("JoinedStr", "AnnAssign", "YieldFrom", "keyword-only", "return annotation"):
        assert expect in got


def test_files_found():
    assert len(FILES) == 9 and all(os.path.isfile(f) for f in FILES)


def test_python2_compiles_if_available(tmp_path):
    py2 = shutil.which("python2") or shutil.which("python2.7")
    if not py2:
        pytest.skip("no python2 interpreter on this machine; AST scan only")
    for f in FILES:
        r = subprocess.run([py2, "-c", "import sys;compile(open(sys.argv[1]).read(), sys.argv[1], 'exec')", f],
                           capture_output=True, text=True)
        assert r.returncode == 0, "%s: %s" % (f, r.stderr)
