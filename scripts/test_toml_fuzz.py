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
inside the mod folder. A second pass mutates the file's bytes rather than
its text, the level a downloaded modlet actually arrives in, and asserts
that a file this mod can read it can also write back byte for byte mark
included, that an invalid byte is refused in every marked encoding and not
only the unmarked one, and that the mark picks the encoding without
deciding whether the body decodes. Run by scripts/run-offline-tests.sh; the
seed and case count are fixed, so the report is identical on two runs. The dotnet
SDK it compiles the harness with is resolved as `make build` resolves it
(`PATH`, then `DOTNET_ROOT`).
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
