# Local Environment

## Machine-local paths live in `.local.env`, nowhere else

Never hardcode a machine-local path in tracked files. Every mod scaffolded
from this template carries an ignored `.local.env` at its root (documented
by the tracked `.local.env.example`, which is the authoritative list) with
these keys:

```dotenv
SEVEN_DAYS_TO_DIE_DIR=""         # client game-install root (required to build C#)
SEVEN_DAYS_TO_DIE_SERVER_DIR=""  # optional SteamCMD Linux dedicated server
HORDEFORGE_ROOT=""               # directory holding the hordeforge tool checkouts
PLAYTEST_ROOT=""                 # hordeforge/7dtd-playtest checkout
CONNECT_ROOT=""                  # hordeforge/7dtd-fastconnect checkout
ASSET_PIPELINE_ROOT=""           # hordeforge/7dtd-asset-pipeline (shamway) checkout
DOTNET_ROOT=""                   # optional; toolchain location when not on PATH
ILSPYCMD=""                      # optional; ilspycmd for Harmony target validation
UNITY_EDITOR=""                  # optional; only to rebuild asset bundles
```

A mod may add its own keys (`Wrench` adds `WRENCH_ATOMIC_MOD_DIR`, the
AtomicDoomsday checkout its live suite edits); read `.local.env.example`
rather than this list when you need the full inventory.

### One precedence rule, everywhere

An exported environment variable wins over the same key in `.local.env`.
The shell scripts share one loader (`scripts/local-env.sh`) that saves every
already-exported value across the source and restores it afterwards; the
Python tools share `scripts/lib/local_env.py`, which reads the environment
first. A key present only in the file always applies, whether or not some
other key was exported: a machine that sets `SEVEN_DAYS_TO_DIE_DIR` in its
shell still gets its `SEVEN_DAYS_TO_DIE_STEAMCMD` from the file. A missing
`.local.env` is not an error; each caller then names the value it could
not find. `scripts/test_local_env_precedence.py` holds this rule.

An exported value is a value even when it is empty, so
`SEVEN_DAYS_TO_DIE_DIR=` in a CI job blanks the key instead of handing back
the path in a developer's file.

Both readers accept one grammar, so the same file answers the same question
to a shell script and to a Python one: a `KEY="value"` assignment per key, an
optional `export ` prefix, blank and `#` lines ignored, and the last
assignment of a repeated key winning the way a later shell assignment does.
`scripts/playtest/Makefile` resolves its game install through the shell
loader rather than sourcing the file a second time, because the mod DLL and
the playtest provider have to be built against the same install.

`DOTNET_ROOT` is resolved the same way by everything that needs the .NET
SDK: `scripts/build.sh` and the offline gates (through
`dotnet_executable()` in `scripts/lib/local_env.py`) take `dotnet` from
`PATH` first and fall back to `$DOTNET_ROOT/dotnet`, so a machine that
keeps its SDK off `PATH` needs the key set once, not once per tool.
`scripts/test_toolchain_floor.py` holds the order.

### Optional dedicated-server overrides

| Key | Default when unset |
|---|---|
| `SEVEN_DAYS_TO_DIE_SERVER_APP_ID` | `294420` (the 7 Days to Die dedicated server) |
| `SEVEN_DAYS_TO_DIE_SERVER_RUN_SECONDS` | `90`, the `make server-smoke` boot window |
| `SEVEN_DAYS_TO_DIE_SERVER_CONFIG` | `<server>/serverconfig.wrench.xml` |
| `SEVEN_DAYS_TO_DIE_STEAMCMD` | SteamCMD on `PATH` |
| `SEVEN_DAYS_TO_DIE_STEAMCMD_DIR` | `~/.local/share/steamcmd` |

`WRENCH_SKIP_DLL=1` is a build-time knob, not a path: it stages the XML-only
package, which is how CI exercises packaging without the game assemblies.

### Optional saves location

| Key | Default when unset |
|---|---|
| `SEVEN_DAYS_TO_DIE_SAVES_DIR` | the Proton prefix derived from the client install: `compatdata/251570/pfx/drive_c/users/steamuser/AppData/Roaming/7DaysToDie/Saves` |

`scripts/verify-patched-config.py` reads it (exported value first, then
`.local.env`); set it when the world lives under a second prefix or a
non-Steam launcher, where that derivation does not hold.

`new-mod.sh` writes this file at scaffold time. On a machine where it is
missing, blank, or invalid: **ask the user for the absolute path before
doing any game-file work.** Do not guess a platform path or reuse one from
docs, chat history, or another machine. Validate a client path by checking
`Data/Config/items.xml` exists under it. `.local.env` must never be
committed, packaged, or made a runtime dependency of the shipped mod.

## Game install (client)

Steam AppID `251570`. On a Linux/Proton setup the install is the Windows
build (`7DaysToDie.exe`), not native. Key subfolders:

| Path | Contents |
|---|---|
| `Data/Config/*.xml` | Vanilla config: items, blocks, entities, recipes, loot, progression. Ground truth to **read (never edit)**. `Data/Config/XML.txt` documents property semantics. |
| `Mods/` | Pre-installed with only `0_TFP_Harmony` (TFP's official Harmony dependency — see csharp-harmony.md). Install-level mods can be dropped here. |

The game install is **read-only reference**. All mod content is authored in
the mod repo and copied or symlinked out; never write anything under the
install directory. When checking reference mods, inspect only the directory
named exactly `Mods/` — not backups, `Mods.DF/`, or other collections.

## Dedicated server

Separate SteamCMD install, AppID `294420` — never installed over the client
directory. Configure it via `SEVEN_DAYS_TO_DIE_SERVER_DIR`; the server's
Managed directory is `7DaysToDieServer_Data/Managed/`. Set
`EACEnabled=false` in its serverconfig when smoke-testing DLL mods.

`make deploy-server` stages the package, copies it to
`<server>/.wrench-deploy/staging`, then swaps it into `Mods/Wrench/` with a
rename; the deployment it replaced is kept at
`<server>/.wrench-deploy/previous` and `make rollback-server` moves it back.
Keep that directory out of `Mods/`: anything with a `ModInfo.xml` under
`Mods/` is loaded as a second copy of the mod.

`install-server`, `deploy-server` and `server-smoke` all take an exclusive
`flock` on `<server>/.wrench-deploy/lock` first (`hold_server_lock` in
`scripts/server-common.sh`), so a second run against the same install waits
instead of racing the staging folder, the rollback point, or a server that
is still booting with the mod it is about to swap out.

## Proton prefix / user data (saves, logs, per-user Mods)

The Steam Play prefix lives under the owning library's
`steamapps/compatdata/251570/`; the 7DTD userdata directory inside it is
`pfx/drive_c/users/steamuser/AppData/Roaming/7DaysToDie/` — containing
`Saves/`, `logs/` (XML patch errors, C# exceptions, Harmony failures at
startup), and a per-user `Mods/` folder. That per-user `Mods/` is generally
preferred over the install-directory one: it survives updates/verifies and
needs no write access to the Steam library.

### The Steam client must be running, even when Proton is launched directly

Launching via `proton run 7DaysToDie.exe` bypasses the Steam *launcher*, not
the Steam *API*. With no Steam process alive the log shows
`[Steamworks.NET] SteamAPI_Init() failed`, startup continues, and the client
later stalls at a rendered menu backdrop with no menu — easily misread as a
GPU/display fault. When a client stalls at the backdrop, grep the log for
`SteamAPI_Init` before investigating anything else. (`steam -silent` starts
Steam in the tray.)

## Deploying a mod for local testing

A 7DTD mod is just a folder:

1. `make build` stages the deployable modlet under `dist/<Name>/`.
2. Symlink or copy it into a Mods folder (per-user
   `AppData/Roaming/7DaysToDie/Mods/<Name>/` preferred).
3. Launch and check the log (or in-game console, `~`) for XPath errors or
   exceptions. A clean log alone does not prove an XPath matched — verify
   the change in game.
4. EAC must be **disabled** for DLL/Harmony mods (launcher toggle; the
   `SkipWithAntiCheat` ModInfo flag is a related but separate per-mod
   setting — see mod-structure.md).

## Client launch, mute, capture: use the sibling tools

Client launch (intro skip, EAC-off Local platform, Epic-dialog avoidance),
OS-level audio mute/unmute, and screenshot/evidence capture are owned by
`hordeforge/7dtd-fastconnect`, `hordeforge/7dtd-playtest`, and `shamway`
(`hordeforge/7dtd-asset-pipeline`) — see
[sibling-tooling.md](sibling-tooling.md). Do not write a launch script,
pactl mute loop, or screenshot loop in the mod. Note the launchers mute the
client's audio stream at the OS layer by default, and WirePlumber persists
that per-application state — unmute with fastconnect's
`unmute_client_audio.sh` while a stream is live.
