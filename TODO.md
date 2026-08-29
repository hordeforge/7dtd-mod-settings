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
- [x] XUi "Mod Settings" screen: options-menu tab (XUi_Menu patches),
      mod list + per-key rows (raw-token text fields, one-click flip for
      booleans), comment block as help text, in-place write-back on edit.
      Human-verified clickable 2026-08-30 after the scrollview depth fix
      (docs/architecture.md).
- [x] Live-reload awareness: detect the Anvil settings component in the
      target mod (restart-required label otherwise) and confirm a save
      was re-read from the log line after writing. Proven live: suite
      run3, all six wrench-mod-settings cases PASS.
- [ ] `# ui:` annotation renderer per the convention in docs/design.md
      (flags → checkboxes with an "all" master, enum, range); strip
      `# ui:` lines from displayed help. First consumer: AtomicDoomsday's
      RaidMode (user 2026-08-30: "should be checkboxes, to select all,
      none or the specific nuke yields").
- [ ] UI polish: the right-hand description panel's text is very small
      (user 2026-08-30); a dark backdrop so the 3D world does not bleed
      through the page; tidy the double row/value borders; mod
      description under the header; hover highlight on rows.
- [ ] Mouse wheel over a row does not scroll the list (row collider does
      not forward scroll; see docs/architecture.md). Lists currently fit
      without scrolling.

## Testing

- [ ] Keep `make test` and `make lint-shell` green on every change.
- [x] First in-game validation: XUi_Menu patches applied cleanly, screen
      visible and interactive in game (2026-08-30, playtest suite +
      manual client).
- [x] Live check against AtomicDoomsday's TOML on this machine: edit
      RaidMode from the UI, confirm Atomic logs the reload. PASS in
      suite run3 (edit applied live in 673ms, restore byte-identical)
      plus human toggle clicks confirmed in the client log.
- [ ] Re-run `make playtest` after the raw-token row rework (cases drive
      SaveEdit directly, so they should hold; the flip button and text
      entry deserve one more human click-through).

## Open questions

- (none yet)
