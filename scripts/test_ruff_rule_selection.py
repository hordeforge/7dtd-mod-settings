#!/usr/bin/env python3
"""The ruff rule selection is the gate on this repo's real defects.

`pyproject.toml` selects ruff's groups; `scripts/lint-python.sh` runs it and
`.github/workflows/ci.yml` fails the build on its exit code, so a group that
leaves the list is a whole class of defect that can merge unseen. Deleting
`B` (bugbear) or `BLE` (blind except) silences the gate without touching a
line of code, and nothing else in the tree would notice. This gate holds the
list, and holds every ignore against a written reason, because an ignore with
no reason recorded is a rule that was switched off in a hurry and never came
back.

An ignore is allowed; a silent one is not. Each code in `ignore` has to be
named in the comment block directly above the `ignore` line, so the reason
travels with the code and the next reader knows what the exclusion buys.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result
from local_env import mod_dir

MOD_DIR = str(mod_dir())
PYPROJECT = os.path.join(MOD_DIR, "pyproject.toml")

# The defect-priority groups, one per line with what it catches. A group
# leaving this list is a deliberate, recorded decision, not an edit.
REQUIRED_GROUPS: dict[str, str] = {
    "E4": "imports, syntax, indentation",
    "E7": "statement-level errors",
    "E9": "syntax and IO errors",
    "E501": "line length",
    "F": "pyflakes: undefined and unused names",
    "I": "import order",
    "B": "bugbear: mutable defaults, zip strictness",
    "UP": "pyupgrade",
    "SIM": "simplifiable control flow",
    "RET": "return consistency",
    "C4": "comprehensions",
    "Q": "quote style",
    "PIE": "misc lints",
    "PLE": "pylint errors",
    "PLW": "pylint warnings",
    "RUF": "ruff-specific rules, including unused noqa",
    "PERF": "per-call performance traps",
    "G": "logging format",
    "ASYNC": "async correctness",
    "EXE": "shebang without the execute bit",
    "ARG": "unused arguments",
    "TID": "relative imports past the package",
    "PGH": "type: ignore without a code, and one that matches nothing",
    "BLE": "blind except",
    "A": "builtins shadowed by a module-level name",
}

# `select = [...]` and `ignore = [...]`, each a TOML array of bare strings.
ARRAY = re.compile(r"^(select|ignore)\s*=\s*\[(.*?)\]", re.DOTALL | re.MULTILINE)
ENTRY = re.compile(r'"([A-Z]+[0-9]*)"')


def read_config() -> str:
    with open(PYPROJECT, encoding="utf-8") as handle:
        return handle.read()


def lint_section(text: str) -> str:
    """The `[tool.ruff.lint]` block, or the whole file when the header is gone.

    Falling back keeps a renamed section a failure of the group checks below
    rather than an IndexError the runner would report as a crashed gate.
    """
    match = re.search(r"^\[tool\.ruff\.lint\]\s*$(.*?)(?=^\[|\Z)",
                      text, re.DOTALL | re.MULTILINE)
    return match.group(1) if match else text


def array_codes(section: str, key: str) -> list[str]:
    match = next((m for m in ARRAY.finditer(section) if m.group(1) == key), None)
    return ENTRY.findall(match.group(2)) if match else []


def reason_block(section: str) -> str:
    """The comment lines directly above the `ignore` line."""
    match = re.search(r"^(?P<comment>(?:#[^\n]*\n)+)ignore\s*=", section, re.MULTILINE)
    return match.group("comment") if match else ""


def main() -> int:
    if not os.path.isfile(PYPROJECT):
        check("pyproject.toml exists", False, PYPROJECT)
        return result()

    section = lint_section(read_config())
    check("pyproject.toml has a [tool.ruff.lint] section",
          "[tool.ruff.lint]" in read_config())

    selected = array_codes(section, "select")
    missing = sorted(set(REQUIRED_GROUPS) - set(selected))
    check("every defect-priority ruff group is selected",
          not missing,
          "missing: " + ", ".join(f"{code} ({why})" for code, why in REQUIRED_GROUPS.items()
                                   if code in missing)
          + " -- a group that leaves the list silences that class of defect")

    ignored = array_codes(section, "ignore")
    reasons = reason_block(section)
    unreasoned = [code for code in ignored if code not in reasons]
    check("every ignored ruff rule has a written reason",
          not unreasoned,
          "no reason names: " + ", ".join(unreasoned)
          + f" -- say what excluding {unreasoned[0]} buys in the comment above `ignore`"
          if unreasoned else "")

    # A group is a prefix, so a group can be silenced by a code inside it.
    # The recorded ignore list is small and deliberate; nothing may join it.
    check("the ignore list stays small and deliberate", len(ignored) <= 5,
          f"{len(ignored)} codes ignored: {', '.join(ignored)}")

    return result()


if __name__ == "__main__":
    sys.exit(main())
