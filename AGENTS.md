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

Corollaries, each enforced by `scripts/test_rules_have_gates.py`:

- A rule that has been broken gets a **gate**, not a paragraph: every
  AGENTS.md section that records a dated incident names the
  `scripts/test_*.py` that enforces it (or declares, by name, what enforces
  it instead).
- Every gate is **deterministic** — no clock, iteration-order, or
  random-seed dependence; the meta-gate runs each gate twice and requires
  byte-identical output.
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

The bundle is built by **shamway** (`hordeforge/7dtd-asset-pipeline`); this
mod owns only its assets, generators, and provenance. **No Unity editor is
required**: the default synthesized lane builds complete bundles —
textures, audio, text, meshes, materials, prefabs — with no editor at all;
`bundle_source = "unity"` (with `UNITY_EDITOR`) is an opt-in lane, and
where an editor exists it is a checker, not a requirement. Start with
`shamway init` (it generates `.shamway.toml` and the pipeline's own
`tools/shamway/AGENTS.md` contract), orient with `shamway status --json`,
and gate every rebuild with `make validate-assets` **before** any client
launch — a bundle without a class-142 `AssetBundle` object is always
rejected at runtime, and a matching UnityFS header is *not* acceptance
evidence. Acceptance is a fresh client loading the bundle. If a build fails
a shamway gate, fix the cause — never downgrade the gate.

## Runtime settings are TOML

This mod's own tunables live in `Config/Wrench.toml`, read by the
DLL from the installed mod folder — see the settings section of
`docs/reference/csharp-harmony.md` for the full contract (hot reload on
save, reset-then-apply, broken save keeps current values, console
`settings|set|reload`). Add a setting in `ModSettings.cs` (its header
comment lists the steps) and mirror it, commented, in the shipped TOML.
`scripts/test_settings_reload.py` holds the contract offline.

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
DOTNET_ROOT="/absolute/dotnet/sdk"
ILSPYCMD="/absolute/ilspycmd"
UNITY_EDITOR="/absolute/Unity"
```

Never commit the file or copy its absolute values into tracked files;
`scripts/test_local_path_inventory.py` enforces the documented keys and the
ignore rule. If a needed key is missing or invalid, **ask the user for the
path** — never guess or reuse one from docs or history. The game install is
**read-only reference**: read `Data/Config/*.xml` freely, never write under
the install directory.

## Repo layout

This directory itself is the modlet — the deployable unit. Mod content
(`ModInfo.xml`, `Config/`, `Resources/`, `UIAtlases/`, …) sits at the root;
`src/` (C# source), `scripts/`, `docs/`, `AGENTS.md`, `CLAUDE.md`,
`TODO.md` are build-time only and excluded from the package. `make build`
stages the deployable modlet under `dist/Wrench/`; `make package`
zips it so extraction yields `Mods/Wrench/ModInfo.xml`. Never nest
deployable content under a further subfolder.

## XML conventions

- Prefer XPath patches over full-file overrides
  (`docs/reference/xml-patching.md`); use a `<configs>` root in every patch
  file.
- Prefer `Extends` on an existing vanilla entry over defining from scratch.
- Match vanilla indentation/style (tabs, one `<property>` per line).
- Localization ships at `Config/Localization.csv` (the engine only reads a
  mod's localization from `<mod>/Config/` — see
  `docs/reference/agent-rules.md`).

## Testing

Offline gates: `make test` (every `scripts/test_*.py`) and
`make lint-shell` (shellcheck, full severity) must pass before any commit.
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
game. Live suites, when this mod grows them, go through
`hordeforge/7dtd-playtest` (an `IScenarioProvider` + thin wrapper), never a
private launcher — and a case belongs to the suite whose feature it proves,
never dropped into another feature's fixture (shared world/inventory state
makes a borrowed case change every case after it).

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
