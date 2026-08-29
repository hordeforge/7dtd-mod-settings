using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;

namespace Wrench
{
	/// <summary>
	/// One installed mod that ships a <c>Config/&lt;Mod&gt;.toml</c>, as the
	/// Mod Settings screen sees it: the parsed document (or the parse error
	/// that makes it read-only), whether the mod hot-reloads a save (the
	/// Anvil settings component in any of its assemblies), and the outcome
	/// of the last save. The file itself is the whole integration surface
	/// (ADR 0001); nothing outside that one file is ever written.
	/// </summary>
	internal sealed class TargetMod
	{
		public enum ESaveState
		{
			None,
			/// <summary>Written; the reload log line not (yet) seen.</summary>
			Saved,
			/// <summary>Written and the mod logged the re-read.</summary>
			AppliedLive,
			SaveFailed,
		}

		public readonly Mod Mod;
		public readonly string TomlPath;
		/// <summary>The Anvil settings component was found, so a save applies without a restart.</summary>
		public readonly bool HotReloads;

		/// <summary>Last file text the entries were parsed from.</summary>
		public string Text { get; private set; }
		/// <summary>Null when the file is unreadable; see <see cref="Error"/>.</summary>
		public List<TomlSettings.DocEntry> Entries { get; private set; }
		public string Error { get; private set; }

		public ESaveState SaveState;
		public string SaveError;

		TargetMod(Mod mod)
		{
			Mod = mod;
			TomlPath = Path.Combine(mod.Path, "Config", mod.Name + ".toml");
			HotReloads = HasSettingsComponent(mod);
			Reload();
		}

		/// <summary>
		/// Substring of the log line the settings component emits after
		/// re-reading a save. Component vintages phrase the line differently
		/// ("settings (reload Config/X.toml)" vs "settings from reload
		/// Config/X.toml:", proven live against AtomicDoomsday), so only the
		/// shared "reload Config/&lt;Mod&gt;.toml" part is matched.
		/// </summary>
		public string ReloadLogMarker
		{
			get { return "reload Config/" + Mod.Name + ".toml"; }
		}

		public void Reload()
		{
			Entries = null;
			Error = null;
			try
			{
				Text = File.ReadAllText(TomlPath);
			}
			catch (Exception ex)
			{
				Text = null;
				Error = ex.Message;
				return;
			}
			List<TomlSettings.DocEntry> entries;
			string error;
			if (TomlSettings.TryReadDocument(Text, out entries, out error))
				Entries = entries;
			else
				Error = error;
		}

		/// <summary>
		/// Replaces one value in place and writes the file. On any failure
		/// nothing is written and the parsed state is unchanged.
		/// </summary>
		public bool TrySave(TomlSettings.DocEntry entry, string newRaw, out string error)
		{
			string newText;
			if (!TomlEdit.TryReplaceValue(Text, entry, newRaw, out newText, out error))
			{
				SaveState = ESaveState.SaveFailed;
				SaveError = error;
				return false;
			}
			try
			{
				File.WriteAllText(TomlPath, newText);
			}
			catch (Exception ex)
			{
				error = ex.Message;
				SaveState = ESaveState.SaveFailed;
				SaveError = error;
				return false;
			}
			SaveState = ESaveState.Saved;
			SaveError = null;
			Reload();
			return true;
		}

		/// <summary>Every loaded mod with a Config/&lt;Mod&gt;.toml, load order preserved.</summary>
		public static List<TargetMod> Discover()
		{
			var result = new List<TargetMod>();
			foreach (var mod in ModManager.GetLoadedMods())
			{
				if (mod == null || string.IsNullOrEmpty(mod.Path))
					continue;
				if (!File.Exists(Path.Combine(mod.Path, "Config", mod.Name + ".toml")))
					continue;
				result.Add(new TargetMod(mod));
			}
			return result;
		}

		/// <summary>
		/// True when any of the mod's assemblies carries the Anvil settings
		/// component: a ModSettings type with the FilePollIntervalSeconds
		/// constant, i.e. the debounced save watch that re-reads the file.
		/// </summary>
		static bool HasSettingsComponent(Mod mod)
		{
			foreach (var assembly in mod.AllAssemblies)
			{
				Type[] types;
				try
				{
					types = assembly.GetTypes();
				}
				catch (ReflectionTypeLoadException ex)
				{
					types = ex.Types;
				}
				foreach (var type in types)
				{
					if (type == null || type.Name != "ModSettings")
						continue;
					if (type.GetField("FilePollIntervalSeconds",
						BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static) != null)
						return true;
				}
			}
			return false;
		}
	}
}
