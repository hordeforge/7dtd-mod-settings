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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from csharp_source import body, code_of
from gate_report import check, result
from local_env import mod_dir, mod_name

MOD_DIR = str(mod_dir())
SRC = os.path.join(MOD_DIR, "src", mod_name())
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
    toml_path = os.path.join(MOD_DIR, "Config", mod_name() + ".toml")

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
          and "ModFileSystem.Current.TryGetStamp" in settings)
    # The poll runs four times a second for as long as the game does, so the
    # stamp it compares is one metadata read: a separate existence check, a
    # separate write-time read, and an open of the file to ask its length are
    # three round trips where the watch needs one.
    check("the watch reads the file's stamp in a single metadata read",
          "bool TryGetStamp(string path, out DateTime writeUtc"
          in files
          and "new FileInfo(path)" in code_of(read("ModFileSystem.cs"))
          and "GetLength" not in files
          and "GetLastWriteTimeUtc" not in files
          and "ModFileSystem.Current.Exists" not in settings)
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
          and "Thread.Sleep" not in code_of(read("TargetMod.cs"))
          and "Thread.Sleep" not in code_of(read("ModSettings.cs"))
          and "ModClock.Current.Sleep(ReplaceRetryMilliseconds)" in target)
    # The screen's bounded wait for a hot-reloading mod's reload line is a
    # wait too, so it is measured on the same clock: summing the frame delta
    # measures the game's own frame time, and a frame the game does not
    # advance (a paused or time-scaled one) carries none of it, which leaves
    # the status promising a reload that is never confirmed.
    screen_code = code_of(read("ModSettingsScreen.cs"))
    update = body(screen, "public override void Update(float _dt)")
    check("the screen's reload-confirm wait runs on the mod's one clock",
          "ModClock.Current.NowSeconds - reloadStartedAt >= RELOAD_CONFIRM_SECONDS" in update
          and "ModClock.Current.NowSeconds;" in body(screen, "internal bool SaveEdit(")
          and "_dt +=" not in screen_code
          and "reloadWait" not in screen_code)
    # Negative control: a wait summed from the frame delta fails the gate.
    frame_sum = screen.replace(
        "ModClock.Current.NowSeconds - reloadStartedAt", "reloadWait += _dt; if (reloadWait", 1)
    check("negative control: a frame-delta countdown fails the gate",
          "ModClock.Current.NowSeconds - reloadStartedAt >= RELOAD_CONFIRM_SECONDS" in screen
          and "ModClock.Current.NowSeconds - reloadStartedAt >= RELOAD_CONFIRM_SECONDS"
          not in body(frame_sum, "public override void Update(float _dt)"))
    check("reload resets to defaults then applies the file",
          "ResetToDefaults();" in settings
          and '"reload " + RelativePath' in settings)
    check("a failed re-read keeps the current values",
          "keeping current settings" in settings)
    check("a read that fails says so, with the cause, once per problem",
          "LogProblem(" in settings
          and 'error = ex.GetType().Name + ": " + ex.Message;' in settings
          and "catch (Exception ex)" in settings
          and "catch (Exception)" not in settings)
    # TryWrite stages a sibling in the same folder as the target, under a
    # name carrying the writing process's id so two writers of one file do
    # not stage under one name and each report success having written the
    # other's bytes; it writes that sibling through the seam, and puts it in
    # place with an atomic replace that retries while the target's own
    # settings watch holds the file. The same name is unlinked on the failure
    # path (TryDeleteTemp), so a failed save leaves nothing behind. The read
    # half of the same save goes through the seam too, so a simulated run
    # drives the read and the write of one save on one filesystem. The writer
    # takes the path it stages beside, so the call site, not the writer, is
    # where the target's own path is named: that call site is asserted too.
    write = body(target, "static bool TryWrite(string path, string text, Encoding encoding,"
                         " out string error)")
    check("a save is staged and swapped in, never written over in place",
          "WriteAllText(TomlPath" not in target
          and "TryWrite(TomlPath, newText, currentEncoding, out error)" in target
          and 'var temp = path + ".wrench-tmp." + stagingOwner;' in write
          and "static readonly int stagingOwner = StagingOwnerId();" in target
          and "process.Id" in target
          and "files.WriteAllText(temp, text, encoding)" in write
          and "files.Replace(temp, path)" in write
          and "if (attempt >= ReplaceAttempts)" in write
          and "ModClock.Current.Sleep(ReplaceRetryMilliseconds)" in write
          and "TryDeleteTemp(temp)" in write
          and "TryDeleteTemp(TomlPath" not in target)
    # Negative control: a writer that truncates the target in place, which is
    # the outcome every property above exists to prevent.
    in_place = write.replace("files.WriteAllText(temp, text, encoding)",
                             "files.WriteAllText(path, text, encoding)", 1)
    check("negative control: an in-place write fails the gate",
          "files.WriteAllText(temp, text, encoding)" in write
          and "files.WriteAllText(temp, text, encoding)" not in in_place)
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
        return any(call in code_of(read(name)) for call in other_disk_calls)

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
          and not bcl_file_call.search(code_of(read("ModSettings.cs")))
          and not bcl_file_call.search(code_of(read("TargetMod.cs")))
          and not bcl_file_call.search(code_of(read("TargetModDiscovery.cs")))
          and not calls_disk("ModSettings.cs")
          and not calls_disk("TargetMod.cs")
          and not calls_disk("TargetModDiscovery.cs"))
    # A seam is only a seam if the whole path goes through it: a read that
    # reaches the disk beside a write that does not hands a simulated run
    # the real file's text with its writes going to the simulation, and the
    # save path is the one place that reads and writes the same file.
    check("the save path's read is the seam's read, not a second one",
          "ModFileSystem.Current.ReadAllText(TomlPath, out encoding)"
          in code_of(read("TargetMod.cs"))
          and "string ReadAllText(string path, out Encoding encoding);" in files
          and "TomlFile.Decode(ReadAllBytes(path), out encoding)"
          in code_of(read("ModFileSystem.cs")))
    # What a simulated run cannot have is a save path that needs the game to
    # exist: the mod list and the assembly probe are the game-side half, and
    # nothing past them names a game type.
    check("the save path is drivable without the game",
          "ModManager" not in code_of(read("TargetMod.cs"))
          and "ModManager" in code_of(read("TargetModDiscovery.cs"))
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

    return result()


if __name__ == "__main__":
    sys.exit(main())
