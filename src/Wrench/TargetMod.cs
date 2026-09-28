using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
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
	///
	/// Nothing here names a game type: what the mod is and where it is
	/// installed arrive as four strings (its ModInfo name, the name to show a
	/// player, its own folder and the path resolved from the two) plus a
	/// yes/no, and finding the file and probing
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

		/// <summary>
		/// The suffix of the sibling the no-atomic-replace fallback moves the
		/// old text to while the staged text is moved into its place.
		/// </summary>
		public const string PreviousSuffix = ".wrench-prev";

		/// <summary>
		/// Puts a settings file back after a run was killed between the two
		/// moves of that fallback, which is the one window in a save where the
		/// destination does not exist: the old text is at its
		/// <see cref="PreviousSuffix"/> sibling and the new one at a staging
		/// file named for a process that is gone. Nothing after that reads
		/// either name, so the mod drops out of the screen for good and its
		/// settings are only reachable by hand.
		///
		/// Re-running is the whole of the fix, and this is what makes the
		/// second run converge: it acts only while the destination is missing,
		/// so a run after the one that recovered finds the file where it
		/// belongs and changes nothing. The text it puts back is the one the
		/// interrupted save was about to replace, so that save is still owed
		/// rather than half made.
		///
		/// What it cannot do is run beside a save of the same file. The
		/// no-atomic-replace fallback below leaves the destination missing on
		/// purpose, for the moment between the two moves of its swap, and
		/// that moment looks exactly like the crash this recovers from: a
		/// recovery landing inside it moves the old text back under the
		/// staged one, and a save whose own move into place then fails has
		/// neither the old text (consumed) nor the new (never moved), which
		/// is the one outcome this whole class exists to prevent. So the
		/// check and the move are taken under the file's save gate, the same
		/// one a save of it takes. Monitor is reentrant, so the save path's
		/// own call at the top of a save is taken under it again without
		/// deadlocking.
		/// </summary>
		public static bool RecoverInterruptedSave(string tomlPath)
		{
			lock (SaveGateFor(tomlPath))
			{
				var files = ModFileSystem.Current;
				if (files.Exists(tomlPath))
					return false;
				var previous = tomlPath + PreviousSuffix;
				if (!files.Exists(previous))
					return false;
				files.Move(previous, tomlPath);
				return true;
			}
		}

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

		// One gate object per settings file, so two mods are still saved in
		// parallel and everything that acts on one file takes the same lock:
		// the read-modify-write of a save, and the recovery of a save that was
		// killed mid-swap. GetOrAdd is atomic, so two threads arriving at a
		// path the table has not seen are handed the one object between them
		// rather than a gate each.
		static object SaveGateFor(string tomlPath)
		{
			return saveGates.GetOrAdd(tomlPath, _ => new object());
		}

		// The staging file's name carries the writing process's id, so a
		// second writer of the same file (a second game, a second thread, a
		// second copy of the mod folder) stages under a name of its own. One
		// shared name corrupts both saves: the second writer to stage
		// truncates and rewrites the first's bytes, and the first's rename
		// then moves the *second* save's text into the destination, so the
		// first save reports success having written the other's text. The
		// gate above already serializes writers inside this process; the
		// process id is what separates the ones it cannot.
		//
		// Settable, like the clock and the filesystem, because the id
		// reaches a simulated run's trace: left as the process id it made
		// two runs of one seed differ in the one value a trace is compared
		// on, and a difference there is either invisible or mistaken for a
		// real one. A simulated run puts an id of its own choosing there.
		public static int StagingOwner = StagingOwnerId();

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

		/// <summary>Last file text the entries were parsed from.</summary>
		public string Text { get; private set; }
		/// <summary>Null when the file is unreadable; see <see cref="Error"/>.</summary>
		public List<TomlSettings.DocEntry> Entries { get; private set; }
		public string Error { get; private set; }

		public ESaveState SaveState;
		public string SaveError;

		public TargetMod(string name, string displayName, string modPath, string tomlPath,
			bool hotReloads)
		{
			Name = name;
			DisplayName = displayName;
			ModPath = modPath;
			TomlPath = tomlPath;
			TomlFileName = Path.GetFileName(tomlPath);
			HotReloads = hotReloads;
			Reload();
		}

		/// <summary>
		/// Substring of the log line the settings component emits after
		/// re-reading a save. Component vintages phrase the line differently
		/// ("settings (reload Config/X.toml)" vs "settings from reload
		/// Config/X.toml:", proven live against AtomicDoomsday), so only the
		/// shared "reload Config/&lt;Mod&gt;.toml" part is matched.
		///
		/// The name in it is the one the mod's ModInfo carries, and two
		/// installed mods can carry the same one while their folders, and so
		/// their settings files, differ. The logged line names no folder, so
		/// the marker cannot separate them, and the screen has to know that
		/// before it waits on one.
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
		/// the file's signature is re-read inside the writer, once the new
		/// text is on the disk and before it takes the file's place: an
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
			lock (SaveGateFor(TomlPath))
			{
				// A save killed between the two moves of its swap left the file
				// at its sibling name, so this run is that save's retry and the
				// file it is about to splice has to be there. Nothing is logged
				// from here: this class names no game type, so the save path can
				// be driven offline, and the run that opens the screen says it.
				RecoverInterruptedSave(TomlPath);
				for (var attempt = 1; ; attempt++)
				{
					string currentText;
					Encoding currentEncoding;
					DateTime writeUtc;
					long length;
					string statError;
					if (!TryRead(out currentText, out currentEncoding, out error))
						return Fail(error);
					if (!TryStamp(TomlPath, out writeUtc, out length, out statError))
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
					// The file's signature is re-read inside the writer, between
					// the new text reaching the disk and taking the file's
					// place, which is the window another program's save can
					// land in. A file that moved on there is spliced around
					// rather than written over: this attempt has put nothing
					// in the file's place, so the next one starts from what the
					// other program left.
					bool moved;
					if (!TryWrite(TomlPath, newText, currentEncoding, writeUtc, length,
						out moved, out error))
						return Fail(error);
					if (moved)
					{
						if (attempt >= SpliceAttempts)
							return Fail(TomlFileName + " is being written to by another "
								+ "program; the edit was not saved.");
						continue;
					}
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
		/// file is recognised by elsewhere in the mod as well, read through
		/// the one metadata call the settings watch makes, so a file that
		/// cannot be stat is reported the way the watch reports it rather
		/// than by an exception caught here.
		/// </summary>
		static bool TryStamp(string path, out DateTime writeUtc, out long length, out string error)
		{
			writeUtc = default(DateTime);
			length = -1;
			// The seam's one metadata read, the same one the settings watch
			// asks for: two of them here would be two answers that can disagree.
			string ioError;
			if (ModFileSystem.Current.TryGetStamp(path, out writeUtc, out length, out ioError))
			{
				error = null;
				return true;
			}
			var name = Path.GetFileName(path);
			error = ioError == null
				? "could not stat " + name + " (it is no longer there)."
				: "could not stat " + name + " (" + ioError + ").";
			return false;
		}

		/// <summary>
		/// Whether the file's signature is no longer the one a splice was made
		/// against. A file that cannot be stat counts as moved: the retry's
		/// own read is what reports a file that is gone or unreadable, with
		/// the cause, rather than this one guessing it.
		/// </summary>
		static bool StampMoved(string path, DateTime writeUtc, long length)
		{
			DateTime nowUtc;
			long nowLength;
			string statError;
			if (!TryStamp(path, out nowUtc, out nowLength, out statError))
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
		///
		/// <paramref name="moved"/> says the file's signature was no longer the
		/// one the text was spliced against, so nothing was put in its place
		/// and the caller re-splices against what the other writer left. The
		/// check belongs here rather than at the call site because the staging
		/// write is itself part of the window: asked for before it, a writer
		/// that lands while the text is being written is written over.
		/// </summary>
		static bool TryWrite(string path, string text, Encoding encoding,
			DateTime writeUtc, long length, out bool moved, out string error)
		{
			moved = false;
			var temp = path + ".wrench-tmp." + StagingOwner;
			var previous = path + PreviousSuffix;
			var files = ModFileSystem.Current;
			try
			{
				files.WriteAllText(temp, text, encoding);
				if (StampMoved(path, writeUtc, length))
				{
					moved = true;
					TryDeleteTemp(temp);
					error = null;
					return true;
				}
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
