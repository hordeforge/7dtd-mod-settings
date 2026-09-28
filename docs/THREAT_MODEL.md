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

Last reviewed: 2026-09-28, against the mod version `0.3.0.0` (`ModInfo.xml:7`).

## Third-party dependencies

The whole inventory, since it is three lines long and every part of it is a
path someone else can change:

| What | Where it enters | Held by |
|---|---|---|
| The mod itself (C# DLL, XML patches, shipped TOML) | none; this repository | `scripts/test_stdlib_only.py` for the Python half; no `.csproj` declares a `PackageReference` or carries vendored source |
| ruff, mypy and mypy's transitive distributions | `requirements-dev.txt`, installed by `.github/workflows/ci.yml` | exact pins in that one file, single-sourced by `scripts/test_lint_toolchain_declared.py` |
| Assembly-CSharp, UnityEngine.CoreModule, LogLibrary, 0Harmony | the game install, by path at build time (`src/Wrench/Wrench.csproj`) | the install is read-only reference; `make build` fails loud when a path is absent |
| The hordeforge tool checkouts (playtest, ilspycmd) | `.local.env` | `scripts/test_local_path_inventory.py`, `scripts/test_upstream_tooling.py` |

Not covered, and not claimed: the tool installs are pinned by version, not by
hash, so a re-upload of a pinned version is not detected; and nothing here
generates an SBOM, which for a modlet a player extracts from a zip rather
than a package it resolves is the point where an inventory stops paying for
itself.

## Risk-ranked summary

Ranked by exploitability against the stated attacker followed by impact. "Local"
means the attacker already runs code as the player on that machine, which is the
base assumption for every entry point except the telnet console.

| # | Threat | Boundary | Who | Impact | Control today |
|---|---|---|---|---|---|
| 1 | Unbounded parser work on third-party TOML: `TomlSettings` is a hand-written parser fed other mods' text on the UI thread, with no size or nesting cap | B2 (installed mod content → game process) | Mod author, or anyone editing a mod's config on disk | UI thread stall, the mod becomes unmanageable in-game | none; see T-3 |
| 2 | Arbitrary setting change from the telnet console: `wrench set` performs no sender or permission check | B3 (network console → process) | Anyone who reaches the telnet port and knows the shared password | Mod behaviour changes without the in-game path | no authz in Wrench; M-17 records the actor; see T-2 |
| 3 | A hostile TOML document declares an encoding or a byte order mark the naive path would mangle; the file this mod does not own is written back | B2 | Mod author, or a file copied between machines | Silent corruption of a third party's config outside the edited span | partial; see M-7, T-6 |
| 4 | Config destruction by a stale or wrong span: a value edit is applied to whatever the file holds at write time | B1 (player → Wrench → disk) | Local, concurrent config writer (config tool, the mod itself, a second client) | A neighbouring key is silently rewritten and the whole file is written back over someone else's save | controls present; see M-1, M-2, M-3 |
| 5 | A mod's own settings file drives live behaviour with no integrity check beyond the TOML grammar | B2 (this mod's `Config/Wrench.toml`) | Anyone with write access to the install folder | Wrench's own behaviour changes on the next poll, no restart | partial; see M-4 |
| 6 | A hostile mod's assembly is reflected over (`GetTypes()`) to decide its hot-reload label | B2 | Mod author | Wrench's decision quality only; assembly loading happens in the mod loader, not here | contained; see T-4 |
| 7 | Setting values and full config paths are written to the game log | B2 (third-party config → host log) | Anyone who can read the game log | Values of a mod this mod does not own become readable to whoever holds the log | see T-7 |
| 8 | Deployment tooling writes into the live game install and server, and holds machine paths in `.local.env` | B4 (tooling → filesystem) | Local | A mistaken deploy overwrites a working mod copy; `rollback-server` exists for that | controls present; see M-5 |

T-1 (path construction from a third-party mod's name) was ranked the top threat
at the previous review and is no longer on this list: `ModTomlPath` now resolves
the name rather than concatenating it, and the resolved path is asserted to stay
inside the mod folder. It is recorded below as M-14 so the control, and the
reason it exists, stay visible.

T-3 and T-2 have no mitigation in the code today. They are recorded here for
`sec-review` and `authz-review` to take; this document does not fix them.

## Attack surface inventory

Entry points, in the order data reaches the process.

| Entry point | Kind | Source | Handling | Reference |
|---|---|---|---|---|
| Mod Settings options page | UI (keyboard, mouse, gamepad) | Local player | Per-row pooled controllers, value written on Enter | `src/Wrench/ModSettingsScreen.cs:25`, `src/Wrench/ModSettingsRows.cs:68` |
| `wrench` console command | CLI, in-game console and dedicated-server telnet over TCP | Local player, or a network peer on the telnet port | Fixed subcommand grammar, name/value pair, output to `SdtdConsole`, every outcome logged with the sender | `src/Wrench/ConsoleCmdWrench.cs:40` |
| `Config/Wrench.toml` (this mod's own settings) | File, polled at runtime | Install folder | mtime/length watch through the filesystem seam, debounce, TOML-subset parse, name lookup | `src/Wrench/ModSettings.cs:93`, `src/Wrench/ModSettings.cs:213` |
| `Config/<Mod>.toml` (every other mod with one) | File, discovered and written | Install folder, third-party content | Path resolved and containment-checked, then discovered, parsed, listed; written only on an explicit user edit | `src/Wrench/TargetModDiscovery.cs:67`, `src/Wrench/ModTomlPath.cs:24` |
| A third-party mod's declared name | Field of third-party content, becomes a path | `ModInfo.xml` of an installed mod | Checked for being one plain file name, then the composed path must resolve under the mod's `Config` directory | `src/Wrench/ModTomlPath.cs:38`, `src/Wrench/ModTomlPath.cs:49` |
| Other mods' managed assemblies | Reflection | Install folder, third-party content | `GetTypes()`, then a name and field lookup, result memoized per mod path | `src/Wrench/TargetModDiscovery.cs:129` |
| The filesystem seam | The one path to a disk, in this mod | Callers inside the mod | Staging sibling created exclusively after an unlink, `File.Replace`, `Flush(true)`, shared-access opens | `src/Wrench/ModFileSystem.cs:158`, `src/Wrench/ModFileSystem.cs:178` |
| A config file's declared encoding and byte order mark | File bytes | Install folder, third-party content | Decoded as the bytes declare, re-encoded as they were read, so a save is byte-faithful outside the edited span | `src/Wrench/ModFileSystem.cs:136`, `src/Wrench/ModFileText.cs:1` |
| `Config/XUi_Menu/*.xml`, `Config/items.xml` | Config file parsed by the engine at load | This repo (trusted), or a player-edited install | XPath patch, loaded by `ModManager`; Wrench does not parse it | `Config/XUi_Menu/windows.xml:1`, `Config/XUi_Menu/xui.xml:1` |
| `scripts/build.sh`, `deploy-server.sh`, `install-server.sh` | Local tooling, writes outside the repo | Developer | Allowlist staging, staged copy then replace, `steamcmd ... validate` | `scripts/build.sh:67`, `scripts/deploy-server.sh:127` |
| `scripts/lib/game_telnet.py` | Network client, TCP to the telnet console | Development server | Shared password held in memory only | `scripts/lib/game_telnet.py:60` |
| `scripts/playtest/` provider mod | Code injected into the running game | Development tooling | Scenario provider, `[InternalsVisibleTo("WrenchPlaytest")]` | `src/Wrench/ModApi.cs:6`, `scripts/playtest/Source/WrenchPlaytest.cs:24` |
| `.github/workflows/ci.yml` | Build/CI, runs on every PR | GitHub | Actions pinned by commit SHA, `permissions: contents: read`, no secrets used | `.github/workflows/ci.yml:7`, `.github/workflows/ci.yml:22` |
| `.local.env` | Local config carrying machine paths | Developer | Gitignored, loaded through `scripts/local-env.sh` and `scripts/lib/local_env.py` | `.gitignore:5`, `.local.env.example:1` |

Not present, and worth stating because it is the common assumption: Wrench opens
no listener, opens no outbound connection, and ships no update or telemetry
mechanism. The only network surface is the console command, which runs inside
the game's own telnet server (`scripts/lib/game_telnet.py:15` describes that
listener and its loopback bind when passwordless).

## Trust boundaries

**B1 — local player to Wrench to other mods' files.** The player drives the
options page; Wrench reads and writes TOML files belonging to other mods, on
the player's behalf. There is no authentication or authorization inside this
boundary at all: whoever can use the game's process owns the writes. The
boundary is therefore exactly the operating-system account.

**B2 — installed mod content to the Wrench process.** Mods are third-party
code and data of unknown provenance. Four crossings: the hand-written TOML
parser fed text from other mods' `Config/<Mod>.toml`
(`src/Wrench/TomlSettings.cs:26`), the target path resolved from a mod's own
declared name (`src/Wrench/ModTomlPath.cs:24`), that file's declared encoding
and byte order mark (`src/Wrench/ModFileSystem.cs:136`), and reflection over a
mod's assemblies (`src/Wrench/TargetModDiscovery.cs:129`). This is the boundary
a hostile mod controls directly.

**B3 — console and telnet to the process.** `ConsoleCmdWrench` is
auto-discovered by the engine, so anyone who can type into the in-game console
or authenticate to the telnet port can run it. Telnet authentication is a single
shared password with no per-user identity, and a passwordless server binds the
listener to loopback (`scripts/lib/game_telnet.py:15`). Wrench performs no
authorization of its own: `CommandSenderInfo` is read only to name the actor in
the log line (`src/Wrench/ConsoleCmdWrench.cs:90`), never to decide whether the
command may run.

**B4 — build and deploy tooling to the machine.** The scripts read `.local.env`,
copy files into the game install and the dedicated server, and connect out to
the telnet console. This boundary is crossed by the developer's own hands, not
by an attacker, and its failure mode is a bad deploy rather than a compromise.

**B5 — build to runtime.** `scripts/build.sh:67` stages an allowlist of
mod-content directories into `dist/Wrench/`, and CI packages with
`WRENCH_SKIP_DLL=1` because the game assemblies are proprietary
(`scripts/verify-package.sh`, the package lane `make check` and CI both run).
A file that is not on the allowlist never
ships, which is the control that keeps build-time material (`src/`, `scripts/`,
`docs/`) out of the deployable.

## Assets and impact

| Asset | Why it matters | Blast radius if lost or corrupted |
|---|---|---|
| Other mods' `Config/<Mod>.toml` files | Wrench's entire product is editing them; they hold each mod's live configuration | That mod misbehaves or stops starting. A wrong write is silent, because the write is verified only against Wrench's own parse (`src/Wrench/TomlEdit.cs:128`) |
| This mod's `Config/Wrench.toml` | Drives Wrench's own behaviour, applied without restart | Wrench misbehaves; currently one boolean, so today the blast radius is small and grows with every added setting (`src/Wrench/ModSettings.cs:381`) |
| The mod install tree and the game install | Wrench writes into other mod folders, inside the install the game trusts | Corruption costs a reinstall, not the machine: every write target is now asserted to be inside the mod's own `Config` directory (`src/Wrench/ModTomlPath.cs:49`) |
| The dedicated server's mod folder | `deploy-server.sh` replaces it in place | Server starts with a broken mod config; the replaced copy is kept for rollback (`scripts/deploy-server.sh:153`) |
| The local machine path inventory in `.local.env` | Names install locations and tool checkouts | Disclosure is information about the host layout, not a credential; it is gitignored (`.gitignore:5`) and enforced by `scripts/test_local_path_inventory.py` |
| Telnet password | Shared, single-password, no identity | Anyone holding it has the whole server console. Wrench does not store it; `scripts/lib/game_telnet.py:60` holds it in memory for the call |
| The game log | Carries Wrench's write and console records (T-7) | A log reader learns setting values and the absolute config paths of mods this mod does not own |
| Player saves and world data | **Not touched by Wrench.** It never opens a world, save, or player profile | none |

No signing keys, no personal data, and no credentials at rest are held by this
mod. That is worth writing down plainly, because the absence is the reason the
remaining impact is limited to configuration integrity.

## Threats per boundary

STRIDE classes that apply, tied to the entry points above.

**B1 (player to files).**
- T-4 (stale-span write): tampering with a user's configuration, through the
  save path itself. The edit is verified against a re-parse of the same text, so
  a stale row landing on a neighbouring key is the real risk; the controls are
  M-1, M-2, and M-3.
- Denial of service, local: an edit that cannot be relocated refuses the write
  rather than guessing (`src/Wrench/TargetMod.cs:440`). The failure mode is a
  refusal message, not data loss.
- Concurrent writers inside one process are serialized by a per-path gate held
  around the whole read-modify-write (`src/Wrench/TargetMod.cs:80`); the
  residual race is between two processes, which is T-4's window.

**B2 (mod content to process).**
- T-3: denial of service through the parser. `TomlSettings` is a hand-written
  parser for a TOML subset, and Wrench parses a third-party file on screen open
  (`src/Wrench/TargetMod.cs:190`) and on every value the user types
  (`src/Wrench/TomlEdit.cs:35`). There is no size or nesting cap in the code.
  A file crafted to be expensive to parse costs a UI-thread stall every time the
  screen is opened.
- T-1, closed: spoofing and elevation of privilege through path construction. A
  mod declares its own name in its `ModInfo.xml`. The name is now checked to be
  one plain file name — no separator, no drive or stream colon, no control
  character, no platform-invalid character, not `.` or `..`, and not a name
  Windows reserves for a device (`src/Wrench/ModTomlPath.cs:96`,
  `src/Wrench/ModTomlPath.cs:121`) — and the composed path must then still
  resolve under the mod's `Config` directory
  (`src/Wrench/ModTomlPath.cs:49`). The second check is what makes the first a
  guarantee, and both run on every platform, because a modlet written on one
  machine runs on another. A mod that fails either is skipped with a log line
  naming the reason (`src/Wrench/TargetModDiscovery.cs:85`).
- T-6: tampering outside the edited span, through encoding. A target file is
  read as its bytes declare and written back in the same encoding, byte order
  mark included (`src/Wrench/ModFileSystem.cs:136`), because a decoder whose
  text is written back must be strict: bytes invalid in the encoding they
  declare are refused rather than replaced. The residual is the declared
  encoding itself, which the file's owner controls.
- Information disclosure: setting values and absolute config paths go to the
  game log on every save (`src/Wrench/ModSettingsScreen.cs:210`) and on every
  console set (`src/Wrench/ConsoleCmdWrench.cs:74`). See T-7.
- Repudiation: a write leaves a game-log line naming the mod, the key, the
  value, and the path (`src/Wrench/ModSettingsScreen.cs:210`). It does not name
  the local account or the player, and there is no separate audit log.
- T-4: reflection over a third-party assembly
  (`src/Wrench/TargetModDiscovery.cs:129`). `GetTypes()` runs a loader for
  every type in the assembly, and `ReflectionTypeLoadException` handling already
  anticipates assemblies that cannot load. The effect on Wrench is bounded to a
  wrong status label (the `wrenchNoteLive` versus `wrenchNoteRestart` note under
  the mod), and the code says so. The residual risk is that a type named
  `ModSettings` with a field named `FilePollIntervalSeconds` is enough to be
  labelled hot-reloading, which is a false label, not a wrong write. An
  inconclusive answer is not memoized, so a load failure is asked again
  (`src/Wrench/TargetModDiscovery.cs:47`).

**B3 (console and telnet).**
- T-2: elevation of privilege. `wrench set` changes a running setting for
  anyone who can reach the console, and the command never checks
  `CommandSenderInfo` before applying the change
  (`src/Wrench/ConsoleCmdWrench.cs:71`). On a dedicated server the telnet
  console is the remote administration surface; whether the engine gates the
  command itself is an `authz-review` question, but Wrench contributes no check
  of its own.
- Spoofing: the telnet password is shared, so the sender name in the log line
  names a console session, not a person. `Sender` falls back to
  `"unknown sender"` when the info carries no name
  (`src/Wrench/ConsoleCmdWrench.cs:92`).
- Repudiation, partly closed: every `set`, `reload`, and rejected subcommand
  writes a game-log line carrying the sender and the outcome
  (`src/Wrench/ConsoleCmdWrench.cs:74`,
  `src/Wrench/ConsoleCmdWrench.cs:60`). The gap that remains is identity, not
  the record: on telnet there is no per-user name to record.
- Information disclosure: `wrench settings` prints current values to the
  console (`src/Wrench/ModSettings.cs:434`), which for Wrench today is one
  boolean and for a config-heavy target mod would be the whole config.

**B4/B5 (tooling and build).**
- T-5: a deploy replaces the server's mod folder in place. Availability of a
  dedicated server depends on it; the retained previous copy is the control.
- No secrets cross B4. `.local.env` holds paths, not credentials, and CI uses
  no secrets at all (`.github/workflows/ci.yml:7`).

## Mitigations

Existing controls, mapped to the threats they cover.

| # | Control | Covers | Reference |
|---|---|---|---|
| M-1 | A value edit is validated against the shared TOML-subset grammar before anything is written | T-3, T-4 | `src/Wrench/TomlEdit.cs:30` |
| M-2 | The whole candidate file is re-parsed and checked to keep every key, in order, and to change no unrelated value | T-4, T-6 | `src/Wrench/TomlEdit.cs:128`, `src/Wrench/TomlEdit.cs:139` |
| M-3 | A stale row is relocated by key name on the file as it is now, and an ambiguous or vanished key refuses the edit | T-4 | `src/Wrench/TargetMod.cs:244`, `src/Wrench/TargetMod.cs:417` |
| M-4 | Writes go to a staging sibling and are swapped in with an atomic replace, retried while the target's own watch holds the file; the staging name is removed on every failing path | T-4, availability | `src/Wrench/TargetMod.cs:330`, `src/Wrench/TargetMod.cs:338` |
| M-5 | A file Wrench cannot parse is listed as unreadable and never written to | T-3, T-4 | `src/Wrench/TargetMod.cs:185`, `src/Wrench/ModSettingsRows.cs:51` |
| M-6 | Every read is wrapped; a mod that cannot be inspected is skipped with a log line instead of taking the screen down | availability | `src/Wrench/TargetMod.cs:447`, `src/Wrench/TargetModDiscovery.cs:80` |
| M-7 | A target file is decoded as its bytes declare and written back in that encoding, byte order mark included, and a decoder whose text is written back refuses bytes invalid in the encoding they claim | T-6 | `src/Wrench/ModFileSystem.cs:136`, `src/Wrench/ModFileSystem.cs:160` |
| M-8 | A broken settings file keeps the current values rather than resetting to defaults, and the reload is debounced so a half-written save is not read | T-3 | `src/Wrench/ModSettings.cs:252`, `src/Wrench/ModSettings.cs:213` |
| M-9 | UI rows come from a fixed pool, and a mod with more settings than rows is reported rather than growing the widget tree without bound | T-3 | `src/Wrench/ModSettingsScreen.cs:310`, `src/Wrench/ModSettingsScreen.cs:315` |
| M-10 | Only a declared setting name is applied, and only a parsed bool is accepted for it; unknown names change nothing | T-2 | `src/Wrench/ModSettings.cs:366`, `src/Wrench/ModSettings.cs:398` |
| M-11 | Staging is an allowlist, so build-time material is not shippable | B5 | `scripts/build.sh:67` |
| M-12 | Server deploy stages a copy and keeps the one it replaced; `make rollback-server` restores it | T-5 | `scripts/deploy-server.sh:127`, `scripts/deploy-server.sh:153` |
| M-13 | CI runs with `contents: read`, no secrets, and actions pinned by commit SHA | B5 | `.github/workflows/ci.yml:7`, `.github/workflows/ci.yml:22` |
| M-14 | A third-party mod's declared name is never concatenated into a path: it is checked to be one plain file name, and the resolved path is asserted to stay under the mod's own `Config` directory | T-1 | `src/Wrench/ModTomlPath.cs:38`, `src/Wrench/ModTomlPath.cs:49` |
| M-15 | The staging sibling is created exclusively after an unlink, so a link planted at that name is unlinked rather than written through, and the write is flushed to the disk before the replace | T-4 | `src/Wrench/ModFileSystem.cs:158`, `src/Wrench/ModFileSystem.cs:172` |
| M-16 | The staging name carries the writing process's id, and a per-path gate serializes writers inside the process, so two savers of one file cannot each report success having written the other's bytes | T-4 | `src/Wrench/TargetMod.cs:92`, `src/Wrench/TargetMod.cs:80` |
| M-17 | Every console subcommand writes a game-log line carrying the sender and the outcome, so a telnet command that outlives its session leaves a record | T-2 repudiation | `src/Wrench/ConsoleCmdWrench.cs:74`, `src/Wrench/ConsoleCmdWrench.cs:90` |
| M-18 | Machine paths live in a gitignored file, enforced by a gate | T-5 | `.gitignore:5`, `scripts/test_local_path_inventory.py` |

M-14, M-15, M-16, and M-17 are the controls the previous review's top-ranked
threats asked for, and each is gated offline rather than asserted here:
`scripts/toml_gate/Program.cs:476` exercises the resolver, `scripts/toml_fuzz/Program.cs:519`
fuzzes it, and `scripts/test_settings_reload.py:210` holds both the
containment and the staging-name contract.

### Gaps

Threats with no mitigation, in the order the summary ranks them.

1. **T-3, parser resource use on third-party text.** No size or nesting cap on
   `TomlSettings`, and it runs on the UI thread. Hand to `sec-review`.
2. **T-2, unauthorized `wrench set`.** No authorization inside Wrench; M-17
   records the actor but does not restrict it. Hand to `authz-review`.
3. **T-6, the declared encoding is the file owner's choice.** A file that
   declares an encoding whose alphabet the file does not hold is refused on
   read (M-7), so the remaining question is what a save writes back for a file
   that declared something exotic but valid. Bounded by the strictness in M-7;
   listed so it is not mistaken for unexamined.
4. **T-7, setting values and paths in the game log.** Deliberate, and the right
   trade for a local mod: a silent write is worse than a readable log
   (`src/Wrench/ModSettingsScreen.cs:208` says so). It does mean a mod's values
   are readable by whoever holds the log.
5. **No signature or provenance check on mod content.** Wrench trusts every
   installed mod's files, exactly as the game does. This is a deliberate
   acceptance, matching the engine's own model, not an oversight.

### Claims the code does not back

Checked against the README, the reference docs, and the previous revision of
this document. The previous revision overstated its own risk, which is the same
defect in the other direction: it named a threat as unmitigated that the code
had already closed, and cited line numbers that had since moved.

- The previous revision claimed the third-party mod name "is concatenated into
  a path" with "nothing checks that the result stays inside `mod.Path`". The
  code resolves it through `ModTomlPath.TryResolve` and asserts containment
  (`src/Wrench/ModTomlPath.cs:49`); the call site says so in its own comment
  ("resolved, never concatenated", `src/Wrench/TargetModDiscovery.cs:61`). The
  claim is withdrawn and the control recorded as M-14.
- It claimed `ConsoleCmdWrench` "does not consult its `CommandSenderInfo` at
  all". It reads it for the log line (`src/Wrench/ConsoleCmdWrench.cs:90`). The
  absence of an authorization check is real and still recorded as T-2.
- It claimed "Wrench never logs setting values, only names and outcomes". Wrench
  logs the value and the absolute path on every save
  (`src/Wrench/ModSettingsScreen.cs:210`) and on every console set
  (`src/Wrench/ConsoleCmdWrench.cs:74`). Corrected, and recorded as T-7.
- The two statements in the shipped docs that come closest to a claim still
  hold:
  - "Server-owned values must be changed on the server (console/telnet)"
    (`Config/Localization.csv:3`) is a statement about the game's model, not
    about a control in Wrench: Wrench's writes are local file writes with no
    channel to a running server. The README already lists pushing server-side
    edits through an authenticated channel as deliberately not built
    (`README.md:37`), so the two agree.
  - The hot-reload label is a heuristic, matched by type and field name
    (`src/Wrench/TargetModDiscovery.cs:129`), and the code says so where it is
    used. It affects a status line only, never a write.

### Single points of failure

- `ModTomlPath` is the only place a mod's declared name becomes a path, and it
  carries the whole of T-1 on two checks (plain name, then containment). One
  place, so it is also the one place a regression would land.
- `TomlSettings` parsing plus `TomlEdit` verification is the only thing standing
  between third-party TOML text and a write to another mod's config. It carries
  T-3, T-4, and T-6 at once, and it is the code to read first when any of them
  is being fixed.
- `ModFileSystem` is the only path to a disk in this mod, so every read, every
  staging write, and the encoding round trip are decided in one file
  (`src/Wrench/ModFileSystem.cs:203`). A defect there is a defect in the whole
  B1 and B2 write path.
- Telnet's single shared password is the whole authentication story on a
  dedicated server. Wrench adds nothing to it and cannot weaken it, but every
  B3 threat sits behind it.

## Abuse cases

Scenarios, each with the code path that enables it. None of these is an exploit
claim against a running system; they are the paths a hostile or careless actor
would walk, named so a review can check them.

1. **A player with only telnet access changes a live setting.** Connect with the
   shared password, run `wrench set <name> <value>`. The command takes the name
   and value straight from the parameter list
   (`src/Wrench/ConsoleCmdWrench.cs:71`) and applies them in process
   (`src/Wrench/ModSettings.cs:366`), with no permission check. M-17 leaves a
   log line naming the console session that asked; the setting is live
   immediately, and it is forgotten when the file is re-read.
2. **A mod ships a config file that is expensive to parse.** The file is parsed
   every time the Mod Settings screen opens (`src/Wrench/TargetMod.cs:190`) and
   again on every value the user types (`src/Wrench/TomlEdit.cs:35`). There is
   no cap to hit, and the parse runs on the UI thread, so the cost lands on the
   player trying to fix the mod.
3. **A second writer races a save.** A config tool saves between Wrench's read
   and its write. M-3 turns the worst outcome into a refusal, and the refusal
   message names the cause ("it changed outside Wrench",
   `src/Wrench/TargetMod.cs:440`). A save that lands between the relocation and
   the write is the residual window M-3 does not close; M-16 closes the same
   race between writers inside one process.
4. **A mod declares an encoding its bytes do not honour.** The read is refused
   rather than silently replacing a byte (`src/Wrench/ModFileSystem.cs:136`),
   so the mod becomes uneditable in-game until a person fixes the file. That is
   the intended trade: a refused write is recoverable, a replaced byte in a file
   this mod does not own is not.
5. **A config file that parses as a different document than the user saw.** The
   screen shows values from the last parse; the write goes to the file as it is
   now. M-2 verifies the result against that same current text, so a key that
   moved meaning is caught only as a parse or key-count failure.

The abuse cases the previous revision listed under a closed threat, a mod named
for a parent directory rewriting a file outside its folder, no longer has a
code path: `ModTomlPath` refuses such a name before it is ever composed
(`src/Wrench/ModTomlPath.cs:38`), and the mod is skipped with a reason
(`src/Wrench/TargetModDiscovery.cs:85`). It stays here as a regression case
rather than an open route, and `scripts/toml_gate/Program.cs:476` exercises it.

No client-side-only enforcement exists to trust wrongly: there is no
client/server split in the mod, the UI is the only editor, and the game process
is the only consumer. What a client can do is bounded by that, and the shipped
UI says so to the player (`Config/Localization.csv:3`).

## Response readiness

Notes only, no infrastructure implied, and no owner, cadence, or process
invented here.

- There is no `SECURITY.md` in this repository. Nothing to correct in one today.
  Adding one requires a disclosure contact and a supported-versions list that
  only the maintainer can supply, so this document does not fabricate them.
- A vulnerability report has no documented path to a fix. The gates a change
  must pass are written down (`AGENTS.md`, "Testing"), and
  `scripts/test_rules_have_gates.py` enforces that every recorded rule names its
  gate; what is missing is a statement of where a report is sent and who decides
  it is a vulnerability.
- Security-relevant events this mod produces are game-log lines: every save and
  its refusal, naming mod, key, value, and path
  (`src/Wrench/ModSettingsScreen.cs:210`); the per-problem line for the
  settings watch (`src/Wrench/ModSettings.cs:287`); the per-mod skip line
  (`src/Wrench/TargetModDiscovery.cs:85`); and every console subcommand with its
  sender (`src/Wrench/ConsoleCmdWrench.cs:74`). There is no structured security
  event and no separate audit log. Log structure belongs to `o11y-review`; what
  is recorded here is that a settings write names the mod, the key, the value,
  the path, and the outcome, but not the local account or the player, so a write
  is traceable to a mod's config and not to a person.
- A gap in offline coverage worth naming: the TOML gate and fuzz harness need a
  .NET SDK, so on a machine without one, T-3, T-4, and T-6 are enforced by
  nothing at all (`scripts/test_toolchain_floor.py` records the requirement).
