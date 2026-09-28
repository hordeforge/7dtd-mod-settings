#!/usr/bin/env python3
"""Prove every shipped XPath patch actually applied, from the running game's own config.

A clean log is not evidence that a patch matched: an XPath that selects
nothing applies silently and logs nothing. A mod upstream of this template was
bitten by exactly that: four `progression.xml` appends were no-ops until the
`crafting_skills` container was added to their paths, with a clean log
throughout.

The engine dumps its fully patched configuration to a `ConfigsDump` directory
inside the save game on every game start, and annotates each patched-in element
with the mod that contributed it. Comparing what this mod's `Config/` asks for
against what the dump actually contains turns "no errors" into a positive check.

Usage:
    scripts/verify-patched-config.py                     # newest smoke world
    scripts/verify-patched-config.py --save-name NAME
    scripts/verify-patched-config.py --configs-dump DIR
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from local_env import game_dir, local_env_value, mod_dir, mod_name

# The Proton prefix layout, from docs/reference/environment.md. Steam AppID
# 251570 is 7 Days to Die; the user directory name is Steam's own default.
GAME_STEAM_APP_ID = "251570"
STEAM_USER = "steamuser"
PREFIX_SAVES = os.path.join(
    "compatdata", GAME_STEAM_APP_ID, "pfx", "drive_c", "users", STEAM_USER,
    "AppData", "Roaming", "7DaysToDie", "Saves")
SAVES_DIR_KEY = "SEVEN_DAYS_TO_DIE_SAVES_DIR"

MOD_DIR = str(mod_dir())
MOD_NAME = mod_name()

APPENDED_BY = re.compile(r'appended by:\s*"([^"]+)"')

# The ops that put a new element into the vanilla file. An insertBefore or
# insertAfter element is annotated in the dump exactly as an appended one is,
# so counting only <append> would expect fewer elements than the dump
# attributes to this mod and report a mismatch that is not there.
INSERT_OPS = frozenset({"append", "insertBefore", "insertAfter"})


class VerifyError(RuntimeError):
    pass


def expected_elements() -> dict[str, int]:
    """Count the elements this mod's Config/ appends, per target file."""
    counts: dict[str, int] = {}
    config_dir = os.path.join(MOD_DIR, "Config")
    # rglob, matching the engine: XmlPatcher loads "<mod>/Config/" + the
    # vanilla file's own relative name, so the XUi patches live a directory
    # down (Config/XUi_InGame/windows.xml) and a flat scan would silently
    # skip them — the same reason validate-xml-targets.py uses rglob.
    for path in sorted(glob.glob(os.path.join(config_dir, "**", "*.xml"), recursive=True)):
        try:
            tree = ET.parse(path)
        except ET.ParseError as exc:
            raise VerifyError(f"{path} is not well-formed XML: {exc}") from exc
        # Counting the children as they come, not `len(list(append))`: the
        # list is a full copy of every appended element's children, held for
        # nothing.
        total = sum(1 for op in tree.getroot().iter()
                    if op.tag in INSERT_OPS for _ in op)
        if total:
            counts[os.path.relpath(path, config_dir).replace(os.sep, "/")] = total
    return counts


def applied_elements(dump_dir: str) -> dict[str, int]:
    """Count elements the dump attributes to this mod, per file."""
    counts: dict[str, int] = {}
    # The dump mirrors Data/Config's subdirectories (ConfigsDump/
    # XUi_InGame/windows.xml), so the scan must descend too or every nested
    # patch reads as missing.
    for path in sorted(glob.glob(os.path.join(dump_dir, "**", "*.xml"), recursive=True)):
        # A dumped config file runs to tens of megabytes, and `findall` over
        # it materializes a string for every element any mod appended, of
        # which this mod's are a handful. `finditer` is the same scan without
        # that list.
        with open(path, encoding="utf-8", errors="replace") as handle:
            hits = sum(1 for match in APPENDED_BY.finditer(handle.read())
                       if match.group(1) == MOD_NAME)
        if hits:
            counts[os.path.relpath(path, dump_dir).replace(os.sep, "/")] = hits
    return counts


def saves_dir(game_dir: str) -> str:
    """Where the engine writes saves, from the inventory or the install path.

    Same precedence as every other inventory key: an exported
    `SEVEN_DAYS_TO_DIE_SAVES_DIR` wins, then the same key in `.local.env`,
    then the Proton prefix derived from the game install.
    """
    configured = os.environ.get(SAVES_DIR_KEY) or local_env_value(SAVES_DIR_KEY)
    if configured:
        return configured
    marker = os.path.join("steamapps", "common") + os.sep
    if marker not in game_dir:
        raise VerifyError(
            f"cannot derive the saves directory from {game_dir}; set "
            f"{SAVES_DIR_KEY} to the saves root (see .local.env.example).")
    return os.path.join(game_dir.split(marker)[0], PREFIX_SAVES)


def find_dump(game_dir: str, save_name: str) -> str:
    saves = saves_dir(game_dir)
    pattern = os.path.join(saves, "*", save_name if save_name else "*", "ConfigsDump")
    candidates = [p for p in glob.glob(pattern) if os.path.isdir(p)]
    if not candidates:
        raise VerifyError(
            f"no ConfigsDump found under {saves}. Load a world first — the engine "
            "writes the dump on game start."
        )
    return max(candidates, key=os.path.getmtime)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configs-dump", default="", help="use this ConfigsDump directory")
    parser.add_argument("--save-name", default="", help="save whose dump to check")
    parser.add_argument("--game-dir", default=game_dir() or "")
    args = parser.parse_args()

    dump = args.configs_dump or find_dump(args.game_dir, args.save_name)
    print("CONFIGS DUMP")
    print(f"  {dump}")
    print()

    expected = expected_elements()
    applied = applied_elements(dump)

    print("PATCHED ELEMENTS")
    print(f"  {'file':<22} {'shipped':>8} {'applied':>8}")
    failures = []
    for filename in sorted(set(expected) | set(applied)):
        want = expected.get(filename, 0)
        got = applied.get(filename, 0)
        flag = "" if want == got else "   <-- MISMATCH"
        print(f"  {filename:<22} {want:>8} {got:>8}{flag}")
        if want != got:
            failures.append(
                f"{filename}: Config/ appends {want} element(s) but the running game "
                f"has {got} attributed to {MOD_NAME}"
            )
    print()

    print("RESULT")
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        print()
        print("  A patch that selects nothing applies silently, so this is the check")
        print("  that a clean log cannot give you.")
        return 1
    total = sum(applied.values())
    print(f"  PASS: all {total} shipped patch elements are present in the running")
    print("        game's own configuration.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except VerifyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
