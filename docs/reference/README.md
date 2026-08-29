# 7 Days To Die Modding Reference

General, mod-agnostic reference material for developing 7 Days To Die mods.
This directory is copied into every mod scaffolded from Anvil, so a
generated mod's `AGENTS.md` can index into it with no external fetch.

Mod-specific design/architecture notes belong in the mod's own `docs/`
(`design.md`, `architecture.md`, `adr/`), never here.

## Contents

- [best-practices.md](best-practices.md) — the vendored canonical guide
  (`hordeforge/.github/MODDING_BEST_PRACTICES.md`): modding layers,
  XPath/XUi/Harmony/ModAPI conventions, dedicated-server tuning, packaging
  checklist, anti-patterns. **Binding, not background reading.** Sync
  manually from upstream when it changes; update its provenance header date.
- [agent-rules.md](agent-rules.md) — the distilled, enforceable core of the
  guide: what an agent must check before shipping a change.
- [mod-structure.md](mod-structure.md) — `ModInfo.xml` schema, folder
  layout, load order, EAC.
- [xml-patching.md](xml-patching.md) — the XPath patch system for modifying
  vanilla config without replacing whole files.
- [csharp-harmony.md](csharp-harmony.md) — C# DLL mods and Harmony patching.
- [environment.md](environment.md) — how machine-local install paths are
  configured (`.local.env`), deploying for testing, client-launch caveats.
- [sibling-tooling.md](sibling-tooling.md) — which hordeforge repo owns
  playtesting, launch, mute, capture, asset builds; what a mod must never
  recreate.
- [playtest_running.example](playtest_running.example) — the shared
  playtest/client exclusivity lock's file format (the lock itself is owned
  by `hordeforge/7dtd-playtest`).

## Where to look things up

Before probing the running game for something it already documents — a
keybind, a console command's arguments, a property's meaning, a Harmony
target's signature — check these first, in order:

1. **The installed game.** `Data/Config/*.xml` for content,
   `Data/Config/controls.xml` for bindings, and
   `ilspycmd -t <Class> Assembly-CSharp.dll` for method bodies,
   console-command names, usage strings, and argument defaults.
   Authoritative for the installed version; read-only.
2. **`hordeforge/7dtd-engine-research`** — existing research on this
   engine. A separate repository: never depend on it from build or runtime
   code; if it is not cloned locally, ask the user where it is rather than
   assuming it is unavailable.
3. **Online sources** — official wiki, patch notes, community references
   (see best-practices.md §17).

If none of those answer it, experimenting in a running client is fine — just
not the first thing to reach for. Whatever you work out by experiment, write
it down (here if general, in the mod's docs if mod-specific), with the
source and tool that produced it. "It seemed to work in game" is not a
source.

## Sources

Anything here that depends on local game files must be verified against the
game installation configured in the mod's ignored `.local.env`
(`SEVEN_DAYS_TO_DIE_DIR`), never against a hardcoded path. Re-verify against
the current game version when in doubt — modding APIs have changed across
major updates.
