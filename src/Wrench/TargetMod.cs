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
			string text;
			string error;
			if (!TryRead(out text, out error))
			{
				Text = null;
				Error = error;
				return;
			}
			Text = text;
			List<TomlSettings.DocEntry> entries;
			if (TomlSettings.TryReadDocument(Text, out entries, out error))
				Entries = entries;
			else
				Error = error;
		}

		/// <summary>
		/// Replaces one value in place and writes the file. On any failure
		/// nothing is written and the parsed state is unchanged.
		///
		/// The edit is spliced by byte offset into the parsed text, so it is
		/// applied to the file as it is *now*, never to the copy parsed at the
		/// last <see cref="Reload"/>: another writer (a config tool, the mod
		/// itself, a second game) can save in between, and stale offsets would
		/// land on a neighbouring key and then write the whole file back over
		/// that save. When the file has moved on, the key is located again by
		/// name; one that is gone or now ambiguous refuses the edit rather
		/// than guessing which span the row meant.
		/// </summary>
		public bool TrySave(TomlSettings.DocEntry entry, string newRaw, out string error)
		{
			string currentText;
			if (!TryRead(out currentText, out error))
				return Fail(error);
			if (currentText != Text)
			{
				Reload();
				TomlSettings.DocEntry fresh;
				if (!TryRelocate(entry, out fresh, out error))
					return Fail(error);
				entry = fresh;
			}

			string newText;
			if (!TomlEdit.TryReplaceValue(Text, entry, newRaw, out newText, out error))
				return Fail(error);
			try
			{
				File.WriteAllText(TomlPath, newText);
			}
			catch (Exception ex)
			{
				error = ex.Message;
				return Fail(error);
			}
			SaveState = ESaveState.Saved;
			SaveError = null;
			Reload();
			return true;
		}

		bool Fail(string message)
		{
			SaveState = ESaveState.SaveFailed;
			SaveError = message;
			return false;
		}

		/// <summary>
		/// The same key's span in the file as it stands now, taken from the
		/// re-read entries. Refuses when the file no longer parses, no longer
		/// carries the key, or carries it more than once: the row the edit
		/// came from is the only thing that knows which key was meant, and a
		/// wrong span is a wrong write.
		/// </summary>
		bool TryRelocate(TomlSettings.DocEntry stale, out TomlSettings.DocEntry found, out string error)
		{
			found = null;
			if (Entries == null)
			{
				error = Error;
				return false;
			}
			for (var i = 0; i < Entries.Count; i++)
			{
				if (Entries[i].Name != stale.Name)
					continue;
				if (found != null)
				{
					error = "'" + stale.Name + "' is in the file more than once now; "
						+ "reopen the screen and edit it there.";
					found = null;
					return false;
				}
				found = Entries[i];
			}
			if (found == null)
			{
				error = "'" + stale.Name + "' is no longer in the file; it changed outside Wrench.";
				return false;
			}
			error = null;
			return true;
		}

		bool TryRead(out string text, out string error)
		{
			try
			{
				text = File.ReadAllText(TomlPath);
				error = null;
				return true;
			}
			catch (Exception ex)
			{
				text = null;
				error = ex.Message;
				return false;
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
		///
		/// One assembly the runtime cannot fully load must not take the whole
		/// screen down: it only decides this mod's status line, and the other
		/// mods in the list still have settings to edit.
		/// </summary>
		static bool HasSettingsComponent(Mod mod)
		{
			if (mod.AllAssemblies == null)
				return false;
			foreach (var assembly in mod.AllAssemblies)
			{
				if (assembly == null)
					continue;
				Type[] types;
				try
				{
					types = assembly.GetTypes();
				}
				catch (ReflectionTypeLoadException ex)
				{
					// A dependency the runtime could not load hides some of the
					// types; the rest are still worth scanning.
					types = ex.Types;
				}
				catch (Exception)
				{
					continue;
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
