# Threat Model — Wrench (Mod Settings)

What can be attacked in this mod, what it costs, and what stands in the way.
Every entry point, boundary, and control below carries a file reference so the
next pass can re-verify it against the code.

Scope: the mod itself (C# DLL, XUi XML patches, shipped TOML) and the repository
tooling that builds, deploys, and playtests it. The game engine, the mod
runtime, and the mod store are out of scope; where Wrench relies on one of them
the reliance is named as a boundary.

Point vulnerabilities belong to `sec-review`, per-endpoint authorization to
`authz-review`, the dependency inventory to `deps-review`. This document is the
map those reviews aim at.

Last reviewed: 2026-09-28, against `docs/architecture.md` decisions through
2026-08-30 and the mod version `0.2.0.0` (`ModInfo.xml`).

## Risk-ranked summary

Ranked by exploitability against the stated attacker followed by impact. "Local"
means the attacker already runs code as the player on that machine, which is the
base assumption for every entry point except the telnet console.

| # | Threat | Boundary | Who | Impact | Control today |
|---|---|---|---|---|---|
| 1 | Write outside a mod folder: the target path is built from the third-party mod's own name, with no path validation | B2 (installed mod content → game process) | Any installed mod author, or anyone who can drop a `ModInfo.xml` | Wrench writes a `.toml` at an attacker-chosen relative path, as the player's account | none; see T-1 |
| 2 | Arbitrary setting change from the telnet console: `wrench set` consults no sender identity or permission | B3 (network console → process) | Anyone who reaches the telnet port and knows the shared password | Mod behaviour changes without the in-game path; no audit trail of who did it | none; see T-2 |
| 3 | Malformed or hostile TOML from a third-party mod stalls the screen: the hand-written parser is fed unbounded third-party text on the UI thread | B2 | Mod author, or anyone editing a mod's config on disk | UI thread stall, settings row pool starved, the mod becomes unmanageable in-game | partial; see T-3 |
| 4 | Config destruction by a stale or wrong span: a value edit is applied to whatever the file holds at write time | B1 (player → Wrench → disk) | Local, concurrent config writer (config tool, the mod itself, a second client) | A neighbouring key is silently rewritten and the whole file is written back over someone else's save | controls present; see M-1, M-2 |
| 5 | A hostile mod's assembly is reflected over (`GetTypes()`) to decide its hot-reload label | B2 | Mod author | Wrench's decision quality only; assembly loading happens in the mod loader, not here | contained; see T-4 |
| 6 | Mod's own settings file drives live behaviour with no integrity check beyond the TOML grammar | B2 (this mod's `Config/Wrench.toml`) | Anyone with write access to the install folder | Wrench's own behaviour changes on the next poll, no restart | partial; see M-4 |
| 7 | Deployment tooling writes into the live game install and server, and holds machine paths in `.local.env` | B4 (tooling → filesystem) | Local | A mistaken deploy overwrites a working mod copy; `rollback-server` exists for that | controls present; see M-5 |

T-1 and T-2 have no mitigation in the code today. They are recorded here for
`sec-review` and `authz-review` to take; this document does not fix them.

## Attack surface inventory

Entry points, in the order data reaches the process.

| Entry point | Kind | Source | Handling | Reference |
|---|---|---|---|---|
| Mod Settings options page | UI (keyboard, mouse, gamepad) | Local player | Per-row pooled controllers, value written on Enter | `src/Wrench/ModSettingsScreen.cs:25`, `src/Wrench/ModSettingsRows.cs:8` |
| `wrench` console command | CLI, in-game console and dedicated-server telnet over TCP | Local player, or a network peer on the telnet port | Fixed subcommand grammar, name/value pair, output to `SdtdConsole` | `src/Wrench/ConsoleCmdWrench.cs:40` |
| `Config/Wrench.toml` (this mod's own settings) | File, polled at runtime | Install folder | mtime/length watch, debounce, TOML-subset parse, name lookup | `src/Wrench/ModSettings.cs:88`, `src/Wrench/ModSettings.cs:71` |
| `Config/<Mod>.toml` (every other mod with one) | File, discovered and written | Install folder, third-party content | Discovered, parsed, listed; written only on an explicit user edit | `src/Wrench/TargetMod.cs:222`, `src/Wrench/TargetMod.cs:100` |
| Other mods' managed assemblies | Reflection | Install folder, third-party content | `GetTypes()`, then a name and field lookup | `src/Wrench/TargetMod.cs:261` |
| `Config/XUi_Menu/*.xml`, `Config/items.xml` | Config file parsed by the engine at load | This repo (trusted), or a player-edited install | XPath patch, loaded by `ModManager`; Wrench does not parse it | `Config/XUi_Menu/windows.xml:1`, `Config/XUi_Menu/xui.xml:1` |
| `scripts/build.sh`, `deploy-server.sh`, `install-server.sh` | Local tooling, writes outside the repo | Developer | Allowlist staging, backups, `steamcmd ... validate` | `scripts/build.sh:9`, `scripts/install-server.sh:17` |
| `scripts/lib/game_telnet.py` | Network client, TCP to the telnet console | Development server | Shared password held in memory only | `scripts/lib/game_telnet.py:50` |
| `scripts/playtest/` provider mod | Code injected into the running game | Development tooling | Scenario provider, `[InternalsVisibleTo("WrenchPlaytest")]` | `src/Wrench/ModApi.cs:5`, `scripts/playtest/Source/WrenchPlaytest.cs:8` |
| `.github/workflows/ci.yml` | Build/CI, runs on every PR | GitHub | Actions pinned by commit SHA, `permissions: contents: read`, no secrets used | `.github/workflows/ci.yml:1` |
| `.local.env` | Local config carrying machine paths | Developer | Gitignored, sourced by the tooling | `.gitignore:5`, `.local.env.example:1` |

Not present, and worth stating because it is the common assumption: Wrench opens
no listener, opens no outbound connection, and ships no update or telemetry
mechanism. The only network surface is the console command, which runs inside
the game's own telnet server (`scripts/lib/game_telnet.py:1` describes that
listener and its loopback bind when passwordless).

## Trust boundaries

**B1 — local player to Wrench to other mods' files.** The player drives the
options page; Wrench reads and writes TOML files belonging to other mods, on
the player's behalf. There is no authentication or authorization inside this
boundary at all: whoever can use the game's process owns the writes. The
boundary is therefore exactly the operating-system account, and Wrench must not
be the thing that widens it (T-1).

**B2 — installed mod content to the Wrench process.** Mods are third-party
code and data of unknown provenance. Three crossings: the hand-written TOML
parser fed text from other mods' `Config/<Mod>.toml` (`src/Wrench/TomlSettings.cs`),
the target path derived from a mod's own declared name
(`src/Wrench/TargetMod.cs:50`), and reflection over a mod's assemblies
(`src/Wrench/TargetMod.cs:261`). This is the boundary a hostile mod controls
directly, and it is the one Wrench treats most carefully on the parse side and
least carefully on the path side.

**B3 — console and telnet to the process.** `ConsoleCmdWrench` is
auto-discovered by the engine, so anyone who can type into the in-game console
or authenticate to the telnet port can run it. Telnet authentication is a single
shared password with no per-user identity, and a passwordless server binds the
listener to loopback (`scripts/lib/game_telnet.py:15`). Wrench's command does
not consult its `CommandSenderInfo` at all (`src/Wrench/ConsoleCmdWrench.cs:40`),
so it is exactly as available as the console it hangs off.

**B4 — build and deploy tooling to the machine.** The scripts read `.local.env`,
copy files into the game install and the dedicated server, and connect out to
the telnet console. This boundary is crossed by the developer's own hands, not
by an attacker, and its failure mode is a bad deploy rather than a compromise.

**B5 — build to runtime.** `scripts/build.sh:45` stages an allowlist of
mod-content directories into `dist/Wrench/`, and CI packages with
`WRECH_SKIP_DLL=1` because the game assemblies are proprietary
(`.github/workflows/ci.yml:31`). A file that is not on the allowlist never
ships, which is the control that keeps build-time material (`src/`, `scripts/`,
`docs/`) out of the deployable.

## Assets and impact

| Asset | Why it matters | Blast radius if lost or corrupted |
|---|---|---|
| Other mods' `Config/<Mod>.toml` files | Wrench's entire product is editing them; they hold each mod's live configuration | That mod misbehaves or stops starting. A wrong write is silent, because the write is verified only against Wrench's own parse (`src/Wrench/TomlEdit.cs:78`) |
| This mod's `Config/Wrench.toml` | Drives Wrench's own behaviour, applied without restart | Wrench misbehaves; currently one boolean, so today the blast radius is small and grows with every added setting (`src/Wrench/ModSettings.cs:29`) |
| The mod install tree and the game install | Wrench writes into other mod folders, inside the install the game trusts | Corruption costs a reinstall, not the machine, except for T-1 |
| The dedicated server's mod folder | `deploy-server.sh` replaces it in place | Server starts with a broken mod config; `rollback-server` is the documented way back |
| The local machine path inventory in `.local.env` | Names install locations and tool checkouts | Disclosure is information about the host layout, not a credential; it is gitignored (`.gitignore:5`) and enforced by `scripts/test_local_path_inventory.py` |
| Telnet password | Shared, single-password, no identity | Anyone holding it has the whole server console. Wrench does not store it; `scripts/lib/game_telnet.py:50` holds it in memory for the call |
| Player saves and world data | **Not touched by Wrench.** It never opens a world, save, or player profile | none |

No signing keys, no personal data, and no credentials at rest are held by this
mod. That is worth writing down plainly, because the absence is the reason the
remaining impact is limited to configuration integrity.

## Threats per boundary

STRIDE classes that apply, tied to the entry points above. T-1 to T-4 are the
ones carried into the summary.

**B1 (player to files).**
- T-4: wrong-span write. Tampering with a user's configuration, through the save
  path itself. The edit is verified against a re-parse of the same text, so a
  stale row landing on a neighbouring key is the real risk; the controls are M-1
  and M-2.
- Denial of service, local: an edit that cannot be relocated refuses the write
  rather than guessing (`src/Wrench/TargetMod.cs:162`). The failure mode is a
  refusal message, not data loss.

**B2 (mod content to process).**
- T-1: spoofing and elevation of privilege through path construction. A mod
  declares its own name in its `ModInfo.xml`; Wrench concatenates that name into
  a path and then reads and writes it (`src/Wrench/TargetMod.cs:50`,
  `src/Wrench/TargetMod.cs:100`). Nothing checks that the result stays inside
  `mod.Path`. A name carrying path separators moves the write outside the mod
  folder, with the player's privileges, and the user is never shown the path
  beyond the display name (`src/Wrench/ModSettingsScreen.cs:221`).
- T-3: denial of service through the parser. `TomlSettings` is a hand-written
  parser for a TOML subset, and Wrench parses a third-party file both on screen
  open (`src/Wrench/TargetMod.cs:81`) and on every value the user types
  (`src/Wrench/TomlEdit.cs:35`). There is no size or nesting cap in the code.
  A file crafted to be expensive to parse costs a UI-thread stall every time the
  screen is opened.
- Information disclosure: none beyond the config text, which is already readable
  by the local account. Wrench never logs setting values, only names and
  outcomes (`src/Wrench/ModSettings.cs:220`).
- Repudiation: a write leaves no record beyond the target mod's own log line.
  Wrench has no audit log of who changed which key.
- T-4: reflection over a third-party assembly (`src/Wrench/TargetMod.cs:261`).
  `GetTypes()` runs a loader for every type in the assembly, and
  `ReflectionTypeLoadException` handling already anticipates assemblies that
  cannot load. The effect on Wrench is bounded to a wrong status label
  ("applies live" versus "restart required"), and the code says so
  (`src/Wrench/TargetMod.cs:290`). The residual risk is that a type named
  `ModSettings` with a field named `FilePollIntervalSeconds` is enough to be
  labelled hot-reloading, which is a false label, not a wrong write.

**B3 (console and telnet).**
- T-2: elevation of privilege. `wrench set` changes a running setting for anyone
  who can reach the console, and the command never looks at
  `CommandSenderInfo` (`src/Wrench/ConsoleCmdWrench.cs:40`). On a dedicated
  server the telnet console is the remote administration surface; whether the
  engine gates the command itself is an `authz-review` question, but Wrench
  contributes no check of its own.
- Spoofing: the telnet password is shared, so the log line naming a console
  action names no person.
- Information disclosure: `wrench settings` prints current values to the
  console (`src/Wrench/ModSettings.cs:324`), which for Wrench today is one
  boolean and for a config-heavy target mod would be the whole config.
- Repudiation: the console log records that `wrench set` ran, not who ran it.

**B4/B5 (tooling and build).**
- T-5: a deploy replaces the server's mod folder in place. Availability of a
  dedicated server depends on it; the backup and rollback path are the control.
- No secrets cross B4. `.local.env` holds paths, not credentials, and CI uses
  no secrets at all (`.github/workflows/ci.yml:7`).

## Mitigations

Existing controls, mapped to the threats they cover.

| # | Control | Covers | Reference |
|---|---|---|---|
| M-1 | A value edit is validated against the shared TOML-subset grammar before anything is written | T-3, T-4 | `src/Wrench/TomlEdit.cs:29` |
| M-2 | The whole candidate file is re-parsed and checked to keep every key, in order, and to change no unrelated value | T-4 | `src/Wrench/TomlEdit.cs:78` |
| M-3 | A stale row is relocated by key name on the file as it is now, and an ambiguous or vanished key refuses the edit | T-4 | `src/Wrench/TargetMod.cs:105`, `src/Wrench/TargetMod.cs:162` |
| M-4 | Writes go to a sibling temp file and are swapped in, and the temp file is removed on every failing path | T-4, availability | `src/Wrench/TargetMod.cs:121` |
| M-5 | A file Wrench cannot parse is listed as unreadable and never written to | T-3, T-4 | `src/Wrench/TargetMod.cs:84`, `src/Wrench/ModSettingsRows.cs:37` |
| M-6 | Every read is wrapped; a mod that cannot be inspected is skipped with a log line instead of taking the screen down | availability | `src/Wrench/TargetMod.cs:192`, `src/Wrench/TargetMod.cs:231` |
| M-7 | A broken settings file keeps the current values rather than resetting to defaults, and the reload is debounced so a half-written save is not read | T-3 | `src/Wrench/ModSettings.cs:147`, `src/Wrench/ModSettings.cs:176` |
| M-8 | UI rows come from a fixed pool, so a mod with many keys cannot grow the widget tree without bound | T-3 | `src/Wrench/ModSettingsScreen.cs:208` |
| M-9 | Only a declared setting name is applied, and only a parsed bool is accepted for it; unknown names change nothing | T-2, T-6 | `src/Wrench/ModSettings.cs:293` |
| M-10 | Staging is an allowlist, so build-time material is not shippable | B5 | `scripts/build.sh:45` |
| M-11 | Server deploy keeps the copy it replaced; `make rollback-server` restores it | T-5 | `scripts/deploy-server.sh` |
| M-12 | CI runs with `contents: read`, no secrets, and actions pinned by commit SHA | B5 | `.github/workflows/ci.yml:7` |
| M-13 | Machine paths live in a gitignored file, enforced by a gate | T-5 | `.gitignore:5`, `scripts/test_local_path_inventory.py` |

### Gaps

Threats with no mitigation, in the order the summary ranks them.

1. **T-1, path construction from a third-party mod name.** No control. The
   check that is missing is a containment test: the resolved path must stay
   under `mod.Path`. Hand to `sec-review`.
2. **T-2, unauthenticated `wrench set`.** No control inside Wrench. Hand to
   `authz-review`; the model records that Wrench performs no sender check.
3. **T-3, parser resource use on third-party text.** No size or nesting cap.
   Hand to `sec-review`.
4. **No audit trail for writes.** A setting change is discoverable only by
   diffing the file. Not a fix this document proposes; noted so the
   `o11y-review` scope is not confused with it.
5. **No signature or provenance check on mod content.** Wrench trusts every
   installed mod's files, exactly as the game does. This is a deliberate
   acceptance, matching the engine's own model, not an oversight.

### Claims the code does not back

Checked against the README and the reference docs, and nothing was found that
overstates a control. The two statements closest to a claim, and what backs them:

- "Server-owned values must be changed on the server (console/telnet)"
  (`Config/Localization.csv:3`) is true and is a statement about the game's
  model, not about a control in Wrench: Wrench's writes are local file writes
  with no channel to a running server. The README already lists pushing
  server-side edits through an authenticated channel as deliberately not built
  (`README.md:37`), so the two agree.
- The hot-reload label is a heuristic, matched by type and field name
  (`src/Wrench/TargetMod.cs:290`), and the code says so where it is used. It
  affects a status line only, never a write.

### Single points of failure

- `TomlSettings` parse plus `TomlEdit` verification is the only thing standing
  between third-party TOML text and a write to another mod's config. It carries
  T-1, T-3, and T-4 at once, and it is the code to read first when any of them
  is being fixed.
- The `TargetMod` constructor is the only place a mod's name becomes a path
  (`src/Wrench/TargetMod.cs:50`). One place, so the T-1 fix is one place.
- Telnet's single shared password is the whole authentication story on a
  dedicated server. Wrench adds nothing to it and cannot weaken it, but every
  B3 threat sits behind it.

## Abuse cases

Scenarios, each with the code path that enables it. None of these is an
exploit claim against a running system; they are the paths a hostile or
careless actor would walk, named so a review can check them.

1. **A mod named for a parent directory rewrites a file outside its folder.**
   The mod author controls the name that becomes `mod.Path + "/Config/" +
   name + ".toml"` (`src/Wrench/TargetMod.cs:50`). Nothing between that line and
   `File.Replace` (`src/Wrench/TargetMod.cs:130`) re-checks the resolved path.
   Wrench only reaches the write because a player opened the Mod Settings tab
   and pressed Enter (`src/Wrench/ModSettingsScreen.cs:144`): the attacker needs
   the file to be listed, not the player to type anything specific.
2. **A player with only telnet access changes a live setting.** Connect with the
   shared password, run `wrench set <name> <value>`. The command takes the
   name and value straight from the parameter list
   (`src/Wrench/ConsoleCmdWrench.cs:64`) and applies them in process
   (`src/Wrench/ModSettings.cs:293`), with no record of who asked.
3. **A mod ships a config file that is expensive to parse.** The file is parsed
   every time the Mod Settings screen opens (`src/Wrench/TargetMod.cs:81`) and
   again on every value the user types (`src/Wrench/TomlEdit.cs:35`). There is
   no cap to hit, and the parse runs on the UI thread, so the cost lands on the
   player trying to fix the mod.
4. **A second writer races a save.** A config tool saves between Wrench's read
   and its write. M-3 turns the worst outcome into a refusal, and the refusal
   message names the cause ("it changed outside Wrench",
   `src/Wrench/TargetMod.cs:185`). A save that lands between the relocation and
   the write is the residual window M-3 does not close.
5. **A config file that parses as a different document than the user saw.** The
   screen shows values from the last parse; the write goes to the file as it is
   now. M-2 verifies the result against that same current text, so a key that
   moved meaning is caught only as a parse or key-count failure.

No client-side-only enforcement exists to trust wrongly: there is no
client/server split in the mod, the UI is the only editor, and the game process
is the only consumer.

## Response readiness

Notes only, no infrastructure implied, and no owner, cadence, or process
invented here.

- There is no `SECURITY.md` in this repository. Nothing to correct in one today.
  Adding one requires a disclosure contact and a supported-versions list that
  only the maintainer can supply, so this document does not fabricate them.
- A vulnerability report has no documented path to a fix. The gates a change
  must pass are written down (`AGENTS.md`, "Testing"), and
  `scripts/test_rules_have_gates.py` enforces that every recorded rule names its
  gate; what is missing is a statement of where a report is sent and who
  decides it is a vulnerability.
- Security-relevant events this mod produces are log lines only: the settings
  applied line (`src/Wrench/ModSettings.cs:332`), the per-problem line
  (`src/Wrench/ModSettings.cs:220`), and the per-mod skip line
  (`src/Wrench/TargetMod.cs:240`). There is no structured security event, no
  write audit, and no log of who issued a console command. Log structure belongs
  to `o11y-review`; the gap recorded here is that settings writes leave no trail
  distinguishing them from an external editor.
