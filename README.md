# 🔧 Wrench (Mod Settings)

> **Part of [HordeForge](https://github.com/hordeforge)**: High-Performance Systems Engineering for 7 Days to Die.

![CI](https://github.com/hordeforge/7dtd-mod-settings/actions/workflows/ci.yml/badge.svg)
![license](https://img.shields.io/github/license/hordeforge/7dtd-mod-settings)

Adds a Mod Settings screen to the in-game options menu, listing every installed mod that ships a Config/<Mod>.toml settings file and letting the player view and edit those settings from the UI. Edits are written back in place to the mod's own TOML; mods built on Anvil's settings component apply them live through their existing hot-reload watch, with no coupling between this mod and theirs.

A 7 Days to Die mod. Scaffolded from
[Anvil](https://github.com/hordeforge/7dtd-mod-template); the modlet is this
directory itself — `make build` stages the deployable copy under
`dist/Wrench/`, `make package` zips it for release.

## Build and test

```bash
make test                   # offline gates (scripts/test_*.py)
make lint-shell             # shellcheck, full severity
make build                  # stage dist/Wrench/ (needs .local.env, see below)
make package                # dist/Wrench.zip — extracts to Mods/Wrench/
make validate-xml           # every Config xpath against the installed game
make verify-patched-config  # every patch element proven applied, from a save's ConfigsDump
make validate-patch-targets # every [HarmonyPatch] target against Assembly-CSharp (ilspycmd)
make install-server         # provision the dedicated server via SteamCMD (EAC off)
make server-smoke           # deploy + boot the server briefly, prove the mod loaded
```

Host tools: `python3`, `git`, `make`, `shellcheck`, `zip`; `dotnet` (net48
build) for C# mods, `ilspycmd` (`dotnet tool install -g ilspycmd`) for
patch-target validation, `steamcmd` for the dedicated-server lane.

Machine-local paths (game install, hordeforge tool checkouts) live in the
ignored `.local.env` — copy `.local.env.example` and fill it in.

Runtime settings live in `Config/Wrench.toml` in the installed mod
folder; saving it applies without a restart, and the in-game/telnet
command `wrench` lists, changes, and reloads them.

## Docs

- [`TODO.md`](TODO.md) — what's next
- [`docs/design.md`](docs/design.md) — gameplay decisions
- [`docs/architecture.md`](docs/architecture.md) — technical decisions ([`docs/adr/`](docs/adr/) for formal records)
- [`docs/reference/`](docs/reference/) — general 7DTD modding reference and best practices (binding)
- [`AGENTS.md`](AGENTS.md) — working instructions for agent sessions
