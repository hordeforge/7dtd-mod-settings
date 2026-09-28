# 🔧 Wrench (Mod Settings)

> **Part of [HordeForge](https://github.com/hordeforge)**: High-Performance Systems Engineering for 7 Days to Die.

![CI](https://github.com/hordeforge/7dtd-mod-settings/actions/workflows/ci.yml/badge.svg)
![license](https://img.shields.io/github/license/hordeforge/7dtd-mod-settings)

Adds a Mod Settings screen to the in-game options menu, listing every installed mod that ships a Config/<Mod>.toml settings file and letting the player view and edit those settings from the UI. Edits are written back in place to the mod's own TOML; mods built on Anvil's settings component apply them live through their existing hot-reload watch, with no coupling between this mod and theirs.

A 7 Days to Die mod. Scaffolded from
[Anvil](https://github.com/hordeforge/7dtd-mod-template); the modlet is this
directory itself — `make build` stages the deployable copy under
`dist/Wrench/`, `make package` zips it for release.

## What it does

- **Mod Settings tab** in the regular options menu (pause menu → Options
  and main menu → Options), pure XUi XML + ModAPI, no Harmony patches
  ([ADR 0002](docs/adr/0002-options-tab-via-xui-patch-no-harmony.md)).
- **Discovery**: every loaded mod with a `Config/<Mod>.toml` appears; a
  file the TOML-subset parser rejects is listed as unreadable and never
  written to.
- **Editing**: every value is edited as its raw token in a text field
  saved on Enter, so a key can change kind (`false` to `["Tactical"]`);
  booleans also get a one-click flip. The comment block above a key is
  its help text, shown in the description panel on hover.
- **In-place write-back**: only the edited key's value span changes; the
  file is byte-identical everywhere else, so comments and layout survive
  ([ADR 0001](docs/adr/0001-toml-file-is-the-integration-surface.md)).
- **Live-reload awareness**: mods built on Anvil's settings component
  are labeled applies-live, and after a save the status reports whether
  the mod actually re-read the file (its own reload log line); others
  are marked restart-required. A joined client is told edits change only
  its local copy.
- Wrench's own `Config/Wrench.toml` shows up in its own UI.

Deliberately not built in v1 (see `docs/design.md`): `# ui:` comment
annotations for labels/ranges/enums, pushing server-side edits through
an authenticated channel, and a WebMod panel over the same file surface.

## Build and test

```bash
make help                   # list every target with a one-line description
make test                   # offline gates (scripts/test_*.py; needs the .NET SDK)
make lint                   # ruff + mypy --strict over scripts/, then shellcheck
make build                  # stage dist/Wrench/ (needs .local.env, see below)
make package                # dist/Wrench.zip — extracts to Mods/Wrench/
make validate-xml           # every Config xpath against the installed game
make verify-patched-config  # every patch element proven applied, from a save's ConfigsDump
make validate-patch-targets # every [HarmonyPatch] target against Assembly-CSharp (ilspycmd)
make install-server         # provision the dedicated server via SteamCMD (EAC off)
make deploy-server          # swap the packaged mod into the server's Mods/ (keeps the previous copy)
make rollback-server        # put the deployment the last one replaced back
make server-smoke           # deploy + boot the server briefly, prove the mod loaded
make playtest               # live wrench-mod-settings suite via hordeforge/7dtd-playtest
```

One gate at a time: `make test TF="toml"` runs only the offline tests whose
name contains `toml`.

Host tools: Python 3.10+ (the floor `pyproject.toml` and `make test` both
enforce), `git`, `make`, `zip`; the pinned `ruff` and `mypy` that `make lint`
runs, installed with `python3 -m pip install -r requirements-dev.txt` (the
one place their versions are written down, and what CI installs, so a green
local run and a green remote run mean the same thing); `shellcheck`; the .NET
SDK, not just the runtime, for the net48 build and for the two TOML
round-trip gates inside `make test` (`global.json` pins the floor at
8.0.100 and rolls forward to a newer major, so a runtime-only install is not
enough); `ilspycmd` (`dotnet tool install -g ilspycmd`) for patch-target
validation, `steamcmd` for the dedicated-server lane.

Machine-local paths (game install, hordeforge tool checkouts) live in the
ignored `.local.env` — copy `.local.env.example` and fill it in.

Runtime settings live in `Config/Wrench.toml` in the installed mod
folder; saving it applies without a restart, and the in-game/telnet
command `wrench` lists, changes, and reloads them.

## Docs

- [`TODO.md`](TODO.md) — what's next
- [`CHANGELOG.md`](CHANGELOG.md) — what each release changed for a player or a mod author
- [`docs/design.md`](docs/design.md) — gameplay decisions
- [`docs/architecture.md`](docs/architecture.md) — technical decisions ([`docs/adr/`](docs/adr/) for formal records)
- [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) — attack surface, trust boundaries, risks, and the controls that back them
- [`docs/reference/`](docs/reference/) — general 7DTD modding reference and best practices (binding)
- [`AGENTS.md`](AGENTS.md) — working instructions for agent sessions
