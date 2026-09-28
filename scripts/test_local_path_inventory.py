#!/usr/bin/env python3
"""Check the machine-local path inventory contract.

AGENTS.md documents the complete .local.env key inventory (so an agent
reads the file instead of searching the host, and records supplied paths
immediately), and .gitignore keeps the file out of the repo.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import FAILURES, check
from local_env import mod_dir

MOD_DIR = mod_dir()
REQUIRED_KEYS = (
    "SEVEN_DAYS_TO_DIE_DIR",
    "SEVEN_DAYS_TO_DIE_SERVER_DIR",
    "HORDEFORGE_ROOT",
    "PLAYTEST_ROOT",
    "CONNECT_ROOT",
    "ASSET_PIPELINE_ROOT",
    "WRENCH_ATOMIC_MOD_DIR",
    "DOTNET_ROOT",
    "ILSPYCMD",
    "UNITY_EDITOR",
)

# Optional overrides the shell targets read; a key that exists in code but
# in no documented inventory is one a machine can set and never discover.
DOCUMENTED_OPTIONAL_KEYS = (
    "SEVEN_DAYS_TO_DIE_SERVER_APP_ID",
    "SEVEN_DAYS_TO_DIE_SERVER_RUN_SECONDS",
    "SEVEN_DAYS_TO_DIE_SERVER_CONFIG",
    "SEVEN_DAYS_TO_DIE_STEAMCMD",
    "SEVEN_DAYS_TO_DIE_STEAMCMD_DIR",
)


def missing_contract_elements(agent_rules: str, ignore_rules: str) -> list[str]:
    missing = [key for key in REQUIRED_KEYS if f'{key}="' not in agent_rules]
    if ".local.env" not in ignore_rules:
        missing.append(".local.env ignore")
    return missing


def main() -> int:
    agent_rules = (MOD_DIR / "AGENTS.md").read_text(encoding="utf-8")
    ignore_rules = (MOD_DIR / ".gitignore").read_text(encoding="utf-8")
    missing = missing_contract_elements(agent_rules, ignore_rules)
    check(
        "local path inventory contract",
        not missing,
        ", ".join(missing),
    )
    broken_rules = agent_rules.replace('PLAYTEST_ROOT="', 'PLAYTEST_ROOT_MISSING="', 1)
    check(
        "negative control rejects rules without PLAYTEST_ROOT",
        "PLAYTEST_ROOT" in missing_contract_elements(broken_rules, ignore_rules),
        "negative control accepted rules without PLAYTEST_ROOT",
    )

    # .local.env.example is the authoritative list a machine copies
    # (docs/reference/environment.md); AGENTS.md's prose is the index.
    example = (MOD_DIR / ".local.env.example").read_text(encoding="utf-8")
    environment_doc = (MOD_DIR / "docs" / "reference" / "environment.md").read_text(
        encoding="utf-8")
    undocumented = [key for key in REQUIRED_KEYS + DOCUMENTED_OPTIONAL_KEYS
                    if f'{key}="' not in example]
    check(
        ".local.env.example carries the full inventory",
        not undocumented,
        ", ".join(undocumented),
    )
    undeclared = [key for key in DOCUMENTED_OPTIONAL_KEYS
                  if key not in environment_doc]
    check(
        "the optional server overrides are documented in "
        "docs/reference/environment.md",
        not undeclared,
        ", ".join(undeclared),
    )
    print("RESULT " + ("FAIL" if FAILURES else "PASS"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
