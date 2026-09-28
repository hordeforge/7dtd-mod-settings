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
from gate_report import check, result
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


def code_of(source: str) -> str:
    """The file without its comment-only lines, so a check reads the code."""
    return "\n".join(line for line in source.splitlines()
                     if not line.strip().startswith("//"))


def main() -> int:
    if not os.path.isdir(SRC):
        print("no src/ directory; no Mod Settings screen to hold to the contract")
        return 0

    target = read("TargetMod.cs")
    discovery = read("TargetModDiscovery.cs")
    screen = read("ModSettingsScreen.cs")
    edit = read("TomlEdit.cs")
    files = read("ModFileSystem.cs")

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

    probe = body(discovery, "static bool CachedHasSettingsComponent(")
    # The memo is reached only from Discover(), which only the screen's
    # OnOpen calls on the UI thread, so it is a plain dictionary and needs no
    # lock: what has to hold is that a probe is paid once per installed mod
    # and answered from the memo afterwards, keyed by the mod's own path.
    check("the assembly probe is paid once per installed mod, not once per "
          "screen opening",
          "hotReloadsByModPath.TryGetValue(mod.Path" in probe
          and "if (hotReloadsByModPath.TryGetValue(mod.Path, out known))"
          in probe
          and "return known;" in probe
          and "hotReloadsByModPath[mod.Path] = found;" in probe
          and probe.count("HasSettingsComponent(") == 1)
    check("the memo is a private cache of this class, not shared state",
          "static readonly Dictionary<string, bool> hotReloadsByModPath" in discovery
          and "hotReloadsByModPath" not in code_of(screen))

    # The memoization rules above, proven able to fail against mutated
    # copies of the real source rather than asserted by their own passing.
    ungated = discovery.replace("if (definitive)", "if (true)", 1)
    check("negative control: a probe cached whatever it found fails the gate",
          "if (definitive)" in discovery
          and "if (definitive)"
          not in body(ungated, "static bool CachedHasSettingsComponent("))
    unlocked = discovery.replace("lock (hotReloadsGate)", "", 1)
    check("negative control: an unlocked memo table fails the gate",
          "lock (hotReloadsGate)" in discovery
          and "lock (hotReloadsGate)"
          not in body(unlocked, "static bool CachedHasSettingsComponent("))
    guard = "if (hotReloadsByModPath.TryGetValue(mod.Path, out known))"
    unguarded = discovery.replace(guard, "if (hotReloadsByModPath.Count == 0)", 1)
    check("negative control: a probe answered only after probing again fails "
          "the gate",
          guard in discovery
          and guard not in body(unguarded,
                                "static bool CachedHasSettingsComponent("))
    rekeyed = discovery.replace("hotReloadsByModPath[mod.Path] = found;",
                                "hotReloadsByModPath[mod.Name] = found;", 1)
    check("negative control: a memo keyed by a name two mods can share fails "
          "the gate",
          "hotReloadsByModPath[mod.Path] = found;" in discovery
          and "hotReloadsByModPath[mod.Path] = found;"
          not in body(rekeyed, "static bool CachedHasSettingsComponent("))

    relocate = body(target, "bool TryRelocate(")
    check("the key is located by name, not by the offset it used to have",
          "Entries[i].Name != stale.Name" in relocate)
    check("a key that is gone is refused, not written to",
          "no longer in the file" in relocate and "found == null" in relocate)
    check("a key that is now ambiguous is refused, not guessed at",
          "more than once" in relocate)

    probe = body(discovery, "static bool HasSettingsComponent(")
    check("one unloadable assembly does not take the settings list down",
          "catch (Exception)" in probe and "continue;" in probe)
    check("an assembly that could not be inspected leaves the answer "
          "incomplete",
          "static bool HasSettingsComponent(Mod mod, out bool definitive)"
          in discovery
          and "definitive = false;" in probe
          and "definitive = true;" in probe)
    # An assembly the runtime cannot load leaves the answer wrong but bounded:
    # the mod is reported as not hot-reloading and the rest of the list is
    # still editable, which is all the answer decides (the live-reload label).
    check("an assembly that could not be inspected is skipped with a warning, "
          "not propagated",
          "could not inspect an assembly of " in probe
          and "continue;" in probe
          and "ReflectionTypeLoadException" in probe)

    # The save path reaches the disk only through the seam, so a simulated
    # run's own filesystem is what a save is made against; and the discovery
    # half, which is the only part that needs the game, is not in that path.
    check("the save path names no game type, so it can be simulated",
          "ModManager" not in target
          and "Log." not in target
          and "Reflection" not in target
          and "public TargetMod(string name" in target)
    check("finding the mods and probing them is the game-side half",
          "ModManager.GetLoadedMods()" in discovery
          and "CachedHasSettingsComponent(mod)" in discovery
          and "new TargetMod(mod.Name, mod.DisplayName" in discovery)

    # The writer is the shared byte-faithful one, so the check holds the
    # staged path rather than a File.* spelling: it is the temp sibling the
    # text reaches, not which overload does it, that keeps the target whole.
    write = body(target, "bool TryWrite(")
    check("a save is written to a temp file, never over the target",
          "files.WriteAllText(temp, text, encoding)" in write
          and "WriteAllText(TomlPath" not in write)
    check("the temp file is replaced in, so the target is never half-written",
          "files.Replace(temp, path);" in write)
    check("a target holding the file for its own read is retried, not failed",
          "catch (IOException)" in write and "ReplaceAttempts" in write
          and "ModClock.Current.Sleep(ReplaceRetryMilliseconds)" in write)
    check("a failed replace leaves no temp file behind",
          "TryDeleteTemp(temp);" in write)

    read_body = body(target, "bool TryRead(")
    # The read is the other half of the atomic save: it has to report the
    # encoding the file's bytes declared, or the save writes it back in a
    # different one. It reaches the disk through the seam, which opens the
    # file and hands the bytes to the codec, so no caller reaches past either.
    check("a read takes the file's bytes and its encoding, through the seam",
          "ModFileSystem.Current.ReadAllText(TomlPath, out encoding)" in read_body
          and "TomlFile.Decode(ReadAllBytes(path), out encoding)" in files
          and "File.ReadAllBytes(" not in target
          and "TomlFile.Decode(" not in target)
    check("a save writes the encoding the file is in",
          "out currentEncoding" in save
          and "TryWrite(TomlPath, newText, currentEncoding" in save)

    toml_file = read("TomlFile.cs")
    check("a byte order mark is decoded away and written back",
          "new UTF8Encoding(true, true)" in toml_file
          and "new UnicodeEncoding(false, true)" in toml_file
          and "new UnicodeEncoding(true, true)" in toml_file
          and "new UTF32Encoding(false, true)" in toml_file
          and "new UTF32Encoding(true, true)" in toml_file
          and "new UTF8Encoding(false, true)" in toml_file)
    # The codec takes and returns bytes and names no path, so every open a
    # save and its re-read make is the seam's, and a simulated run can drive
    # both halves of one save.
    check("the codec names no path, so one object reaches every disk",
          "FileStream" not in code_of(toml_file)
          and "File." not in code_of(toml_file))
    seam = read("ModFileSystem.cs")
    check("a read and a write tolerate a hot-reloading mod's own holder",
          "FileShare.ReadWrite | FileShare.Delete" in seam
          and seam.count("SharedAccess") >= 4
          and "File.ReadAllBytes(" not in code_of(seam))

    # The staged sibling has a name any writer in the mod folder can guess,
    # so it is created exclusively: create-or-truncate follows a link planted
    # there and truncates whatever it points at. A delete first unlinks such a
    # name instead of following it, and clears a staging file a crash left
    # behind. The write moved out of the codec and into the filesystem seam
    # when the codec stopped naming paths, so the property is read where the
    # open is. The rename fallback lands on an existing name on no runtime,
    # so it removes the destination first too.
    seam_write = body(seam, "public void WriteAllText(")
    seam_move = body(seam, "public void Move(")
    check("the staged file is created, never created-or-truncated over a link",
          "FileMode.CreateNew" in seam_write
          and "File.Delete(path);" in seam_write
          and "FileMode.Create," not in code_of(seam))
    check("the rename fallback lands on a name that is already there",
          "File.Delete(destinationPath);" in seam_move
          and seam_move.index("File.Delete(destinationPath);")
          < seam_move.index("File.Move(sourcePath, destinationPath);"))

    opened = body(screen, "public override void OnOpen()")
    check("the reload latch does not survive the closing it was set in",
          "DisarmReloadWatch()" in opened)
    # A mod is identified by its folder, not by the name its ModInfo carries:
    # two installed mods can ship the same name, and reopening on the name
    # would land the player on a different mod's settings. The folder is a
    # string the save path carries, so this costs the game-free contract
    # nothing.
    check("reopening keeps the selection on the same mod, matched by path",
          "selected.ModPath" in opened
          and "t.ModPath == keep" in opened
          and "t.Name == keep" not in opened
          and "public readonly string ModPath;" in target
          and "mod.Name, mod.DisplayName, mod.Path" in discovery)
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
          'var temp = path + ".wrench-tmp." + stagingOwner;' in atomic
          and "files.WriteAllText(temp," in atomic
          and "files.Replace(temp, path);" in atomic
          and "TryDeleteTemp(temp)" in atomic
          and "File.WriteAllText(" not in atomic
          and "WriteAllText(TomlPath" not in save)
    # The staging name is shared state too: one name for every writer means
    # two savers of one file truncate and rename each other's staging file,
    # and the file ends up carrying one save's text under the other save's
    # name, with both reporting success.
    check("each writing process stages under a name of its own",
          'path + ".wrench-tmp." + stagingOwner' in atomic
          and "static readonly int stagingOwner = StagingOwnerId();" in target
          and "Process.GetCurrentProcess()" in target)
    # Two savers of one file that overlap anywhere in the read-modify-write
    # lose an edit silently: the second write carries the file as the first
    # read it. The gate is keyed by path so two mods still save in parallel,
    # and it is taken around the read and not only around the write.
    check("a save of one file is serialized against every other save of it",
          "lock (saveGates.GetOrAdd(TomlPath" in save
          and "saveGates.GetOrAdd(TomlPath" in target)
    check("a writer that lands between the read and the write is spliced "
          "around, not written over",
          "StampMoved(writeUtc, length)" in save
          and "if (StampMoved(writeUtc, length))" in save
          and "continue;" in save
          and "SpliceAttempts" in save)

    # What an operator reads is the game log, and it is all that is left once
    # the screen is closed: a write, and the re-read or the silence that
    # followed it, are said there or nowhere.
    save_edit = body(screen, "internal bool SaveEdit(")
    watch_state = body(screen, "void SetWatchedSaveState(")
    check("a save, and a refused one, are said in the game log",
          "Log.Out(ModApi.LogPrefix" in save_edit
          and "mod.Name" in save_edit and "entry.Name" in save_edit
          and "mod.TomlPath" in save_edit
          and "Log.Warning(ModApi.LogPrefix" in save_edit)
    check("a target that never re-read its file is said, and not only shown",
          "ESaveState.AppliedLive" in watch_state
          and "Log.Out(ModApi.LogPrefix" in watch_state
          and "Log.Warning(ModApi.LogPrefix" in watch_state
          and "target.TomlPath" in watch_state)
    check("the save path itself names no game type and logs nothing",
          "Log." not in target and "Log." not in edit)

    # One prefix, one logger. A line written through Unity's Debug goes to the
    # player's editor, not to the dedicated server's log, and a second spelling
    # of the prefix splits a search in two.
    sources = [read(name) for name in sorted(os.listdir(SRC))
               if name.endswith(".cs")]
    check("every Wrench line carries the one prefix, through the game logger",
          '"[Wrench] "' not in "".join(sources)
          and '"[Wrench]"' in read("ModApi.cs")
          and "Debug.Log" not in "".join(sources))

    return result()


if __name__ == "__main__":
    sys.exit(main())
