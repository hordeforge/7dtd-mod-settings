# Design — Wrench (Mod Settings)

Gameplay decisions for this mod. Record every decision the moment it is
made, under a dated heading, and never leave stale contradictory statements.

## Goal

Adds a Mod Settings screen to the in-game options menu, listing every installed mod that ships a Config/<Mod>.toml settings file and letting the player view and edit those settings from the UI. Edits are written back in place to the mod's own TOML; mods built on Anvil's settings component apply them live through their existing hot-reload watch, with no coupling between this mod and theirs.

## Decisions

(Format: `## Decided YYYY-MM-DD: <topic>` — what was decided and why.)

## Decided 2026-08-30: v1 scope

From the planning doc that started this mod (`~/code/mod-settings-ui.md`):

1. **Discovery**: scan the loaded mod list (`ModManager`) for
   `Config/<ModName>.toml`. One entry per mod found.
2. **Rendering**: a "Mod Settings" tab in the regular options menu
   (pause menu → Options, and main menu → Options). Per mod: key list
   with current values; edit controls typed from the parsed value
   (toggle for booleans, numeric field for numbers, text field for
   strings/arrays). The comment block directly above a key renders as
   its help text.
3. **Write-back**: value replacement in place on the existing `Key = `
   line so comments and layout survive; keys are never reordered or
   reformatted. Hot-reload consumers apply the save live; for others
   the UI marks "takes effect after restart".
4. **Server settings**: a joined client edits only its local copy; the
   UI says so. Editing the server copy stays a server-console/telnet
   task in v1.
5. **Own settings**: Wrench is built from Anvil, so its own TOML
   appears in its own UI.

A file the parser rejects is listed as unreadable — never shown
half-parsed, never written back to.

## Deliberately not built (v1)

- `# ui:` annotations in TOML comments for labels, ranges, and enums.
- Pushing server-side edits through an authenticated channel.
- A WebMod panel reusing the same file surface.

## Open questions

- (none yet)
