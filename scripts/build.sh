#!/usr/bin/env bash
# Stage the deployable modlet under dist/<Name>/. Compiles the C# DLL first
# when src/ exists (requires SEVEN_DAYS_TO_DIE_DIR via env or .local.env).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOD_NAME="Wrench"
OUT="$ROOT/dist/$MOD_NAME"
SRC="$ROOT/src/$MOD_NAME"

rm -rf "$OUT"
mkdir -p "$OUT"

if [[ -d "$SRC" ]]; then
	GAME_DIR="${SEVEN_DAYS_TO_DIE_DIR:-}"
	if [[ -z "$GAME_DIR" && -f "$ROOT/.local.env" ]]; then
		# The ignored file is the documented machine-local game reference.
		set -a
		# shellcheck disable=SC1090,SC1091
		source "$ROOT/.local.env"
		set +a
		GAME_DIR="${SEVEN_DAYS_TO_DIE_DIR:-}"
	fi
	if [[ -z "$GAME_DIR" ]]; then
		echo "ERROR: set SEVEN_DAYS_TO_DIE_DIR or create .local.env with the client game-install directory before building." >&2
		exit 1
	fi
	MANAGED="$GAME_DIR/7DaysToDie_Data/Managed"
	HARMONY="$GAME_DIR/Mods/0_TFP_Harmony/0Harmony.dll"
	[[ -f "$MANAGED/Assembly-CSharp.dll" ]] || { echo "ERROR: Assembly-CSharp.dll not found under $MANAGED." >&2; exit 1; }
	[[ -f "$HARMONY" ]] || { echo "ERROR: stock 0_TFP_Harmony/0Harmony.dll not found in the game install." >&2; exit 1; }
	command -v dotnet >/dev/null 2>&1 || { echo "ERROR: dotnet not found; required to build the net48 mod DLL." >&2; exit 1; }
	dotnet build "$SRC/$MOD_NAME.csproj" -c Release -o "$OUT" \
		-p:GameManagedDir="$MANAGED" -p:HarmonyPath="$HARMONY"
fi

cp "$ROOT/ModInfo.xml" "$OUT/ModInfo.xml"
# the player-facing release readme (game version, EAC, Harmony, install)
cp "$ROOT/README.txt" "$OUT/README.txt"
# Localization ships inside Config/: the engine reads a mod's localization
# only from <mod>/Config/Localization.csv (ModManager passes mod.Path +
# "/Config" to Localization.LoadPatchDictionaries).
for entry in Config Prefabs Resources UIAtlases WebMod; do
	if [[ -e "$ROOT/$entry" ]]; then
		cp -R "$ROOT/$entry" "$OUT/$entry"
	fi
done

echo "OK -> $OUT"
