using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;

namespace Wrench
{
	/// <summary>
	/// Which installed mod a target came from, held as the two strings that
	/// survive the mod object the game handed over: its folder and the name
	/// its ModInfo carries.
	///
	/// The folder is the identity. Two installed mods can ship the same
	/// ModInfo name, so a screen that remembers the last selection by name
	/// can come back on a different mod's settings; a path is one mod's and
	/// no other's. It is a value, not the game's <c>Mod</c>, because the
	/// save path below it is driven offline (ADR 0001).
	/// </summary>
	internal readonly struct ModIdentity
	{
		/// <summary>The mod's own folder, or null when the target is not one.</summary>
		public readonly string Path;
		/// <summary>The name its ModInfo carries.</summary>
		public readonly string Name;

		public ModIdentity(string path, string name)
		{
			Path = path;
			Name = name;
		}
	}

	/// <summary>
	/// One installed mod that ships a <c>Config/&lt;Mod&gt;.toml</c>, as the
	/// Mod Settings screen sees it: the parsed document (or the parse error
	/// that makes it read-only), whether the mod hot-reloads a save (the
	/// Anvil settings component in any of its assemblies), and the outcome
	/// of the last save. The file itself is the whole integration surface
	/// (ADR 0001); no other file is ever kept, and a save only ever lands
	/// through a short-lived temp sibling of that same file.
	///
	/// Nothing here names a game type: what the mod is and where it is
	/// installed arrive as three strings, and finding the file and probing
	/// its assemblies is
	/// <see cref="TargetModDiscovery"/>'s work, on the game side. So the
	/// whole save path, from the read that locates the span to the replace
	/// that lands it, is the code a simulated run drives against its own
	/// clock and its own filesystem.
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
		public const int ReplaceAttempts = 3;
		public const int ReplaceRetryMilliseconds = 40;

		/// <summary>
		/// How often the splice is redone when the file changed underneath it
		/// between the read and the write. One program saving at a time is the
		/// normal case, so this bounds an in-flight clash, not a shared
		/// folder: see <see cref="TrySave"/>.
		/// </summary>
		public const int SpliceAttempts = 4;

		// A save is a read, a splice into what that read produced, and a
		// whole-file write. Two savers of one file that overlap anywhere in
		// that lose an edit: the second write carries the file as the first
		// read it, so whichever lands second undoes the other, and both
		// report success. The gate is keyed by path, so two mods are still
		// saved in parallel, and it is held around the whole
		// read-modify-write rather than around the write alone: a lock on the
		// write alone would not stop the two reads from racing.
		static readonly ConcurrentDictionary<string, object> saveGates =
			new ConcurrentDictionary<string, object>(StringComparer.Ordinal);

		// The staging file's name carries the writing process's id, so a
		// second writer of the same file (a second game, a second thread, a
		// second copy of the mod folder) stages under a name of its own. One
		// shared name corrupts both saves: the second writer to stage
		// truncates and rewrites the first's bytes, and the first's rename
		// then moves the *second* save's text into the destination, so the
		// first save reports success having written the other's text. The
		// gate above already serializes writers inside this process; the
		// process id is what separates the ones it cannot.
		static readonly int stagingOwner = StagingOwnerId();

		static int StagingOwnerId()
		{
			using (var process = Process.GetCurrentProcess())
				return process.Id;
		}

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

		/// <summary>The mod's own name, as its ModInfo spells it.</summary>
		public readonly string Name;
		/// <summary>The name to show a player.</summary>
		public readonly string DisplayName;
		/// <summary>
		/// The mod's own installed folder. Two installed mods can carry the
		/// same name, so this, not <see cref="Name"/>, is what tells one from
		/// another: a reopened screen keeps its selection by it, and a log
		/// line naming a mod names the file it wrote.
		/// </summary>
		public readonly string ModPath;
		public readonly string TomlPath;
		/// <summary>The file's own name, safe to show and to match in a log line.</summary>
		public readonly string TomlFileName;
		/// <summary>The Anvil settings component was found, so a save applies without a restart.</summary>
		public readonly bool HotReloads;
		/// <summary>Which installed mod this is; see <see cref="ModIdentity"/>.</summary>
		public readonly ModIdentity Mod;

		/// <summary>Last file text the entries were parsed from.</summary>
		public string Text { get; private set; }
		/// <summary>Null when the file is unreadable; see <see cref="Error"/>.</summary>
		public List<TomlSettings.DocEntry> Entries { get; private set; }
		public string Error { get; private set; }

		public ESaveState SaveState;
		public string SaveError;

		public TargetMod(string name, string displayName, string modPath, string tomlPath,
			bool hotReloads, ModIdentity mod = default(ModIdentity))
		{
			Name = name;
			DisplayName = displayName;
			ModPath = modPath;
			TomlPath = tomlPath;
			TomlFileName = Path.GetFileName(tomlPath);
			HotReloads = hotReloads;
			Mod = mod;
			Reload();
		}

		/// <summary>
		/// A target that was not discovered through the game, so only the file
		/// it edits is known. <paramref name="modPath"/> and
		/// <see cref="Mod"/> are the identity of an installed mod, and neither
		/// is a property of the file alone.
		/// </summary>
		public TargetMod(string name, string displayName, string tomlPath, bool hotReloads)
			: this(name, displayName, null, tomlPath, hotReloads)
		{
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
		///
		/// The whole read-modify-write runs under the file's save gate, and
		/// the file's signature is re-read just before the staging write: an
		/// outside writer that landed in between is spliced around rather
		/// than written over. That closes the window for a writer this
		/// process cannot lock against (a second game, a config tool) as far
		/// as the file's own signature can show it; two programs saving one
		/// file at the same instant are not made safe by it, and the last
		/// writer still wins.
		/// </summary>
		public bool TrySave(TomlSettings.DocEntry entry, string newRaw, out string error)
		{
			error = null;
			lock (saveGates.GetOrAdd(TomlPath, _ => new object()))
			{
				for (var attempt = 1; ; attempt++)
				{
					string currentText;
					Encoding currentEncoding;
					DateTime writeUtc;
					long length;
					string statError;
					if (!TryRead(out currentText, out currentEncoding, out error))
						return Fail(error);
					if (!TryStamp(out writeUtc, out length, out statError))
						return Fail(statError);
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
					if (!TomlEdit.TryReplaceValue(Text, Entries, entry, newRaw,
						out newText, out newEntries, out error))
						return Fail(error);
					if (StampMoved(writeUtc, length))
					{
						// The file moved on while this splice was being made,
						// so the text above describes a file that no longer
						// exists: staging it would put the other save back
						// where it was. Re-splice into the file as it is now.
						if (attempt >= SpliceAttempts)
							return Fail(TomlFileName + " is being written to by another "
								+ "program; the edit was not saved.");
						continue;
					}
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
			}
		}

		/// <summary>
		/// The file's write time and length, the pair every change of this
		/// file is recognised by elsewhere in the mod as well.
		/// </summary>
		bool TryStamp(out DateTime writeUtc, out long length, out string error)
		{
			error = null;
			try
			{
				writeUtc = ModFileSystem.Current.GetLastWriteTimeUtc(TomlPath);
				length = ModFileSystem.Current.GetLength(TomlPath);
				return true;
			}
			catch (Exception ex)
			{
				writeUtc = default(DateTime);
				length = -1;
				error = "could not stat " + TomlFileName + " (" + ex.Message + ").";
				return false;
			}
		}

		/// <summary>
		/// Whether the file's signature is no longer the one a splice was made
		/// against. A file that cannot be stat counts as moved: the retry's
		/// own read is what reports a file that is gone or unreadable, with
		/// the cause, rather than this one guessing it.
		/// </summary>
		bool StampMoved(DateTime writeUtc, long length)
		{
			DateTime nowUtc;
			long nowLength;
			string statError;
			if (!TryStamp(out nowUtc, out nowLength, out statError))
				return true;
			return nowUtc != writeUtc || nowLength != length;
		}

		/// <summary>
		/// Writes <paramref name="text"/> to <paramref name="path"/> through a
		/// sibling temp file and an atomic replace. Writing in place
		/// truncates the target first, so a crash, a shutdown, or a full disk
		/// between the truncate and the last byte leaves the mod with a
		/// settings file it cannot read at all, or with none. The file is the
		/// whole integration surface (ADR 0001); the one outcome that must
		/// never happen is losing it.
		/// </summary>
		static bool TryWrite(string path, string text, Encoding encoding, out string error)
		{
			var temp = path + ".wrench-tmp." + stagingOwner;
			var previous = path + ".wrench-prev";
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
						// is the closest this platform gets. It is moved aside
						// rather than deleted, and put back when the move that
						// replaces it fails: a delete leaves the old text only
						// in this process, and a move that fails after it has
						// lost the file.
						files.Delete(previous);
						files.Move(path, previous);
						try
						{
							files.Move(temp, path);
						}
						catch (Exception swap)
						{
							try
							{
								files.Move(previous, path);
							}
							catch (Exception restore)
							{
								// Both failures belong in the one message: the
								// file is still missing, and the text that
								// filled it is named.
								throw new IOException("the swap failed (" + swap.Message
									+ ") and the previous text could not be put back ("
									+ restore.Message + "); it is at " + previous + ".",
									swap);
							}
							throw;
						}
						files.Delete(previous);
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
				// The staging file is the only surviving copy of the new text
				// once the fallback above has deleted the destination and its
				// move failed, and a settings file the mod can no longer read
				// is the one outcome ADR 0001 forbids. Every other failure
				// leaves the destination in place, and the staging file beside
				// it is a stray the next save overwrites.
				if (!files.Exists(path))
				{
					error = ex.Message + " The new text is at " + temp + ".";
					return false;
				}
				TryDeleteTemp(temp);
				// Shown to a player on the status line, so it names the step
				// that failed, in the plainest words the exception allows; the
				// exception's own type and text follow for the detail.
				error = "the settings file could not be written: "
					+ ex.GetType().Name + ": " + ex.Message;
				// The old text left beside the target is the only copy of the
				// player's settings left, so the message has to name it.
				if (files.Exists(previous))
					error += " The previous text is at " + previous + ".";
				return false;
			}
			error = null;
			return true;
		}

		static void TryDeleteTemp(string tempPath)
		{
			try
			{
				ModFileSystem.Current.Delete(tempPath);
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
				// Through the seam, not straight at the disk: the same read has
				// to be drivable against a simulated filesystem, and a
				// hardwired reader here would hand a simulated save the real
				// file's text while its writes went to the simulation.
				text = ModFileSystem.Current.ReadAllText(TomlPath, out encoding);
				error = null;
				return true;
			}
			catch (Exception ex)
			{
				text = null;
				encoding = new UTF8Encoding(false);
				// The status line shows this to a player, so it says what
				// happened in the plainest words the exception allows; the
				// exception's own type and text follow for the detail.
				error = "the settings file could not be read: "
					+ ex.GetType().Name + ": " + ex.Message;
				return false;
			}
		}
	}
}
