#!/usr/bin/env python3
"""Structural proof of the TOML settings contract.

The mod's runtime settings are Config/<Mod>.toml, read by the DLL itself:
applied at InitMod, re-read on save without a restart (UnityUpdate watch,
debounced), reset-to-defaults-then-apply, and a broken save keeps the
current values. The console command shares the value grammar via TrySet.
A write to another mod's settings file is staged and swapped in, and every
failure on either path is reported with its cause. This gate holds those
source-level contracts so a refactor cannot quietly drop one; the live
behavior itself is proven in game.

A mod without src/ has no settings reader; the gate passes with a note.
"""

from __future__ import annotations

import os
import re
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
# A call into System.IO.File, not the tail of this mod's `TomlFile.`.
bcl_file_call = re.compile(r"(?<![\w.])File\.")


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

    def read_script(name: str) -> str:
        """A build-time file of this mod, by a path relative to its root."""
        path = os.path.join(MOD_DIR, name)
        if not os.path.isfile(path):
            return ""
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def body(source: str, signature: str) -> str:
        """The `{ ... }` block that follows a method signature, braces counted.

        String literals in this file hold no braces, so a plain count is
        enough and keeps the gate free of a C# parser it would otherwise need.
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

    def code_of(name: str) -> str:
        """The file without its comment lines, so a check reads the code."""
        return "\n".join(line for line in read(name).splitlines()
                         if not line.strip().startswith("//"))

    def names_file_api(code: str) -> bool:
        """True when *code* names System.IO's static `File` API itself.

        The name must not be the tail of a longer identifier, or the
        sanctioned `TomlFile` seam would read as a direct `File.` call. A
        dotted qualifier still counts: `System.IO.File.Exists` is one.
        """
        return re.search(r"(?<!\w)File\.", code) is not None

    settings = read("ModSettings.cs")
    target = read("TargetMod.cs")
    clock = read("ModClock.cs")
    files = read("ModFileSystem.cs")
    api = read("ModApi.cs")
    screen = read("ModSettingsScreen.cs")
    toml_path = os.path.join(MOD_DIR, "Config", MOD_NAME + ".toml")

    check("the shipped settings TOML exists beside its reader",
          os.path.isfile(toml_path))
    check("ModSettings reads the TOML through the shared TrySet grammar",
          "TomlSettings.TryRead" in settings
          and "TrySet(entries[i].Name, entries[i].Value" in settings)
    # TOML keys are case sensitive, so a key whose case is wrong is an
    # unknown key: the file reader must not accept it as a second spelling
    # of a declared setting. The console, whose name is typed by hand, still
    # matches case-insensitively.
    check("a file key whose case is wrong is unknown, not a second name",
          "ignoreNameCase: false" in body(settings, "static bool ReloadLocked(")
          and "StringComparison.OrdinalIgnoreCase" in settings
          and "StringComparison.Ordinal;" in settings)
    check("a save is picked up on UnityUpdate without a Harmony patch",
          "ModEvents.UnityUpdate.RegisterHandler" in api
          and "ModSettings.Poll()" in api
          and "FilePollIntervalSeconds" in settings
          and "FileReloadDebounceSeconds" in settings
          and "ModFileSystem.Current.GetLastWriteTimeUtc" in settings)
    check("the file watch measures elapsed time on the mod's one clock",
          "ModClock.Current.NowSeconds" in settings
          and "Stopwatch" not in settings
          and "Time.unscaledTime -" not in settings
          and "seenAt = Time.unscaledTime" not in settings
          and "DateTime.Now" not in settings)
    check("every wait goes through that clock, so a simulated run can step it",
          "interface IMonotonicClock" in clock
          and "class StopwatchClock : IMonotonicClock" in clock
          and "static IMonotonicClock Current { get; set; }" in clock
          and "Thread.Sleep" not in code_of("TargetMod.cs")
          and "Thread.Sleep" not in code_of("ModSettings.cs")
          and "ModClock.Current.Sleep(ReplaceRetryMilliseconds)" in target)
    check("reload resets to defaults then applies the file",
          "ResetToDefaults();" in settings
          and '"reload " + RelativePath' in settings)
    check("a failed re-read keeps the current values",
          "keeping current settings" in settings)
    check("a read that fails says so, with the cause, once per problem",
          "LogProblem(" in settings
          and "error = ex.Message;" in settings
          and "catch (Exception ex)" in settings
          and "catch (Exception)" not in settings)
    # TryWrite stages the sibling `TomlPath + ".wrench-tmp"` in the same
    # folder as the target, writes it through the seam, and puts it in place
    # with an atomic replace that retries while the target's own settings
    # watch holds the file; the same name is unlinked on the failure path
    # (TryDeleteTemp), so a failed save leaves nothing behind. The read half
    # of the same save goes through the seam too, so a simulated run drives
    # the read and the write of one save on one filesystem.
    check("a save is staged and swapped in, never written over in place",
          "WriteAllText(TomlPath" not in target
          and 'var tempPath = TomlPath + ".wrench-tmp";' in target
          and "files.WriteAllText(tempPath, newText, encoding)" in target
          and "files.Replace(tempPath, TomlPath)" in target
          and "if (attempt >= ReplaceAttempts)" in target
          and "TryDeleteTemp(tempPath)" in target)
    # The mod name comes out of another mod's ModInfo.xml, and this screen
    # writes to the file it names: the path must be resolved, not
    # concatenated. scripts/toml_gate exercises the resolver itself.
    check("another mod's name cannot steer the settings file out of its folder",
          read("ModTomlPath.cs") != ""
          and "ModTomlPath.TryResolve(mod.Path, mod.Name" in read("TargetModDiscovery.cs")
          and 'Path.Combine(mod.Path, "Config", mod.Name' not in read("TargetModDiscovery.cs"))
    # A Linux or macOS host reports only NUL and the separator as the
    # characters a file name may not hold, so a downloaded modlet can name
    # itself with a line break; the name then goes into a log line and into
    # the reload-marker match.
    gate = read_script(os.path.join("scripts", "toml_gate", "Program.cs"))
    check("a mod name cannot carry a control character into the log or the "
          "reload marker",
          "c < ' ' || c == (char)0x7f" in read("ModTomlPath.cs")
          and 'Rejected("a name with a newline"' in gate)
    # Both hooks are registered on a static/engine-owned list that nothing
    # else unhooks, so an unguarded second registration keeps the first one
    # alive for the rest of the session: the file watch polls twice per
    # frame, and the screen stays reachable from Log.LogCallbacks after it
    # closed, holding every discovered TargetMod and its parsed text.
    check("the file watch is registered once per process",
          "if (!updateHooked)" in api
          and "updateHooked = true;" in api)
    check("the screen subscribes to the log once and unhooks on close",
          "if (!watchingLog)" in screen
          and "if (watchingLog)" in screen
          and "Log.LogCallbacks -= OnLogLine" in screen
          and "Log.LogCallbacks += OnLogLine" in screen)
    check("the Unity poll and the telnet console thread share one lock, so a "
          "`wrench set` cannot interleave with a reload's reset and apply",
          "static readonly object Gate" in settings
          and "lock (Gate)" in settings
          and "lock (Gate)" in body(settings, "static bool Apply(")
          and "lock (Gate)" in body(settings, "public static bool TrySet(")
          and "lock (Gate)" in body(settings, "public static string[] Describe()"))
    # The watch remembers one file's write time, length and text. Switching
    # to another settings file (a second InitMod on a long-running server)
    # has to forget them: a new file of the same length written in the same
    # timestamp tick would otherwise be taken for the one already applied.
    stamp = body(settings, "static void ForgetStamps(")
    check("watching a different settings file forgets the previous one's "
          "signature",
          "ForgetStamps();" in body(settings, "public static void Load(")
          and "static void ForgetStamps(" in settings
          and "ForgetStamps();"
          in body(settings, "static bool ApplyMissingFileDefaults(")
          and "appliedText = null;" in stamp
          and "nextPollAt = -1d;" in stamp)
    kept = settings.replace("ForgetStamps();\n", "", 1)
    check("negative control: a watch that keeps the old signature across a "
          "new file fails the gate",
          "ForgetStamps();" in settings
          and "ForgetStamps();"
          not in body(kept, "public static void Load("))
    check("the Applied event is raised outside the lock, so a handler cannot "
          "run against half-applied values or block the polling thread",
          "handlers?.Invoke();" in settings
          and "handlers = Applied;" in body(settings, "static bool Apply(")
          and "Invoke()" not in body(settings, "static bool ReloadLocked(")
          and "Invoke()" not in body(settings, "static bool ApplyMissingFileDefaults("))
    # The disk-touching spellings that do not go through `File.` are named
    # separately, so a stream or a directory reached for directly past the
    # seam fails the gate too.
    other_disk_calls = ("FileStream", "StreamReader", "Directory.")

    def calls_disk(name: str) -> bool:
        return any(call in code_of(name) for call in other_disk_calls)

    # `File.` has to be matched as the BCL type, not as the tail of this mod's
    # own `TomlFile.`, which is a call through the seam and nothing else:
    # `TomlFile` is the byte-faithful seam a target mod's own file goes
    # through (architecture.md, "another mod's TOML is read and written
    # through TomlFile"), so a plain substring rule would forbid the seam
    # that decision put in place.
    check("the shipped sources touch a disk only through the two seams",
          "interface IFileSystem" in files
          and "class SystemFileSystem : IFileSystem" in files
          and "static IFileSystem Current { get; set; }" in files
          and not bcl_file_call.search(code_of("ModSettings.cs"))
          and not bcl_file_call.search(code_of("TargetMod.cs"))
          and not bcl_file_call.search(code_of("TargetModDiscovery.cs"))
          and not calls_disk("ModSettings.cs")
          and not calls_disk("TargetMod.cs")
          and not calls_disk("TargetModDiscovery.cs"))
    # A seam is only a seam if the whole path goes through it: a read that
    # reaches the disk beside a write that does not hands a simulated run
    # the real file's text with its writes going to the simulation, and the
    # save path is the one place that reads and writes the same file.
    check("the save path's read is the seam's read, not a second one",
          "ModFileSystem.Current.ReadAllText(TomlPath, out encoding)" in code_of("TargetMod.cs")
          and "string ReadAllText(string path, out Encoding encoding);" in files
          and "TomlFile.ReadAllText(path, out encoding)" in code_of("ModFileSystem.cs"))
    # What a simulated run cannot have is a save path that needs the game to
    # exist: the mod list and the assembly probe are the game-side half, and
    # nothing past them names a game type.
    check("the save path is drivable without the game",
          "ModManager" not in code_of("TargetMod.cs")
          and "ModManager" in code_of("TargetModDiscovery.cs")
          and "public TargetMod(string name" in target)
    # The seam check reads a bare `File.` as System.IO's static API, so an
    # identifier that merely ends in `File` must not read as one: TomlFile is
    # the sanctioned reader for another mod's settings file, and the rule
    # existed to catch a real File call slipping past the IFileSystem seam.
    check("negative control: the seam check still catches a direct File. call",
          names_file_api("var text = File.ReadAllText(path);")
          and names_file_api("System.IO.File.Exists(path)")
          and not names_file_api("text = TomlFile.ReadAllText(path, out encoding);")
          and not names_file_api("ModFileSystem.Current.Replace(temp, path);"))

    print("RESULT " + ("FAIL" if FAILURES else "PASS"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
