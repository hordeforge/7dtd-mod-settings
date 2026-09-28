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

    settings = read("ModSettings.cs")
    target = read("TargetMod.cs")
    api = read("ModApi.cs")
    screen = read("ModSettingsScreen.cs")
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
    check("the file watch measures elapsed time on a monotonic clock",
          "Stopwatch.StartNew()" in settings
          and "Time.unscaledTime -" not in settings
          and "seenAt = Time.unscaledTime" not in settings)
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
    # The staged sibling is named `temp` in TryWrite: the temp file is a
    # sibling of the target, the replace is what puts it in, and the same
    # name is unlinked on the failure path (TryDeleteTemp) so a failed save
    # leaves nothing behind.
    check("a save is staged and swapped in, never written over in place",
          "File.WriteAllText(TomlPath" not in target
          and 'var temp = path + ".wrench-tmp";' in target
          and "File.WriteAllText(temp, text, encoding)" in target
          and "File.Replace(temp, path, null)" in target
          and "TryDeleteTemp(temp)" in target)
    # The mod name comes out of another mod's ModInfo.xml, and this screen
    # writes to the file it names: the path must be resolved, not
    # concatenated. scripts/toml_gate exercises the resolver itself.
    check("another mod's name cannot steer the settings file out of its folder",
          read("ModTomlPath.cs") != ""
          and "ModTomlPath.TryResolve(mod.Path, mod.Name" in target
          and 'Path.Combine(mod.Path, "Config", mod.Name' not in target)
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
    check("the Applied event is raised outside the lock, so a handler cannot "
          "run against half-applied values or block the polling thread",
          "handlers?.Invoke();" in settings
          and "handlers = Applied;" in body(settings, "static bool Apply(")
          and "Invoke()" not in body(settings, "static bool ReloadLocked(")
          and "Invoke()" not in body(settings, "static bool ApplyMissingFileDefaults("))

    print("RESULT " + ("FAIL" if FAILURES else "PASS"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
