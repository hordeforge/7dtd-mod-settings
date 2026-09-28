#!/usr/bin/env python3
"""The offline suite's Python floor is stated once and checked everywhere.

A contributor on an older interpreter gets an ImportError from whichever
test happens to use a newer stdlib feature, named in terms of a module they
never touched. The floor is what pyproject.toml's mypy runs against, what
scripts/run-offline-tests.sh refuses to start under, and what README tells
the contributor to install; this gate holds the three to the same number and
fails loudly when the interpreter running the suite is below it.
"""

from __future__ import annotations

import os
import re
import sys

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(MOD_DIR, "scripts", "run-offline-tests.sh")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import FAILURES, check  # noqa: E402


def pyproject_floor(text: str) -> tuple[int, ...]:
    match = re.search(r'^python_version = "(\d+)\.(\d+)"$', text, re.MULTILINE)
    if match is None:
        return ()
    return (int(match.group(1)), int(match.group(2)))


def main() -> int:
    with open(os.path.join(MOD_DIR, "pyproject.toml"), encoding="utf-8") as handle:
        floor = pyproject_floor(handle.read())
    check("pyproject.toml states a Python floor for mypy", bool(floor))
    if not floor:
        print(f"{len(FAILURES)} failures.")
        return 1

    needed = f"{floor[0]}.{floor[1]}"
    check("the interpreter running the suite is the stated floor or newer",
          sys.version_info[:2] >= floor,
          f"need Python {needed}+, running "
          f"{sys.version_info[0]}.{sys.version_info[1]}")

    with open(RUNNER, encoding="utf-8") as handle:
        runner = handle.read()
    check("the test runner refuses to start below the floor, by name",
          re.search(r'^MIN_PY="(\d+\.\d+)"$', runner, re.MULTILINE) is not None
          and "Python $MIN_PY+ required" in runner)
    check("the runner's floor is the one pyproject states",
          f'MIN_PY="{needed}"' in runner,
          f'run-offline-tests.sh must pin MIN_PY="{needed}"')

    with open(os.path.join(MOD_DIR, "README.md"), encoding="utf-8") as handle:
        readme = handle.read()
    check("README states the Python floor", f"Python {needed}+" in readme)

    print(f"{len(FAILURES)} failures.")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
