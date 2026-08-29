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

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ModInfo Name == directory name (enforced by test_static_checks.py)
MOD_NAME = os.path.basename(MOD_DIR)

# Patches whose value depends on landing inside a specific parent. These are
# the ones a wrong-but-valid XPath would silently misplace.
# Placement-sensitive patches: (file, parent tag, parent name, regex the
# element must match inside that parent). A wrong-but-valid XPath lands an
# append in the wrong container silently; list such patches here, e.g.:
#   ("progression.xml", "crafting_skill", "craftingExplosives",
#    r'item="myModItem"'),
CONTAINER_EXPECTATIONS: tuple[tuple[str, str, str, str], ...] = ()

APPENDED_BY = re.compile(r'appended by:\s*"([^"]+)"')


def configured_game_dir() -> str:
    path = os.environ.get("SEVEN_DAYS_TO_DIE_DIR", "")
    env_file = os.path.join(MOD_DIR, ".local.env")
    if not path and os.path.isfile(env_file):
        with open(env_file, encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("SEVEN_DAYS_TO_DIE_DIR="):
                    path = line.split("=", 1)[1].strip().strip('"')
    return path


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
        total = sum(len(list(append)) for append in tree.getroot().iter("append"))
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
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            hits = sum(1 for name in APPENDED_BY.findall(handle.read()) if name == MOD_NAME)
        if hits:
            counts[os.path.relpath(path, dump_dir).replace(os.sep, "/")] = hits
    return counts


def check_containers(dump_dir: str) -> list[str]:
    """Verify the placement-sensitive patches landed in the right parent."""
    failures = []
    for filename, parent_tag, parent_name, pattern in CONTAINER_EXPECTATIONS:
        path = os.path.join(dump_dir, filename)
        if not os.path.exists(path):
            failures.append(f"{filename} is not in the dump")
            continue
        current = None
        found = False
        wrong_parent = None
        parent_re = re.compile(rf'<{parent_tag} name="([^"]+)"')
        target_re = re.compile(pattern)
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                match = parent_re.search(line)
                if match:
                    current = match.group(1)
                if target_re.search(line):
                    if current == parent_name:
                        found = True
                        break
                    # One item may be appended under several parents by
                    # design (the timed nuke unlocks at Explosives 65 and
                    # Electrician 45), so keep scanning for the expected one
                    # and only report the first wrong parent if none matches.
                    if wrong_parent is None:
                        wrong_parent = current
        if not found:
            if wrong_parent is not None:
                failures.append(
                    f"{filename}: {pattern!r} landed under "
                    f"{parent_tag} {wrong_parent!r}, expected {parent_name!r}"
                )
            elif not any(pattern in f for f in failures):
                failures.append(f"{filename}: {pattern!r} is not present at all")
    return failures


def find_dump(game_dir: str, save_name: str) -> str:
    saves = os.environ.get("SEVEN_DAYS_TO_DIE_SAVES_DIR")
    if not saves:
        if "/steamapps/common/" not in game_dir:
            raise VerifyError("cannot derive the saves directory; set SEVEN_DAYS_TO_DIE_SAVES_DIR.")
        steamapps = game_dir.split("/common/")[0]
        saves = os.path.join(
            steamapps, "compatdata", "251570", "pfx", "drive_c", "users", "steamuser",
            "AppData", "Roaming", "7DaysToDie", "Saves",
        )
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
    parser.add_argument("--game-dir", default=configured_game_dir())
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

    container_failures = check_containers(dump)
    print("PLACEMENT")
    if container_failures:
        for failure in container_failures:
            print(f"  FAIL  {failure}")
    else:
        print("  OK    no placement-sensitive patches declared, or all landed"
              " in their intended parents")
    print()

    failures += container_failures
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
    print(f"        game's own configuration, in their intended parents.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except VerifyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
