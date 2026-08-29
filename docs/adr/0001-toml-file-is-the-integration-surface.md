# 0001. The target mod's TOML file is the integration surface

Date: 2026-08-30

## Status

Accepted

## Context

Wrench shows and edits other mods' settings. Some coupling shape had to
be chosen between this mod and every mod it edits:

1. **A registration API** the target mod calls to describe its
   settings. Rejected: version coupling (shared assembly or reflected
   contract), a load-order dependency, and every existing mod would
   need a change before appearing in the UI.
2. **Reflecting into each mod's `ModSettings` type.** Rejected: couples
   Wrench to a private type shape that mods are free to refactor, for
   no information the file does not already carry.
3. **Editing the mod's own `Config/<Mod>.toml` file.** Chosen.

The Anvil template already ships the mod-side half of option 3: every
scaffolded C# mod reads `Config/<Mod>.toml` at startup and re-reads it
on save (debounced watch on `ModEvents.UnityUpdate`, reset-to-defaults
then apply, broken save keeps current values; AtomicDoomsday ADRs 0006
and 0015 are the production shape). The file is therefore already a
public, uniform surface: bare keys, booleans, integers, floats, basic
strings, arrays.

## Decision

The TOML file itself is the whole integration. Wrench discovers mods by
the presence of `Config/<Mod>.toml` in each loaded mod's folder, parses
it with the same TOML subset grammar Anvil ships, and writes edits back
by replacing only the value span on the existing `Key = ` line, so
comments and layout survive byte-for-byte.

- A mod built on the Anvil settings component applies the save live
  through its own watch; Wrench never signals it.
- A mod that predates the component still appears in the UI; its edits
  need a restart and the UI says so.
- A file the parser rejects is listed as unreadable, never shown
  half-parsed, and never written back to.

## Consequences

- No API to version, no assembly to share, no load order to manage. A
  mod opts in by shipping a TOML file, which Anvil mods already do.
- Wrench's parser must stay exactly as strict as Anvil's
  `TomlSettings`: anything Wrench would accept but the target rejects
  could be written into a file the target then refuses to load
  (refusing keeps current values, so the failure is soft, but the edit
  silently stops applying).
- Wrench cannot know which side owns a value on a server: a joined
  client edits only its local copy, and the UI has to say so rather
  than pretend otherwise.
- The write path must be in-place value replacement, never a
  serialize-from-model rewrite, or comments and operator formatting
  would be destroyed on first save.
