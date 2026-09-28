# TODO — Wrench (Mod Settings)

Task queue. Claim a task by changing `[ ]` to `[-]` with
`in progress — <agent>, YYYY-MM-DD; session: <id>` (see AGENTS.md); mark it
`[x]` the moment it completes. Next task = first unchecked item under the
earliest unfinished section.

## Purpose

See [`docs/design.md`](docs/design.md) "Goal". The task queue below tracks
the work that goal describes; the goal itself is stated there once.

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
      run3, every wrench-mod-settings case PASS.
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

- [ ] Keep `make test` and `make lint` green on every change.
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
- [ ] Simulated runs of the settings watch and a save, through the
      `ModClock` / `ModFileSystem` seams (docs/architecture.md,
      2026-09-28): a seeded scenario drives the poll interval, the
      debounce and the replace retry on a virtual clock and an in-memory
      filesystem, with faults injected (replace lost to a reader, a write
      that fails half way, a reload at a chosen moment), each run
      printing its seed so a failure replays from it. Needs the state
      machines free of `UnityEngine`/game references to be driven from
      the game-free gate host in `scripts/toml_gate/`.
      Done for the save path: `TargetMod` is game-free and
      `scripts/toml_gate/Simulation.cs` runs it from a seed with those
      faults. Left: the watch itself, which still reaches
      `UnityEngine.Debug` and takes a `Mod`; it needs the same log seam
      and split before the poll and debounce can be stepped.
- [x] The four save-path checks `scripts/toml_gate/` first reported on
      2026-09-28 (the save path moved onto `TomlFile` and gained the
      post-staging signature re-read). A save that stages while another
      program writes the same file now re-splices around that write
      instead of landing its own whole-file copy over it, and a fallback
      move that fails keeps the staged text and names where it was left
      beside the file. The gate asserts all four now, including "a save
      keeps the other program's save made mid-save".
- [ ] Re-run the live suite after the save path moved onto `TomlFile`
      (read, temp sibling and all): the offline gates cannot compile the
      mod DLL here, so the atomic replace, the mark round trip and the
      shared-access open need one real save on the client.

## Release

- [ ] Cut the two release tags that were never cut, from the commits that
      set the versions: `v0.2.0` at `db6930a` and `v0.3.0` at `4ee39c1`
      (`git tag -a v0.2.0 db6930a`, then the same for `v0.3.0`, then
      `git push origin v0.2.0 v0.3.0`). Both numbers are published: they are
      the newest heading in `CHANGELOG.md` and the version in `ModInfo.xml`
      when they were declared, and `git tag` lists only `v0.1.0`, so a
      player asking for "the 0.3.0 download" finds nothing. The tag cannot
      be cut from a later commit: the release is that tree.
- [ ] Say in the next release heading that the strict marked-encoding read
      refuses a file 0.3.0 loaded, so the release is a minor. The entry
      already describes the change; the bump is decided when the heading is
      written.

## Open questions

- (none yet)
