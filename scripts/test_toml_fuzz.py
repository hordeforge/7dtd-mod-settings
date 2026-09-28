#!/usr/bin/env python3
"""Seeded fuzz gate for the parser that reads another mod's settings file.

A modlet downloaded from anywhere carries its own `Config/<Mod>.toml`, and
that file is parsed inside the game process by the same reader the screen
edits with. Compiles src/Wrench/{TomlSettings,TomlEdit,ModTomlPath}.cs into
a net8 harness (scripts/toml_fuzz/, no game references) that mutates real
settings documents and asserts the invariants the screen depends on: the
reader never throws, a refusal always says why, captured spans re-parse to
their own value, an edit touches one value span and nothing else, what the
writer encodes reads back unchanged, and a mod name that resolves stays
inside the mod folder. Run by scripts/run-offline-tests.sh; the seed and
case count are fixed, so the report is identical on two runs.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from dotnet_host import run_harness

TOML_FUZZ_FAILURE = "toml fuzz invariants"


def main() -> int:
    return run_harness("toml_fuzz", TOML_FUZZ_FAILURE)


if __name__ == "__main__":
    sys.exit(main())
