#!/usr/bin/env python3
"""The Python defect class no configured analyzer catches: a statement
that follows a jump in the same block, so it can never run, and a
subprocess call that has no timeout, so a wedged child hangs the suite.

Ruff (`scripts/lint-python.sh`, pyproject.toml) owns the rest of the
stdlib-detectable floor for every tracked *.py: E999 parse errors, E722 bare
`except`, B006 mutable default arguments, F601 duplicate dict-literal keys,
F631 assert on a tuple literal, and E711 `== None`. This gate keeps the one
class ruff has no rule for, rather than running a second analyzer over the
rest of the same territory. Every subprocess here decodes its output with an
explicit encoding, because the locale's is ASCII under a bare LANG, and
every one of them names a timeout, because a child that never exits takes the
suite runner down with it and reports nothing.

Stdlib-only, tracked files only via `git ls-files`, sorted deterministic
output, and negative controls proving the detector can fail, against
fixture source strings inside this file and never the shared tree.
"""

from __future__ import annotations

import ast
import os
import sys
from itertools import pairwise

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result
from git_tracked import tracked_paths
from local_env import mod_dir

MOD_DIR = str(mod_dir())

JUMPS = (ast.Return, ast.Raise, ast.Break, ast.Continue)


def tracked_py() -> list[str]:
    """Every tracked *.py under this mod, sorted — never filesystem order."""
    return tracked_paths("*.py")


def _scan_block(body: list[ast.stmt], found: list[tuple[int, str]]) -> None:
    """Flag any statement that follows a jump inside this exact block."""
    for prev, nxt in pairwise(body):
        if isinstance(prev, JUMPS):
            kind = type(prev).__name__.lower()
            found.append((nxt.lineno, f"unreachable statement after {kind}"))
            return


def findings(source: str) -> list[str]:
    """The unreachable-statement findings in *source*, as 'lineno: kind'."""
    return _unreachable_statements(ast.parse(source))


def _unreachable_statements(tree: ast.Module) -> list[str]:
    """The unreachable-statement findings in an already parsed *tree*."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list):
                _scan_block(block, found)
        for handler in getattr(node, "handlers", []):
            _scan_block(handler.body, found)
        for case in getattr(node, "cases", []):
            _scan_block(case.body, found)
    return [f"{line}: {kind}" for line, kind in sorted(found)]


SUBPROCESS_CALLS = {"run", "Popen", "check_call", "check_output"}
# The calls that take a `timeout` keyword, so a child that never exits fails
# the caller instead of taking the suite down with it.
TIMED_SUBPROCESS_CALLS = {"run", "check_call", "check_output"}
TEXT_ARGUMENTS = {"text", "universal_newlines"}


def is_text_flag(value: ast.expr | None) -> bool:
    """Whether a keyword argument is the literal `True`."""
    return isinstance(value, ast.Constant) and value.value is True


def subprocess_calls(tree: ast.Module) -> list[tuple[ast.Call, str]]:
    """Every `subprocess.<something>(...)` call in *tree* with its name.

    Matched on the module, not on the method name alone: `GameTelnet.run` is
    a console command, and reading it as a subprocess would be wrong.
    """
    found: list[tuple[ast.Call, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        target = node.func.value
        names_subprocess = isinstance(target, ast.Name) and target.id == "subprocess"
        if isinstance(target, ast.Attribute):
            names_subprocess = target.attr == "subprocess"
        if names_subprocess:
            found.append((node, node.func.attr))
    return found


def undecoded_text_calls(source: str) -> list[str]:
    """The subprocess calls decoding text without naming an encoding."""
    return _undecoded_text_calls(ast.parse(source))


def _undecoded_text_calls(tree: ast.Module) -> list[str]:
    """As `undecoded_text_calls`, over an already parsed *tree*.

    `text=True` decodes with the locale's encoding, which is ASCII under a
    bare LANG, so a subprocess that prints one non-ASCII byte then raises
    UnicodeDecodeError. The call site has to say which encoding it means.
    """
    found: list[tuple[int, str]] = []
    for node, call in subprocess_calls(tree):
        if call not in SUBPROCESS_CALLS:
            continue
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        if not any(is_text_flag(keywords.get(name)) for name in TEXT_ARGUMENTS):
            continue
        encoding = keywords.get("encoding")
        if encoding is None or (isinstance(encoding, ast.Constant) and encoding.value is None):
            found.append((node.lineno, f"{call}() decodes text with the locale's encoding"))
    return [f"{line}: {kind}" for line, kind in sorted(found)]


def untimed_subprocess_calls(source: str) -> list[str]:
    """The subprocess calls that can wait for a wedged child forever."""
    return _untimed_subprocess_calls(ast.parse(source))


def _untimed_subprocess_calls(tree: ast.Module) -> list[str]:
    """As `untimed_subprocess_calls`, over an already parsed *tree*.

    `run` and `check_output` take a `timeout`, and without one a child that
    never exits takes the caller with it: the suite runner waits for it, and a
    gate that never returns reports nothing at all. `Popen` has no such
    keyword, so a call that spawns is out of this detector's reach.
    """
    found: list[tuple[int, str]] = []
    for node, call in subprocess_calls(tree):
        if call not in TIMED_SUBPROCESS_CALLS:
            continue
        if not any(keyword.arg == "timeout" for keyword in node.keywords):
            found.append((node.lineno, f"{call}() can wait for a wedged child forever"))
    return [f"{line}: {kind}" for line, kind in sorted(found)]


def tracked_files_stay_clean() -> None:
    unreachable: list[str] = []
    undecoded: list[str] = []
    untimed: list[str] = []
    for relpath in tracked_py():
        path = os.path.join(MOD_DIR, relpath)
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        # One parse per file, shared by all three detectors: the tree is the
        # whole input each of them walks, and parsing a tracked file twice to
        # ask two questions of it is the gate's own duplicated work.
        try:
            tree = ast.parse(source)
        except SyntaxError:
            # A parse error is ruff's E999 to report, not this gate's.
            continue
        unreachable += [f"{relpath}:{item}" for item in _unreachable_statements(tree)]
        undecoded += [f"{relpath}:{item}" for item in _undecoded_text_calls(tree)]
        untimed += [f"{relpath}:{item}" for item in _untimed_subprocess_calls(tree)]
    check(
        "no unreachable statements in tracked *.py",
        not unreachable,
        "; ".join(unreachable),
    )
    check(
        "no subprocess text output without an explicit encoding in tracked *.py",
        not undecoded,
        "; ".join(undecoded),
    )
    check(
        "no subprocess call without a timeout in tracked *.py",
        not untimed,
        "; ".join(untimed),
    )


def negative_controls() -> None:
    """Prove the detector can fail, without breaking the shared tree."""
    clean = findings("def f(x):\n    if x is None:\n        return 0\n    return 1\n")
    check("negative control: clean source raises nothing", not clean, str(clean))
    cases = (
        (
            "unreachable statement after return",
            "def f(x):\n    return x\n    print('dead')\n",
        ),
        (
            "unreachable statement after raise",
            "def f(x):\n    raise ValueError(x)\n    return x\n",
        ),
    )
    for kind, snippet in cases:
        hits = findings(snippet)
        check(
            "negative control rejects " + kind,
            any(item.endswith(kind) for item in hits),
            f"{kind} slipped through: {hits!r}",
        )
    # A trailing jump must NOT read as dead code: nothing follows it.
    tail_ok = findings("def f(x):\n    return x\n")
    check(
        "negative control: trailing return is not unreachable",
        not tail_ok,
        str(tail_ok),
    )
    encoded = undecoded_text_calls(
        "import subprocess\n"
        "subprocess.run(['x'], text=True, encoding='utf-8', errors='replace')\n"
        "subprocess.run(['x'], capture_output=True)\n"
    )
    check(
        "negative control: an explicit encoding is not flagged",
        not encoded,
        str(encoded),
    )
    implicit = undecoded_text_calls(
        "import subprocess\n"
        "subprocess.run(['x'], text=True)\n"
        "subprocess.check_call(['x'], text=True)\n"
        "subprocess.check_output(['x'], universal_newlines=True)\n"
    )
    check(
        "negative control rejects text decoded with the locale's encoding",
        len(implicit) == 3,
        f"{len(implicit)} of 3 undecoded calls slipped through: {implicit!r}",
    )
    timed = untimed_subprocess_calls(
        "import subprocess\n"
        "subprocess.run(['x'], timeout=30)\n"
        "subprocess.check_output(['x'], timeout=30)\n"
        "subprocess.Popen(['x'])\n"
    )
    check(
        "negative control: an explicit timeout is not flagged",
        not timed,
        str(timed),
    )
    unbounded = untimed_subprocess_calls(
        "import subprocess\n"
        "subprocess.run(['x'], capture_output=True)\n"
        "subprocess.check_output(['x'])\n"
    )
    check(
        "negative control rejects a subprocess call that can wait forever",
        len(unbounded) == 2,
        f"{len(unbounded)} of 2 untimed calls slipped through: {unbounded!r}",
    )


def main() -> int:
    tracked_files_stay_clean()
    negative_controls()
    return result()


if __name__ == "__main__":
    raise SystemExit(main())
