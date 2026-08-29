# Mod Folder Structure & ModInfo.xml

A 7DTD mod ("modlet") is a plain folder placed in a Mods directory (see
`environment.md`). The folder name is conventionally the mod's internal name.

## Minimal example

```
MyMod/
├── ModInfo.xml
└── MyMod.dll
```

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<xml>
    <Name value="MyMod" />
    <DisplayName value="My Mod" />
    <Description value="Short description shown in the mod list." />
    <Author value="Author" />
    <Version value="1.0.0.0" />
    <Website value="" />
    <SkipWithAntiCheat value="false" />
</xml>
```

`ModInfo.xml` fields:

| Field | Purpose |
|---|---|
| `Name` | Internal/unique mod id. Should match the folder name by convention. |
| `DisplayName` | Human-readable name shown in-game (mod list). |
| `Description` | Shown in-game. |
| `Author` | Free text. |
| `Version` | Free-form version string, e.g. `1.0.0.0`. |
| `Website` | Optional URL. |
| `SkipWithAntiCheat` | `true` marks the mod as safe to still load when EAC is enabled (only true for cosmetic/non-cheating mods; most gameplay/content/code mods should leave this `false` or omit it). |

## Larger mod: conventional subfolders

```
MyMod/
├── ModInfo.xml
├── Config/            # XML: items.xml, blocks.xml, recipes.xml, entityclasses.xml, ...
│   └── *.xml           # either full overrides or XPath <config> patches — see xml-patching.md
├── Prefabs/            # custom prefabs (POIs, world objects)
├── Resources/           # custom Unity asset bundles (*.unity3d) — models, sounds
├── UIAtlases/           # custom icon atlases (ItemIconAtlas, UIAtlas)
├── UI/                  # custom XUi windows.xml / styles
├── Harmony-MyMod.dll     # optional compiled C# Harmony patch assembly
└── *.dll                 # any other compiled code
```

Any of these subfolders is optional — include only what the mod needs. A
pure config-tweak mod may be nothing but `ModInfo.xml` + `Config/`.

## Load order

Mods load in alphabetical folder-name order by default (hence the common
`0_` numeric prefix in stock `0_TFP_Harmony`) to force dependencies/core mods
to load before content that depends on them. There is no general dependency
declaration field; ordering is folder-name based.

## EAC (EasyAntiCheat)

Most non-cosmetic mods require EAC to be disabled in the launcher (see
`environment.md`). `SkipWithAntiCheat="true"` in `ModInfo.xml` is how a mod
opts in to still being loaded when EAC *is* enabled — only appropriate for
mods that don't touch anything EAC would flag (e.g. pure client-side
tweaks with no gameplay-affecting code).
