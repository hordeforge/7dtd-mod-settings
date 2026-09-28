# Contributing to Wrench

Wrench is a 7 Days to Die mod: the modlet is this repository's root, `src/`
holds the C#, `scripts/` holds the gates and the build, and `docs/` holds the
decisions. The host tools you need and where the machine-local paths go are
in [README.md](README.md#build-and-test); this file is what to do once you
have them.

## Before you push

```bash
make check        # everything CI runs: the offline gates, both linters, the package
```

`make check` is the same sequence, in the same order, as
`.github/workflows/ci.yml`, and a gate that existed only in the workflow
would not be in it (held by `scripts/test_static_checks.py`). While editing,
run one gate instead of the suite:

```bash
make test TF="toml"     # only the gates whose filename contains "toml"
./scripts/test_toml_document.py   # one gate, by path
make help               # every target, with what each needs
```

`make check` needs the .NET SDK for the two TOML round-trip gates; every other
target runs without a game install. Targets that need the game install say so
by name when the install is missing.

## A pull request

- Branch from `main` (`feat/`, `fix/`, `docs/`, `refactor/`, `test/`,
  `chore/`), never commit to `main`. The clone is shared by concurrent
  sessions, so take a worktree per unit of work rather than switching
  branches in place.
- Add an entry under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md), under
  `Added`, `Changed`, `Fixed` or `Removed`, saying what changed for a player
  or a mod author. Work that has not shipped needs no version bump.
- Cutting a release is one change in four files, and
  `scripts/test_version_declaration.py` fails if they disagree: the version in
  `ModInfo.xml`, the same number in `README.txt` and
  `scripts/playtest/ModInfo.xml`, and a `## [x.y.z]` heading in the changelog
  naming that version. A published number is never reused.
- Keep a gate green rather than relaxing it. If a gate is genuinely wrong,
  say so in the PR and make it stricter about the new truth.

## Adding a gate

A gate is a standalone `scripts/test_*.py` the runner picks up by glob: no
registration, no list to update. It reports through
`scripts/lib/gate_report.py` (`check` and `result`) so a piped run keeps its
failures, and it must be deterministic: `scripts/test_rules_have_gates.py`
runs every gate twice and requires byte-identical output, so no clock, no
random seed and no iteration-order dependence. New Python is ruff- and
mypy-`--strict`-clean, and a new shell script is shellcheck-clean at full
severity; both run in `make lint` and in CI.

When a rule in [AGENTS.md](AGENTS.md) is broken by something, the repair that
lasts is a gate, not a paragraph: `scripts/test_rules_have_gates.py` requires
each dated incident section there to name the gate that enforces it.

Scratch work goes in `.scratch/` (gitignored); nothing build-time belongs
under `Config/`, which is what the mod ships.

## Working on the mod itself

`docs/THREAT_MODEL.md` names the trust boundaries, `docs/reference/` is the
7DTD modding reference and its best-practices file is binding when authoring,
and `TODO.md` is what is next.
