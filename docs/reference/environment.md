# Local Environment

## Machine-local paths live in `.local.env`, nowhere else

Never hardcode a machine-local path in tracked files. Every mod scaffolded
from this template carries an ignored `.local.env` at its root (documented
by the tracked `.local.env.example`) with these keys:

```dotenv
SEVEN_DAYS_TO_DIE_DIR=""         # client game-install root (required to build C#)
SEVEN_DAYS_TO_DIE_SERVER_DIR=""  # optional SteamCMD Linux dedicated server
UNITY_EDITOR=""                  # optional; only to rebuild asset bundles
HORDEFORGE_ROOT=""               # directory holding the hordeforge tool checkouts
```

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
