# Architecture — Wrench (Mod Settings)

Technical implementation decisions. Significant, hard-to-reverse decisions
also get an ADR in [`adr/`](adr/) — link it from here. Layer escalations
(XML-only → Harmony, per docs/reference/agent-rules.md) always warrant one.

## Decisions

(Format: `## Decided YYYY-MM-DD: <topic>` — approach, alternatives, why.)

## Decided 2026-08-30: the TOML file is the integration surface

See [ADR 0001](adr/0001-toml-file-is-the-integration-surface.md). Wrench
edits the target mod's `Config/<Mod>.toml` in place; mods built on
Anvil's settings component notice the save through their own hot-reload
watch. No registration API, no shared assembly, no load-order
dependency.

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
on reopen. The "applied live" observation is a one-shot latch and is
cleared when the screen opens, so a reload line seen while it was closed
cannot stamp a newly discovered mod as saved-and-applied.

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

## Open questions

- (none yet)
