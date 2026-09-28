# Changelog

Every release of Wrench, in the order it shipped. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the version
under a heading is the one in `ModInfo.xml`, which is also the version the
game shows in its mod list. A version is never reused: once a number is
published it is fixed, and the next change ships under a new one.

Breaking changes for players and for mod authors are called out under
**Changed** or **Fixed**; a release with none says so under
**Compatibility**. Work that has not shipped sits under
`## [Unreleased]`, above the newest release heading, and moves down to
its own numbered heading when the version it ships under is declared.

## [Unreleased]

### Fixed

- Another mod's settings file marked UTF-16 or UTF-32 is refused when it
  holds a byte that is not valid in the encoding its own mark names,
  instead of being read with replacement characters. The marked
  candidates were built with the two-argument constructors, whose second
  argument is the byte order mark and not the fallback, so those two
  decoders were lenient where the unmarked UTF-8 one is strict; a save
  after such a read wrote the replacement characters back into a file
  this mod does not own. A marked file is now read under the same rule
  as every other one.

- The packaged modlet is no longer staged read-only, so saving a setting
  works on an install whose extractor restored the modes the zip records.
  A save writes a staged file into `Config/` and replaces
  `Config/Wrench.toml` with it; a folder or file the installing user
  cannot write refused every save, and the screen reported the refusal.
  Extract the new package over the old folder, or make the installed
  folder writable by its owner (`chmod -R u+w Mods/Wrench`).
- Reopening the Mod Settings screen keeps the selection on the mod whose
  folder it was on, instead of the mod whose `ModInfo` name matches. Two
  installed mods can carry the same name, and the reopen landed the player
  on the other mod's settings.
- A mod whose assemblies the runtime cannot fully load is asked again on
  the next opening of the screen instead of being remembered as not
  hot-reloading for the rest of the session, and the memoized answers are
  read and filled under one lock.
- Editor and OS leftovers under a shipped mod content directory
  (`.DS_Store`, `Thumbs.db`, `*~`, `*.bak`, `*.orig`, `*.rej`, `*.swp`)
  no longer reach `dist/Wrench.zip`. Staging copied the whole directory,
  so a file no `git status` lists shipped inside the release package.
  The package a player extracts is now exactly the mod's own files.
- The .NET SDK that compiles the DLL is pinned to the 8.0 feature band
  (`global.json` rolled forward to any newer major, so two machines could
  build different bytes from the same source). A patch or feature update
  still rolls forward; a major no longer does.
- The DLL build maps its source paths out of the output
  (`ContinuousIntegrationBuild=true`), so the checkout's absolute directory
  no longer reaches the shipped binary.

### Removed

- An empty `Config/items.xml` placeholder no longer ships in the
  package. It patched nothing.

## [0.3.0] - 2026-09-28

Requires 7 Days to Die V3.2, the same as 0.2.0. Upgrade by replacing the
whole `Mods/Wrench` folder: no config migration, no new setting, and no
removed setting. Three files that loaded under 0.2.0 are refused under
0.3.0; each is named under **Fixed** with what to do about it.

### Fixed

- A setting key whose case does not match is now reported as an unknown
  key instead of applying the setting it only looks like. TOML keys are
  case sensitive, and `wrench set` still accepts a name typed in any case.
  A file that spelled a key with the wrong case set that setting from
  0.1.0 to 0.2.0; from 0.3.0 the key is unknown, is logged as unknown,
  and the default stands. Rename the key in the file to the spelling the
  key column uses.
- A third-party settings file whose bytes are not valid in the encoding
  it declares is reported unreadable instead of being read with the bad
  bytes replaced. Reading it lossily meant a later save wrote the
  replacement character over the original byte, so a file that has
  loaded is now refused rather than quietly altered. Re-save the file as
  UTF-8, which is what a mod's own reader accepts.
- A mod whose name holds a control character is skipped and logged. On
  Linux and macOS .NET reports only NUL and the separator as invalid in
  a file name, so such a name resolved to a real file whose name then
  reached the log and the reload marker, and a newline in either forged
  a log line of its own. Rename the mod's folder and its
  `Config/<Mod>.toml` to match.

### Added

- Every string the Mod Settings screen shows is now a key in
  `Config/Localization.csv`, so the screen can be translated. The English
  text is unchanged, and no existing key was renamed or removed.

### Compatibility

- No setting key was renamed or removed, no default changed, the
  `Config/<Mod>.toml` layout is the same, and the console commands
  (`wrench`, `wrench settings`, `wrench set <name> <value>`, `wrench
  reload`) take the same arguments and print the same reports. The three
  refusals above change what Wrench does with a file or a name that was
  wrong to begin with, which is why this is a minor release: a mod whose
  settings file, or whose folder name, no longer loads is described
  under **Fixed** rather than failing quietly.

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

- The settings file watch asked the disk three times per poll, once of
  them by opening the file, every quarter second for as long as the game
  ran. One metadata read now answers existence, write time and length.
- The offline TOML fuzz gate could not compile: it called
  `TomlEdit.TryParseRawValue` with a fourth argument the method has never
  taken, so the build failed and the gate never ran.
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
