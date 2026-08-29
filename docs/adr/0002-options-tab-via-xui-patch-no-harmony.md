# 0002. The options tab is an XUi XML patch, not a Harmony hook

Date: 2026-08-30

## Status

Accepted

## Context

The Mod Settings screen has to be reachable from the regular options
menu, in game (ESC → Options) and from the main menu. The layer rule
(docs/reference/agent-rules.md) demands the shallowest layer that works,
and a Harmony patch into the menu code is a layer deeper than XML.

Read with ilspycmd on the installed V3.2.0 `Assembly-CSharp`:

- The in-game Options button opens
  `XUiC_OptionsMenuNew.ParentSelector.WindowGroup`
  (`XUiC_InGameMenuWindow.BtnOptions_OnPressed`) — the same
  `optionsPaging` selector the main menu uses, on the primary UI.
- `XUiC_WindowSelector.OpenSelectedWindow` opens the window group named
  by the pressed tab button's view ID.

So the options menu is data-driven end to end: a tab is a
`pagingheader_button` in the `optionsPaging` window and a window group of
the same name.

## Decision

Two XPath patches in `Config/XUi_Menu/` are the whole integration:
`insertBefore` of one `pagingheader_button` (before the right paging
arrow) and `append` of one window group plus one window. No Harmony
patch, no supported-hook escalation.

The window's controller, `Wrench.XUiC_ModSettingsScreen`, subclasses the
game's public `XUiC_OptionsDialogBase`, inheriting the options-frame
behavior the vanilla pages get: selector selection on open, back/ESC via
`TryClose`, main-menu reopen when closed outside a world, and the
hovered-description panel (`options_descriptions` binds
`hovered_custom_attributes`, which falls back to the dialog controller's
own `CustomAttributes` — the hovered key's comment block is fed through
there).

## Consequences

- Layer 3 (ModAPI + XUi) holds; the Harmony `PatchAll` in `InitMod`
  still patches nothing.
- One engine-update risk surface: the `optionsPaging` table shape and
  `XUiC_OptionsDialogBase`'s members. Both are exercised by the
  `wrench-mod-settings` live suite, so a game update that moves them
  fails the suite rather than a player.
- An append/insert cannot collide with another mod editing the same
  table; two mods both appending tabs coexist.
- `make validate-xml` checks both patch targets against the installed
  game's `XUi_Menu` files after every update.
