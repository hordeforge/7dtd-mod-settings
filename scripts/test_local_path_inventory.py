#!/usr/bin/env python3
"""Check the machine-local path inventory contract.

AGENTS.md documents the complete .local.env key inventory (so an agent
reads the file instead of searching the host, and records supplied paths
immediately), and .gitignore keeps the file out of the repo.
"""

from __future__ import annotations

from pathlib import Path

MOD_DIR = Path(__file__).resolve().parent.parent
REQUIRED_KEYS = (
    "SEVEN_DAYS_TO_DIE_DIR",
    "SEVEN_DAYS_TO_DIE_SERVER_DIR",
    "HORDEFORGE_ROOT",
    "PLAYTEST_ROOT",
    "CONNECT_ROOT",
    "ASSET_PIPELINE_ROOT",
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
    if missing:
        print("FAIL local path inventory contract: " + ", ".join(missing))
        return 1
    broken_rules = agent_rules.replace('PLAYTEST_ROOT="', 'PLAYTEST_ROOT_MISSING="', 1)
    if "PLAYTEST_ROOT" not in missing_contract_elements(broken_rules, ignore_rules):
        print("FAIL negative control accepted rules without PLAYTEST_ROOT")
        return 1
    print("PASS local path inventory contract and negative control")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
