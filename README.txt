Wrench (Mod Settings) 0.1.0.0

7 DAYS TO DIE V3.2

INSTALL

Extract this folder so ModInfo.xml is located at:

  7 Days To Die/Mods/Wrench/ModInfo.xml

For a dedicated server, install the same complete folder in the server's
Mods directory. XML-only mods push config to joining clients; a mod DLL or
custom assets must also be installed on every player client.

REQUIREMENTS

Keep the stock 0_TFP_Harmony mod installed. Do not include another Harmony
copy in this folder. If this mod ships a DLL, disable Easy Anti-Cheat on
client and server.

CONTENT

Adds a Mod Settings screen to the in-game options menu, listing every installed mod that ships a Config/<Mod>.toml settings file and letting the player view and edit those settings from the UI. Edits are written back in place to the mod's own TOML; mods built on Anvil's settings component apply them live through their existing hot-reload watch, with no coupling between this mod and theirs.

TROUBLESHOOTING

After startup, check the game log for "Loaded Mod: Wrench" (and the
[Wrench] init lines if this mod ships a DLL). For XML or Harmony
errors, remove the mod, confirm the game starts, then restore the complete
folder. Client and server must use the same mod version in multiplayer.
