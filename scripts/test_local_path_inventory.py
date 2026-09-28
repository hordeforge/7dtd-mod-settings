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
    print("RESULT " + ("FAIL" if FAILURES else "PASS"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
