#!/usr/bin/env python3
"""AGENTS.md keeps the full shared-checkout worktree rule.

A session once ran `git checkout -b` / `git checkout main` / `git branch -D`
in a shared hordeforge clone and destroyed another session's commit; it
survived only because the object was still in the object store. The rule
that came out of it — take a `git worktree` per unit of work, never switch
branches in a shared clone — cannot be enforced against git behaviour from
here, so this gate enforces the next best deterministic thing: the file
agents read carries the exact worktree commands and the complete list of
banned operations. A file that silently loses the rule is how the next
session repeats the incident. (CLAUDE.md is `@AGENTS.md`, so one file
suffices.)
"""

from __future__ import annotations

import os
import sys

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUIRED_ELEMENTS = (
    "git branch -D",
    "git checkout",
    "git switch",
    "worktree add",
)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print("PASS " + name)
        return
    FAILURES.append(name)
    print("FAIL " + name + (": " + detail if detail else ""), file=sys.stderr)


def missing_elements(text: str) -> list[str]:
    return [item for item in REQUIRED_ELEMENTS if item not in text]


def main() -> int:
    fixture = "Never git checkout or git switch in a shared clone."
    check(
        "negative control: a rule without the worktree commands fails",
        missing_elements(fixture) == ["git branch -D", "worktree add"],
        repr(missing_elements(fixture)),
    )

    path = os.path.join(MOD_DIR, "AGENTS.md")
    if not os.path.isfile(path):
        check("AGENTS.md exists", False, "missing")
    else:
        with open(path, encoding="utf-8") as handle:
            gone = missing_elements(handle.read())
        check("AGENTS.md states the full shared-checkout worktree rule",
              gone == [], "missing " + repr(gone))

    print("RESULT " + ("FAIL" if FAILURES else "PASS"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
