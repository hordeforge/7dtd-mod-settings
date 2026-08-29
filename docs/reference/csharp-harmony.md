# C# / Harmony Mods

For behavior that can't be expressed through XML config (new game logic,
hooking into engine methods, custom UI code), mods ship a compiled C#
assembly (`.dll`) alongside `ModInfo.xml`.

## Harmony dependency

`0_TFP_Harmony` is TFP's **official** Harmony dependency — developer-provided
and pre-installed with the base game, not a third-party mod. Structurally
it's still just a modlet though (not part of `Data/Config/`, not baked into
the game binary): it follows the exact same `ModInfo.xml` + DLL layout any
other mod uses, TFP just ships it pre-installed in the base install's
`Mods/` folder (verified on disk at `Mods/0_TFP_Harmony/`) as a shared
dependency so individual mods don't each need to bundle their own copy of
Harmony:

```
0_TFP_Harmony/
├── ModInfo.xml
├── 0Harmony.dll          # Lib.Harmony — runtime IL patching library
├── TfpHarmony.dll         # Fun Pimps' own harness/loader around Harmony
├── Mono.Cecil*.dll         # IL manipulation (Harmony dependency)
├── MonoMod.*.dll            # IL manipulation (Harmony dependency)
└── System.ValueTuple.dll
```

Any mod that wants to Harmony-patch game methods references `0Harmony.dll`
at compile time and relies on `0_TFP_Harmony` being present and loading
first (hence its `0_` name prefix — see load order in `mod-structure.md`).

For local reference, inspect only `<game install>/Mods/`. Do not use sibling
or backup directories as evidence for the current local install.

## General pattern (standard Harmony usage — not verified by decompiling
these specific DLLs, but this is the standard/documented approach)

```csharp
[HarmonyPatch(typeof(SomeGameClass), "SomeMethod")]
public class SomeGameClass_SomeMethod_Patch
{
    static bool Prefix(SomeGameClass __instance, ref int someArg)
    {
        // return false to skip the original method, true to let it run
        return true;
    }

    static void Postfix(SomeGameClass __instance)
    {
        // runs after the original method
    }
}
```

A mod's DLL typically has a `ModApi`-implementing entry class that Harmony's
`PatchAll()` is invoked from on mod load.

## Mod settings file (runtime config the mod reads itself)

The hordeforge default for a mod's own tunables is a **TOML file the DLL
reads itself**: `Config/<Mod>.toml` in the installed mod folder, resolved
from the path the game hands you (`_modInstance.Path` in `InitMod`) — never
a hardcoded path or the working directory. The engine's XML patcher never
sees it (the patcher only opens `Config/` files named after vanilla files),
and net48 has no TOML library, so the template ships a fail-loud TOML
subset parser (`TomlSettings.cs`: bare keys, booleans, numbers, strings,
arrays; tables and dotted keys rejected).

The scaffolded wiring (`ModSettings.cs` + the mod's console command)
carries the full contract, taken from AtomicDoomsday (its ADRs 0006/0015):

- applied at `InitMod`; a missing file is the normal fresh-install case
  (defaults stand, one log line says so)
- **saving the file applies without a restart**: a mtime/length watch
  polled from `ModEvents.UnityUpdate`, debounced so a half-written save is
  not read; `<mod> reload` re-reads immediately
- a reload **resets to shipped defaults, then applies the file**; a broken
  save keeps the current values and logs the error
- the console command's `set` shares one name/value grammar with the file
  via `ModSettings.TrySet`, and changes the session only until the file is
  re-read
- `ModSettings.Applied` fires after each apply — the hook for anything
  that must react to changed values (synced CVars, a future settings UI)

In multiplayer the **server's copy is authoritative** for server-side
behavior; when clients need the values, sync them explicitly (AtomicDoomsday
pushes them through player CVars — its ADR 0012 pattern).
`scripts/test_settings_reload.py` holds the source-level contract offline.

## When you actually need this vs. XML

Prefer XML (`xml-patching.md`) whenever the desired behavior is expressible
as config: new items/blocks/entities, stat tweaks, recipes, loot, buffs,
explosion parameters, etc. — this covers a large fraction of "new
weapon/item" style mods without any C# at all (see `thrownGrenadeNukeAdmin`
in vanilla `items.xml`, a full nuke-grenade item defined purely in XML).
Reach for a Harmony DLL only when the change requires new logic the XML
system has no hook for.
