# TODO — Wrench (Mod Settings)

Task queue. Claim a task by changing `[ ]` to `[-]` with
`in progress — <agent>, YYYY-MM-DD; session: <id>` (see AGENTS.md); mark it
`[x]` the moment it completes. Next task = first unchecked item under the
earliest unfinished section.

## Purpose

Adds a Mod Settings screen to the in-game options menu, listing every installed mod that ships a Config/<Mod>.toml settings file and letting the player view and edit those settings from the UI. Edits are written back in place to the mod's own TOML; mods built on Anvil's settings component apply them live through their existing hot-reload watch, with no coupling between this mod and theirs.

## Design

- [ ] Break the purpose above into concrete gameplay decisions in
      `docs/design.md` (dated `Decided:` entries); raise open questions for
      the user instead of inventing answers.

## Implementation

- [ ] (add tasks as the design firms up)

## Testing

- [ ] Keep `make test` and `make lint-shell` green on every change.
- [ ] First in-game validation: `make build`, deploy per
      `docs/reference/environment.md`, verify the log is clean of XPath
      errors AND the change is visible in game.

## Open questions

- (none yet)
