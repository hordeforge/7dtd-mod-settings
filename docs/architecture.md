# Architecture — Wrench (Mod Settings)

Technical implementation decisions. Significant, hard-to-reverse decisions
also get an ADR in [`adr/`](adr/) — link it from here. Layer escalations
(XML-only → Harmony, per docs/reference/agent-rules.md) always warrant one.

## Repo map

`src/Wrench/` is the mod, in three layers with dependencies running down:
the TOML document (`TomlSettings.cs` parses, `TomlEdit.cs` writes, and
`TomlFile.cs` is the byte-faithful codec both go through, over
`ModFileSystem.cs`, the one filesystem) and the
target-mod model (`TargetMod.cs`, `ModTomlPath.cs`) know nothing about the
UI; the XUi controllers (`ModSettingsScreen.cs`, `ModSettingsRows.cs`) sit on
top of them; the entry points (`ModApi.cs`, `ConsoleCmdWrench.cs`,
`ModSettings.cs`, which is the mod's own `Config/Wrench.toml` reader and
reads it through `ModFileText.cs`) wire the two together, with `WrenchText.cs`
holding the screen's localization lookups. One namespace, no subfolders: at
this size a folder split would carry no information the names do not.

`ModClock.cs` and `ModFileSystem.cs` sit under all three: the clock and the
filesystem every one of those files reads (see the injection decision
below), so nothing in the mod reaches for `Time`, `File.` or
`Thread.Sleep` directly.

`scripts/` splits three ways, and nothing crosses the lines:

- `test_*.py` are the offline gates, at the top level because
  `run-offline-tests.sh` globs for them there. `validate-*.py` and
  `verify-*.py` need an installed game, so they are tools, not gates.
- `lib/` is the only shared layer. `gate_report.py` owns the PASS/FAIL shape
  every gate prints, `local_env.py` owns both the `.local.env` lookup and
  the marker walk every script uses to find the mod root, along with
  `mod_dir()` and `mod_name()`, `dotnet_host.py` the build-and-run of a C#
  harness, `git_tracked.py` the tracked-file walk, `csharp_source.py` the
  C# method-body reader the source-shape gates use, and `game_telnet.py`
  the stdlib console client. A script that needs any of them imports it; it
  does not keep a second copy.
- `toml_gate/`, `toml_fuzz/` and `playtest/` are the C# hosts: two console
  runners over the game-free sources (one round-trips the parser, writer
  and `TomlFile`, the other fuzzes the reader) and the provider that drives
  the live suite. They are build-time, so they sit under `scripts/`, not
  `src/`.

Shell scripts sit beside the Python they drive (`server-common.sh` with the
server lane, `run-offline-tests.sh` with the gates) and share no library
with them. `configure-server-config.py` is a tool, not a gate: it derives
the mod-owned serverconfig from the vanilla one before the mod is
deployed.

## Decisions

(Format: `## Decided YYYY-MM-DD: <topic>` — approach, alternatives, why.)

## Decided 2026-08-30: the TOML file is the integration surface

See [ADR 0001](adr/0001-toml-file-is-the-integration-surface.md). Wrench
edits the target mod's `Config/<Mod>.toml` in place; mods built on
Anvil's settings component notice the save through their own hot-reload
watch. No registration API, no shared assembly, no load-order
dependency.

## Decided 2026-09-28: text boundaries in the TOML path

Wrench reads and writes text it does not own: another mod's `Config/*.toml`
and its comments. Three decisions follow, enforced by
`scripts/test_toml_document.py`.

- **Encoding.** Wrench's own `Config/Wrench.toml` is read and written as
  UTF-8 without a byte order mark (`ModFileText`), a BOM still honoured on
  read so a file from elsewhere loads. Another mod's file keeps whatever
  encoding it is in (`TomlFile`, decided below). Relying on the API
  default made the written bytes depend on the runtime rather than on the
  mod. A decoder whose text is written back is strict: bytes that are not
  valid in the encoding they declare are refused, not replaced with
  U+FFFD, and the strict decoder is the same on the marked and the
  unmarked form, so a three-byte preamble cannot decide how forgiving a
  read is. That is every read of another mod's file; nothing writes
  `Wrench.toml` back, so a stray byte in its comment costs nothing there
  and its decoder may replace. Held by
  `scripts/test_toml_document.py`, which reads back an unmarked and a
  marked file carrying a byte no UTF-8 sequence starts with.
- **One string grammar, both directions.** The reader accepts the whole
  TOML escape set the writer can emit, and the writer escapes every
  control character rather than the two that read well, so a value Wrench
  writes is a value the target mod's parser accepts. A raw control
  character and an unpaired surrogate escape are refused on read instead
  of passing through as U+FFFD.
- **Keys are case sensitive.** `Foo` and `foo` are two TOML keys; a
  case-insensitive duplicate check refused a file that is valid, and
  disagreed with the ordinal comparison the save path already used to
  find a key's span.

Rejected: normalizing to NFC on ingestion. Nothing here compares a
human-typed name against another spelling, and rewriting another mod's
comments on a save is exactly the byte-for-byte guarantee the in-place
edit exists to keep.

## Decided 2026-08-30: naming and repo shape

Codename **🔧 Wrench**, repo `hordeforge/7dtd-mod-settings` (HordeForge
convention: codename + kebab repo slug). The checkout directory is the
repo slug, so `test_static_checks.py` holds ModInfo's `Name` to the
build tooling (`scripts/build.sh` `MOD_NAME`, `src/Wrench/Wrench.csproj`)
instead of the directory name; the deployable folder name comes from
`make build` staging `dist/Wrench/`.

## Decided 2026-08-30: options-menu integration is XUi XML plus a dialog subclass

No Harmony (see [ADR 0002](adr/0002-options-tab-via-xui-patch-no-harmony.md)):
the options paging header opens the window group named by a tab button
(`XUiC_WindowSelector.OpenSelectedWindow`, read with ilspycmd on the
installed V3.2.0 Assembly-CSharp), so a `pagingheader_button` inserted by
XPath into `optionsPaging` plus an appended window group is the whole
integration. The screen controller subclasses the game's public
`XUiC_OptionsDialogBase` for back/ESC handling, selector selection, and
the hovered-description panel (fed via the controller's own
`CustomAttributes`, which `options_descriptions` falls back to).

## Decided 2026-08-30: live-reload awareness

A target mod is labeled hot-reloading when any of its assemblies has a
`ModSettings` type with the `FilePollIntervalSeconds` constant (the Anvil
settings component's debounced save watch). After a save the screen
subscribes to `Log.LogCallbacks` and reports applied-live only once a line
carrying `reload Config/<Mod>.toml` appears — the substring every component
vintage shares, since they phrase the rest of the line differently. Mods
without the component are marked restart-required up front.

## Decided 2026-08-30: pooled XUi rows

Mod list and setting rows are fixed pools built by a grid with
`repeat_content` (vanilla's keyboard-bindings-list pattern); unused rows
hide via a binding, overflow past the pool is logged and not shown.
Every value is edited as its raw token in a text field that saves on
Enter, and a boolean additionally gets a one-click flip. Raw rather than
decoded because a key in this TOML subset is type-fluid (AtomicDoomsday's
`RaidMode` is legitimately `false`, `"all"`, or `["Tactical"]`), which a
decode-and-re-encode field could never express.

## Decided 2026-08-30: scrollview panels need an explicit depth bump

XUi view depths sum down the hierarchy; a `scrollview` is its own UIPanel
at that summed depth; NGUI raycasts pick the collider with the highest
`panel.depth * 1000 + widget.depth`. A scrollview without a `depth`
attribute therefore lands its panel at the window's depth, one below the
window's own panel (`XUiV_Window` sets `depth + 1`) — and any collider
directly in the window panel (a scrollarea's `on_scroll` collider) masks
every control inside the scrollview. Both Mod Settings lists carry
`depth="2"` for this reason; vanilla's server-browser list does the same.
Measured live with a raycast probe on 2026-08-30 after the whole screen
was mouse-dead; sources: `XUiV_Panel`, `XUiV_Window`,
`UIWidget.raycastDepth`, `NGUITools.CalculateRaycastDepth` (ilspycmd,
V3.2.0).

Known ceiling: the mouse wheel over a row hits the row's collider, which
does not forward scroll, so wheel-scrolling works only beside the rows
and via the scrollbar. Lists currently fit without scrolling.

## Decided 2026-09-28: the suite's restore writes the captured baseline

`wrench-mod-settings` edits AtomicDoomsday's shipped
`Config/AtomicDoomsday.toml` and then puts it back. The restore therefore
has to be re-runnable: a retried case, a second lap, or a re-run of the
suite must end in the same file the first run started from. It writes the
`RaidMode` raw token captured before the first write, not a hardcoded
`false`, and the baseline is captured once through a guarded
`CaptureBaseline()`, so no execution can take its baseline from a file the
suite already edited. Enforced by `scripts/test_playtest_rerun_safety.py`.

## Decided 2026-09-28: the parsed file is a cache, and a write re-reads it

`TargetMod.Text` / `TargetMod.Entries` are a cache of the target's TOML,
taken when the screen opens and after every save. Consistency requirement:
an edit lands in the file as it is at the moment of the save. So `TrySave`
re-reads the file first, and when it has moved on it re-parses and locates
the key by name; a key that is gone or now appears twice is refused with a
message instead of being spliced at a byte offset that now points somewhere
else, which would write a stale copy of the whole file over the other
writer's save. Display staleness is the looser part and is left alone: the
rows show the file as of the last open or save, so an external edit appears
on reopen. The "applied live" observation is a one-shot latch, armed by one
save and marking the mod that save was made to (not whichever mod happens
to be selected when the line arrives), and it is cleared when the screen
opens, so a reload line seen while it was closed cannot stamp a newly
discovered mod as saved-and-applied. A save that is refused, or to a mod
that only applies on a restart, disarms the latch rather than leaving the
previous mod's marker armed. The re-read is at the start of a save; the
decision below keeps the write half from reading the file back again.

## Decided 2026-09-28: a save is replaced in atomically, in the file's own encoding

The file is the whole integration surface (ADR 0001), so a save must never
be able to destroy it. Two properties, both held by
`scripts/test_target_save_coherence.py`:

- `TargetMod.TryWrite` writes a sibling `.wrench-tmp.<process id>` and puts
  it in with
  `File.Replace`, with a bounded retry because the target mod's own settings
  watch holds the file for the milliseconds it takes to read it and a
  replace needs delete access. `File.WriteAllText` on the target truncates
  first, so a crash, a shutdown, or a full disk between the truncate and
  the last byte would leave the mod with an unparsable settings file, or
  with none, which is the one outcome the file-as-surface rule exists to
  prevent. A runtime with no atomic replace falls back to move-then-move:
  the target moves aside to `.wrench-prev` and the staged text takes its
  place, and a move that fails puts the old text back (naming the file if
  even that fails), so the only window in which the target is missing is
  one the same method closes again. A run *killed* between the two moves
  is the one window the same method cannot close, and the `.wrench-prev`
  sibling is what it leaves behind. `TargetMod.RecoverInterruptedSave`
  moves that back when the target is missing, and the screen's discovery
  asks before it drops a mod whose file is not there, so the run after a
  killed save lands the mod on the screen again instead of losing its
  settings to a sibling name nothing else reads. It acts only while the
  target is missing, so a further run changes nothing.
- The staged file is created with `FileMode.CreateNew` after unlinking
  whatever is at that name, never `FileMode.Create`. The stage has a fixed,
  guessable name beside the target, so on a shared server install anything
  that can write the mod folder can leave a link there before the save;
  create-or-truncate follows it and truncates whatever it points at, while
  the delete-then-create unlinks it. The wait is the mod's monotonic clock,
  the same bounded retry the replace uses.
- `TargetMod.TryRead` reads bytes, not text, and reports the encoding it
  decoded; the save writes that same encoding back. Both go through
  `ModFileSystem.Current`, which detects the declared mark (UTF-8, UTF-16
  or UTF-32, a mark either way round) and falls back to UTF-8 with none;
  `File.ReadAllText` decodes a mark away and keeps no record of it, so a
  plain UTF-8 write stripped a mark the file was carrying: an edit that
  changed one value token had silently changed the file's first three bytes
  as well.

## Decided 2026-09-28: a save parses the file once, and probes an assembly once

`TargetMod.TrySave` reads the file once, splices into that read, and takes
its new `Text`/`Entries` from the parse `TomlEdit.TryReplaceValue` already
verified before writing, instead of reading the file back and re-parsing
what it had just written. The verification itself is unchanged: the
candidate is still re-parsed and compared key by key against the caller's
parse of the original text, which the caller supplies instead of having
the writer re-derive it.

`TargetModDiscovery.HasSettingsComponent` walks every type every assembly
of a mod declares, and an installed mod's assemblies do not change while the
game runs, so its answer is memoized per mod path and paid once per mod
rather than on every opening of the screen. Only a conclusive probe is kept:
an assembly the runtime cannot enumerate, or enumerates only in part, may
hold the component, so its "no" is reported for that opening and left out
of the table rather than cached as the mod's answer; a mod remembered as
not hot-reloading because one assembly would not load keeps saying "restart
required" for the rest of the session, and a component that was found is
conclusive whatever else went unread. The table is read and filled under
one lock, `hotReloadsGate`, because the screen is opened from the Unity
thread while a dedicated server's telnet thread can discover a mod of its
own. Enforced by
`scripts/test_target_save_coherence.py`.

The settings watch in `ModSettings` keeps the applied file's write time,
length and text so an unchanged file is not re-read four times a second.
Those belong to one file: a second `Load` (a mod reloaded on a long-running
dedicated server) that watches a different path forgets them through
`ForgetStamps`, or a new file of the same length written in the same
timestamp tick is taken for the one already applied and the old values
stay in place. Enforced by `scripts/test_settings_reload.py`.

## Decided 2026-09-28: bounded reload wait, empty-state labels

The post-save wait for a hot-reloading mod's reload line is bounded by
`RELOAD_CONFIRM_SECONDS` in `XUiC_ModSettingsScreen`; past it the mod's
save state becomes `SaveUnconfirmed` and the status says the change was
saved but not re-read, instead of promising a reload forever. The state
belongs to the watched mod, not to the selection, so switching mods
mid-wait cannot move the outcome onto the wrong row. The wait is elapsed
time on `ModClock`, not a sum of the frame delta the update loop is
handed: that delta is the game's own frame time, and a frame the game
does not advance carries none of it, so a countdown built from it cannot
finish while the player sits on the screen. Held by
`scripts/test_settings_reload.py`.

Both list panes carry an empty-state label (localization keys
`wrenchNoMods` and `wrenchNoSettings`, bound to `{nomods}` and
`{noentries}`), so a window with nothing to show says why rather than
showing an empty frame.

Corrected 2026-09-28: the wait had three ways to end and only one settled
the save it was watching. A save to a hot-reloading mod moves the state to
`Saved` and arms the marker; only the reload line or
`RELOAD_CONFIRM_SECONDS` resolved it. Closing the screen or picking
another mod in between disarmed the marker and dropped the target, so that
mod kept `Saved` for the rest of the session: its status line read as
"waiting for the mod to re-read the file" with nothing left to end that,
and the game-log line an operator reads after the screen is closed was
never written at all. `StopReloadWatch` is now the one way the wait ends
without a line, and it resolves the save as `SaveUnconfirmed` (a no-op
when no save is pending, so a close never logs a save it did not make).
`SaveEdit` still arms directly: the only save it can supersede is another
save to the same mod, and resolving that one as unconfirmed would report
a timeout that had not happened. Enforced by
`scripts/test_target_save_coherence.py`.

## Decided 2026-09-28: every Mod Settings string is a localization key

The strings the screen builds in C# used to be English literals in
`StatusLine`, `ShowHelp` and the mod row's note, next to a catalog that
already shipped the empty-state sentences. They now go through
`WrenchText.Get`/`WrenchText.Format` (`src/Wrench/WrenchText.cs`), which
reads `Config/Localization.csv` through the game's `Localization` and falls
back to the English source text when no dictionary holds the key, because
`Localization.Get` hands back the key itself for a missing one and a
player must never read that. A value goes into a `$1` slot
(`WrenchText.Format`) instead of being concatenated, so a translation can
put it where its own word order wants it.

`scripts/test_localization_catalog.py` holds the catalog and the code
together: every key named in C# or in a `text_key` attribute exists
exactly once with a non-empty english column, and that column is the same
string the C# falls back to. Its negative controls prove both checks can
fail. The two bottom labels in `Config/XUi_Menu/windows.xml` wrap, since a
German or Russian sentence runs past one 1200px line at their font sizes.

## Decided 2026-09-28: another mod's TOML is read and written through `TomlFile`

`File.ReadAllText` and `File.WriteAllText` are wrong on both sides of the
settings screen's write. They strip a byte order mark on read and never
write one back, so the first save of a mod's `Config/<Mod>.toml` changes
bytes outside the edited span, which ADR 0001 forbids; and both open with
`FileShare.Read`, which Windows refuses with a sharing violation while the
hot-reloading mod's own save watcher holds the same file open for read and
write, the mode `ModSettings.Poll` uses. `TomlFile.cs` takes a file's
bytes, detects the declared encoding (UTF-8 with or without a mark, UTF-16
and UTF-32 either way round) and codes the bytes to text and back, byte
order mark included; every one of those decoders is strict, so a file in
some other 8-bit encoding is refused and left alone instead of being
rewritten full of U+FFFD the first time a value is saved. `ModFileSystem`
makes every open, both sides, with `FileShare.ReadWrite | FileShare.Delete`.
`TargetMod` reads and writes the target through that one seam, temp sibling
included, so this is the shipped path and not a helper only the gate
exercises.

Decided 2026-09-28: the settings watch's stamp is one metadata read.
`ModSettings.Poll` runs from `ModEvents.UnityUpdate` every frame and acts
four times a second, for as long as the process lives, so what it asks the
disk is the only I/O this mod does continuously. `IFileSystem` exposes
`TryGetStamp` (existence, write time and length, one `FileInfo`) rather
than `Exists` plus `GetLastWriteTimeUtc` plus `GetLength`: the old three
calls cost two stats and a full open of the file per poll, and the poll
only ever wanted to know whether the file changed. A missing file and an
unreadable one stay distinguishable, so a deleted settings file still falls
back to the shipped defaults and a real I/O failure still names its cause.

The split is deliberate: the codec takes and returns bytes and
names no path, so the read half of a save and the write half of the same
save cannot reach two different filesystems, which is the one thing a
simulated run needs and what a static that opened a path could not give it.
Enforced by
`scripts/test_toml_document.py`, which round-trips each of those file
shapes through the shipped writer, and by `test_target_save_coherence.py`,
which holds the shape `TargetMod` keeps.

## Decided 2026-09-28: the settings reader is fuzzed with a fixed seed

A downloaded modlet carries its own `Config/<Mod>.toml`, so the reader
parses bytes this mod did not write, inside the game process. A parser
with no fuzz target is a parser whose malformed-input behavior is whatever
the unit cases happen to cover. `scripts/toml_fuzz/` mutates seed documents
(the shipped `Config/Wrench.toml` and the shapes the screen edits) and
asserts the invariants the screen depends on: the reader never throws, a
refusal always gives a reason, a captured span re-parses to its own value,
an edit changes one value span and nothing else, an encoded value reads
back unchanged, and an accepted mod name resolves inside the mod folder.
The seed and case count are fixed, so `scripts/test_toml_fuzz.py` is
deterministic and runs with the rest of the offline suite.

The first run of that harness found the reader accepting `A = 0.001B = 2`
as two keys: the value span ended before the trailing text, so an edit
rewrote it to `A = trueB = 2`, which the mod on the other side refuses. A
value may now be followed only by end of line or a comment.

## Decided 2026-09-28: a mod's settings file is resolved, never concatenated

`Mod.Name` is not this mod's to choose: it comes out of whichever
`ModInfo.xml` a downloaded modlet carries, and the Mod Settings screen both
reads and writes `Config/<Name>.toml` under that mod's folder. So the path
goes through `ModTomlPath.TryResolve`, which requires the name to be one
plain file name (no directory separator on any platform, no drive or stream
colon, nothing the platform forbids in a file name, no control character,
and no name Windows reserves for a device such as `NUL` or `Com1`, which
.NET's invalid-name list does not carry) and then requires the composed
path to still resolve inside `<mod>/Config/`. A mod that fails is skipped
with a line in the log rather than half-listed. The second check is the
guarantee; the name filter only makes the failure message say why.

The two rules the platform does not give are the control character and the
device name. A Linux or macOS host reports only NUL and the separator as the
characters a name may not hold, and the name is then written into a log line
and matched against the reload marker, where a newline forges a line. A name
that is a device on the machine the mod runs on opens that device, so a read
returns nothing and a save disappears.

Enforced by `scripts/toml_gate/Program.cs` (`TestModTomlPath`, run by
`scripts/test_toml_document.py`) and, at source level, by
`scripts/test_settings_reload.py`.

## Decided 2026-09-28: a float is written in the spelling of the runtime that writes it

The in-game DLL targets net48 and the offline gate compiles the same file
as net8, so the two are not the same runtime and do not format a double
alike. `"R"` is the shortest round-trip spelling only from .NET Core 3.0
on; on .NET Framework it is the older format and is not exact for every
double, which is how a setting the player saved comes back as a different
number. `FormatFloat` therefore uses `"G17"` under `NETFRAMEWORK` and
`"R"` everywhere else. The gate can only exercise the net8 branch, so the
net48 one rests on the format's documented guarantee rather than on a
failing case that was seen.

## Decided 2026-09-28: a handler on a static list is registered once

`ModApi` registers the `ModEvents.UnityUpdate` poll and
`XUiC_ModSettingsScreen` registers `Log.LogCallbacks`; neither list is
unhooked by the engine or the game. So each registration is guarded by a
flag (`updateHooked`, `watchingLog`) and the unhook runs only when the
guard is set. An unguarded second registration is a real leak rather than
a duplicate callback: the static event keeps the screen alive, holding
every discovered `TargetMod` and its parsed text, and the poll runs twice
per frame. Enforced by `scripts/test_settings_reload.py`.

The ilspy runtime fallback in `scripts/verify-patch-targets.py` restores
`PATH` from the value it started with after every failed candidate: a
failed candidate's SDK directory left prepended shadows the real `dotnet`
for the rest of the run.

## Decided 2026-09-28: the settings reader and the save path are guarded

Two threads reach this mod's state. The Unity thread polls the watched
TOML from `ModEvents.UnityUpdate` and draws the settings screen; the
dedicated server runs the console command on its telnet thread, and
`Log.LogCallbacks` fires on whichever thread logged. So:

- every static field in `ModSettings` (the watched path, the mtime/length
  stamps, the setting values) is read and written under one `Gate`. A
  `wrench set` from telnet therefore cannot land between a reload's
  `ResetToDefaults` and its apply. `Monitor` is reentrant, which is what
  lets the reload path call the public `TrySet` while holding the gate,
  and the `Applied` event is raised after the lock is released so a
  handler never sees half-applied values.
- the screen's reload latch is marker and flag under one lock, not a
  `volatile` flag beside a plain field: a log line arriving between the
  marker swap and the flag clear would otherwise be dropped.
- a save is a whole read-modify-write of one file, so it runs under a
  per-path lock, and the file's write time and length are re-read after
  the staging write and before the swap: the staging write is itself part
  of the window another program's save can land in, so asking any earlier
  writes that writer over. An outside writer that landed is re-spliced
  around (`SpliceAttempts` bounds it) instead of being overwritten by a
  whole-file copy of what the save read. The staging name
  carries the writing process's id, so two writers of one file never
  truncate or rename each other's staging file. Two programs saving one
  file in the same instant are still last-writer-wins; the signature
  re-read narrows that window, it does not close it.
- the assembly probe's memo table is filled under its own lock, and an
  inconclusive probe is not memoized: the lookup and the fill are one
  check-then-act, and caching a partial answer would pin a live-reloading
  mod to "restart required" for the rest of the session.
- `TrySave` writes through `<path>.wrench-tmp.<process id>` and renames it
  over the destination, as the save-replacement decision above sets out;
  that record carries the reasoning and the staging-name hazard. Writing
  in place truncates first, so a hot-reloading mod polling the file (or a
  config tool reading it) can read a half-written settings file, and a
  crash in that window loses the old text with no rollback path.
  `File.Replace` is the rename; where a runtime does not implement it,
  the fallback is delete plus move.

Enforced by `scripts/test_settings_reload.py` and
`scripts/test_target_save_coherence.py`.

## Decided 2026-09-28: time and the file system are injected, not reached for

The two places this mod waits or touches a disk are the settings file's
watch (a poll interval and a debounce, on elapsed time) and a save's
staging swap (a retry that waits between attempts). Both read the
environment directly: a private `Stopwatch` for elapsed time, and
`System.IO.File` for everything. A run of either therefore cannot be
reproduced, and neither can be stepped through the timing that decides
what happens: the debounce that stands between a half-written save and a
read one, and the replace that loses to the target's own reader.

`ModClock` (`IMonotonicClock`, `StopwatchClock`, one settable `Current`)
is the only clock the shipped sources read, and `ModFileSystem`
(`IFileSystem`, `SystemFileSystem`, one settable `Current`) is the only
filesystem they read or write through: the codec it codes with,
`TomlFile`, takes and returns bytes and names no path, so no other
route to a disk is left open to the code that makes a decision. The
production implementations
hold the behavior that was already there: monotonic elapsed time rather
than `Time.unscaledTime` (a float loses sub-second resolution on a
dedicated server with weeks of uptime, and a saved file silently stops
being picked up), and the tolerant share mode plus the file's own encoding
on the way out. What changed is that a simulated run can put its own
clock and filesystem in those two slots and drive the same decisions the
game makes, including a save that loses the replace race, a write that
fails, and a reload that lands at a chosen moment.

`scripts/test_settings_reload.py` holds both seams: no direct
`System.IO` file call (`File.` or `Directory.` on a word boundary) and no
`Thread.Sleep` outside a comment in `ModSettings.cs` or `TargetMod.cs`,
and each caller reading its clock and its filesystem through the seam. A
target mod's bytes go through `TomlFile`, the seam decided below, so the
ban is on the call and not on the letters in its name.

## Decided 2026-09-28: the save path is game-free, and simulated from a seed

Two seams are only seams if the whole path goes through them. One read
did not: `TargetMod.TryRead` called `TomlFile` directly while the write
beside it went through `ModFileSystem`, so a simulated save would have read
the real file and written the simulated one. That read is now
`IFileSystem.ReadAllText(path, out encoding)`, whose production
implementation opens the file through the seam's own share mode and hands
the bytes to `TomlFile` to decode, and the byte-level reader is public so a
simulated disk decodes by the same rule the game does. The seam also
creates a staged sibling exclusively, removing the name first: a
create-or-truncate follows a link planted at a name any writer in the mod
folder can guess.

The second thing a simulated save needs is for the code it drives to exist
without the game. `TargetMod` took a `Mod`, probed its assemblies and
called `ModManager` and `Log`; the screen, the playtest provider and every
caller of it reached through that. So the mod list and the assembly probe
moved to `TargetModDiscovery.cs`, and a `TargetMod` is now a name, a
display name, the mod's own folder, the file's path and a yes/no. The
folder is a string, so the contract costs nothing, and it is what
distinguishes two installed mods carrying the same name: the screen
reopens on it and a log line names the file it wrote. `TargetMod.cs` compiles with no game
reference, which is what lets `scripts/toml_gate/` build it as shipped.

`scripts/toml_gate/Simulation.cs` is that run: a virtual clock, an
in-memory disk whose faults are offered on demand (a replace lost to a
reader, a write that fails before it lands, a read that fails, a runtime
with no atomic replace), and a seed that draws the faults and the edits
and nothing else. Thirty-two seeds, each a whole run, each checked after
every step rather than at the end: the file is always a whole document
that parses with all of its keys, a save reported as successful is
byte-identical to the text the target then holds, a save reported as
failed changed nothing, a staging file never outlives its save, and one
lost replace waits exactly once, on the injected clock. Every fourth step
another writer gets in first, so the stale-span relocate is walked too.
The gate runs the canonical seed twice and diffs the two traces, so a
determinism leak is a non-empty diff naming the step that leaked, and the
seed is printed with the trace so a failure replays from it.

`ModSettings`, the watched file's poll and debounce, is not in that run
yet: it is coupled to `UnityEngine`'s logger and to `Mod`, and giving it a
log seam is the same move `TargetMod` just made. Enforced by
`scripts/test_settings_reload.py` and
`scripts/test_target_save_coherence.py` (the seams, and the game-free
save path), and by `scripts/test_toml_document.py` (the run itself).

## Decided 2026-09-28: running a save twice lands where running it once did

A save is the operation a second execution actually reaches. The player
presses save again, the screen's own retry re-runs it, a launch after a
crash lands on whatever the killed run left, and a hot-reloading mod's
watch re-reads the file either way.

- The edit itself is idempotent (one value span is replaced with one
  value span), and the gate now proves the whole thing: the same save run
  twice leaves the file byte-identical to one run, with no staging file
  left behind either time.
- The swap's two-move fallback has one window the method cannot close: a
  run killed between `Move(target, previous)` and `Move(staged, target)`
  leaves the mod with no settings file, its old text at `.wrench-prev` and
  its new text at a `.wrench-tmp.<pid>` name no later run looks for.
  Discovery skipped a mod whose file is not there, so the mod disappeared
  from the screen and the settings were reachable only by hand.
  `TargetMod.RecoverInterruptedSave` moves the sibling back, and both
  discovery and the save path ask before reading, so the next run
  converges. It acts only while the target is missing, which is what makes
  the run after *that* one a no-op.
- The failure paths that close their own swap are unchanged: a save that
  reports success leaves exactly the text it showed, and a save that
  reports failure changed nothing. Both are already gate invariants.

Held by the same run: `scripts/test_toml_document.py` drives the
interrupted-swap and save-twice scenarios, and
`scripts/test_target_save_coherence.py` holds the shape of the recovery
so a refactor cannot quietly drop it.

## Decided 2026-09-28: a mod is identified by its folder, and an unproven answer is not an answer

A selection the screen restores on reopen and a label the status line shows
are both answers about an installed mod, and both were wrong in ways a
player pays for:

- Two installed mods can carry the same ModInfo name, so restoring the
  selection by name could come back on the other mod's settings.
  `TargetMod` now holds a `ModIdentity` (the mod's folder plus its ModInfo
  name) and the screen matches on the folder. The identity is a value, not
  the game's `Mod`, so the save path stays drivable offline.
- `HasSettingsComponent` answers false both for "this mod has no settings
  component" and for "an assembly would not load, so I could not tell".
  Memoizing the second as the first labelled the mod "restart required" for
  the rest of the session, so the probe now reports whether it was
  definitive and only a definitive answer is memoized. The memo table is
  read and filled under one lock, since the probe runs on whichever thread
  asked for it.

Both are held by `scripts/test_target_save_coherence.py`, whose two
negative controls mutate the file the probe actually lives in
(`TargetModDiscovery.cs`); they had been pointed at `TargetMod.cs`, where
the method is not, so a mutation there could never have been observed.

The screen's own bindings are held the same way: every `{name}` in
`Config/XUi_Menu/windows.xml` is answered by a `case` in a controller, so a
renamed or mistyped binding cannot reach a player as the literal `{name}` on
a label (`scripts/test_static_checks.py`, "binding-answered").

## Decided 2026-09-28: the status line is tinted, and an unreadable file is not an empty one

The status line is the screen's only feedback, and it was one flat grey for
four different situations, so reading which one applied cost the whole
sentence. It is now tinted by the same switch that picks the sentence
(`{statuscolor}`, from `XUiC_ModSettingsScreen.StatusColor`), so the two can
never disagree: applied is green, waiting and unconfirmed amber, refused
and unreadable red, everything else the neutral grey.

The settings list's empty state said "this mod has no editable settings
here" for a file that would not parse, which is the opposite of the truth
and points a player at the wrong problem. The two cases are separate now
(`{noentries}` and `{noreadable}`, `wrenchSettingsUnreadable`), and a read
or write refused by the OS says which step failed before the exception's own
text, which was the only part of it written for a developer.

## Decided 2026-09-28: the package carries nothing about the machine that made it

`make package` zips the staged tree, so every entry's stored metadata is
shipped bytes. Three leaks were there and are now closed:

- entry **modes**. `cp` creates each staged file through the builder's umask
  and `zip` stores the result, so the same source packaged under umask 077 and
  under umask 022 produced two archives that differ in every entry.
  `scripts/build.sh` ends by normalizing the staged tree to `a-w,a+rX`, which
  also means a later run (and `make clean`) has to restore owner-write before
  removing it: unlinking a file needs write permission on its directory.
- the build machine's **timezone**. `zip` writes the DOS timestamp in the
  local zone, so a builder in UTC+9 stamped every entry nine hours later than
  one in UTC. The package recipe exports `TZ=UTC` and `LC_ALL=C` (the sort was
  already `LC_ALL=C`; the whole pipeline is now under it).
- the **toolchain**. The net48 DLL was built by whatever `dotnet` the host
  happened to carry, and the documented `DOTNET_ROOT` inventory key was never
  read by the build, so a machine whose SDK was off `PATH` failed even with
  the key set. `global.json` now pins the SDK (8.0.100, rolling forward only
  inside the 8.0 feature band: a major bump changes Roslyn's emitted metadata,
  so an unpinned major builds different bytes from the same source) and
  `scripts/build.sh` resolves `dotnet` from `PATH` first,
  then `$DOTNET_ROOT/dotnet`. The offline gates that compile a C# harness
  resolve it the same way, through `dotnet_executable()` in
  `scripts/lib/local_env.py`, so a machine that keeps its SDK off `PATH`
  builds the mod and runs `make test` alike.
  `scripts/test_toolchain_floor.py` holds that one order against both.

Timestamps come from `SOURCE_DATE_EPOCH` (the last commit's time, overridable),
never the wall clock, and entries are added in sorted order. Enforced by
`scripts/verify-package.sh`, which packages twice under a different umask,
locale and timezone and compares the sha256; CI's package step and
`make check` both run that one script, so a local run and a push cannot
disagree about it.

## Decided 2026-09-28: the game log is the whole observability surface

A save is two events, not one: the file is written, and the mod that owns
it re-reads it. Both were silent. The status line is on the screen the
player closes, so on a dedicated server nobody could tell afterwards
whether a settings change had landed, which key it changed, or which mod
had not picked it up. Both events are now in the game log, through
`Log.Out`/`Log.Warning` under the one `ModApi.LogPrefix`, naming the mod,
the key, the value and the file: the write, the refused write with its
cause, the re-read, and the ten seconds of silence after a save to a
hot-reloading mod that never logged its re-read. The console command says
the same for what it changes, with the sender, because a telnet session
ends with its console.

There are no metrics, no traces and no alerts, and adding any would cost
more than it returns: a Unity mod running inside the game has no
collector to send them to, and the game log is what an operator of a
dedicated server already reads. `Log` is the only logger used anywhere in
`src/`: a line written through Unity's `Debug` reaches the editor, not
the server's log, and a second spelling of the prefix splits a search.
Enforced by `scripts/test_target_save_coherence.py`.

An exception that escapes the settings load at `InitMod` is now caught
and named rather than aborting the mod's load with a bare stack trace,
and every caught exception that becomes an error message carries its type
beside its message, so "access denied" is not read as a parse error.

## Decided 2026-09-28: the save-path gate follows the writer's new shape

`TargetMod.TryWrite` takes the path it stages beside instead of reading
`TomlPath` itself, so the staged-write assertions in
`scripts/test_settings_reload.py` were naming locals the writer no longer
has and the gate was red on a contract the code still met. The gate now
reads the writer's body and its call site, and holds the same properties
one step tighter than before: the staging sibling, the seam write, the
atomic replace, the retry and its wait, the unlink on the failure path,
and the one call site that names the target's path. A negative control
turns the staging write into an in-place one and requires the gate to
reject it.

## Open questions

- (none yet)
