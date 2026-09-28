using HarmonyLib;
using System;
using System.Runtime.CompilerServices;
using System.Reflection;

[assembly: InternalsVisibleTo("WrenchPlaytest")]

namespace Wrench
{
	public class ModApi : IModApi
	{
		public const string LogPrefix = "[Wrench]";

		static bool updateHooked;

		public void InitMod(Mod _modInstance)
		{
			// Fast and defensive: log, never throw if recoverable. Fast
			// because the game waits here, defensive because the settings
			// and UI must work even if something below fails.
			Log.Out(ModApi.LogPrefix + " loading; settings are read from "
				+ ModSettings.RelativePath);
			try
			{
				ModSettings.Load(_modInstance);
			}
			catch (Exception ex)
			{
				// An exception out of here aborts the mod's load and lands in
				// the log as a bare stack trace from a load the operator did
				// not ask for. Named, it says which mod failed to read its
				// settings and leaves the rest of the mod working.
				Log.Error(ModApi.LogPrefix + " could not read " + ModSettings.RelativePath
					+ " at load: " + ex);
			}
			// Re-reads Config/Wrench.toml when it is saved, via the
			// engine's UnityUpdate event (client and dedicated) — no restart,
			// no Harmony patch.
			// Registered once per process: a second InitMod (a mod reloaded
			// on a long-running server) would otherwise leave the first
			// registration in the engine's handler list, so the file watch
			// would poll twice per frame with no unhook to remove it.
			if (!updateHooked)
			{
				ModEvents.UnityUpdate.RegisterHandler(OnUnityUpdate);
				updateHooked = true;
			}
			// Patches nothing today: the options tab is an XUi XML patch
			// (ADR 0002). When a patch does land, wrap it per-patch so one
			// target the game renamed cannot stop the mod from loading.
			new Harmony("com.ywy50.wrench")
				.PatchAll(Assembly.GetExecutingAssembly());
		}

		static void OnUnityUpdate(ref ModEvents.SUnityUpdateData data)
		{
			ModSettings.Poll();
		}
	}
}
