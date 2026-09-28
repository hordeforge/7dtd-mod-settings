using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Wrench;

/// <summary>
/// A clock the scenario owns. The same decisions are made on it as on the
/// game's <see cref="StopwatchClock"/>, without spending the seconds they
/// stand for, and a wait is observable here where the production one is
/// invisible: a replace that had to retry shows up as elapsed time.
/// </summary>
sealed class VirtualClock : IMonotonicClock
{
	public double NowSeconds { get; private set; }
	public int Sleeps { get; private set; }
	public double SleptMilliseconds { get; private set; }

	public void Advance(double seconds)
	{
		NowSeconds += seconds;
	}

	public void Sleep(int milliseconds)
	{
		Sleeps++;
		SleptMilliseconds += milliseconds;
		Advance(milliseconds / 1000d);
	}
}

/// <summary>
/// The filesystem a simulated run saves into: no disk, and every fault the
/// save path can meet offered on demand rather than waited for. A replace
/// lost to another reader, a write that fails before it lands, a read that
/// fails, a runtime with no atomic replace: the same faults the game
/// produces, chosen by the run's seed rather than by timing.
/// </summary>
sealed class MemoryFileSystem : IFileSystem
{
	/// <summary>The virtual mtime a file written at t=0 answers with.</summary>
	static readonly DateTime Epoch = new DateTime(2026, 1, 1, 0, 0, 0, DateTimeKind.Utc);

	readonly Dictionary<string, byte[]> contents = new Dictionary<string, byte[]>(StringComparer.Ordinal);
	readonly SortedSet<string> names = new SortedSet<string>(StringComparer.Ordinal);
	readonly VirtualClock clock;

	public int Replaces { get; private set; }
	public int Reads { get; private set; }
	public int Writes { get; private set; }
	public int Moves { get; private set; }
	/// <summary>Replaces that threw because another reader held the file.</summary>
	public int ReplacesLostToReader { get; private set; }

	/// <summary>Replaces still to be lost to a reader.</summary>
	public int PendingReaderContention;
	/// <summary>Replaces still to be answered with no atomic replace.</summary>
	public int PendingNoAtomicReplace;
	/// <summary>Writes still to be failed before anything is stored.</summary>
	public int PendingWriteFaults;
	/// <summary>Reads still to be failed.</summary>
	public int PendingReadFaults;
	/// <summary>Staging writes still to be raced by an outside writer.</summary>
	public int PendingMidSaveWrites;
	/// <summary>The file that outside writer saves to.</summary>
	public string RacingPath;

	public MemoryFileSystem(VirtualClock clock)
	{
		this.clock = clock;
	}

	/// <summary>Puts a file there as an external writer would: whole bytes.</summary>
	public void Seed(string path, string text, Encoding encoding)
	{
		Store(path, encoding, text);
	}

	/// <summary>Whether anything is there under that name.</summary>
	public bool Has(string path)
	{
		return contents.ContainsKey(path);
	}

	/// <summary>
	/// What the file holds, as the scenario itself looks at it. The observer
	/// is not the system under test, so this read takes no fault and is not
	/// counted: an injected fault belongs to the save path, not to the check
	/// that the save path left the file whole.
	/// </summary>
	public string Peek(string path)
	{
		if (!contents.ContainsKey(path))
			return "";
		var bytes = contents[path];
		int preambleLength;
		var encoding = TomlFile.DetectEncoding(bytes, out preambleLength);
		return encoding.GetString(bytes, preambleLength, bytes.Length - preambleLength);
	}

	/// <summary>Names present, ordered, so a trace never depends on a hash.</summary>
	public string Listing()
	{
		return string.Join(",", names);
	}

	/// <summary>
	/// Names beginning with the prefix, ordered. A save stages under a name
	/// carrying its writing process's id, so the leftover check is by
	/// prefix and not against one name.
	/// </summary>
	public List<string> NamesStartingWith(string prefix)
	{
		var found = new List<string>();
		foreach (var name in names)
			if (name.StartsWith(prefix, StringComparison.Ordinal))
				found.Add(name);
		return found;
	}

	public bool Exists(string path)
	{
		return contents.ContainsKey(path);
	}

	public DateTime GetLastWriteTimeUtc(string path)
	{
		Require(path);
		return Epoch.AddSeconds(clock.NowSeconds);
	}

	public long GetLength(string path)
	{
		Require(path);
		return contents[path].Length;
	}

	public string ReadAllText(string path)
	{
		Encoding encoding;
		return ReadAllText(path, out encoding);
	}

	public byte[] ReadAllBytes(string path)
	{
		Require(path);
		var bytes = contents[path];
		var copy = new byte[bytes.Length];
		Buffer.BlockCopy(bytes, 0, copy, 0, bytes.Length);
		return copy;
	}

	public string ReadAllText(string path, out Encoding encoding)
	{
		Require(path);
		Reads++;
		if (PendingReadFaults > 0)
		{
			PendingReadFaults--;
			throw new IOException("injected read fault on " + path);
		}
		var bytes = contents[path];
		int preambleLength;
		encoding = TomlFile.DetectEncoding(bytes, out preambleLength);
		return encoding.GetString(bytes, preambleLength, bytes.Length - preambleLength);
	}

	public void WriteAllText(string path, string text, Encoding encoding)
	{
		Writes++;
		if (PendingWriteFaults > 0)
		{
			PendingWriteFaults--;
			throw new IOException("injected write fault on " + path);
		}
		// A write lands whole or not at all, which is what the staging file
		// buys; a fault throws before anything is stored.
		if (PendingMidSaveWrites > 0)
		{
			PendingMidSaveWrites--;
			// Another program saves the file in the window between this
			// save's read and this staging write, so the text about to be
			// staged describes a file that no longer exists. Nothing
			// reports the save but its bytes.
			Seed(RacingPath, Peek(RacingPath) + OtherWriterLine,
				new UTF8Encoding(false));
		}
		Store(path, encoding, text);
	}

	public void Replace(string sourcePath, string destinationPath)
	{
		Require(sourcePath);
		Replaces++;
		if (PendingNoAtomicReplace > 0)
		{
			PendingNoAtomicReplace--;
			throw new NotSupportedException("injected: no atomic replace here");
		}
		if (PendingReaderContention > 0)
		{
			PendingReaderContention--;
			ReplacesLostToReader++;
			throw new IOException("injected: another reader holds " + destinationPath);
		}
		Move(sourcePath, destinationPath);
	}

	public void Move(string sourcePath, string destinationPath)
	{
		Require(sourcePath);
		Moves++;
		var bytes = contents[sourcePath];
		contents.Remove(sourcePath);
		names.Remove(sourcePath);
		contents[destinationPath] = bytes;
		names.Add(destinationPath);
	}

	public void Delete(string path)
	{
		contents.Remove(path);
		names.Remove(path);
	}

	void Store(string path, Encoding encoding, string text)
	{
		var preamble = encoding.GetPreamble();
		var body = encoding.GetBytes(text);
		var bytes = new byte[preamble.Length + body.Length];
		Buffer.BlockCopy(preamble, 0, bytes, 0, preamble.Length);
		Buffer.BlockCopy(body, 0, bytes, preamble.Length, body.Length);
		contents[path] = bytes;
		names.Add(path);
	}

	void Require(string path)
	{
		if (!contents.ContainsKey(path))
			throw new FileNotFoundException("no such file on the simulated disk", path);
	}
}

/// <summary>
/// One seeded run of the save path against a virtual clock and an in-memory
/// disk, with faults injected at the points the game produces them.
///
/// The run is a function of its seed and nothing else: the same seed draws
/// the same faults, makes the same edits in the same order, and prints the
/// same trace, so a failure replays from the seed printed beside it. The
/// invariants are checked after every step, not at the end, because the
/// window they cover (a read of the file, a staged write, a replace, a retry
/// between them) is exactly the window a torn save would live in.
/// </summary>
static class Simulation
{
	/// <summary>The seed whose trace the gate prints, to replay from.</summary>
	public const int Seed = 20260928;
	/// <summary>How many seeds the gate walks.</summary>
	public const int SeedCount = 32;
	/// <summary>How many edits one seed makes.</summary>
	public const int StepsPerSeed = 24;

	const string ModPath = "/sim/Mods/Example";
	const string TomlPath = "/sim/Mods/Example/Config/Example.toml";
	/// <summary>Every name a save stages under, whatever process staged it.</summary>
	const string TempPrefix = TomlPath + ".wrench-tmp";
	const string CountKey = "Count";

	const string Pristine =
		"# Rounds per raid.\n" +
		"Count = 12\n" +
		"Chance = 0.001\n" +
		"Label = \"hi\"\n";

	/// <summary>What the outside writer's save leaves behind.</summary>
	const string OtherWriterLine = "# written by another program\n";

	/// <summary>Runs one seed and returns its trace; throws on a broken invariant.</summary>
	public static string Run(int seed)
	{
		var rng = new Rng(seed);
		var clock = new VirtualClock();
		var files = new MemoryFileSystem(clock);
		files.Seed(TomlPath, Pristine, new UTF8Encoding(false));

		// The seams, and only the seams: everything the run does from here is
		// the code the game runs.
		var savedFiles = ModFileSystem.Current;
		var savedClock = ModClock.Current;
		ModFileSystem.Current = files;
		ModClock.Current = clock;
		var trace = new StringBuilder();
		trace.Append("seed ").Append(seed).Append('\n');
		try
		{
			var target = new TargetMod("Example", "Example", ModPath,
				TomlPath, true);
			CheckInvariants(files, clock, target, 0);
			for (var step = 1; step <= StepsPerSeed; step++)
			{
				clock.Advance(0.25d);
				Step(files, clock, target, rng, step, trace);
				CheckInvariants(files, clock, target, step);
			}
			trace.Append("files ").Append(files.Listing()).Append('\n');
			trace.Append("reads ").Append(files.Reads)
				.Append(" writes ").Append(files.Writes)
				.Append(" replaces ").Append(files.Replaces)
				.Append(" lost ").Append(files.ReplacesLostToReader)
				.Append(" moves ").Append(files.Moves)
				.Append(" sleeps ").Append(clock.Sleeps)
				.Append(" slept ").Append(clock.SleptMilliseconds.ToString("0.###")).Append("ms")
				.Append(" at ").Append(clock.NowSeconds.ToString("0.###")).Append('\n');
			return trace.ToString();
		}
		finally
		{
			ModFileSystem.Current = savedFiles;
			ModClock.Current = savedClock;
		}
	}

	/// <summary>
	/// One run in which another program saves the file in the window between
	/// this save's read and its staging write: the interleaving two game
	/// processes on one mod folder can reach, and the one a config tool in
	/// the player's editor reaches. The two saves are independent, so the
	/// file has to end up holding both. A save that staged its own
	/// whole-file copy of what it read would report success having written
	/// the other program's save back where it was.
	/// </summary>
	public static string RunMidSaveRace()
	{
		var clock = new VirtualClock();
		var files = new MemoryFileSystem(clock);
		files.Seed(TomlPath, Pristine, new UTF8Encoding(false));

		var savedFiles = ModFileSystem.Current;
		var savedClock = ModClock.Current;
		ModFileSystem.Current = files;
		ModClock.Current = clock;
		try
		{
			var target = new TargetMod("Example", "Example", ModPath,
				TomlPath, true);
			var entry = FindCount(target);
			Check(entry != null, "the fixture has " + CountKey + " to edit");
			files.RacingPath = TomlPath;
			files.PendingMidSaveWrites = 1;

			string error;
			var saved = target.TrySave(entry, "77", out error);
			Check(saved, "the save reported failure: " + error);

			var text = files.Peek(TomlPath);
			Check(text.Contains(OtherWriterLine.TrimEnd('\n')),
				"the save wrote its stale copy over the other program's save: " + text);
			Check(text.Contains(CountKey + " = 77"),
				"the save did not land its own value: " + text);
			Check(files.NamesStartingWith(TempPrefix).Count == 0,
				"a staging file outlived the save that staged it");
			return "mid-save race: " + text.Replace("\n", " / ") + "\n";
		}
		finally
		{
			ModFileSystem.Current = savedFiles;
			ModClock.Current = savedClock;
		}
	}

	// One step: a fault draw, an edit, and whatever the save makes of it. The
	// faults come from the seed, so a seed that loses a replace twice walks
	// the retry and a seed that hits the write fault walks the failure path,
	// and both replay from the seed alone.
	static void Step(MemoryFileSystem files, VirtualClock clock, TargetMod target,
		Rng rng, int step, StringBuilder trace)
	{
		files.PendingReaderContention = rng.Next(3);
		files.PendingWriteFaults = rng.Next(8) == 0 ? 1 : 0;
		files.PendingReadFaults = rng.Next(8) == 0 ? 1 : 0;
		files.PendingNoAtomicReplace = rng.Next(16) == 0 ? 1 : 0;

		// Every fourth step another writer gets in first, so the span the row
		// was built from is stale and the key has to be located again.
		if (step % 4 == 0)
		{
			var current = Read(files);
			files.Seed(TomlPath, current.TrimEnd('\n') + "\n", new UTF8Encoding(false));
			trace.Append("step ").Append(step).Append(" external write\n");
		}

		var entry = FindCount(target);
		if (entry == null)
		{
			trace.Append("step ").Append(step).Append(" ").Append(CountKey)
				.Append(" is gone; nothing to edit\n");
			return;
		}

		var newRaw = (12 + rng.Next(100)).ToString();
		var beforeSave = Read(files);
		var lostBefore = files.ReplacesLostToReader;
		var sleptBefore = clock.Sleeps;
		string error;
		var saved = target.TrySave(entry, newRaw, out error);
		var lost = files.ReplacesLostToReader - lostBefore;
		var slept = clock.Sleeps - sleptBefore;

		trace.Append("step ").Append(step)
			.Append(' ').Append(CountKey).Append(" -> ").Append(newRaw)
			.Append(saved ? " saved" : " failed: " + error)
			.Append(" state ").Append(target.SaveState)
			.Append(" lost ").Append(lost)
			.Append(" slept ").Append(slept).Append('\n');

		// A save that reported success must have landed exactly the text it
		// now shows; a save that reported failure must have changed nothing.
		if (saved)
			Check(Read(files) == target.Text,
				"step " + step + ": a saved file is not the text the target now holds");
		else
			Check(Read(files) == beforeSave,
				"step " + step + ": a failed save changed the file");
		// One wait per lost replace, and no wait at all when none was lost:
		// the retry is the only thing that sleeps, and it sleeps on the
		// injected clock.
		Check(lost <= TargetMod.ReplaceAttempts,
			"step " + step + ": a replace was retried past the attempt limit");
		Check(slept == lost,
			"step " + step + ": " + lost + " lost replaces waited " + slept + " times");
	}

	static TomlSettings.DocEntry FindCount(TargetMod target)
	{
		if (target.Entries == null)
			return null;
		for (var i = 0; i < target.Entries.Count; i++)
		{
			if (target.Entries[i].Name == CountKey)
				return target.Entries[i];
		}
		return null;
	}

	static string Read(MemoryFileSystem files)
	{
		return files.Peek(TomlPath);
	}

	// The oracle, checked after every step: the target mod's file is always
	// a whole document that parses with all of its keys, the save never left
	// its staging file behind, and what the target shows is a document too.
	static void CheckInvariants(MemoryFileSystem files, VirtualClock clock,
		TargetMod target, int step)
	{
		var text = Read(files);
		List<TomlSettings.DocEntry> entries = null;
		string error = null;
		var parsed = text.Length > 0 && TomlSettings.TryReadDocument(text, out entries, out error);
		Check(parsed,
			"step " + step + ": the file is not a whole document (" + error + ")");
		Check(entries != null && entries.Count == 3,
			"step " + step + ": the file lost a key");
		List<TomlSettings.DocEntry> cached = null;
		string cachedError = null;
		Check(target.Text == null
				|| TomlSettings.TryReadDocument(target.Text, out cached, out cachedError),
			"step " + step + ": the cached text is not a whole document");
		Check(files.NamesStartingWith(TempPrefix).Count == 0,
			"step " + step + ": a staging file outlived the save that staged it");
		Check(clock.Sleeps == 0 || clock.SleptMilliseconds > 0d,
			"step " + step + ": the clock waited without advancing");
	}

	static void Check(bool ok, string what)
	{
		if (!ok)
			throw new InvalidOperationException("invariant broken: " + what);
	}
}

/// <summary>
/// A seeded source of the fault draw and the edit values, and nothing else:
/// no clock, no entropy, no address. xorshift32, so it is the same sequence
/// on every platform and every runtime, which is what makes a seed replay.
/// </summary>
sealed class Rng
{
	uint state;

	public Rng(int seed)
	{
		state = unchecked((uint)seed * 2654435761u) + 1u;
		if (state == 0)
			state = 0x9E3779B9u;
	}

	public int Next(int bound)
	{
		state ^= state << 13;
		state ^= state >> 17;
		state ^= state << 5;
		return (int)(state % (uint)bound);
	}
}
