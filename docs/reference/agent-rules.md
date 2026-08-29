# Agent rules — the enforceable core of the best-practices guide

The distilled rules from [best-practices.md](best-practices.md) that an
agent must apply on every change. That file is the authority; this one is
the checklist. Section references (§) point into it.

## Layer discipline (§2)

Prefer the **shallowest** layer that solves the problem. Depth costs update
fragility, EAC friction, and install burden:

0. Outside `Mods/` (Telnet/WebAPI/host tools) — survives everything
1. XML/XPath modlet — survives updates while XPath stays valid
2. Assets (bundles, icons) — must match the game's Unity version
3. ModAPI C# (`IModApi`, net48) — rebuild per game update
4. Harmony — breaks on method renames; Prefix/Postfix before Transpiler
5. Engine expand / binary patch — exceptional; not for ordinary mods

Escalating a layer is an architecture decision: record it (ADR).

## Structure and packaging (§4, §14)

- `ModInfo.xml` directly under `Mods/<Name>/`; folder name matches `Name`.
- Never delete or duplicate `0_TFP_Harmony`; never ship a second Harmony.
- Never edit vanilla `Data/Config/*` on disk — the game install is
  read-only reference.
- Zip so extraction into `Mods/` yields `Mods/<Name>/ModInfo.xml`
  immediately; no nested folders.
- Release README states: supported game version, stock `0_TFP_Harmony`
  requirement, EAC-off requirement if DLL, client vs server install, how to
  read logs.
- `Localization.csv`, never `.txt`. **Ship it at `Config/Localization.csv`:**
  the engine loads mod localization from `mod.Path + "/Config"`
  (`ModManager` → `Localization.LoadPatchDictionaries`, verified by
  decompilation). The guide's §4 layout drawing shows it at the mod root;
  the decompiled loader is the stricter truth — a root-level file is ignored.

## XML/XPath (§5)

- `<configs>` root in every patch file; targeted `set`/`append`/`csv` over
  whole-file copies; no fragile positional indices; XPath is case-sensitive.
- `set` only changes existing attributes (warns, does not create);
  `setattribute` creates. Verify the *full* path against the vanilla file —
  a non-matching xpath applies silently.
- Prefer `Extends` on a vanilla entry over redefining from scratch.
- V3 shapes only: `XUi_InGame/` (not `XUi/`), `templates.xml` (not
  `controls.xml`), `{% expression %}` (not `{binding}`), Sandbox knobs via
  `SandboxCode` (not removed V2 serverconfig properties).

## C#/Harmony (§7, §8)

- Target **net48**; reference `Assembly-CSharp`, `UnityEngine.CoreModule`,
  and the game's `0Harmony.dll` with `Private=false`; never ship vanilla
  assemblies. Rebuild against *this install's* Managed after every update.
- Entry point `IModApi.InitMod` — fast and defensive; log under a clear
  `[<ModName>]` prefix; fail soft per feature (one missing Harmony target
  must not kill the mod).
- Unique Harmony id (`com.<author>.<mod>`); Prefix/Postfix before
  Transpiler; patch stable methods; document targets + game version; gate
  dedicated-only logic with `GameManager.IsDedicatedServer`.
- EAC off for DLL mods; `SkipWithAntiCheat` in ModInfo per §4 semantics.

## Validation (§12)

Minimum proof per change type — a clean log alone does not prove an XPath
matched:

| Change | Minimum proof |
|---|---|
| XPath tweak | fresh world + log clean of XPath errors + in-game check |
| ModAPI command | init logged + command works via telnet/console |
| Harmony optional skip | patch applied or soft-failed in log; gameplay path intact |
| Asset bundle | offline validate (shamway) + fresh-client load |

After every Steam update: verify files, rebuild C#, re-check Harmony
targets, retest XPath.

## Anti-patterns (§15) — hard stops

Deleting `0_TFP_Harmony` · nested zip folders · editing `Data/Config` in
place · shipping `Assembly-CSharp.dll` · no game version on a release ·
Harmony on hot ticks without measured budgets · crossplay + DLL mods ·
pre-V3 XUi paths or `{binding}` · `Localization.txt` · removed V2
serverconfig properties.
