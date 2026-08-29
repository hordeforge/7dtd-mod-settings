#!/usr/bin/env python3
"""Structural proof of the TOML settings contract.

The mod's runtime settings are Config/<Mod>.toml, read by the DLL itself:
applied at InitMod, re-read on save without a restart (UnityUpdate watch,
debounced), reset-to-defaults-then-apply, and a broken save keeps the
current values. The console command shares the value grammar via TrySet.
This gate holds those source-level contracts so a refactor cannot quietly
drop one; the live behavior itself is proven in game.

A mod without src/ has no settings reader; the gate passes with a note.
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The checkout is named after the repo slug, not the mod; ModInfo.xml is
# the authority (test_static_checks.py holds it to the build tooling).
MOD_NAME = next(
    p.get("value") or ""
    for p in ET.parse(os.path.join(MOD_DIR, "ModInfo.xml")).getroot()
    if p.tag == "Name")
SRC = os.path.join(MOD_DIR, "src", MOD_NAME)

FAILURES: list[str] = []


def check(name: str, ok: bool) -> None:
    if ok:
        print("PASS " + name)
    else:
        FAILURES.append(name)
        print("FAIL " + name, file=sys.stderr)


def main() -> int:
    if not os.path.isdir(SRC):
        print("no src/ directory; no settings reader to hold to the contract")
        return 0

    def read(name: str) -> str:
        path = os.path.join(SRC, name)
        if not os.path.isfile(path):
            return ""
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    settings = read("ModSettings.cs")
    api = read("ModApi.cs")
    toml_path = os.path.join(MOD_DIR, "Config", MOD_NAME + ".toml")

    check("the shipped settings TOML exists beside its reader",
          os.path.isfile(toml_path))
    check("ModSettings reads the TOML through the shared TrySet grammar",
          "TomlSettings.TryRead" in settings
          and "TrySet(entries[i].Name, entries[i].Value" in settings)
    check("a save is picked up on UnityUpdate without a Harmony patch",
          "ModEvents.UnityUpdate.RegisterHandler" in api
          and "ModSettings.Poll()" in api
          and "FilePollIntervalSeconds" in settings
          and "FileReloadDebounceSeconds" in settings
          and "SdFile.GetLastWriteTimeUtc" in settings)
    check("reload resets to defaults then applies the file",
          "ResetToDefaults();" in settings
          and '"reload " + RelativePath' in settings)
    check("a failed re-read keeps the current values",
          "keeping current settings" in settings)

    print(f"{len(FAILURES)} failures.")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
