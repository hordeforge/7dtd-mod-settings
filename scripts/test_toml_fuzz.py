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
deciding whether the body decodes. A third pass stands the same values up as
log records: what `ModTomlPath.ForLog` writes is one line, an ordinary value
is logged as itself, and its escapes decode back to the value they stand for,
because a mod's name and a telnet session's words reach the game log through
that one function. Run by scripts/run-offline-tests.sh; the
seed and case count are fixed, so the report is identical on two runs. The dotnet
SDK it compiles the harness with is resolved as `make build` resolves it
(`PATH`, then `DOTNET_ROOT`).

A failing run prints the seed it drew, and the seed is replayable from here
without editing the harness: `scripts/test_toml_fuzz.py -- --seed <hex>
[--iterations <n>]` runs the harness on that seed alone. Without the seed in
the report a failing case is a shape of input nobody can get back to, and
with no way to pass one in, a seed that found a case could only be replayed
by rebuilding the harness with the constant changed.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from dotnet_host import run_harness
from gate_report import check, result

TOML_FUZZ_FAILURE = "toml fuzz invariants"

# What the harness itself takes. Anything else is refused here rather than
# passed on, so a mistyped replay says what is wrong instead of running the
# whole suite and looking like a seed that found nothing.
OPTIONS = ("--seed", "--iterations")


def replay_args(argv: list[str]) -> tuple[list[str], str]:
    """The harness options a replay asked for, and why not if it asked wrongly."""
    args = list(argv)
    if "--" in args:
        args = args[args.index("--") + 1 :]
    for i in range(0, len(args), 2):
        if args[i] not in OPTIONS:
            return [], f"unknown option: {args[i]}"
        if i + 1 >= len(args):
            return [], f"{args[i]} takes a value"
    return args, ""


def main() -> int:
    args, error = replay_args(sys.argv[1:])
    if error:
        check("a replay names an option the harness takes", False, error)
        return result()
    if args:
        print("replaying toml_fuzz with " + " ".join(args))
    return run_harness("toml_fuzz", TOML_FUZZ_FAILURE, *args)


if __name__ == "__main__":
    sys.exit(main())
