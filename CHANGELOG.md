# Changelog

Every release of Wrench, in the order it shipped. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the version
under a heading is the one in `ModInfo.xml`, which is also the version the
game shows in its mod list. A version is never reused: once a number is
published it is fixed, and the next change ships under a new one.

Breaking changes for players and for mod authors are called out under
**Changed** or **Fixed**; a release with none says so under
**Compatibility**.

## [0.2.1] - 2026-09-28

Requires 7 Days to Die V3.2, the same as 0.2.0. Upgrade by replacing the
whole `Mods/Wrench` folder: no config migration, no new key, and no
removed key.

### Fixed

- A setting key whose case does not match is now reported as an unknown
  key instead of applying the setting it only looks like. TOML keys are
  case sensitive, and `wrench set` still accepts a name typed in any case.

### Compatibility

- No breaking change: no setting key was renamed or removed, no default
  changed, and the console commands take the same arguments and print
  the same reports. A file that spelled a key with the wrong case set
  that setting from 0.1.0 to 0.2.0; from 0.2.1 the key is unknown, is
  logged as unknown, and the default stands.

## [0.2.0] - 2026-09-28

Requires 7 Days to Die V3.2, the same as 0.1.0. Upgrade by replacing the
whole `Mods/Wrench` folder: no config migration, no new key, and no
removed key. Wrench.toml files written by 0.1.0 are read by 0.2.0 and
kept as they are until the next save, which rewrites only the edited
value.

### Added

- Empty states on the Mod Settings screen: a message when no installed
  mod ships a `Config/<Mod>.toml`, and one when the selected mod's file
  could not be read. Before this the two cases were a blank panel.
- Every value is edited as its raw token, so a setting can change kind
  in place (`false` to `["Tactical"]`). Booleans keep their one-click
  flip.

### Changed

- A mod's settings file is resolved inside that mod's own folder. A mod
  name carrying a directory part is refused, logged, and the mod is
  skipped, instead of pointing the read and the save outside the folder.
  0.1.0 concatenated the name into the path, so a mod named
  `../elsewhere` had its file read and written from outside its folder.
- A save is written to a temp file and renamed over the destination, in
  the encoding the file itself declares. A crash or a full disk during a
  save can no longer leave a truncated settings file, and a non-ASCII
  comment or a byte order mark in a third-party file survives a save
  unchanged.
- The wait for a mod's reload confirmation is bounded, and the file watch
  is timed off a monotonic clock, so a clock step or a mod that never
  logs a reload cannot stall the screen.
- Settings file case: `Foo` and `foo` are two TOML keys. 0.1.0 rejected a
  file holding both; 0.2.0 reads it and edits each key separately.

### Fixed

- A stale in-memory copy of a settings file could be written over a
  newer file on save.
- After a mod was reloaded on a long-running dedicated server, the file
  watch was registered a second time and polled twice per frame with no
  way to unhook the first. It is registered once per process.
- Cross-thread reads of the settings state are guarded.
- A mod whose assembly the runtime could not load once was remembered as
  not hot-reloading for the rest of the session, so its row kept saying
  "restart required" after the assembly was loadable again. An
  incomplete probe is no longer kept, and the remembered answers are
  looked up and filled under one lock.
- Switching the settings watch to a different file (a mod reloaded on a
  long-running dedicated server) kept the previous file's write time and
  length, so a new file of the same size written in the same timestamp
  tick was taken for one already applied and the old values stayed in
  place. The signature is forgotten when the watched path changes.
- A failed save is reported on the screen and in the log instead of
  being reported as applied, and a mod is marked applies-live only
  after its save succeeded.
- Wrench's own broken settings file is no longer re-logged on every
  frame.
- A mod's settings file that is not valid UTF-8 is now reported as
  unreadable instead of being read with replacement characters. Saving
  one such file turned every byte the decoder could not read into U+FFFD,
  for good; a file whose bytes are not valid in the encoding it declares
  is now left exactly as it is. The marked and unmarked forms behaved
  differently before, so three bytes of preamble decided how forgiving
  the read was.
- TOML string escapes follow the TOML grammar in both directions:
  `\b \f \r \t \n \" \\`, `\uXXXX` and `\UXXXXXXXX` including surrogate
  pairs are read and written correctly, a raw control character in a
  basic string is refused, and an unpaired surrogate escape is refused
  rather than silently replaced. A value's span is measured in
  characters, so a value containing non-ASCII text is no longer written
  back at a wrong offset.
- `make deploy-server` could not swap the package into the server's
  `Mods/Wrench`: moving a folder needs write permission on the folder
  being moved, and the staged tree is read-only. A re-run could not
  clear the staging and rollback folders an earlier run left (they are
  read-only for the same reason), and `make rollback-server` deleted the
  deployed mod before the previous one was in place, so an interrupted
  rollback left the server with no mod and no way back. Both directions
  now keep the folder they replace until their own move has landed, and
  a run after an interrupted one converges.

### Compatibility

- No breaking change: no setting key was renamed or removed, no default
  changed, and the console commands (`wrench`, `wrench settings`,
  `wrench set <name> <value>`, `wrench reload`) take the same arguments
  and print the same reports.
- A settings file that 0.1.0 refused to read is now readable (case
  variant keys, TOML escapes, non-ASCII values). Nothing that 0.1.0
  read is refused by 0.2.0.

## [0.1.0] - 2026-09-11

First release.

- A Mod Settings screen in the regular options menu (pause menu and main
  menu), added as an XUi XML patch.
- Every loaded mod that ships a `Config/<Mod>.toml` is listed, with the
  comment block above each key as its help text.
- Edits are written back in place: only the edited key's value span
  changes, so comments and layout survive.
- Mods built on Anvil's settings component are labelled applies-live,
  and the status reports whether the mod re-read the file.
- Wrench's own `Config/Wrench.toml` is listed and editable, with hot
  reload on save and the `wrench` console command.
