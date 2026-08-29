# Sibling tooling: what a mod must not recreate

Host-side 7 Days to Die automation for this machine lives in the
`hordeforge/7dtd-*` repositories. A mod **consumes** those tools; it never
reimplements them, and it never grows a private copy "just for this mod"
when the capability is general. The offline gate
`scripts/test_upstream_tooling.py` in each scaffolded mod scans script
*content* for the banned tool calls, so a renamed copy fails too.

Default checkouts live under the directory named by `HORDEFORGE_ROOT` in the
mod's `.local.env`. If a needed
sibling is missing:

```bash
gh repo clone hordeforge/<repo> "$HORDEFORGE_ROOT/<repo>"
```

## Who owns what

| Need | Owner | The mod may |
|---|---|---|
| Live suite orchestration, the machine-wide playtest/client exclusivity lock (`scripts/playtest_lock.py`), stock cases, `CaseDef`/`Helpers`/`Report`, staged-frame capture (`capture_frames.sh`), run-audio recording (`capture_audio.sh`), real mining (`MiningProbe`) | `hordeforge/7dtd-playtest` | Ship a thin wrapper and an `IScenarioProvider` with the mod's own cases; reuse upstream `Helpers` before writing an engine walk |
| Client launch (EAC-off Local platform, intro skip), OS audio mute/unmute | `hordeforge/7dtd-fastconnect` | Call `launch_client.sh` / `mute_client_audio.sh` / `unmute_client_audio.sh` |
| Asset bundle build/validate/icon gates, Unity editor install, fresh-client acceptance (deploy, launch, log, screenshot+manifest, Discord pref) | `hordeforge/7dtd-asset-pipeline` (**shamway**) | `shamway build` / `validate` / `check-icons` / `client …`; keep only the mod's own assets and generators |
| Load-volume peer clients | `hordeforge/7dtd-loadgen` | Consume; never ship a second bot |
| Dedicated server APM / measurement | `hordeforge/7dtd-server-apm` | Optional host tool |
| Dedicated optimizer (EfficientServer) | `hordeforge/7dtd-server-optimizer` | Opt-in install; not a fork |
| Stock-engine research | `hordeforge/7dtd-engine-research` | Look up, never vendor |
| Zig dedicated server | `hordeforge/zdtd-server` | Separate target; not templated here |

## What the mod itself owns

- Its modlet content, its `IScenarioProvider` playtest cases, its asset
  sources and generators
- Offline `scripts/test_*.py` that compile or parse **this** mod's files
- Thin wrappers that `exec` upstream tools with this mod's arguments
- `scripts/new-session-id.sh` for TODO claims — which must never grow into
  a second lock file

## Banned in a mod's scripts (the gate scans for these)

Screenshot/window tools (`spectacle`, `grim`, KWin/`qdbus`, `xdotool`),
audio recorders (`parec`, `pw-record`), `pactl` mute loops, a local
`playtest_lock.py` or any second lock path, OCR menu drivers,
`steam -applaunch` suite launchers, `pgrep`-on-the-runtime waits, forks of a
sibling's script under the same basename.

## When a capability is general, put it upstream

If any mod on this harness would want it, the work is: implement it in the
owning `hordeforge/7dtd-*` repo (worktree → branch → commit → push → PR →
merge), then consume the public API. A local substitute left "until
upstream exists" is the defect — a TODO saying "upstream X" is done when X
is merged upstream and the mod's wrapper calls it, not when a copy of X
lands in the mod.
