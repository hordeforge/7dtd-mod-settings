using System;
using System.Collections.Generic;
using System.Reflection;

namespace Wrench
{
	/// <summary>
	/// Finding the mods the Mod Settings screen lists, and deciding which of
	/// them hot-reload a save. Both answers come from the game (the loaded
	/// mod list, a mod's assemblies) and neither is a decision the save path
	/// makes, so they live here rather than in <see cref="TargetMod"/>: what
	/// comes back is a mod's name, a path and a yes/no, and everything past
	/// that is drivable without the game.
	/// </summary>
	internal static class TargetModDiscovery
	{
		// Probing a mod walks every type every one of its assemblies declares,
		// and an installed mod's assemblies do not change while the game runs,
		// so the answer is paid once per mod rather than on every opening of
		// the screen. The only cost of being wrong about that is the live
		// reload label, as it is for the probe itself (ADR 0001).
		//
		// The table is static state shared by every caller, and the screen is
		// not the only one that can reach it: the lookup and the fill are one
		// check-then-act, so two threads discovering at once would both
		// probe and then both write the same dictionary, which is what
		// corrupts it. A Dictionary is not safe to read while another thread
		// writes it, and the screen is opened from the Unity thread while a
		// dedicated server's telnet thread can discover a mod of its own. One
		// lock around the whole sequence, with the probe inside it, so a miss
		// is filled before the next lookup sees it.
		//
		// Only a conclusive probe is kept: an assembly the runtime could not
		// enumerate, or enumerates only in part, may hide the component, so
		// its "no" is an absence of evidence and memoizing it would fix a
		// wrong live-reload label for the rest of the session.
		static readonly Dictionary<string, bool> hotReloadsByModPath =
			new Dictionary<string, bool>(StringComparer.Ordinal);
		static readonly object hotReloadsGate = new object();

		public static bool CachedHasSettingsComponent(Mod mod)
		{
			lock (hotReloadsGate)
			{
				bool known;
				if (hotReloadsByModPath.TryGetValue(mod.Path, out known))
					return known;
				bool definitive;
				var found = HasSettingsComponent(mod, out definitive);
				// An assembly the runtime could not fully load leaves the
				// answer unknown rather than no. Caching that would pin the
				// mod to "restart required" for the rest of the session over
				// a load failure that may never happen again, so it is asked
				// again on the next opening.
				if (definitive)
					hotReloadsByModPath[mod.Path] = found;
				return found;
			}
		}

		/// <summary>Every loaded mod with a Config/&lt;Mod&gt;.toml, load order preserved.</summary>
		public static List<TargetMod> Discover()
		{
			var result = new List<TargetMod>();
			foreach (var mod in ModManager.GetLoadedMods())
			{
				if (mod == null || string.IsNullOrEmpty(mod.Path))
					continue;
				// The mod's name is its own ModInfo's, so the file it points
				// at is resolved, never concatenated: a name carrying a
				// directory part would make this screen read, and its save
				// write, outside the mod folder.
				string tomlPath;
				string error;
				if (!ModTomlPath.TryResolve(mod.Path, mod.Name, out tomlPath, out error))
				{
					Log.Warning(ModApi.LogPrefix + " skipped " + mod.Name + " (" + error + ")");
					continue;
				}
				if (!ModFileSystem.Current.Exists(tomlPath))
					continue;
				try
				{
					result.Add(new TargetMod(mod.Name, mod.DisplayName, mod.Path, tomlPath,
						CachedHasSettingsComponent(mod),
						new ModIdentity(mod.Path, mod.Name)));
				}
				catch (Exception ex)
				{
					// One mod whose DLLs cannot be inspected must not take the
					// whole screen down; the rest stay editable, and the mod
					// that was dropped says so in the log.
					Log.Warning(ModApi.LogPrefix + " skipped " + mod.Name
						+ " (" + tomlPath + "): " + ex.Message);
				}
			}
			return result;
		}

		/// <summary>
		/// True when any of the mod's assemblies carries the Anvil settings
		/// component: a ModSettings type with the FilePollIntervalSeconds
		/// constant, i.e. the debounced save watch that re-reads the file.
		/// Matched by name because the component is another mod's type
		/// (ADR 0001: no shared assembly). A rename upstream can only cost
		/// the live-reload label and the applied-live status, never a
		/// wrong write, so the heuristic is safe to keep.
		///
		/// One assembly the runtime cannot fully load must not take the whole
		/// screen down: it only decides this mod's status line, and the other
		/// mods in the list still have settings to edit.
		/// <paramref name="definitive"/> says whether every assembly was fully
		/// inspected. It is not when one of them could not be enumerated, or
		/// enumerated only in part: an unread type may be the component, so
		/// the answer is then "not found in what was looked at" and that "no"
		/// is reported for this opening and left unmemoized rather than cached
		/// as the mod's answer, which would label a hot-reloading mod
		/// restart-only for the rest of the session over a type that would not
		/// load once.
		/// </summary>
		public static bool HasSettingsComponent(Mod mod, out bool definitive)
		{
			definitive = false;
			if (mod.AllAssemblies == null)
			{
				definitive = false;
				return false;
			}
			var complete = true;
			var found = false;
			foreach (var assembly in mod.AllAssemblies)
			{
				if (assembly == null)
				{
					complete = false;
					continue;
				}
				Type[] types;
				try
				{
					types = assembly.GetTypes();
				}
				catch (ReflectionTypeLoadException ex)
				{
					// Null entries are the types whose dependencies could not
					// be loaded; the rest still answer the question, and a type
					// that is missing may be the one that was being asked
					// about, so the answer stops here.
					types = ex.Types;
					complete = false;
					if (types == null)
						continue;
				}
				catch (Exception ex)
				{
					// A partial negative is not a negative: this mod may well
					// carry the component in an assembly that would not load.
					// The label costs the player one status line, a wrong one
					// costs them the truth for the rest of the session.
					definitive = false;
					Log.Warning(ModApi.LogPrefix + " could not inspect an assembly of "
						+ mod.Name + " (" + ex.Message + "); the mod is reported as "
						+ "not hot-reloading until an inspection succeeds.");
					complete = false;
					continue;
				}
				foreach (var type in types)
				{
					if (type == null)
					{
						complete = false;
						continue;
					}
					if (type.Name != "ModSettings")
						continue;
					if (type.GetField("FilePollIntervalSeconds",
						BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static) != null)
					{
						found = true;
						break;
					}
				}
				if (found)
					break;
			}
			if (complete)
				definitive = true;
			return found;
		}
	}
}
