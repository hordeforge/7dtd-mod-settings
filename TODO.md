# TODO — Wrench (Mod Settings)

Task queue. Claim a task by changing `[ ]` to `[-]` with
`in progress — <agent>, YYYY-MM-DD; session: <id>` (see AGENTS.md); mark it
`[x]` the moment it completes. Next task = first unchecked item under the
earliest unfinished section.

## Purpose

Adds a Mod Settings screen to the in-game options menu, listing every installed mod that ships a Config/<Mod>.toml settings file and letting the player view and edit those settings from the UI. Edits are written back in place to the mod's own TOML; mods built on Anvil's settings component apply them live through their existing hot-reload watch, with no coupling between this mod and theirs.

## Design

- [x] Break the purpose above into concrete gameplay decisions in
      `docs/design.md` (dated `Decided:` entries); raise open questions for
      the user instead of inventing answers.

## Implementation

- [x] TOML document parser: extend `TomlSettings.cs` with span/comment
      capture (each key's raw value span + preceding comment block +
      typed kind), reusing the existing value reader; plus the in-place
      writer that replaces only an edited key's value span. Offline
      round-trip gate in `scripts/`.
- [x] Discovery: enumerate loaded mods' `Config/<Mod>.toml` files;
      unreadable files listed but not editable.
- [-] XUi "Mod Settings" screen: options-menu tab (XUi_Menu patches),
      mod list + per-key rows (toggle for bools, text fields otherwise),
      comment block as help text, in-place write-back on edit.
      in progress — Claude, 2026-08-30; session: claude-20260829-183855-553b7f4344e0
      (renders and edits live; mouse interactivity being verified with a
      human at the client)
- [-] Live-reload awareness: detect the Anvil settings component in the
      target mod (restart-required label otherwise) and confirm a save
      was re-read from the log line after writing.
      in progress — Claude, 2026-08-30; session: claude-20260829-183855-553b7f4344e0
      (marker fixed after run2: Atomic phrases the line 'settings from
      reload', template 'settings (reload'; rerun pending)
- [ ] UI polish (user: "we can improve the ui still"): clearer toggle
      affordance for booleans, tidy the double row/value borders, mod
      description under the header, hover highlight on rows.

## Testing

- [ ] Keep `make test` and `make lint-shell` green on every change.
- [ ] First in-game validation: `make build`, deploy per
      `docs/reference/environment.md`, verify the log is clean of XPath
      errors AND the change is visible in game.
- [ ] Live check against AtomicDoomsday's TOML on this machine: edit
      RaidMode from the UI, confirm Atomic logs the reload (shared
      playtest lock applies).

## Open questions

- (none yet)
