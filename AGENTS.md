# Agent Instructions — Wrench (Mod Settings)

Working instructions for implementing this mod. This file is *how to work*;
what was decided lives in `docs/`, and how 7DTD modding works in general
lives in `docs/reference/`.

## Starting a session

On "continue" or any vague/no-context start: read `TODO.md` first (next
unchecked item under the earliest unfinished section is the next task), then
skim `docs/design.md` (gameplay decisions) and `docs/architecture.md`
(technical decisions) for what's already locked in — don't re-litigate
anything already marked "Decided"/"Resolved", and don't re-derive facts
already recorded. Only ask the user what to do if `TODO.md` has nothing
actionable or the design genuinely isn't decided yet.

If you are unfamiliar with 7DTD modding, read `docs/reference/README.md`
first. `docs/reference/best-practices.md` is **binding** when authoring;
`docs/reference/agent-rules.md` is its enforceable core — layer discipline
(shallowest layer that solves the problem), XPath conventions, Harmony
hygiene, packaging.

## Keep docs and TODO current — as you go, not after

The point of this doc structure is that a fresh session with zero
conversation history can resume correctly from files alone. Any decision or
progress that exists only in chat scrollback is lost.

- **Claim before work:** before researching, editing, or testing a
  TODO-tracked task, change its marker from `[ ]` to `[-]` and append
  `in progress — <agent>, YYYY-MM-DD; session: <id>`. That is the exclusive
  ownership signal for other agents. Only then begin.
- The moment a **gameplay** decision is made, record it in `docs/design.md`
  under a dated heading (`Decided YYYY-MM-DD: …`).
- The moment a **technical** decision is made, record it in
  `docs/architecture.md` the same way — and write an ADR in `docs/adr/`
  when it is significant and hard to reverse (see `docs/adr/README.md`).
  Gameplay/balance decisions are never ADRs.
- The moment a task completes, mark it `[x]` in the same turn and remove
  the in-progress text. Released or blocked: restore `[ ]` with the reason.
  Never leave a stale `[-]`.
- New follow-up work or open questions go into `TODO.md` immediately.
- If a decision changes course, fix the now-stale statements in the same
  edit.

## Parallel sessions

When multiple agent sessions work here concurrently, each generates a
durable ID before claiming anything:

```bash
scripts/new-session-id.sh <agent-family>   # e.g. claude, codex
```

The ID identifies the session; the `[-]` marker remains the ownership
claim. Never reuse an ID. Expect other agents' edits in the tree: stage
commits by explicit path only — never `git add -A` / `git add .` /
`git commit -a`.

## Playtest / live-client exclusivity

There is one shared 7 Days to Die client (and dedicated-server runtime) on
this machine, coordinated by the lock owned by `hordeforge/7dtd-playtest`
(`scripts/playtest_lock.py`), at its default path
`~/.cache/7dtd-playtest/playtest_running`. Before any exclusive live-client
work: read the lock (missing file = free); a fresh `running=yes` for
another session means **do not start**; acquire with your session id before
launching; refresh `heartbeat` (~30s, 120s stale window); release
(`running=no`) when done if you own it. A stale lock may be reclaimed only
when no live client/server process exists — and a sandboxed empty `ps` is
not evidence of that. **Never invent a second lock or a second lock path.**

## Gates are not negotiable

A gate is any check that fails a change: an offline `scripts/test_*.py`
assertion, an XML validator, a live case's assert. **When a gate rejects
your change, change the change.** Never relax, narrow, or delete an
assertion so work fits through — the gate is the accumulated memory of a
defect somebody already shipped. If a gate is genuinely wrong (asserts
something the design has since changed), say so in the commit message and
the deciding doc, and make it *stricter about the new truth*, never looser.

Corollaries; the first two are enforced by
`scripts/test_rules_have_gates.py`, the third is a habit no gate can check:

- A rule that has been broken gets a **gate**, not a paragraph: every
  AGENTS.md section that records a dated incident names the
  `scripts/test_*.py` that enforces it (or declares, by name, what enforces
  it instead).
- Every gate is **deterministic** — no clock, iteration-order, or
  random-seed dependence; the meta-gate runs each gate twice and requires
  byte-identical output.
- A script's **report is stdout**, PASS and FAIL alike, through
  `scripts/lib/gate_report.py` (one definition, not a copy per gate), so a
  redirected or piped run keeps the failures; stderr is only for a script
  that produced no report at all. Exit status: 0 pass, 1 a check failed,
  2 a bad command line or a missing install, and any unknown option is an
  error rather than a silently skipped argument. Enforced by
  `scripts/test_rules_have_gates.py`.
- **Prove a gate can fail** before trusting it — against a fixture or a
  scratchpad copy, never by breaking the shared tree.

## Sibling tooling is mandatory; do not recreate it

Playtesting, the client lock, launch, mute, capture, asset builds, and
engine research belong to the `hordeforge/7dtd-*` repositories — the map is
`docs/reference/sibling-tooling.md`, and `scripts/test_upstream_tooling.py`
scans script content for the banned tool calls. If a capability is general
and missing, add it upstream first (worktree → branch → PR → merge in the
owning repo), then consume it; a local substitute "until upstream exists"
is the defect. Sibling repos are separate checkouts found via
`HORDEFORGE_ROOT` in `.local.env` — never a build input or required
relative path of this repo.

## Asset bundles (when this mod ships them)

This mod ships none, and the Makefile has no asset targets on purpose. If
it ever does, the bundle is built by **shamway**
(`hordeforge/7dtd-asset-pipeline`) and every rebuild is gated there with
`shamway validate` and `shamway check-icons` before a client launch; a
bundle without a class-142 `AssetBundle` object is always rejected at
runtime, and a matching UnityFS header is not acceptance evidence. If a
build fails one of those gates, fix the cause, never downgrade the gate.
The tool map is `docs/reference/sibling-tooling.md`.

## Runtime settings are TOML

This mod's own tunables live in `Config/Wrench.toml`, read by the
DLL from the installed mod folder — see the settings section of
`docs/reference/csharp-harmony.md` for the full contract (hot reload on
save, reset-then-apply, broken save keeps current values, console
`settings|set|reload`). Add a setting in `ModSettings.cs` (its header
comment lists the steps) and mirror it, commented, in the shipped TOML.
`scripts/test_settings_reload.py` holds the contract offline.

## Dependencies

The mod's Python is stdlib only: `pyproject.toml` declares a virtual project
with no dependencies and `uv.lock` resolves it empty, so no third-party
package arrives by accident. ruff and mypy are developer and CI tools pinned
in `requirements-dev.txt` (the one place a version is written down), together
with the distributions mypy pulls in, because an unpinned one of those enters
the lint lane unreviewed the day it is published; shellcheck is a host tool;
the dotnet SDK is read-only reference for the C#
TOML harnesses, so `make test` needs an interpreter and that SDK, no game
install. A third-party package is a decision to make on purpose, not a
reflex: declare it in `pyproject.toml`, take the install with it, and write
down why. `scripts/test_stdlib_only.py` holds the no-import claim, so
nothing arrives on one contributor's disk instead.

## Releases

`ModInfo.xml` declares the version; `README.txt` (staged into the package
by `scripts/build.sh`) and the newest `## [x.y.z]` heading in
`CHANGELOG.md` declare the same release. The mod is `0.x`, so a
behaviour change for a player or a mod author is a minor bump, and a
new feature or a fix is a patch bump; the fourth version component stays
`0` so every shipped number has a changelog heading. A published number
is never reused for different work, and the changelog entry says what
changed for a consumer (breaking change, new key, migration), not which
commit changed it. `scripts/test_version_declaration.py` holds all of
that offline, including that no release is documented twice. The release
tag is cut from the commit that sets the version, so the changelog's
newest heading is that commit's release and nothing after it.

Added 2026-09-28: the version was declared in three files that nothing
held together.

Added 2026-09-28: a behaviour change shipped as the patch `0.2.1` (a
key spelled with the wrong case stopped applying), three more landed
after it with no entry at all, and `docs/THREAT_MODEL.md` still named
`0.2.0.0` as the build it reviewed. All three ship as the minor
`0.3.0`; a doc that names a version, the newest entry's Compatibility
section, and the placement of an `## [Unreleased]` heading are enforced
by `scripts/test_version_declaration.py`.

## Local path inventory

All machine-specific paths live in the ignored `.local.env` (format:
`.local.env.example`); see `docs/reference/environment.md`. **Read it
before searching the host** for tools or installations, and when a user
supplies a machine path — or setup discovers one — record it there
immediately. Keep the complete inventory together, including these keys
when their targets exist:

```dotenv
SEVEN_DAYS_TO_DIE_DIR="/absolute/client/install"
SEVEN_DAYS_TO_DIE_SERVER_DIR="/absolute/dedicated/server/install"
HORDEFORGE_ROOT="/absolute/dir/of/hordeforge/checkouts"
PLAYTEST_ROOT="/absolute/checkout/7dtd-playtest"
CONNECT_ROOT="/absolute/checkout/7dtd-fastconnect"
ASSET_PIPELINE_ROOT="/absolute/checkout/7dtd-asset-pipeline"
WRENCH_ATOMIC_MOD_DIR="/absolute/checkout/AtomicDoomsday"
DOTNET_ROOT="/absolute/dotnet/sdk"
ILSPYCMD="/absolute/ilspycmd"
UNITY_EDITOR="/absolute/Unity"
```

Never commit the file or copy its absolute values into tracked files;
`scripts/test_local_path_inventory.py` enforces the documented keys and the
ignore rule. An exported environment variable always wins over the file, and
a file-only key still applies: load through `scripts/local-env.sh` (shell) or
`scripts/lib/local_env.py` (Python), never by sourcing the file yourself —
`scripts/test_local_env_precedence.py` holds that rule. If a needed key is
missing or invalid, **ask the user for the path** — never guess or reuse one
from docs or history. The game install is **read-only reference**: read
`Data/Config/*.xml` freely, never write under the install directory.

## Repo layout

This directory itself is the modlet — the deployable unit. Mod content
(`ModInfo.xml`, `Config/`, `Prefabs/`, `Resources/`, `UIAtlases/`,
`WebMod/`) sits at the root; `src/` (C# source), `scripts/`, `docs/`,
`AGENTS.md`, `CLAUDE.md`, `TODO.md` are build-time only. `scripts/build.sh`
stages by allowlist, so a new mod-content directory ships only after it is
added there. `make build` stages the deployable modlet under `dist/Wrench/`;
`make package` zips it so extraction yields
`Mods/Wrench/ModInfo.xml`. Never nest deployable content under a further
subfolder.

Corrected 2026-09-28: the staged tree was made world-readable and
writable by nobody for a reproducible zip, and the zip records those
modes. Every install whose extractor restored them (unzip does) got a
read-only `Config/`, and this mod saves a setting by writing a staged
sibling into `Config/` and replacing `Config/Wrench.toml` with it, so
every save failed on exactly those installs. The package is now staged
`a+rX,u+w` and `scripts/test_package_contents.py` builds the real zip
and holds the shipped file set, the entry modes, and a negative control
on the read-only tree they replaced.

## XML conventions

- Prefer XPath patches over full-file overrides
  (`docs/reference/xml-patching.md`); use a `<configs>` root in every patch
  file.
- Prefer `Extends` on an existing vanilla entry over defining from scratch.
- Match vanilla indentation/style (tabs, one `<property>` per line).
- Localization ships at `Config/Localization.csv` (the engine only reads a
  mod's localization from `<mod>/Config/` — see
  `docs/reference/agent-rules.md`).

## Text handling

- Wrench's own `Config/Wrench.toml` is read and written as UTF-8 without a
  byte order mark, through `ModFileText`; a BOM on read is still honoured.
  Another mod's file is read and written through `ModFileSystem` (the one
  filesystem) with `TomlFile` as the byte-faithful codec, in whatever
  encoding its bytes declare, so a non-ASCII comment in it survives a save
  unchanged, mark included.
- A decoder whose text is written back is strict: bytes that are not
  valid in the encoding they declare are refused, never replaced with
  U+FFFD. That is every read of another mod's file, since a save writes
  the decoded text back and a replaced byte would be lost from a file
  this mod does not own. The strict decoder is the same whether or not a
  byte order mark is there. `Wrench.toml` is the other case: nothing
  writes it back, so a stray byte in a comment costs nothing there and
  its decoder may replace.
- The TOML string grammar is TOML's, both directions: the reader
  understands every escape the writer emits (`\b \f \r \t \n \" \\`,
  `\uXXXX`, `\UXXXXXXXX`, surrogate pairs), a raw control character in a
  basic string is refused, and an unpaired surrogate escape is refused
  rather than silently turned into U+FFFD. TOML keys are case sensitive,
  so `Foo` and `foo` are two keys.
- A value's span is measured in characters, never bytes, and a value is
  only ever replaced as a whole span: no slicing at a multi-byte or
  surrogate boundary.
- Any subprocess whose output is decoded as text declares its encoding
  (`encoding="utf-8", errors="replace"`); the locale's default is ASCII
  under a bare `LANG`.
- Every user-facing string is a `Config/Localization.csv` key, and a
  catalog key and a broken C# string literal reading the game log alike.
  The label a key is drawn in is sized for it: an NGUI label clips at its
  own height, so `wrap="true"` alone does not help, and a box cut to the
  English source cuts the German, Russian or Japanese rendering off
  mid-sentence.

Corrected 2026-09-28: the two bottom labels were one line high, so the
status line and the server note were clipped in every language, and
nothing but the screen said so; enforced by
`scripts/test_localization_catalog.py`, which measures each label against
the catalog's own english text grown for translation, counts a CJK or kana
character at full width, and holds `modnote` and `selmodstatus` (the two
bindings whose text comes from the C# rather than a `text_key`) to the same
measure.

Corrected 2026-09-28: escapes, encoding, and key case in the TOML path;
enforced by `scripts/test_toml_document.py` (spans, escapes, non-ASCII
round trips, a file whose bytes are not valid in the encoding it declares
refused on read, marked UTF-16 and UTF-32 included), `scripts/test_toml_fuzz.py`
(mutated documents and mutated byte arrays against the
reader/writer/resolver invariants, fixed seed), and
`scripts/test_python_defects.py` (text output without an
explicit encoding).

## Testing

Offline gates: `make test` (every `scripts/test_*.py`) and
`make lint` (`make lint-python`: ruff plus mypy `--strict` over every tracked
`*.py` per `pyproject.toml`; then `make lint-shell`: shellcheck at full
severity) must pass before any commit.
Install-dependent checks: `make validate-xml` (every Config xpath against
vanilla), `make verify-patched-config` (after loading a world: every
shipped patch element counted in the save's own `ConfigsDump`, attributed
to this mod, in its intended parent — the positive proof a clean log cannot
give, since a patch matching nothing applies silently) and, for C# mods,
`make validate-patch-targets` (every `[HarmonyPatch]` target against the
installed Assembly-CSharp) — run them after any config/patch change and
after every game update. `scripts/lib/game_telnet.py` is the stdlib client
for dedicated-server console oracles when a check needs to ask the running
game what is true. Dedicated
server: `make install-server` / `deploy-server` / `server-smoke` boot the
configured server briefly and prove the mod loaded from its log.

Live behavior: deploy per `docs/reference/environment.md` and check the
game log — a clean log alone does not prove an XPath matched; verify in
game. The live lane is `make playtest` (`scripts/playtest-maci.sh`): it
builds and deploys the mod plus the `WrenchPlaytest` provider
(`scripts/playtest/`) and runs the default `wrench-mod-settings` suite
through `hordeforge/7dtd-playtest`, which takes the exclusivity lock
itself. Select another suite with `make playtest SUITE=<id>`. Never write a
private launcher. A new case belongs to the suite whose feature it proves,
never dropped into another feature's fixture (shared world/inventory state
makes a borrowed case change every case after it).

Corrected 2026-09-28: `make test` needs the .NET SDK, not only a Python
interpreter, because `test_toml_document.py` and `test_toml_fuzz.py`
compile `src/Wrench/*.cs` (`scripts/test_toolchain_floor.py`); the lint
tool versions are written down in `requirements-dev.txt` only, which CI
installs (`scripts/test_lint_toolchain_declared.py`).

## Git workflow

This is a standalone hordeforge repository and the clone may be shared by
concurrent sessions: never `git checkout` / `git switch` / `git branch -D`
in it — take a worktree per unit of work
(`git worktree add /tmp/Wrench-<topic> -b <branch> origin/main`).
Complete the full lifecycle autonomously when unblocked: branch → commit →
push → PR → merge; never commit directly to the default branch. Stage by
explicit path. No `Co-Authored-By` or other attribution trailers in commits
or PRs. If another session is working on something — a dirty file, a live
branch, an open PR — do not touch it at all.

## Scope

Only build what's decided in `docs/design.md`, `docs/architecture.md`, or
`TODO.md`. If the design isn't decided yet, that's a question for the user,
not something to invent mid-implementation.
