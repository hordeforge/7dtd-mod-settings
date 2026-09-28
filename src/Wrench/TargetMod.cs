using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;

namespace Wrench
{
	/// <summary>
	/// One installed mod that ships a <c>Config/&lt;Mod&gt;.toml</c>, as the
	/// Mod Settings screen sees it: the parsed document (or the parse error
	/// that makes it read-only), whether the mod hot-reloads a save (the
	/// Anvil settings component in any of its assemblies), and the outcome
	/// of the last save. The file itself is the whole integration surface
	/// (ADR 0001); no other file is ever kept, and a save only ever lands
	/// through a short-lived temp sibling of that same file.
	/// </summary>
	internal sealed class TargetMod
	{
		/// <summary>
		/// How often the in-place replace is retried, and how long it waits
		/// between tries. A target mod's own settings watch holds the file
		/// open for the few milliseconds it takes to read, and a replace
		/// needs delete access, so one attempt can lose to a poll that was
		/// never going to be there on the next one.
		/// </summary>
		const int ReplaceAttempts = 3;
		const int ReplaceRetryMilliseconds = 40;

		public enum ESaveState
		{
			None,
			/// <summary>Written; the reload log line not (yet) seen.</summary>
			Saved,
			/// <summary>Written and the mod logged the re-read.</summary>
			AppliedLive,
			/// <summary>Written, but no re-read line arrived in time.</summary>
			SaveUnconfirmed,
			SaveFailed,
		}

		public readonly Mod Mod;
		public readonly string TomlPath;
		/// <summary>The file's own name, safe to show and to match in a log line.</summary>
		public readonly string TomlFileName;
		/// <summary>The Anvil settings component was found, so a save applies without a restart.</summary>
		public readonly bool HotReloads;

		/// <summary>Last file text the entries were parsed from.</summary>
		public string Text { get; private set; }
		/// <summary>Null when the file is unreadable; see <see cref="Error"/>.</summary>
		public List<TomlSettings.DocEntry> Entries { get; private set; }
		public string Error { get; private set; }

		public ESaveState SaveState;
		public string SaveError;

		TargetMod(Mod mod, string tomlPath)
		{
			Mod = mod;
			TomlPath = tomlPath;
			TomlFileName = Path.GetFileName(tomlPath);
			HotReloads = CachedHasSettingsComponent(mod);
			Reload();
		}

		// Probing a mod walks every type every one of its assemblies declares,
		// and an installed mod's assemblies do not change while the game runs,
		// so the answer is paid once per mod rather than on every opening of
		// the screen. The only cost of being wrong about that is the live
		// reload label, as it is for the probe itself (ADR 0001).
		static readonly Dictionary<string, bool> hotReloadsByModPath =
			new Dictionary<string, bool>(StringComparer.Ordinal);

		static bool CachedHasSettingsComponent(Mod mod)
		{
			bool known;
			if (hotReloadsByModPath.TryGetValue(mod.Path, out known))
				return known;
			var found = HasSettingsComponent(mod);
			hotReloadsByModPath[mod.Path] = found;
			return found;
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
			get { return "reload Config/" + TomlFileName; }
		}

		public void Reload()
		{
			Entries = null;
			Error = null;
			string text;
			string error;
			if (!TryRead(out text, out _, out error))
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
		///
		/// The new text is written through a temporary file in the same
		/// directory and renamed over the destination, so a hot-reloading mod
		/// polling the file, or any other reader, sees the whole old text or
		/// the whole new one, never a half-written file.
		///
		/// The write is in the encoding the file is in right now, so every
		/// byte outside the edited value span survives, byte order mark
		/// included.
		/// </summary>
		public bool TrySave(TomlSettings.DocEntry entry, string newRaw, out string error)
		{
			string currentText;
			Encoding currentEncoding;
			if (!TryRead(out currentText, out currentEncoding, out error))
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
			List<TomlSettings.DocEntry> newEntries;
			if (!TomlEdit.TryReplaceValue(Text, Entries, entry, newRaw, out newText, out newEntries, out error))
				return Fail(error);
			if (!TryWrite(TomlPath, newText, currentEncoding, out error))
				return Fail(error);
			SaveState = ESaveState.Saved;
			SaveError = null;
			// The write put exactly the text the writer verified, and the
			// verified parse of it is already in hand: re-reading the file here
			// would only parse the same bytes a second time.
			Text = newText;
			Entries = newEntries;
			Error = null;
			return true;
		}

		/// <summary>
		/// Writes the file through a sibling temp file and an atomic replace.
		/// Writing in place truncates the target first, so a crash, a
		/// shutdown, or a full disk between the truncate and the last byte
		/// leaves the mod with a settings file it cannot read at all, or
		/// with none. The file is the whole integration surface (ADR 0001);
		/// the one outcome that must never happen is losing it.
		/// </summary>
		static bool TryWrite(string path, string text, Encoding encoding, out string error)
		{
			var temp = path + ".wrench-tmp";
			var files = ModFileSystem.Current;
			try
			{
				files.WriteAllText(temp, text, encoding);
				for (var attempt = 1; ; attempt++)
				{
					try
					{
						files.Replace(temp, path);
						break;
					}
					catch (NotSupportedException)
					{
						// A runtime with no atomic replace: the file goes away
						// for an instant instead of being half-written, which
						// is the closest this platform gets.
						files.Delete(path);
						files.Move(temp, path);
						break;
					}
					catch (IOException)
					{
						// The target's own settings watch holds the file for
						// the few milliseconds it takes to read it, and a
						// replace needs delete access. Retry: the reader is
						// gone before the next one starts.
						if (attempt >= ReplaceAttempts)
							throw;
						ModClock.Current.Sleep(ReplaceRetryMilliseconds);
					}
				}
			}
			catch (Exception ex)
			{
				TryDeleteTemp(temp);
				error = ex.Message;
				return false;
			}
			error = null;
			return true;
		}

		static void TryDeleteTemp(string temp)
		{
			try
			{
				ModFileSystem.Current.Delete(temp);
			}
			catch (Exception)
			{
				// A temp file nobody could delete is one stray file beside the
				// target, and the next save writes over the same name.
			}
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

		bool TryRead(out string text, out Encoding encoding, out string error)
		{
			try
			{
				var bytes = ModFileSystem.Current.ReadAllBytes(TomlPath);
				text = Decode(bytes, out encoding);
				error = null;
				return true;
			}
			catch (Exception ex)
			{
				text = null;
				encoding = new UTF8Encoding(false);
				error = ex.Message;
				return false;
			}
		}

		/// <summary>
		/// Decodes the file and reports the encoding it is in, byte order mark
		/// included, so a save can write the same one back. <c>File.ReadAllText</c>
		/// decodes a mark away and keeps no record of it, and a plain
		/// UTF-8 write then drops it: an edit that changed one value token
		/// would have silently changed the file's first three bytes too.
		/// Anything with no recognizable mark is decoded as UTF-8, which is
		/// what the file would be read as before; a file in some other
		/// encoding then fails the TOML parse and is listed unreadable
		/// rather than written back unreadable bytes.
		/// </summary>
		static string Decode(byte[] bytes, out Encoding encoding)
		{
			if (bytes.Length >= 3 && bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF)
			{
				encoding = new UTF8Encoding(true);
				return encoding.GetString(bytes, 3, bytes.Length - 3);
			}
			if (bytes.Length >= 2 && bytes[0] == 0xFF && bytes[1] == 0xFE)
			{
				encoding = Encoding.Unicode;
				return encoding.GetString(bytes, 2, bytes.Length - 2);
			}
			if (bytes.Length >= 2 && bytes[0] == 0xFE && bytes[1] == 0xFF)
			{
				encoding = Encoding.BigEndianUnicode;
				return encoding.GetString(bytes, 2, bytes.Length - 2);
			}
			encoding = new UTF8Encoding(false);
			return encoding.GetString(bytes);
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
					result.Add(new TargetMod(mod, tomlPath));
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
					// Null entries are the types whose dependencies could not
					// be loaded; the rest still answer the question.
					types = ex.Types;
				}
				catch (Exception)
				{
					Log.Warning(ModApi.LogPrefix + " could not inspect an assembly of "
						+ mod.Name + "; the mod is treated as not hot-reloading.");
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
