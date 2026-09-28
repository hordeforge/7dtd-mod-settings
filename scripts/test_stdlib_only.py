#!/usr/bin/env python3
"""No third-party Python dependency can enter the tree undeclared.

The mod's gates run on the contributor's interpreter with nothing installed:
`uv.lock` resolves a virtual project with no dependencies, and CI installs
only the pinned ruff and mypy it lints with. That is the cheapest supply
chain a Python tree can have, and it is a claim nothing enforced, so one
`import requests` in a gate would install with the next contributor's
`pip install` and run there and nowhere else.

This gate reads the imports of every tracked *.py and fails on a top-level
name that is neither a stdlib module nor a module in this tree. Adding a
real dependency is allowed and is a decision to make on purpose, not a
refusal: declare it in pyproject.toml, take the install with it, and add the
name to EXEMPT.

Stdlib-only, tracked files only via `git ls-files`, sorted deterministic
output, and a negative control proving the detector can fail, against a
fixture source string inside this file and never the shared tree.
"""

from __future__ import annotations

import ast
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result
from git_tracked import tracked_paths
from local_env import mod_dir

MOD_DIR = str(mod_dir())

# Third-party names this tree is allowed to import, each with the manifest
# entry that declares it. Empty by design: nothing is installed here.
EXEMPT: dict[str, str] = {}


def tracked_py() -> list[str]:
    """Every tracked *.py under this mod, sorted — never filesystem order."""
    return tracked_paths("*.py")


def in_tree_modules() -> set[str]:
    """Top-level names a local import can resolve to inside this mod.

    Read off the filesystem, not `git ls-files`: a module a working tree
    just gained is a local import, and reading the index instead reported
    it as a third-party dependency until it was committed. The files this
    gate *scans* are still the tracked ones, so an untracked scratch file
    can neither add a dependency nor hide one.

    An installed package tree is not this mod's source, though: every
    directory leaf and every module stem below one is absorbed as an
    in-tree name, so a `.venv` under the checkout (the uv workflow's
    default) would make `import requests` in a gate pass this gate, and the
    negative control below would stop detecting it too.
    """
    names: set[str] = set()
    for base, dirs, files in os.walk(MOD_DIR):
        dirs[:] = [d for d in dirs
                   if d not in {"__pycache__", "node_modules", ".venv", "venv",
                                "bin", "build", "dist", "obj", ".git", ".tmp",
                                ".mypy_cache", ".ruff_cache", ".pytest_cache",
                                ".shamway", ".scratch"}]
        rel = os.path.relpath(base, MOD_DIR).split(os.sep)
        if rel != ["."]:
            names.update(rel)
        for name in files:
            if name.endswith(".py"):
                names.add(name[:-3])
    return names


def imported_names(source: str) -> set[str]:
    """The top-level module names `source` imports, relative imports aside."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name.partition(".")[0] for alias in node.names)
        elif (isinstance(node, ast.ImportFrom)
              and not node.level and node.module):
            found.add(node.module.partition(".")[0])
    return found


def read(*parts: str) -> str:
    with open(os.path.join(MOD_DIR, *parts), encoding="utf-8") as handle:
        return handle.read()


def main() -> int:
    allowed = sys.stdlib_module_names | {"__future__"} | in_tree_modules() | set(EXEMPT)

    # A negative control: without it a gate that never looks at anything
    # passes forever, which is the one outcome this gate exists to prevent.
    check("negative-control-detects-a-third-party-import",
          imported_names("import yaml\nfrom lxml import etree\n") - allowed
          == {"lxml", "yaml"})

    files = tracked_py()
    check("tracked-python-files-are-listed", bool(files))
    for path in files:
        try:
            source = read(path)
        except OSError as error:
            check("reads:" + path, False, str(error))
            continue
        foreign = sorted(imported_names(source) - allowed)
        check("stdlib-or-local-imports:" + path, not foreign,
              f"undeclared third-party import(s): {', '.join(foreign)}")

    return result()


if __name__ == "__main__":
    sys.exit(main())
