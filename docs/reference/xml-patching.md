# XML Patching (XPath)

Vanilla config lives in `Data/Config/*.xml` (see `environment.md`). A mod can
affect these files two ways:

1. **Full override** — ship a `Config/items.xml` (etc.) that's a complete
   replacement. Simple but fragile: it fully replaces the vanilla file, so it
   silently drops any vanilla changes from later game updates and conflicts
   with any other mod that also overrides the same file.

2. **XPath patch** — ship a `Config/<file>.xml` containing a `<configs>`
   root plus `<set>`/`<append>`/etc. elements with an `xpath` attribute that
   surgically targets nodes inside the vanilla file. Preferred for anything
   that isn't a wholesale content replacement, since multiple mods' patches
   can coexist and vanilla updates are more likely to keep working.

   **On the root element name:** use `<configs>` in hordeforge mods. The
   patcher has accepted both `<config>` and `<configs>` in observed mods, but
   consistency matters more than spelling here, and existing hordeforge mods' `Config/`
   already use `<configs>`.

   ```xml
   <configs>
       <set xpath="/items/item[@name='thrownGrenadeContact']/property[@name='Stacknumber']/@value">50</set>
   </configs>
   ```

   Here `<set xpath="...">` replaces the matched attribute value.

## Patch operations (general knowledge — re-verify against current game version)

The XML patcher (based on XPath 1.0 expressions against the vanilla file's
DOM) supports operations along these lines:

- `<append xpath="...">` — add new child node(s) under the matched node.
- `<insertBefore xpath="...">` / `<insertAfter xpath="...">` — insert a
  sibling relative to the matched node.
- `<set xpath="..." value="...">` (or with child content) — replace an
  attribute value or a node's content.
- `<remove xpath="..."/>` — delete the matched node/attribute.
- `xpath` can target attributes too, e.g.
  `xpath="/items/item[@name='thrownGrenade']/@name"`.

For a new item/block/etc., the common pattern is `append` at the parent
element (e.g. `/items`) with a full `<item name="...">...</item>` block as
the payload — this adds a brand-new entry without touching anything vanilla.
For tweaking an existing vanilla entry, target it with a predicate
(`[@name='...']`) and `set`/`append` just the specific property you need to
change, e.g.:

```xml
<configs>
    <append xpath="/items">
        <item name="myNewItem">
            <property name="Extends" value="thrownGrenadeContact"/>
            ...
        </item>
    </append>

    <set xpath="/items/item[@name='thrownGrenadeContact']/property[@name='Stacknumber']/@value">50</set>
</configs>
```

Watch the *full* path to the node, not just its name. Vanilla nests some
entries under a container element — `crafting_skill` lives at
`/progression/crafting_skills/crafting_skill`, not `/progression/crafting_skill`
— and an `xpath` that omits the container matches nothing and applies
silently rather than erroring. Confirm the real path in the vanilla file
before trusting a patch, and check the log (step 3 below) to see it landed.

## `Extends`

Vanilla items/entities/etc. frequently use `<property name="Extends" value="otherItemName"/>`
to inherit all properties from another entry and then override specific
ones. This is the standard way to create a variant of an existing
item/block/entity without duplicating its whole definition. Verified example:
`thrownGrenadeNukeAdmin` in `Data/Config/items.xml` extends
`thrownGrenadeContact`.

## Practical workflow

1. Find the vanilla node to change/extend in `Data/Config/*.xml` (read-only —
   never edit the game install).
2. Write a *patch* file under the mod's `Config/` with the same filename,
   using a `<configs>` root + xpath ops rather than a full override, unless
   a complete replacement is actually intended.
3. Check the game log (`environment.md`) on load — the patcher logs XPath
   errors (node not found, malformed expression) at startup.
