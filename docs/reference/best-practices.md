<!-- Vendored from hordeforge/.github MODDING_BEST_PRACTICES.md (upstream state: 2026-08-28, game V3.2.0 b9).
     This local copy exists so scaffolded mods follow the guide with no external fetch.
     Machine-local install paths in §1 describe the machine the guide was validated on;
     your paths live in the mod's ignored .local.env (see environment.md).
     One local change: sibling-repo doc paths (the intro "Deeper doc" table and inline
     references) are rewritten to their GitHub URLs so they resolve without local checkouts.
     Sync manually when upstream changes, re-applying that rewrite (manual chore,
     deliberately not automated). -->

# 7 Days to Die modding: consolidated best practices

**Target game:** V **3.2.0** (b9) Stable, Henpocalypse line  
**Engine (this machine):** Unity **2022.3.62f2**, **Mono** (not IL2CPP), WindowsPlayer under Proton for client; dedicated is Linux/x86_64 headless  
**Last validated:** 2026-08-28 against official V3.2.0 (b9) + local V3.2.0 (b9) dedicated, [7d2dmodding.wiki.gg](https://7d2dmodding.wiki.gg/) (pages marked verified for 3.0), official [Mod Interface](https://7daystodie.wiki.gg/wiki/Mod_Interface) / [XUi](https://7daystodie.wiki.gg/wiki/XUi), [7DaysToDieMods.com](https://7daystodiemods.com/) install guidance, **local Steam installs + client log**, and the projects in this workspace.

This is the **workspace root** canonical guide. Project-specific docs stay for deep detail; this file owns **what to do where**, **which method to use when**, and **how to validate** after game updates.

| Deeper doc | Owns |
|---|---|
| [`7dtd-server-optimizer/docs/DEVELOPMENT.md`](https://github.com/hordeforge/7dtd-server-optimizer/blob/HEAD/docs/DEVELOPMENT.md) | EfficientServer-only workflow (rebuild, feature groups, RE dumps) |
| [`7dtd-server-optimizer/docs/ARCHITECTURE.md`](https://github.com/hordeforge/7dtd-server-optimizer/blob/HEAD/docs/ARCHITECTURE.md) | Dedicated-server hot path RE notes |
| [`7dtd-server-optimizer/docs/HOST_TUNING.md`](https://github.com/hordeforge/7dtd-server-optimizer/blob/HEAD/docs/HOST_TUNING.md) | CCD/NUMA/affinity, IRQ, storage; measure-first host ops |
| [`7dtd-server-optimizer/docs/OPTIMIZATION_IDEAS.md`](https://github.com/hordeforge/7dtd-server-optimizer/blob/HEAD/docs/OPTIMIZATION_IDEAS.md) | Research map: threading, I/O, net, near/far levers |
| [`7dtd-server-optimizer/docs/OPTIMIZATION_CANDIDATES.md`](https://github.com/hordeforge/7dtd-server-optimizer/blob/HEAD/docs/OPTIMIZATION_CANDIDATES.md) | Graded optim candidates from dedicated RE |
| [`7dtd-server-optimizer/docs/SCALE_1000x10000.md`](https://github.com/hordeforge/7dtd-server-optimizer/blob/HEAD/docs/SCALE_1000x10000.md) | Thought experiment: data structures for huge MP/AI |
| [`7dtd-server-optimizer/docs/SIM_PARALLELISM.md`](https://github.com/hordeforge/7dtd-server-optimizer/blob/HEAD/docs/SIM_PARALLELISM.md) | Speeding sim: extract off main, threading policy, hot paths, Amdahl |
| [`7dtd-server-optimizer/docs/FEATURES.md`](https://github.com/hordeforge/7dtd-server-optimizer/blob/HEAD/docs/FEATURES.md) | EfficientServer patch groups and acceptance notes |
| [`research/oss-tools/NOTES.md`](https://github.com/hordeforge/7dtd-engine-research/blob/HEAD/oss-tools/NOTES.md) | OSS tools survey (optim lessons from IceCoffee, SphereII, CSMM, …) |
| [`research/7dtd-ServerTools/NOTES.md`](https://github.com/hordeforge/7dtd-engine-research/blob/HEAD/oss-tools/servertools.md) | ServerTools optim-relevant bits |
| [`research/naiwazi/NOTES.md`](https://github.com/hordeforge/7dtd-engine-research/blob/HEAD/oss-tools/naiwazi.md) | NAIWAZI ServerKit reconstruction |
| [`research/docs/loop.md`](https://github.com/hordeforge/7dtd-engine-research/blob/HEAD/docs/loop.md) | Complete dedicated server game/sim loop RE map |
| [`research/docs/INDEX.md`](https://github.com/hordeforge/7dtd-engine-research/blob/HEAD/docs/INDEX.md) | Dedicated RE dumps index |
| [`7dtd-realearth/docs/MODDING_REFERENCES.md`](https://github.com/hordeforge/7dtd-realearth/blob/HEAD/docs/MODDING_REFERENCES.md) | Link index (sites, Discords, tools) |
| [`7dtd-realearth/docs/MODLET.md`](https://github.com/hordeforge/7dtd-realearth/blob/HEAD/docs/MODLET.md) | RealEarth install + YDim expand |
| [`7dtd-realearth/docs/HEIGHT_LIMITS.md`](https://github.com/hordeforge/7dtd-realearth/blob/HEAD/docs/HEIGHT_LIMITS.md) | Vertical engine limits |
| [`7dtd-server-apm/docs/APM.md`](https://github.com/hordeforge/7dtd-server-apm/blob/HEAD/docs/APM.md) | Capture validity and evidence model |

### Evidence grades used below

| Grade | Meaning |
|---|---|
| **Measured** | Observed on this machine (log, filesystem, `serverconfig.xml`, assemblies) |
| **Official** | TFP release notes or official wiki |
| **Community 3.0** | 7d2dmodding.wiki.gg pages marked verified for 3.0 |
| **Workspace** | True of these four projects by design / code |

---

## 1. Current version snapshot

| Field | Value | Grade |
|---|---|---|
| Client log version | `Version: V 3.2.0 (b9) Compatibility Version: V 3.2.0` | Measured (Constants.cVersion* + Steam build 2026-08-28) |
| Unity | `2022.3.62f2` | Measured (`UnityPlayer.so` strings) + ARCHITECTURE |
| Runtime | Mono / MonoBleedingEdge | Measured (log: Mono path + Manager ReloadAssembly) |
| Stock Harmony | `Mods/0_TFP_Harmony`, `Name=TFP_Harmony`, **Version 1.1.0.4**, `SkipWithAntiCheat=true` | Measured |
| Localization vanilla file | `Data/Config/Localization.csv` (not `.txt`) | Measured |
| XUi folders | `XUi_Common`, `XUi_Menu`, `XUi_InGame` each with `styles.xml`, `templates.xml`, … | Measured |
| Vertical markers in assembly | `Height255`, `ChunkBlockYDim`, `ChunkBlockYDimM1`, … | Measured (`strings` on dedicated `Assembly-CSharp`) |
| Local install pins | Client + dedicated both present under Steam common | Measured; see `7dtd-realearth/docs/GAME_VERSION.md` |

### Install roots on this machine (Measured)

| Role | Path |
|---|---|
| Client (Proton) | `~/.local/share/Steam/steamapps/common/7 Days To Die` |
| Dedicated | `~/.local/share/Steam/steamapps/common/7 Days to Die Dedicated Server` |
| Client Managed | `…/7 Days To Die/7DaysToDie_Data/Managed/` |
| Dedicated Managed | `…/7 Days to Die Dedicated Server/7DaysToDieServer_Data/Managed/` |
| Mods (both) | `<install>/Mods/` (log: load from `…_Data/../Mods`) |
| Proton userdata | `…/compatdata/251570/pfx/drive_c/users/steamuser/AppData/Roaming/7DaysToDie/` |
| Native userdata (if used) | `~/.local/share/7DaysToDie/` |
| Client logs (Proton) | `…/Roaming/7DaysToDie/logs/output_log_client__*.txt` |
| Generated worlds (Proton) | `…/Roaming/7DaysToDie/GeneratedWorlds/` |
| Stock worlds | `<install>/Data/Worlds/` (`Navezgane`, `Pregen*`, …) |
| Prefabs | `<install>/Data/Prefabs/` (`POIs`, `RWGTiles`, …) |

Dedicated can override userdata with uncommented `UserDataFolder` in `serverconfig.xml` (stock comment documents this).

### V3.0 modding deltas that still matter on 3.0.1 (Official)

From [V3.0 release notes](https://7daystodie.com/v3-0-dead-hot-summer-release-notes/) (still the API contract; V3.0.1 is bugfix only):

1. **WebDashboard is in core.** Code mods reference **`Assembly-CSharp.dll` only** for game APIs (no extra WebDashboard assemblies).
2. **Publicizer:** overrides of vanilla methods may need to be **public**.
3. **`Localization.txt` → `Localization.csv`.**
4. **`entitygroups.xml`** is proper XML again (old text format still accepted for now; write real XML).
5. **XUi overhaul:** folder `XUi` → **`XUi_InGame`**, `controls.xml` → **`templates.xml`**, new binding system `{% expression %}`, new views, rect-over-panel preference.
6. **Sandbox:** many legacy `serverconfig.xml` knobs moved into **`SandboxCode`**.
7. **XML shape refactors** (pipe properties → nested classes, composite tile entities, renamed properties like `Map.Color` → `MapColor`). XPath targeting old shapes will break.
8. **Major-version save warning** when loading older major saves (Added in V3.0 changelog).

[V3.0.1 Stable](https://7daystodie.com/v3-0-1-stable-release/): Sign-Tech, cosmetics, degradation reset, loot bag UI, multiplayer edge cases. **No new mod API surface.**

### After every Steam update

1. Stop client and dedicated.
2. Verify game files if anything looks wrong (also undoes engine expand).
3. Rebuild every C# mod against **this install’s** `*_Data/Managed/`.
4. Re-check Harmony targets (ILSpy / Cecil dumps).
5. Re-run a short loadgen + APM scenario before trusting optimizations.
6. If you use RealEarth engine expand: re-apply after Verify.

---

## 2. Mental model: layers (shallowest first)

Prefer the **shallowest** layer that solves the problem. Depth costs update fragility, EAC friction, and install burden.

| Layer | Changes | Client install? | EAC? | Survives updates? | Use for |
|---|---|---|---|---|---|
| **0. Outside `Mods/`** | Telnet / WebAPI / host tools / external bots | No | On OK | Yes | Crossplay admin, APM **host** capture, loadgen process |
| **1. XML / XPath modlet** | `Data/Config` via mod `Config/*.xml` | Server only (XML push) | Usually on | Yes if XPath stays valid | Balance, loot, recipes, spawns, progression |
| **2. Assets** | Bundles, icons (`UIAtlases/…`) | **Yes** every client | Usually on | Bundle must match Unity | Models, sounds, icons |
| **3. ModAPI (C# `IModApi`)** | New systems / commands / WebMod plugins | Usually yes if clients run code | Usually **off** | Rebuild each update | Console cmds, session systems, bridges |
| **4. Harmony** | Runtime patches on `Assembly-CSharp` | Same as C# | Usually **off** | Breaks on renames | Intercept compiled behavior |
| **5. Engine expand / binary patch** | Permanent edits to game DLLs (e.g. YDim) | Matching expanded install | Off / no EAC path | **Verify undoes it** | Only when stock limits block the product (RealEarth height) |

**Crossplay:** stock `serverconfig.xml` documents `ServerAllowCrossplay`. Community Getting Started (3.0): crossplay wants **EAC on** and effectively **no content mods** for console join; use layer 0 for automation. Crossplay also constrains slots and RWG size (community wiki; re-check current console branch if multi-platform).

**Never delete `Mods/0_TFP_Harmony`.** Stock Harmony is required for C# mods. Measured: client loads it first and runs `[Harmony] Init done` before other mod `InitMod`.

### Method chooser (when to use what)

| Goal | Method | Do not |
|---|---|---|
| Change numbers in XML data (damage, loot, recipes, spawn tables) | **XPath modlet** | Edit vanilla `Data/Config` on disk |
| Add text strings | **`Localization.csv`** in mod root | `Localization.txt` |
| New mesh / sound / icon | **Asset bundle / UIAtlases** + XML refs | Expect server to push assets |
| New console command, session object, JSON config load | **`IModApi.InitMod`** | Patch `Update` every frame for config |
| Change behavior of existing compiled methods | **Harmony** Prefix/Postfix first | Transpile first; ship second Harmony |
| Skip work only on dedicated | Harmony + **`GameManager.IsDedicatedServer`** gate | Run presentation skips on clients blindly |
| Measure host CPU / GC / threads | **`7dtd-server-apm` host collectors** (layer 0) | Put optimizers in the capturer |
| Measure managed method time | **APM bridge** Harmony instrumentation only | Combine with AI LOD “fixes” in same DLL |
| Apply reviewed AI/mesh budgets | **EfficientServer** after APM evidence | Invent patches without a baseline |
| Fake multiplayer load | **`7dtd-loadgen`** LiteNetLib clients | Use real clients for CI soak only if needed |
| Earth terrain / tall columns | **RealEarth** tiles + **YDim expand** (required for real height) | Put expand in EfficientServer |
| Choose API for a RealEarth gap | **`7dtd-realearth/docs/GAP_HARMONY_MODLETS.md` §0b** (vs XPath/IModApi/Harmony/XUi/WebMod/bake) | Force XML-only or second Harmony |
| Admin automation with empty `Mods/` | **Telnet / WebDashboard** | Harmony admin frameworks on crossplay |
| UI layout / HUD | **XUi XPath** under `Config/XUi_*` + `{% %}` | Pre-3.0 `{binding}` / `XUi/` paths |
| Sandbox difficulty-style knobs | **`SandboxCode`** in `serverconfig.xml` | Removed V2 property names (see §10) |

---

## 3. Workspace project boundaries (what goes where)

These four projects are independent. None silently installs or mutates another. (Workspace README + each project README.)

| Project | Responsibility | Must not | Typical install surface |
|---|---|---|---|
| **`7dtd-loadgen`** | Controlled LiteNetLib clients, dedicated start helpers, workload manifests | Measure or optimize the server; ship game-balance content | **No** game `Mods/` entry; external `net8` process |
| **`7dtd-server-apm`** | Host + optional bridge **measurement**, compare, budget, export | Apply performance “fixes”; embed loadgen protocol; auto-edit EfficientServer | Host: Python/`uv`. Optional: `Mods/7dtd-server-apm-bridge/` |
| **`7dtd-server-optimizer`** (EfficientServer) | **Reviewed** Harmony optimizations only (AI LOD, dedicated skips, mesh budgets, pathfinding graph throttle) | Ship profiler UI; generate load; invent patches without APM evidence | `Mods/EfficientServer/` (dedicated) |
| **`7dtd-realearth`** (RealEarth) | Real-world terrain packs, streaming, real-height inject, world bake | Become a general optimizer or APM tool | `Mods/RealEarth/` + engine expand tools; offline Python under `tools/` |

### Offline tooling vs in-game mod (Workspace)

| Kind | Lives in | Loaded by game? | TFM examples |
|---|---|---|---|
| In-game mod DLL | `Mods/<Name>/*.dll` | Yes | **net48** (EfficientServer, APM bridge, RealEarth) |
| Offline pipeline | `7dtd-realearth/tools/` Python | No | uv / Python 3.11+ |
| Engine height patcher | RealEarth `Tools/` / `engine_patcher` | No (run while game stopped) | net48 console app |
| Loadgen client | `7dtd-loadgen` | No | **net8.0** |
| Host APM | `7dtd-server-apm` Python + optional eBPF | No | uv |

**Rule:** if it is not loaded through `[MODS]`, it may use modern .NET or Python. If it is loaded by the game, target **net48** and reference **this** install’s Managed assemblies with `Private=false`.

### Intended performance loop (Workspace)

```
loadgen scenario  →  APM baseline  →  explicit EfficientServer change
                  →  same load shape  →  APM compare + budget gate
```

RealEarth can be the world under test; it is not required by the other three.

### Where work belongs (decision table)

| You want to… | Put it in |
|---|---|
| Join N simulated clients and wander/die/respawn | `7dtd-loadgen` |
| Capture CPU, GC, threads, managed timings | `7dtd-server-apm` (+ optional bridge DLL) |
| Tighten distant AI / skip dedicated-only work / bound mesh | `7dtd-server-optimizer` after evidence |
| Build Earth tiles, stream terrain, expand YDim | `7dtd-realearth` |
| Change zombie HP / loot tables / recipes | XML modlet (own or separate), not optimizer |
| Automate admin without blocking crossplay | Telnet / WebAPI (layer 0), not Harmony |
| Add a HUD globe for RealEarth | RealEarth XUi + assets, not EfficientServer |
| Instrument `gmUpdate` for a report | APM bridge only (no optimization side effects) |
| Bake a finite playable heightmap world | RealEarth offline `bake-world` → GeneratedWorlds / importer path |
| Stream absolute Earth tiles at runtime | RealEarth C# streamer + Harmony inject |

### Who installs which DLL (Workspace + Measured installs)

| Mod | Client | Dedicated | Notes |
|---|---|---|---|
| `0_TFP_Harmony` | Stock | Stock | Never delete |
| EfficientServer | Usually no | Yes | Config `DedicatedOnly` default **true** (code) |
| 7dtd-server-apm-bridge | No | Optional | Instrumentation + WebMod panel; EAC off when using mods |
| RealEarth | Yes (product) | Yes (MP/tests) | Expand tools required for real height product |
| TFP_CommandExtensions | Stock sample on DS | Stock | Extra server commands |
| Xample_MarkersMod | Stock sample on DS | Stock | Example **WebMod** markers plugin |

### Evidence rules (APM, Workspace)

- Missing evidence is **unavailable**, not a healthy zero.
- Health grades need sufficient coverage (see APM docs; ~80% weighted coverage threshold).
- Comparisons reject mismatched layer sets, collector selection, or durations differing by more than ~10%.
- Lower CPU alone does **not** accept an optimization: validate combat, sleepers, quests, MP separation, saves.
- Deep entity/path hooks in the bridge are **off by default** because high-frequency timing has measurable overhead (bridge README).

---

## 4. Modlet layout (always)

```
7DaysToDie/   or   7 Days to Die Dedicated Server/
  7DaysToDie.exe | 7DaysToDieServer.x86_64
  Mods/
    0_TFP_Harmony/                 # stock; never delete or replace
      ModInfo.xml
      0Harmony.dll
      TfpHarmony.dll
      Mono.Cecil*.dll              # shipped by TFP for HarmonyX (Measured)
      MonoMod.*.dll
    YourMod/
      ModInfo.xml                  # required or folder is ignored
      Config/                      # XPath; mirror Data/Config names
        items.xml                  # must use <configs> root for XPath ops
        blocks.xml
        XUi_InGame/windows.xml     # V3 path names (Measured folders)
      YourMod.dll                  # optional C#
      Config/yourmod.json          # optional runtime config (this workspace)
      Localization.csv             # 3.x (not .txt)
      UIAtlases/ItemIconAtlas/     # icons (not legacy ItemIcons/ post-A18)
      WebMod/                      # optional WebDashboard plugin assets
```

### Install rules

1. **`ModInfo.xml` sits directly under `Mods/YourMod/`** (no zip nesting `YourMod/YourMod/`). Community install guides + Measured load paths.
2. **Do not edit** vanilla `Data/Config/*` in place. Updates wipe it; use XPath. (Community 3.0 + Official)
3. **Load order** is folder order under `Mods/`. Measured client log: `0_TFP_Harmony` then `RealEarth` (alphabetical / `0_` prefix). Last writer wins on conflicting XPath.
4. **Same mod on client and dedicated** when the DLL or assets matter. Pure XML server-only is the exception. Dedicated-only optimizers are an intentional exception (EfficientServer).
5. **Tag releases** with **game version** (`3.0.1`) as well as mod semver.
6. Keep stock **`0_TFP_Harmony`**. Do not ship a second Harmony or a competing MonoMod stack in your mod folder.

### Modern `ModInfo.xml` (Measured stock + workspace mods)

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<xml>
  <Name value="YourModId" />
  <DisplayName value="Human Readable Name" />
  <Description value="What it does." />
  <Author value="You" />
  <Version value="1.0.0" />
  <Website value="" />
  <!-- stock Harmony and our server DLLs set this -->
  <SkipWithAntiCheat value="true" />
</xml>
```

Pre-1.0 ModInfo shapes are obsolete (Community 3.0). `Name` is the mod id used in logs (`Loaded Mod: TFP_Harmony`).

---

## 5. XML / XPath best practices

### How patches work (Community 3.0)

1. Game loads vanilla `Data/Config/foo.xml`.
2. Each mod’s `Config/foo.xml` applies **XPath operations** in load order.
3. Prefer **targeted** set/append/remove over wholesale file replace.

**Root element:** XPath files use a **`<configs>`** root (community XPath page). Vanilla files use their own roots (`<items>`, …). Do not paste vanilla root wrappers into XPath files.

Commands (verified for 3.0 on community wiki): `set`, `setattribute`, `remove`, `removeattribute`, `append`, `insertAfter`, `insertBefore`, `csv`. Optional A22+ `<if condition="HasMod('OtherMod')">` for soft deps.

| Command | Use when | Missing target |
|---|---|---|
| `set` | Attribute **exists**; change its value | Warns; does not create |
| `setattribute` | Add or change attribute by name | Creates attribute |
| `append` | Add children or suffix attribute text | Creates children |
| `insertBefore` / `insertAfter` | Precise sibling placement | Creates siblings |
| `remove` / `removeattribute` | Delete node or attribute | Warns if absent |
| `csv` | One entry in a delimited list (tags) | Per wiki semantics |

### Prefer

```xml
<configs>
  <set xpath="/items/item[@name='gunHandgunT1Pistol']/property[@name='DegradationMax']/@value">500</set>

  <append xpath="/recipes">
    <recipe name="myItem" count="1" craft_area="workbench">
      <ingredient name="resourceScrapIron" count="10"/>
    </recipe>
  </append>

  <csv xpath="/items/item[@name='toolPickaxeT0Stone']/property[@name='Tags']/@value"
       delim="," op="add">mytag</csv>
</configs>
```

### Avoid

- Copy-pasting entire vanilla files into the mod.
- Fragile indices (`/items/item[17]`) that shift every patch.
- Over-broad paths that rewrite every item accidentally.
- Editing `Data/Config` on disk.
- Missing leading `/` on XPath; wrong case (XPath is case-sensitive).
- Using `<` inside attributes without `&lt;`.

### Developer notes on disk

Vanilla ships **`Data/Config/XML.txt`** (Measured: ~123 KB on client and dedicated). Informal but useful for property semantics. Prefer it over random forum posts for field meaning.

### Localization (3.x)

- **`Localization.csv`** in the mod root (Official + Measured vanilla file name).
- Prefix keys with mod id (`yourmod_ui_title`).

### Cheatsheets

- [XPath (3.0)](https://7d2dmodding.wiki.gg/wiki/XPath)
- [XPath Cheat Sheet](https://7d2dmodding.wiki.gg/wiki/XPath_Cheat_Sheet)
- [XML File Index](https://7d2dmodding.wiki.gg/wiki/XML_File_Index)
- sphereii XPath thread (TFP forums)

### Sandbox / serverconfig (V3) (Official + Measured stock DS config)

- Difficulty-style knobs live in **`SandboxCode`**. Stock default comment: Adventurer equivalent `AAAJABJACJADJARFBNC`.
- Generate codes via in-game sandbox UI “copy code”, or community [Sandbox Code Generator](https://7d2dmodding.wiki.gg/wiki/Sandbox_Code_Generator).
- **Still in `serverconfig.xml` on this install** (non-exhaustive, Measured): ports, visibility, `EACEnabled`, `ServerAllowCrossplay`, `Telnet*`, `WebDashboard*`, `MaxSpawnedZombies`, `MaxSpawnedAnimals`, `ServerMaxAllowedViewDistance`, `DynamicMesh*`, `WorldGenSeed` / `WorldGenSize`, `GameWorld`, `UserDataFolder` (commented), land claim knobs, `SandboxCode`.
- **Removed / converted into Sandbox** (Official V3.0 list): `GameDifficulty`, `BlockDamagePlayer`, `BlockDamageAI`, `BlockDamageAIBM`, `XPMultiplier`, `DayNightLength`, `DayLightLength`, `BiomeProgression`, `StormFreq`, `DeathPenalty`, `DropOnDeath`, `DropOnQuit`, `JarRefund`, `EnemySpawnMode`, `EnemyDifficulty`, `ZombieFeralSense`, `ZombieMove`, `ZombieMoveNight`, `ZombieFeralMove`, `ZombieBMMove`, `AISmellMode`, `BloodMoonFrequency`, `BloodMoonRange`, `BloodMoonWarning`, `BloodMoonEnemyCount`, `LootAbundance`, `LootRespawnDays`, `AirDropFrequency`, `AirDropMarker`, `QuestProgressionDailyLimit`.

Do not invent removed property names. Prefer `SandboxCode` + remaining dedicated knobs.

**RWG size (Measured stock comment):** officially supported widths **6144-10240**, multiple of **2048** (e.g. 6144, 8192, 10240). Larger custom worlds exist in the wild but are outside that comment’s support statement.

---

## 6. Assets and XUi (V3)

### Assets

- Match **Unity version to the game** for bundles (**2022.3.62f2** on this install).
- Icons: **`UIAtlases/ItemIconAtlas/`** (Official Mod Interface: path changed A18; legacy `ItemIcons/` is obsolete).
- Clients must install asset mods; they do **not** push like XML (Community 3.0).
- A bundle the runtime accepts needs a class-142 `AssetBundle` object and the game's own editor revision. `shamway` ([`hordeforge/7dtd-asset-pipeline`](https://github.com/hordeforge/7dtd-asset-pipeline)) gates both offline, plus stem collisions, icon atlas cells and clip format. It also synthesizes texture, audio and text bundles without Unity; meshes, prefabs and materials still need the editor.

### XUi (V3 overhaul) (Official wiki + Measured folders)

| Old (pre-3.0) | Current (3.0+) |
|---|---|
| `Data/Config/XUi/` | **`XUi_InGame/`** (plus `XUi_Menu/`, `XUi_Common/`) |
| `controls.xml` | **`templates.xml`** |
| `{binding}` / `{# ncalc }` | Prefer **`{% expression %}`** (typed NCalc bindings) |
| `force_hide` | Use normal **`visible`** |

Rules of thumb:

- Prefer **rect** over **panel** where possible.
- Register custom bindings/parsers in **`IModApi.InitMod`** before UI init (`BindingMethodCache` / `ParsingMethodCache`) per official XUi page.
- Main menu was redesigned in 3.0; full in-game HUD overhaul is still forthcoming (Official notes). Expect further UI churn.
- Docs: [XUi](https://7daystodie.wiki.gg/wiki/XUi).

### WebDashboard / WebMod (Official V3 + Measured stock samples)

- WebDashboard is **core**, not a separate mod assembly (Official V3.0).
- Stock DS includes **`Xample_MarkersMod`** with a `WebMod/` folder (example plugin).
- APM bridge uses the same pattern: `WebMod/` UI + authenticated API route; does **not** open a separate web listener (bridge README). Enable `WebDashboardEnabled` and use `WebDashboardPort` (stock default **8080**).
- **When:** extend dashboard with a plugin. **When not:** do not reintroduce old external WebDashboard DLL references.

---

## 7. C# ModAPI best practices

### Entry point

```csharp
public class ModApi : IModApi
{
    public void InitMod(Mod _modInstance)
    {
        // Fast, defensive: log, never throw if you can recover
    }
}
```

Measured log sequence: `[MODS] Found ModAPI in assembly …, creating instance` then your init. Console commands subclassing `ConsoleCmdAbstract` are auto-discovered (community + common practice; used across this workspace).

### Project setup (Measured csproj patterns)

| Setting | Practice | Evidence |
|---|---|---|
| Target | **net48** for in-game mod DLLs | RealEarth, EfficientServer, ApmBridge csproj |
| References | `Assembly-CSharp`, `UnityEngine.CoreModule`, game’s `0Harmony`; **Private=false** | Same |
| Optional Managed refs | `Newtonsoft.Json`, `LogLibrary`, … as needed | EfficientServer / bridge |
| Harmony path | `<install>/Mods/0_TFP_Harmony/0Harmony.dll` | RealEarth csproj |
| Do not ship | Vanilla assemblies, second Harmony, extra MonoMod stack | Stock already ships Cecil for Harmony |
| Path | Build against **this** install’s Managed after every update | GAME_VERSION.md |
| V3 WebDashboard | Core only; no extra dashboard assembly refs | Official V3.0 |

Tools **not** loaded by the game (loadgen, host APM, patchers) may use modern .NET (loadgen **net8.0**).

### Do

- Gate dedicated-only logic with `GameManager.IsDedicatedServer` (EfficientServer: `DedicatedOnly` config, default true).
- Prefer public APIs over private field digging when possible.
- Register console commands via `ConsoleCmdAbstract`.
- Log with the game logger under a clear prefix (`[YourMod]` / project constants).
- Fail soft per feature: one missing Harmony target must not kill the whole mod (`PatchAllSafe` pattern in EfficientServer; optional targets in DedicatedSkipPatch).

### Don’t

- Ship a second Harmony that conflicts with `0_TFP_Harmony`.
- Hardcode absolute Steam paths in released builds; inject `GameDir` at build time (RealEarth uses `SEVENDTD_GAME_DIR` / `GameDir`).
- Assume Windows-only paths on Linux dedicated (`7DaysToDieServer_Data` vs `7DaysToDie_Data`).
- Put measurement and optimization in the same DLL (this workspace splits APM bridge vs EfficientServer on purpose).

### EAC

- Client: launch **without EAC** for most DLL mods (Community 3.0).
- Dedicated: `EACEnabled=false` when required (loadgen serverconfig uses false for bots).
- Stock dedicated default on this install: `EACEnabled=true` (Measured). Turn off only when your mod set requires it.
- Some server-side admin tools claim EAC-safe operation; treat as exception and verify their docs.
- Loadgen: EAC/encryption path is **not** implemented for simulated clients (loadgen codec comments); test servers must disable EAC for bots.

---

## 8. Harmony best practices

Harmony ships as **HarmonyX** via stock `Mods/0_TFP_Harmony`. Since A20 you do not need SDX/DMT for normal patching (Community glossary). Measured: TFP loads Cecil + MonoMod stack from that folder only.

### Which Harmony tool when

| Tool | Use when | Avoid when |
|---|---|---|
| **Prefix** | Guard, skip original (`return false`), rewrite args, timing start | You only need after-effects |
| **Postfix** | Observe/adjust result, timing end, logging | You must prevent original side effects |
| **Transpiler** | No other option; surgical IL edit of large method | First choice; untested IL; every update |
| **Finalizer** | Must run cleanup after exceptions | Normal control flow |
| **Manual `Patch(MethodInfo)`** | Optional/reflection targets, missing methods OK | Everything is a stable public API |
| **`PatchAll` on a type** | Cohesive patch class with known targets | One failure should not abort others without try/catch |

Workspace patterns:

- EfficientServer: `new Harmony("com.7dtd.efficientserver")` + per-group `PatchAllSafe`; compile-time `[HarmonyPatch(typeof(World), nameof(World.EntityActivityUpdate))]` etc.
- APM bridge: name-resolved methods + Prefix/Postfix timing; missing hooks → `unavailable`.
- RealEarth: runtime discovery where TFP renames are expected.

### Hygiene

| Practice | Why |
|---|---|
| Unique Harmony id (`com.author.mod`) | Avoid clobbering other mods |
| Prefer Prefix/Postfix over Transpiler | Easier to debug and update |
| Catch / isolate per-patch failures | One bad target should not kill the mod |
| Patch **stable methods** (public tick/API) | Private renames break every patch |
| Document targets + game version | Next update: re-check with ILSpy |
| Avoid double-patching incompatible prefixes | Load-order wars |
| Budget hot paths | Entity ticks, pathfinding, terrain inject scale badly |

### What not to do

- Transpile giant methods without tests.
- Patch ultra-hot paths every frame without APM budgets.
- Replace whole systems when XML or a postfix would do.
- Auto-generate Harmony patches from profiler heuristics into production (APM deliberately removed this).
- Reimplement the dedicated server to “fix lag” (ARCHITECTURE: multi-year full sim rewrite is the wrong first move).

Docs: [Harmony](https://harmony.pardeike.net/) · community [Harmony Patch Targets](https://7d2dmodding.wiki.gg/wiki/Harmony_Patch_Targets)

---

## 9. Engine expand / binary patch (exceptional)

**Default answer: do not patch `Assembly-CSharp` on disk.** Prefer Harmony.

**Exception in this workspace:** RealEarth **YDim expand** (`EngineHeightPatcher`) raises vertical column limits so true tall terrain is possible. Stock markers include `Height255` / chunk Y dims (Measured). Compression alone cannot give 1 m = 1 block Everest-scale mountains (HEIGHT_LIMITS.md).

| Mode | When | Behavior |
|---|---|---|
| Stock-safe | Expand not applied | Compress real meters into ~0-250; mod still loads |
| Expanded | `make engine-expand` / Tools script | YDim raised (product docs: 16384 path); full height |

Rules:

1. Document that **Steam Verify undoes** the patch; re-apply after updates.
2. Never redistribute stock or patched `Assembly-CSharp.dll`.
3. Ship the **patcher tool**, not a game binary.
4. Keep expand logic in **RealEarth**, not in EfficientServer or APM.
5. Treat expand as a **product prerequisite**, not a casual optimization.
6. Close the game before patching (MODLET.md).

See `7dtd-realearth/docs/MODLET.md` and `HEIGHT_LIMITS.md`.

---

## 10. Dedicated server specifics

| Topic | Practice | Grade |
|---|---|---|
| Install path | Same `Mods/` next to dedicated binary | Measured |
| Managed | `7DaysToDieServer_Data/Managed/` | Measured |
| Client vs dedicated DLL | Often the **same** DLL works both; rebuild against dedicated Managed if APIs diverge | Workspace practice |
| Headless flags | `-quit -batchmode -nographics -dedicated -configfile=…` | ARCHITECTURE / stock scripts |
| Simulation | Lag is almost always **sim budget** (AI, chunks, mesh), not missing protocol | ARCHITECTURE |
| Network | LiteNetLib primary; optional SteamNetworking (can disable via `ServerDisabledNetworkProtocols`) | ARCHITECTURE + loadgen config |
| XML | Still pushes to clients | Community 3.0 |
| Harmony that changes sim | Must match client expectations or you get desync/kicks | Engineering truth |
| Telnet | `TelnetEnabled` / `TelnetPort` (stock **8081**) / password | Measured stock config |
| Web dashboard | `WebDashboardEnabled` / port **8080** | Measured |
| Crossplay | `ServerAllowCrossplay`; empty/mod policy per community; version match | Measured + Community |
| Userdata | `UserDataFolder` override; else platform default | Measured comment |

Hot path research (for optimizers): `GameManager.gmUpdate` → world tick → entity AI → dynamic mesh. See `7dtd-server-optimizer/docs/ARCHITECTURE.md`.

Known lag drivers (ordered, ARCHITECTURE): entity AI + pathfinding → active chunk volume / view distance → spawn walks → dynamic mesh / deco → disk saves → heavy terrain mods → single-thread main loop.

### Tunables that are *not* mods (use first)

Before writing Harmony, exhaust stock knobs that still exist on dedicated:

- `MaxSpawnedZombies` / `MaxSpawnedAnimals` (stock comments warn of huge perf impact)
- `ServerMaxAllowedViewDistance`
- `DynamicMeshEnabled`, `DynamicMeshLandClaimOnly`, `DynamicMeshLandClaimBuffer`, `DynamicMeshMaxItemCache`
- `MaxQueuedMeshLayers`
- `SandboxCode` (spawn density, blood moon, etc. without XML)

EfficientServer tightens **beyond** stock AI LOD / mesh budgets; it does not replace these knobs.

After config + sim-side work, if APM still shows a hot main thread and sched noise, use **host topology** (CCD pin, NUMA bind, isolation, IRQ steering). That is ops, not a game mod: [`7dtd-server-optimizer/docs/HOST_TUNING.md`](https://github.com/hordeforge/7dtd-server-optimizer/blob/HEAD/docs/HOST_TUNING.md).

---

## 11. Worlds, prefabs, and RealEarth content boundaries

| Content | Where it lives | How you change it |
|---|---|---|
| Stock pregens / Navezgane | `<install>/Data/Worlds/` | Usually leave alone; point `GameWorld` at name |
| RWG / custom generated | `UserData…/GeneratedWorlds/` | RWG settings, heightmap importers, bake-world export |
| Prefab library | `<install>/Data/Prefabs/` | Prefab editor / POI packs (asset + XML), not EfficientServer |
| Save games | `UserData…/Saves/` | Backup before invasive mods |
| RealEarth offline packs | repo `data/`, `worlds/`, `.rte` tiles | Python pipeline only |
| RealEarth runtime | `Mods/RealEarth` + tile path config | C# streamer / inject |

### Baked vs Streamed (RealEarth, Workspace)

| Mode | Method | MP story |
|---|---|---|
| **Baked** | Offline `bake-world` → finite map in GeneratedWorlds / importer | Best MP story: one shared vanilla-sized world |
| **Streamed** | Absolute Earth + tile bubbles + host window | Shared origin rules matter; see MULTIPLAYER_STREAMING.md |

**Do not** invent a second combat/coordinate model. Vanilla already has shared coords, chunks, and hits (MULTIPLAYER_STREAMING.md). RealEarth only answers: when a chunk is needed at (x,z), what terrain data fills it.

| Concern | Where / how |
|---|---|
| Shared absolute Earth coords | RealEarth session; not loadgen |
| Sliding local window vs shared fixed origin | Config (`SoloSlide` vs `SharedFixed`); document for MP |
| Tile bubble / CDN | RealEarth streamer; measure with APM under loadgen |
| Fake client join soak | loadgen only |
| Height inject cost | RealEarth Harmony; validate with APM, do not “fix” by deleting instrumentation |

World sizes: stock RWG comment supports 6k-10k class sizes; pure PC can go larger but memory and mesh cost dominate. Do not bake a planet-sized heightmap.

---

## 12. Debugging and validation

### Logs (Measured paths)

- Look for `[MODS]` load lines, `Loaded Mod:`, `Found ModAPI`, and your prefix.
- Failed Harmony patches often show during init.
- After updates: confirm patch targets still exist in `Assembly-CSharp`.
- Proton client logs: `…/7DaysToDie/logs/output_log_client__*.txt`.
- Dedicated: use `-logfile` or the userdata logs location for that install/`UserDataFolder`.

### Local RE / tooling

| Tool | Use | Where in this workspace |
|---|---|---|
| ILSpy / ilspycmd / dnSpyEx / monodis | Browse / decompile Managed | Host tools |
| Mono.Cecil dump helpers | Scripted type/method dumps | `7dtd-server-optimizer/tools/` (Dump*.cs) |
| Harmony file logs | When patches misbehave | Game / Harmony config |
| Telnet | Live commands without restart | Dedicated `TelnetPort` |
| `7dtd-server-apm` | Host + managed evidence | Sibling project |
| `7dtd-loadgen` | Repeatable MP load | Sibling project |
| eBPF / perf | Scheduler, IO, syscalls | `7dtd-server-apm` collectors (not optimizer) |
| AssetStudio / UABE | Unity assets (version-sensitive) | External |
| Wireshark | LiteNetLib traffic (protocol work) | External; loadgen territory |

### Test discipline

1. Fresh throwaway world for spawn/loot/progression changes.
2. Backup saves before invasive mods or engine expand:
   - Windows: `%AppData%/Roaming/7DaysToDie/`
   - Proton (this machine): `compatdata/251570/.../AppData/Roaming/7DaysToDie/`
   - Native Linux: `~/.local/share/7DaysToDie/` when used
3. Bisect: empty `Mods` → Harmony only → your mod → others.
4. After Steam update: verify files, rebuild C#, retest XPath, re-expand if used.
5. Performance claims: **same** loadgen manifest, duration, and APM preset for baseline vs candidate.
6. Optimizations that change AI/mesh: soak combat, sleepers, quests, multi-player separation (`7dtd-server-optimizer/docs/FEATURES.md`).

### Validation matrix (Workspace)

| Change type | Minimum proof |
|---|---|
| XPath balance tweak | Fresh world + log clean of XPath errors + in-game check |
| ModAPI command | Dedicated or client log init OK + command works via telnet/console |
| Harmony optional skip | Log shows patch applied or soft-failed; gameplay path still correct |
| EfficientServer feature group | APM baseline → change one group → APM compare + budget + gameplay soak |
| RealEarth height/stream | Correct heightMode log; MP origin rules; no desync in co-op smoke |
| Engine expand | Log/assert expanded YDim; Verify restores stock; re-expand documented |

---

## 13. Tooling map

### Authoring

| Tool | Role |
|---|---|
| VS Code / Rider / VS 2022 | XML + C# |
| .NET SDK targeting **net48** | In-game mod DLLs |
| .NET 8+ SDK | Loadgen and other out-of-process tools |
| Unity (**game-matched**, here 2022.3.62f2) | Asset bundles only |
| Notepad++ / any good XML editor | Lightweight XPath (avoid plain Notepad) |
| `uv` + Python 3.11+ | RealEarth offline pipeline, APM host |
| `shamway` (`7dtd-asset-pipeline`) | Build, gate and stage a mod AssetBundle; synthesize texture, audio and text bundles with no editor |

### Reverse engineering

| Tool | Role |
|---|---|
| ILSpy / AvaloniaILSpy / dnSpyEx / ilspycmd | Decompile Managed |
| Mono.Cecil | Automated dumps, RealEarth height patcher, optimizer Dump* tools |
| AssetStudio / UABE | Unity assets (pin versions carefully) |
| Wireshark | LiteNetLib / join protocol (advanced; prefer loadgen for load) |

### Distribution / discovery

| Site | Role |
|---|---|
| [7DaysToDieMods.com](https://7daystodiemods.com/) | Primary 7D2D mod hub; install guides; keep-Harmony warnings |
| [Nexus Mods](https://www.nexusmods.com/7daystodie) | Alternate hosting, tools |
| [TFP forums](https://community.thefunpimps.com/) | Official + sphereii XPath |
| [7d2dmodding.wiki.gg](https://7d2dmodding.wiki.gg/) | Community technical wiki (3.0) |
| [7daystodie.wiki.gg Modding](https://7daystodie.wiki.gg/wiki/Modding) | Official wiki hub |

### Server ops (often not mods)

| Tooling | Role |
|---|---|
| Telnet / WebDashboard (core V3) | Automation and admin without invasive patches |
| Allocs / Server Tools family | Map, claims, web UI (check EAC claims **per version**) |
| TianYi / ServerKit-style kits | Full control panels (version-pin carefully) |
| systemd / Docker | Process supervision (your ops, not TFP); `CPUAffinity=` for CCD pin |
| CCD / NUMA / IRQ / governor | Host topology; see [`7dtd-server-optimizer/docs/HOST_TUNING.md`](https://github.com/hordeforge/7dtd-server-optimizer/blob/HEAD/docs/HOST_TUNING.md) |
| `7dtd-server-apm` + `7dtd-loadgen` | Evidence-backed capacity work in this workspace |

### Templates and learning

- https://github.com/7D2D/Templates-and-Utilities
- https://github.com/7D2D/Unity-Scripts
- Harmony intro: https://harmony.pardeike.net/articles/intro.html
- XPath intro: https://darkaoraidenx.github.io/7DTD/introduction.html
- Discords: Guppycur modding, 7d2d wiki, 7DaysToDieMods.com, TFP official (see `7dtd-realearth/docs/MODDING_REFERENCES.md`)

---

## 14. Packaging checklist (release)

```
Mods/YourMod/
  ModInfo.xml
  YourMod.dll                 # if C#
  Config/**                   # XPath + json only
  Localization.csv            # if needed
  UIAtlases/...               # if icons
  WebMod/...                  # if dashboard plugin
  README.txt                  # game version, EAC, Harmony note, client vs server
```

Zip so extracting into `Mods/` yields `Mods/YourMod/ModInfo.xml` immediately.

README must state:

1. Supported **game version** (e.g. 3.0.1).
2. Requires stock **`0_TFP_Harmony`** (do not delete).
3. **EAC** off if DLL.
4. Client vs server install requirements.
5. How to read logs if it fails.
6. If engine expand: stop game, apply tool, re-apply after Verify.

Distribution hubs: [7DaysToDieMods.com](https://7daystodiemods.com/), [Nexus](https://www.nexusmods.com/7daystodie), TFP resources.

---

## 15. Anti-patterns

| Anti-pattern | Prefer |
|---|---|
| Delete `0_TFP_Harmony` | Keep stock Harmony |
| Nested zip folders | Flat `Mods/Name/ModInfo.xml` |
| Editing `Data/Config` in place | XPath modlet |
| One mega-DLL that optimizes + profiles + generates load | Split projects (this workspace) |
| No game version on release page | Pin version; retest every patch |
| Harmony on every entity tick without budgets | Profile first (APM) |
| Crossplay server + DLL mods | Choose mods **or** consoles |
| Shipping `Assembly-CSharp.dll` | Runtime Harmony, or document expand tool |
| Accepting CPU drop without sim fidelity checks | APM + gameplay soak |
| Auto-codegen Harmony from samples as production code | Human-reviewed patches only |
| Pre-3.0 XUi paths / `{binding}` only | `XUi_InGame` + `{% %}` |
| `Localization.txt` | `Localization.csv` |
| Extra WebDashboard assembly refs | Core `Assembly-CSharp` only |
| Removed V2 `serverconfig` difficulty properties | `SandboxCode` |
| Second combat/coordinate system for streaming maps | Shared origin + vanilla netcode |
| Loadgen against EAC-on servers | EAC off for bot protocol |
| Putting Python bake logic inside the game DLL | Offline `tools/` pipeline |

---

## 16. Quick decision trees

### Feature layer

```
Need balance / recipes / loot / spawn rates?
  → XML modlet (layer 1)

Need new mesh / sound / icon?
  → Assets + XML (layer 2); clients install

Need new command or small system?
  → ModAPI DLL (layer 3)

Need to intercept existing compiled logic?
  → Harmony Prefix/Postfix first (layer 4)

Need host automation without blocking crossplay?
  → Telnet / WebAPI (layer 0)

Need vertical world beyond stock ~255 markers?
  → RealEarth expand path (layer 5), not a random Harmony one-liner

Need dashboard UI plugin?
  → WebMod/ under a server mod + WebDashboardEnabled
```

### Performance work (this monorepo)

```
Can stock serverconfig knobs fix it (zombie caps, view distance, dynamic mesh)?
  → Change config first; re-measure

Need a controlled multiplayer workload?
  → 7dtd-loadgen (EAC off)

Need evidence of where time goes?
  → 7dtd-server-apm host (± bridge)

Need a reviewed sim change with budgets?
  → 7dtd-server-optimizer, one feature group at a time

Main thread hot, multi-CCD/NUMA host, knobs already sane?
  → Host pin / isolation (HOST_TUNING.md); do not put affinity in the mod DLL

Need real-world terrain product work?
  → 7dtd-realearth (offline bake vs runtime stream)
```

### Harmony patch style

```
Only need to observe or tweak return?
  → Postfix

Need to skip or gate original?
  → Prefix (return false carefully)

Method missing on some builds / optional feature?
  → Manual Patch(MethodInfo) + soft fail

Must edit IL mid-method?
  → Transpiler last; pin game version; add tests
```

---

## 17. External references (primary)

### Official

| Resource | URL |
|---|---|
| V3.0 release notes (modding section) | https://7daystodie.com/v3-0-dead-hot-summer-release-notes/ |
| V3.2.0 (b9) | Steam 2026-08-28; exact-diff: `7dtd-engine-research/docs/changelog-3.2.0.md` |
| V3.1.0 Henpocalypse | https://7daystodie.com/v3-1-0-henpocalypse-release-notes/ |
| V3.0.1 Stable | https://7daystodie.com/v3-0-1-stable-release/ |
| Mod Interface | https://7daystodie.wiki.gg/wiki/Mod_Interface |
| XUi (V3 bindings) | https://7daystodie.wiki.gg/wiki/XUi |
| Modding Resources | https://7daystodie.wiki.gg/wiki/Modding_Resources |
| TFP forums / news | https://community.thefunpimps.com/ |
| Official Discord | https://discord.gg/taYNEUS |

### Community (technical)

| Resource | URL |
|---|---|
| 7D2D Modding Wiki (3.0) | https://7d2dmodding.wiki.gg/ |
| Getting Started | https://7d2dmodding.wiki.gg/wiki/Getting_Started |
| XPath | https://7d2dmodding.wiki.gg/wiki/XPath |
| Harmony targets | https://7d2dmodding.wiki.gg/wiki/Harmony_Patch_Targets |
| Sandbox Code Generator | https://7d2dmodding.wiki.gg/wiki/Sandbox_Code_Generator |
| 7DaysToDieMods.com | https://7daystodiemods.com/ |
| Install guide | https://7daystodiemods.com/posts/how-to-install-7-days-to-die-mods |
| Nexus | https://www.nexusmods.com/7daystodie |
| Harmony docs | https://harmony.pardeike.net/articles/intro.html |
| Templates | https://github.com/7D2D/Templates-and-Utilities |
| XPath intro | https://darkaoraidenx.github.io/7DTD/introduction.html |

### Discords

Guppycur modding, 7d2d wiki modding, 7DaysToDieMods.com, TFP official: see `7dtd-realearth/docs/MODDING_REFERENCES.md`.

---

## 18. Legal / distribution

- Own a legitimate game copy.
- Do not redistribute decompiled game IL or `Assembly-CSharp.dll`.
- Ship only your mod binaries, configs, tools you wrote, and original notes.
- Respect EAC and platform policies; document EAC requirements honestly.
- Attribute third-party data (elevation, landcover, OSM) in RealEarth packaging.

---

## Changelog

- **2026-07-16 (sim):** SIM_PARALLELISM description covers extract-off-main, threading policy, hot paths.
- **2026-07-16 (oss):** Linked research notes for OSS tools survey, ServerTools, and NAIWAZI.
- **2026-07-16 (host):** Linked [`7dtd-server-optimizer/docs/HOST_TUNING.md`](https://github.com/hordeforge/7dtd-server-optimizer/blob/HEAD/docs/HOST_TUNING.md) (CCD/NUMA/affinity measure-first ops).
- **2026-07-16 (merge):** Folded remaining unique content from `7dtd-server-optimizer/docs/MODDING_BEST_PRACTICES.md` (tooling map, server-ops tools, RE tool names, Windows save path, client/dedicated DLL note). Optimizer file replaced by project-specific `DEVELOPMENT.md`.
- **2026-07-16 (review):** Grounded version/Unity/Harmony/paths/logs in local installs and client log; added method chooser, evidence grades, offline vs in-game TFMs, stock serverconfig property lists (kept vs Sandbox-migrated), WebMod/WebDashboard, world/prefab boundaries, Harmony tool matrix, stock-knob-before-Harmony, validation matrix, XPath `<configs>`/`set` vs `setattribute`, loadgen EAC limit.
- **2026-07-16:** Initial workspace consolidation from optimizer draft, RealEarth packaging/height/modlet notes, APM/loadgen/optimizer boundaries, V3.0 / V3.0.1 notes, 7d2dmodding Getting Started + XPath (3.0), official XUi / Mod Interface, 7DaysToDieMods install conventions.

- **2026-08-28:** Retarget workspace modding guide to V3.2.0 (b9); wire + held-entity notes carried from V3.1.0, exact-diff changelog in `7dtd-engine-research`.
- **2026-08-02:** Retarget workspace modding guide to V3.1.0 (b14) Henpocalypse; TE wire + held-entity notes.
