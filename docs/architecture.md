# Architecture — Wrench (Mod Settings)

Technical implementation decisions. Significant, hard-to-reverse decisions
also get an ADR in [`adr/`](adr/) — link it from here. Layer escalations
(XML-only → Harmony, per docs/reference/agent-rules.md) always warrant one.

## Repo map

`src/Wrench/` is the mod, in three layers with dependencies running down:
the TOML document (`TomlSettings.cs` parses, `TomlEdit.cs` writes) and the
target-mod model (`TargetMod.cs`) know nothing about the UI; the XUi
controllers (`ModSettingsScreen.cs`, `ModSettingsRows.cs`) sit on top of them;
the entry points (`ModApi.cs`, `ConsoleCmdWrench.cs`, `ModSettings.cs`) wire
the two together. One namespace, no subfolders: at eight files the folder
would carry no information the names do not.

`scripts/` splits three ways, and nothing crosses the lines:

- `test_*.py` are the offline gates, at the top level because
  `run-offline-tests.sh` globs for them there. `validate-*.py` and
  `verify-*.py` need an installed game, so they are tools, not gates.
- `lib/` is the only shared layer. `gate_report.py` owns the PASS/FAIL shape
  every gate prints, and `local_env.py` owns both the `.local.env` lookup and
  `mod_dir()`, the marker walk every script uses to find the mod root. A
  script that needs either imports it; it does not keep a second copy.
- `toml_gate/` and `playtest/` are the C# hosts: a console runner that
  exercises the parser and writer, and the provider that drives the live
  suite. They are build-time, so they sit under `scripts/`, not `src/`.

Shell scripts sit beside the Python they drive (`server-common.sh` with the
server lane, `run-offline-tests.sh` with the gates) and share no library
with them.

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

- **Encoding.** UTF-8 without a byte order mark on every read and write
  (`ModFileText`), a BOM still honoured on read so a file from elsewhere
  loads. Relying on the API default made the written bytes depend on the
  runtime rather than on the mod.
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
subscribes to `Log.LogCallbacks` and reports applied-live only once that
mod's own `settings (reload Config/<Mod>.toml)` line appears; mods
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
previous mod's marker armed.

## Decided 2026-09-28: a save is replaced in atomically, in the file's own encoding

The file is the whole integration surface (ADR 0001), so a save must never
be able to destroy it. Two properties, both held by
`scripts/test_target_save_coherence.py`:

- `TargetMod.TryWrite` writes a sibling `.wrench-tmp` and puts it in with
  `File.Replace`, with a bounded retry because the target mod's own settings
  watch holds the file for the milliseconds it takes to read it and a
  replace needs delete access. `File.WriteAllText` on the target truncates
  first, so a crash, a shutdown, or a full disk between the truncate and
  the last byte would leave the mod with an unparsable settings file, or
  with none, which is the one outcome the file-as-surface rule exists to
  prevent. A runtime with no atomic replace falls back to delete-then-move,
  which still never writes over the target in place.
- `TargetMod.TryRead` reads bytes, not text, and reports the encoding it
  decoded (UTF-8 with or without byte order mark, UTF-16 either way); the
  save writes that same encoding back. `File.ReadAllText` decodes a mark
  away and keeps no record of it, so a plain UTF-8 write stripped a mark
  the file was carrying: an edit that changed one value token had silently
  changed the file's first three bytes as well.

## Decided 2026-09-28: a save parses the file once, and probes an assembly once

`TargetMod.TrySave` reads the file once, splices into that read, and takes
its new `Text`/`Entries` from the parse `TomlEdit.TryReplaceValue` already
verified before writing, instead of reading the file back and re-parsing
what it had just written. The verification itself is unchanged: the
candidate is still re-parsed and compared key by key against the caller's
parse of the original text, which the caller supplies instead of having
the writer re-derive it.

`TargetMod.HasSettingsComponent` walks every type every assembly of a mod
declares, and an installed mod's assemblies do not change while the game
runs, so its answer is memoized per mod path and paid once per mod rather
than on every opening of the screen. Enforced by
`scripts/test_target_save_coherence.py`.

## Decided 2026-09-28: bounded reload wait, empty-state labels

The post-save wait for a hot-reloading mod's reload line is bounded by
`RELOAD_CONFIRM_SECONDS` in `XUiC_ModSettingsScreen`; past it the mod's
save state becomes `SaveUnconfirmed` and the status says the change was
saved but not re-read, instead of promising a reload forever. The state
belongs to the watched mod, not to the selection, so switching mods
mid-wait cannot move the outcome onto the wrong row.

Both list panes carry an empty-state label (`nomods`, `noentries`),
so a window with nothing to show says why rather than showing an empty
frame; the strings are localization keys, as every other Mod Settings
string that is not a live status is.

## Decided 2026-09-28: another mod's TOML is read and written through `TomlFile`

`File.ReadAllText` and `File.WriteAllText` are wrong on both sides of the
settings screen's write. They strip a byte order mark on read and never
write one back, so the first save of a mod's `Config/<Mod>.toml` changes
bytes outside the edited span, which ADR 0001 forbids; and both open with
`FileShare.Read`, which Windows refuses with a sharing violation while the
hot-reloading mod's own save watcher holds the same file open for read and
write, the mode `ModSettings.Poll` uses. `TomlFile.cs` reads the bytes,
detects the declared encoding (UTF-8 with or without a mark, UTF-16 and
UTF-32 either way round), and writes the file back in it, both sides with
`FileShare.ReadWrite | FileShare.Delete`. Enforced by
`scripts/test_toml_document.py`, which round-trips each of those file
shapes through the shipped writer.

## Decided 2026-09-28: a mod's settings file is resolved, never concatenated

`Mod.Name` is not this mod's to choose: it comes out of whichever
`ModInfo.xml` a downloaded modlet carries, and the Mod Settings screen both
reads and writes `Config/<Name>.toml` under that mod's folder. So the path
goes through `ModTomlPath.TryResolve`, which requires the name to be one
plain file name (no directory separator on any platform, no drive or stream
colon, nothing the platform forbids in a file name) and then requires the
composed path to still resolve inside `<mod>/Config/`. A mod that fails is
skipped with a line in the log rather than half-listed. The second check is
the guarantee; the name filter only makes the failure message say why.

Enforced by `scripts/toml_gate/Program.cs` (`TestModTomlPath`, run by
`scripts/test_toml_document.py`) and, at source level, by
`scripts/test_settings_reload.py`.

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

## Open questions

- (none yet)
