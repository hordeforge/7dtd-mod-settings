#!/usr/bin/env python3
"""The lint toolchain's versions are written down once, in requirements-dev.txt.

A pin copied into the workflow, the README or a script is a pin that drifts:
CI installs a version, a contributor installs another, and the failure lands
after the push instead of before it. This gate holds the pins in the one file
that owns them, and fails when a version is repeated anywhere else.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(MOD_DIR, "scripts")
REQUIREMENTS = "requirements-dev.txt"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import FAILURES, check  # noqa: E402

# The tools scripts/lint-python.sh refuses to start without.
REQUIRED_TOOLS = ("ruff", "mypy")

# A pin: `tool==version`, with or without extras or an environment marker.
PIN = re.compile(r"\b([A-Za-z][A-Za-z0-9._-]*)==[^\s\"']+")

# Tracked text files a pin could hide in. Anything else is binary, a build
# output or an image, none of which a contributor reads instructions from.
TEXT_SUFFIXES = (".md", ".txt", ".toml", ".yml", ".yaml", ".sh", ".py", ".cfg",
                 ".cs", ".csproj", ".xml", ".json")


def read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def tracked_text_files() -> list[str]:
    """Every tracked text file the drift check reads.

    A path the working tree no longer holds is left out: `git ls-files` still
    lists a file between the delete and the commit that records it, and
    reading it then raises instead of reporting a verdict.
    """
    listing = subprocess.run(["git", "ls-files"], cwd=MOD_DIR, capture_output=True,
                             text=True, encoding="utf-8", errors="replace", check=False)
    return sorted(name for name in listing.stdout.splitlines()
                  if (name.endswith(TEXT_SUFFIXES) or name in ("Makefile", REQUIREMENTS))
                  and os.path.isfile(os.path.join(MOD_DIR, name)))


def pinned(text: str) -> dict[str, str]:
    return {match.group(1): match.group(0) for match in PIN.finditer(text)
            if match.group(1) in REQUIRED_TOOLS}


def main() -> int:
    requirements = os.path.join(MOD_DIR, REQUIREMENTS)
    check("requirements-dev.txt exists", os.path.isfile(requirements))
    if FAILURES:
        print(f"{len(FAILURES)} failures.")
        return 1

    declared = pinned(read(requirements))
    check("every lint tool is pinned in requirements-dev.txt",
          all(tool in declared for tool in REQUIRED_TOOLS),
          "missing: " + ", ".join(t for t in REQUIRED_TOOLS if t not in declared))
    for tool in REQUIRED_TOOLS:
        check(f"{tool} is pinned to an exact version",
              re.fullmatch(rf"{tool}==\d+(\.\d+)+", declared.get(tool, "")) is not None,
              f"{tool} is not pinned to an exact version")

    workflow = read(os.path.join(MOD_DIR, ".github", "workflows", "ci.yml"))
    check("CI installs the pinned toolchain from requirements-dev.txt",
          re.search(r"pip install[^\n]*-r\s+" + REQUIREMENTS, workflow) is not None,
          "the workflow must install " + REQUIREMENTS + ", not inline pins")

    lint_script = read(os.path.join(SCRIPTS, "lint-python.sh"))
    check("the missing-tool error names the install command",
          REQUIREMENTS in lint_script and "python3 -m pip install" in lint_script,
          "scripts/lint-python.sh must print how to install the missing tool")

    readme = read(os.path.join(MOD_DIR, "README.md"))
    check("README points at requirements-dev.txt", REQUIREMENTS in readme,
          "README must name " + REQUIREMENTS + " instead of listing versions")

    # The drift check itself: no other tracked text file states a version for
    # a lint tool, so there is no second place to update and no second place
    # to forget.
    stray = {name: found for name in tracked_text_files() if name != REQUIREMENTS
             and (found := pinned(read(os.path.join(MOD_DIR, name))))}
    check("no tracked file restates a lint tool's version",
          not stray,
          "; ".join(f"{name}: {', '.join(sorted(found.values()))}"
                    for name, found in sorted(stray.items()))
          + f" -- state it in {REQUIREMENTS} only")

    print(f"{len(FAILURES)} failures.")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
