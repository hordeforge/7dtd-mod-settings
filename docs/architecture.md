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
Booleans toggle on press; every other kind is a text field that saves on
Enter (strings are decoded for display and re-encoded on save; other
kinds show the raw token).

## Open questions

- (none yet)
