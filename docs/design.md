# Design — Wrench (Mod Settings)

Gameplay decisions for this mod. Record every decision the moment it is
made, under a dated heading, and never leave stale contradictory statements.

## Goal

Adds a Mod Settings screen to the in-game options menu, listing every installed mod that ships a Config/<Mod>.toml settings file and letting the player view and edit those settings from the UI. Edits are written back in place to the mod's own TOML; mods built on Anvil's settings component apply them live through their existing hot-reload watch, with no coupling between this mod and theirs.

## Decisions

(Format: `## Decided YYYY-MM-DD: <topic>` — what was decided and why.)

## Open questions

- (none yet)
