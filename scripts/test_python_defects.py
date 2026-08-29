#!/usr/bin/env python3
"""The Python static-analysis floor: stdlib-detectable defect classes the
tree starts at zero on, kept there.

No third-party Python analyzer is assumed on the host, so this gate is the
floor for every tracked *.py (the mod's own gates and tools):

- **Every tracked `*.py` parses** — most of these files are tools a human
  runs mid-emergency, not code the suite executes.
- **Bare `except:`** — swallows KeyboardInterrupt/SystemExit and hides real
  defects; `except Exception:` with a stated reason stays allowed.
- **Mutable default arguments** — evaluated once at def time and shared.
- **Duplicate dict-literal keys** — the later entry silently wins, so a
  lookup table or patch map ships with half its entries dead.
- **Unreachable statements** — any statement after return/raise/break/
  continue in the same block is dead code pretending to be behaviour.
- **assert (tuple)** — a non-empty tuple literal is always truthy, so the
  assertion can never fire; an empty one can never pass.
- **== None / != None** — identity comparison belongs to `is` / `is not`;
  `==` dispatches a stray __eq__ and misses None-correct objects.

Stdlib-only, tracked files only via `git ls-files`, sorted deterministic
output, and negative controls proving every detector can fail — fixture
source strings inside this file, never the shared tree. Retire overlapping
checks in favour of a real linter if one ever lands rather than running two
analyzers over the same territory.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

JUMPS = (ast.Return, ast.Raise, ast.Break, ast.Continue)
MUTABLE_LITERALS = (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)
MUTABLE_CALLS = ("list", "dict", "set")

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print("PASS " + name)
        return
    FAILURES.append(name)
    print("FAIL " + name + (": " + detail if detail else ""), file=sys.stderr)


def tracked_py() -> list[str]:
    """Every tracked *.py under this mod, sorted — never filesystem order."""
    done = subprocess.run(
        ["git", "-C", MOD_DIR, "ls-files", "-z", "--", "*.py"],
        capture_output=True, text=True, timeout=60,
    )
    if done.returncode != 0:
        raise SystemExit("ERROR: git ls-files failed: " + done.stderr)
    return sorted(name for name in done.stdout.split("\0") if name)


def _scan_block(body: list[ast.stmt], found: list[tuple[int, str]]) -> None:
    """Flag any statement that follows a jump inside this exact block."""
    for prev, nxt in zip(body, body[1:]):
        if isinstance(prev, JUMPS):
            kind = type(prev).__name__.lower()
            found.append((nxt.lineno, f"unreachable statement after {kind}"))
            return


def findings(source: str) -> list[str]:
    """The defect classes in *source*, as 'lineno: kind'."""
    tree = ast.parse(source)
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
        if isinstance(node, ast.Dict):
            seen: set[tuple[str, str]] = set()
            for key in node.keys:
                if not isinstance(key, ast.Constant) or key.value is Ellipsis:
                    continue  # **unpacking and computed keys are not literals
                ident = (type(key.value).__name__, repr(key.value))
                if ident in seen:
                    found.append((key.lineno, "duplicate dict-literal key"))
                seen.add(ident)
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            found.append((node.lineno, "bare except"))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = list(node.args.defaults) + [
                d for d in node.args.kw_defaults if d is not None
            ]
            for default in defaults:
                mutable = isinstance(default, MUTABLE_LITERALS) or (
                    isinstance(default, ast.Call)
                    and isinstance(default.func, ast.Name)
                    and default.func.id in MUTABLE_CALLS
                )
                if mutable:
                    found.append((default.lineno, "mutable default argument"))
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Tuple):
            found.append((node.test.lineno, "assert on a tuple literal"))
        if isinstance(node, ast.Compare):
            operands: list[ast.expr] = [node.left, *node.comparators]
            for op, operand in zip(node.ops, operands[1:]):
                wrong_identity = isinstance(operand, ast.Constant) and (
                    operand.value is None
                ) and isinstance(op, (ast.Eq, ast.NotEq))
                if wrong_identity:
                    found.append((operand.lineno, "==/!= None comparison"))
            if (
                isinstance(node.left, ast.Constant)
                and node.left.value is None
                and node.ops
                and isinstance(node.ops[0], (ast.Eq, ast.NotEq))
            ):
                found.append((node.left.lineno, "==/!= None comparison"))
    return [f"{line}: {kind}" for line, kind in sorted(found)]


def tracked_files_stay_clean() -> None:
    problems: list[str] = []
    syntax_errors: list[str] = []
    for relpath in tracked_py():
        path = os.path.join(MOD_DIR, relpath)
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        try:
            problems += [f"{relpath}:{item}" for item in findings(source)]
        except SyntaxError as exc:
            syntax_errors.append(f"{relpath}:{exc.lineno}: {exc.msg}")
    check(
        "every tracked *.py parses",
        not syntax_errors,
        "; ".join(syntax_errors),
    )
    check(
        "no bare excepts, mutable defaults, duplicate dict keys, "
        "unreachable statements, tuple asserts, == None",
        not problems,
        "; ".join(problems),
    )


def negative_controls() -> None:
    """Prove each detector can fail, without breaking the shared tree."""
    clean = findings(
        "D = {'x': 1, 'y': 2}\n"
        "def f(x):\n"
        "    if x is None:\n"
        "        return 0\n"
        "    try:\n"
        "        return int(x)\n"
        "    except ValueError:\n"
        "        raise\n"
        "assert f('1')\n"
    )
    check("negative control: clean source raises nothing", not clean, str(clean))
    cases = (
        ("duplicate dict-literal key", "D = {'x': 1, 'x': 2}\n"),
        ("duplicate dict-literal key", "D = {True: 'a', True: 'b'}\n"),
        (
            "unreachable statement after return",
            "def f(x):\n"
            "    return x\n"
            "    print('dead')\n",
        ),
        (
            "unreachable statement after raise",
            "def f(x):\n"
            "    raise ValueError(x)\n"
            "    return x\n",
        ),
        ("assert on a tuple literal", "assert (1, 2)\n"),
        (
            "bare except",
            "def f(x):\n"
            "    try:\n"
            "        return int(x)\n"
            "    except:\n"
            "        return 0\n",
        ),
        ("mutable default argument", "def f(x, acc=[]):\n    return acc\n"),
        ("mutable default argument", "def f(x, acc=dict()):\n    return acc\n"),
        ("==/!= None comparison", "ok = (x != None)\n" "def f(x):\n" "    return ok\n"),
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


def main() -> int:
    tracked_files_stay_clean()
    negative_controls()
    print("RESULT " + ("FAIL" if FAILURES else "PASS"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
