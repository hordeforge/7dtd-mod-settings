#!/usr/bin/env python3
"""The lint toolchain's versions are written down once, in pyproject.toml.

A pin copied into the workflow, the README or a script is a pin that drifts:
CI installs a version, a contributor installs another, and the failure lands
after the push instead of before it. This gate holds the pins in the dev group
of pyproject.toml, and fails when a version is repeated anywhere else.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result
from git_tracked import tracked_paths

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(MOD_DIR, "scripts")
PYPROJECT = "pyproject.toml"
LOCK = "uv.lock"
# `git ls-files` reads one index and exits; a git that never answers must not
# hold this gate open.
GIT_LIST_TIMEOUT_SECONDS = 60

# The tools scripts/lint-python.sh refuses to start without.
REQUIRED_TOOLS = ("ruff", "mypy")

# The distributions those two pull in. uv.lock pins them; a version restated
# in another file is a second version that drifts from the lock, so the
# drift check below covers the closure, not only the two tools.
TRANSITIVE = ("mypy_extensions", "typing_extensions", "pathspec", "librt", "ast-serialize", "tomli")
PINNED_NAMES = REQUIRED_TOOLS + TRANSITIVE

# A pin: `tool==version`, with or without extras or an environment marker.
PIN = re.compile(r"\b([A-Za-z][A-Za-z0-9._-]*)==[^\s\"']+")

# What an acceptable pin looks like: an exact version, optionally followed
# by the environment marker that scopes it to some interpreters.
EXACT = re.compile(r"([A-Za-z][A-Za-z0-9._-]*)==\d+(\.\d+)+;?")

# Tracked text files a pin could hide in. Anything else is binary, a build
# output or an image, none of which a contributor reads instructions from.
TEXT_SUFFIXES = (
    ".md",
    ".txt",
    ".toml",
    ".yml",
    ".yaml",
    ".sh",
    ".py",
    ".cfg",
    ".cs",
    ".csproj",
    ".xml",
    ".json",
)


def read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def tracked_text_files() -> list[str]:
    """Every tracked text file the drift check reads.

    A path the working tree no longer holds is left out: `git ls-files` still
    lists a file between the delete and the commit that records it, and
    reading it then raises instead of reporting a verdict. A listing that
    could not be read is a `SystemExit` from the shared reader, not an
    empty list: a drift check that walked nothing finds nothing.
    """
    return sorted(
        name
        for name in tracked_paths()
        if (name.endswith(TEXT_SUFFIXES) or name == "Makefile")
        and os.path.isfile(os.path.join(MOD_DIR, name))
    )


def pinned(text: str) -> dict[str, str]:
    return {
        match.group(1): match.group(0)
        for match in PIN.finditer(text)
        if match.group(1) in PINNED_NAMES
    }


def dev_group(text: str) -> str:
    """The `[dependency-groups]` table of pyproject.toml, as text.

    Read with a pattern, not tomllib: the gate runs on the 3.10 floor, which
    has no TOML parser in the stdlib.
    """
    match = re.search(r"^\[dependency-groups\]\n(.*?)(?=^\[|\Z)", text, re.M | re.S)
    return match.group(1) if match else ""


def main() -> int:
    pyproject = read(os.path.join(MOD_DIR, PYPROJECT))
    declared = pinned(dev_group(pyproject))
    check(
        "every lint tool is pinned in the dev group of pyproject.toml",
        all(tool in declared for tool in REQUIRED_TOOLS),
        "missing: " + ", ".join(t for t in REQUIRED_TOOLS if t not in declared),
    )
    for tool in REQUIRED_TOOLS:
        check(
            f"{tool} is pinned to an exact version",
            EXACT.fullmatch(declared.get(tool, "")) is not None,
            f"{tool} is not pinned to an exact version",
        )
    lock = os.path.join(MOD_DIR, LOCK)
    check(f"{LOCK} exists", os.path.isfile(lock), f"run `uv lock` and commit {LOCK}")

    makefile = read(os.path.join(MOD_DIR, "Makefile"))
    check(
        "make lint-python installs the dev group from uv.lock",
        re.search(r"^lint-python:\n\tuv run --locked \S*lint-python\.sh", makefile, re.M)
        is not None,
        "the lint-python recipe must run scripts/lint-python.sh through `uv run --locked`",
    )

    workflow = read(os.path.join(MOD_DIR, ".github", "workflows", "ci.yml"))
    check(
        "CI runs the lint through make lint-python",
        re.search(r"^\s+run: make lint-python$", workflow, re.M) is not None,
        "the workflow must run `make lint-python`, not install inline pins",
    )

    lint_script = read(os.path.join(SCRIPTS, "lint-python.sh"))
    check(
        "the missing-tool error names the install command",
        "uv run --locked" in lint_script,
        "scripts/lint-python.sh must print how to run with the pinned tools",
    )

    readme = read(os.path.join(MOD_DIR, "README.md"))
    check(
        "README points at the dev group",
        "`dev` group" in readme and PYPROJECT in readme,
        "README must name the dev group in pyproject.toml instead of listing versions",
    )

    # uv is the project's only Python toolchain (AGENTS.md, "Python
    # Toolchain"). An install path that reaches for pip is a second answer
    # to "how do I get the toolchain" and a second resolver behind the pins,
    # so the repository states one installer everywhere it states the other.
    pip_users = {
        name: lines
        for name in tracked_text_files()
        if (
            lines := re.findall(
                r"(?<!uv )\bpip install\b[^\n]*-r\b[^\n]*", read(os.path.join(MOD_DIR, name))
            )
        )
    }
    check(
        "no tracked file installs the toolchain with pip",
        not pip_users,
        "; ".join(f"{name}: {lines[0].strip()}" for name, lines in sorted(pip_users.items()))
        + " -- run the toolchain through uv",
    )

    # The drift check itself: no other tracked text file states a version for
    # a pinned distribution, so there is no second place to update and no
    # second place to forget.
    stray = {
        name: found
        for name in tracked_text_files()
        if name != PYPROJECT and (found := pinned(read(os.path.join(MOD_DIR, name))))
    }
    check(
        "no tracked file restates a pinned toolchain version",
        not stray,
        "; ".join(
            f"{name}: {', '.join(sorted(found.values()))}" for name, found in sorted(stray.items())
        )
        + f" -- state it in {PYPROJECT} only",
    )

    return result()


if __name__ == "__main__":
    sys.exit(main())
