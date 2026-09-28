#!/usr/bin/env python3
"""Structural proof of the Mod Settings screen's cached-file contract.

The screen keeps each mod's file text and its parsed entries in memory
(`TargetMod.Text` / `TargetMod.Entries`) and edits them in place by byte
offset. Three things must hold for that to be safe:

- a save is spliced into the file as it is *now*, not into the copy parsed
  when the screen opened, or a save made elsewhere in the meantime is
  silently overwritten (and a shifted file puts the edit on a neighbouring
  key);
- the save reaches the file without destroying it first: a truncating write
  leaves the mod with an unparsable or missing settings file if anything goes
  wrong between the truncate and the last byte, and a save made in the
  file's own encoding keeps every byte outside the edited value span, byte
  order mark included;
- the "the mod re-read the file" observation is a one-shot latch scoped to
  the opening it was made in, or a line seen while the screen was closed
  stamps a freshly discovered mod as applied-live for a save that never
  happened. The log callback runs off the Unity thread, so the marker and
  the latch share one lock;
- a save is written through a temp file and renamed over the destination, so
  the mod polling the file never reads a half-written one.

All three are source-level contracts here: the behavior is proven live by the
`wrench-mod-settings` suite, and the C# cannot be executed offline. This gate
holds the shape of the fix so a refactor cannot quietly drop it.

A mod without src/ has no screen; the gate passes with a note.
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import FAILURES, check
from local_env import mod_dir

MOD_DIR = str(mod_dir())
# The checkout is named after the repo slug, not the mod; ModInfo.xml is
# the authority (test_static_checks.py holds it to the build tooling).
MOD_NAME = next(
    p.get("value") or ""
    for p in ET.parse(os.path.join(MOD_DIR, "ModInfo.xml")).getroot()
    if p.tag == "Name")
SRC = os.path.join(MOD_DIR, "src", MOD_NAME)


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
    edit = read("TomlEdit.cs")

    save = body(target, "public bool TrySave(")
    check("a save re-reads the file before splicing into it",
          "TryRead(" in save and "currentText != Text" in save)
    check("a file that moved on is re-read before the entry is located again",
          "Reload();" in save and "TryRelocate(" in save)
    check("a save reads the file once, and takes its new state from the "
          "verified parse it already holds",
          save.count("TryRead(") == 1
          and "Text = newText;" in save
          and "Entries = newEntries;" in save)

    replace = body(edit, "public static bool TryReplaceValue(")
    check("the edit parses the candidate once, from the caller's parse of "
          "the original text",
          "List<TomlSettings.DocEntry> before, TomlSettings.DocEntry entry" in edit
          and replace.count("TryReadDocument(") == 1
          and "out List<TomlSettings.DocEntry> after" in edit)

    probe = body(target, "static bool CachedHasSettingsComponent(")
    check("the assembly probe is paid once per installed mod, not once per "
          "screen opening",
          "hotReloadsByModPath.TryGetValue(mod.Path" in probe
          and "HasSettingsComponent(mod)" in probe)

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

    # The writer is the shared byte-faithful one, so the check holds the
    # staged path rather than a File.* spelling: it is the temp sibling the
    # text reaches, not which overload does it, that keeps the target whole.
    write = body(target, "bool TryWrite(")
    check("a save is written to a temp file, never over the target",
          "files.WriteAllText(tempPath, newText" in write
          and "WriteAllText(TomlPath" not in write)
    check("the temp file is replaced in, so the target is never half-written",
          "files.Replace(tempPath, TomlPath);" in write)
    check("a target holding the file for its own read is retried, not failed",
          "catch (IOException)" in write and "ReplaceAttempts" in write
          and "ModClock.Current.Sleep(ReplaceRetryMilliseconds)" in write)
    check("a failed replace leaves no temp file behind",
          "TryDeleteTemp(tempPath);" in write)

    read_body = body(target, "bool TryRead(")
    check("a read takes the file's bytes and its encoding, not just its text",
          "TomlFile.ReadAllText(TomlPath, out encoding)" in read_body
          and "File.ReadAllBytes(" not in target
          and target.count("ReadAllText(") == 1)
    check("a save writes the encoding the file is in",
          "out currentEncoding" in save
          and "TryWrite(newText, currentEncoding" in save)

    toml_file = read("TomlFile.cs")
    check("a byte order mark is decoded away and written back",
          "new UTF8Encoding(true)" in toml_file
          and "new UnicodeEncoding(false, true)" in toml_file
          and "new UnicodeEncoding(true, true)" in toml_file
          and "new UTF32Encoding(false, true)" in toml_file
          and "new UTF32Encoding(true, true)" in toml_file
          and "new UTF8Encoding(false)" in toml_file)
    check("a read and a write tolerate a hot-reloading mod's own holder",
          "FileShare.ReadWrite | FileShare.Delete" in toml_file
          and toml_file.count("SharedAccess") >= 3)

    opened = body(screen, "public override void OnOpen()")
    check("the reload latch does not survive the closing it was set in",
          "DisarmReloadWatch()" in opened)
    check("a rejected save and a new selection both disarm the latch",
          "ArmReloadWatch(" in body(screen, "internal bool SaveEdit(")
          and "DisarmReloadWatch()" in body(screen, "internal void SelectMod("))

    logline = body(screen, "void OnLogLine(")
    take = body(screen, "bool TakeReloadSeen(")
    check("the log callback and the latch take one lock, so a line cannot "
          "land between the marker swap and the latch clear",
          "lock (reloadGate)" in logline
          and "lock (reloadGate)" in take
          and "reloadSeen = false;" in take
          and "watchedReloadMarker = null;" in take
          and "volatile bool reloadSeen" not in screen)

    atomic = write
    check("a save is staged in a temp file and swapped in, never truncated "
          "in place",
          'var tempPath = TomlPath + ".wrench-tmp";' in atomic
          and "files.WriteAllText(tempPath," in atomic
          and "files.Replace(tempPath, TomlPath);" in atomic
          and "TryDeleteTemp(tempPath)" in atomic
          and "File.WriteAllText(" not in atomic
          and "WriteAllText(TomlPath" not in save)

    print("RESULT " + ("FAIL" if FAILURES else "PASS"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
