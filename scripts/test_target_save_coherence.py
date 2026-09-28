#!/usr/bin/env python3
"""Structural proof of the Mod Settings screen's cached-file contract.

The screen keeps each mod's file text and its parsed entries in memory
(`TargetMod.Text` / `TargetMod.Entries`) and edits them in place by byte
offset. Two things must hold for that to be safe:

- a save is spliced into the file as it is *now*, not into the copy parsed
  when the screen opened, or a save made elsewhere in the meantime is
  silently overwritten (and a shifted file puts the edit on a neighbouring
  key);
- the "the mod re-read the file" observation is a one-shot latch scoped to
  the opening it was made in, or a line seen while the screen was closed
  stamps a freshly discovered mod as applied-live for a save that never
  happened.

Both are source-level contracts here: the behavior is proven live by the
`wrench-mod-settings` suite, and the C# cannot be executed offline. This gate
holds the shape of the fix so a refactor cannot quietly drop it.

A mod without src/ has no screen; the gate passes with a note.
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


def read(name: str) -> str:
    path = os.path.join(SRC, name)
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def body(source: str, signature: str) -> str:
    """The `{ ... }` block that follows a method signature, braces counted.

    String literals in these files hold no braces, so a plain count is enough
    and keeps the gate free of a C# parser it would otherwise need.
    """
    start = source.find(signature)
    if start < 0:
        return ""
    brace = source.find("{", start + len(signature))
    if brace < 0:
        return ""
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace:index + 1]
    return ""


def main() -> int:
    if not os.path.isdir(SRC):
        print("no src/ directory; no Mod Settings screen to hold to the contract")
        return 0

    target = read("TargetMod.cs")
    screen = read("ModSettingsScreen.cs")

    save = body(target, "public bool TrySave(")
    check("a save re-reads the file before splicing into it",
          "TryRead(" in save and "currentText != Text" in save)
    check("a file that moved on is re-read before the entry is located again",
          "Reload();" in save and "TryRelocate(" in save)

    relocate = body(target, "bool TryRelocate(")
    check("the key is located by name, not by the offset it used to have",
          "Entries[i].Name != stale.Name" in relocate)
    check("a key that is gone is refused, not written to",
          "no longer in the file" in relocate and "found == null" in relocate)
    check("a key that is now ambiguous is refused, not guessed at",
          "more than once" in relocate)

    probe = body(target, "static bool HasSettingsComponent(")
    check("one unloadable assembly does not take the settings list down",
          "catch (Exception)" in probe and "continue;" in probe)

    opened = body(screen, "public override void OnOpen()")
    check("the reload latch does not survive the closing it was set in",
          "reloadSeen = false;" in opened and "watchedReloadMarker = null;" in opened)

    print(f"{len(FAILURES)} failures.")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
