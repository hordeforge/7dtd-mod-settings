using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using Wrench;

// Offline gate for the TOML document parser, the in-place writer and the
// mod settings path resolver: parse captures spans, kinds, and comment
// blocks; an edit changes one value span and nothing else, byte-for-byte;
// a mod name taken from another mod's ModInfo.xml cannot steer the screen's
// read or write out of that mod's folder. Run by
// scripts/test_toml_document.py; output must be deterministic.
static class Program
{
	static int failures;

	static void Check(string name, bool ok, string detail = "")
	{
		if (ok)
		{
			Console.WriteLine("PASS " + name);
		}
		else
		{
			failures++;
			Console.WriteLine("FAIL " + name + (detail.Length > 0 ? ": " + detail : ""));
		}
	}

	const string Fixture =
		"# File header block, separated from the first key by a blank\n" +
		"# line: it belongs to the file, not to AllowThing.\n" +
		"\n" +
		"# Gates the thing. Off by default.\n" +
		"# Second help line.\n" +
		"AllowThing = false\n" +
		"\n" +
		"Count = 12\n" +
		"Chance = 0.001 # trailing note, not Chance2's help\n" +
		"Chance2 = -1.5\n" +
		"Label = \"hi \\\"there\\\"\"\n" +
		"# Tokens, one per yield.\n" +
		"Modes = [\n" +
		"\t# not help for anything\n" +
		"\t\"A\", \"B\",\n" +
		"]\n";

	static void Main()
	{
		TestParse();
		TestNumbers();
		TestEdits();
		TestRejections();
		TestUnicodeAndEscapes();
		TestCrlf();
		TestFileIo();
		TestModTomlPath();
		TestShippedFile();
		TestSimulatedSave();
		TestFailedFallbackKeepsTheOnlyCopy();
		TestSaveTwiceIsOneSave();
		TestInterruptedSwapConvergesOnRerun();
		Console.WriteLine(failures + " failures.");
		Environment.Exit(failures > 0 ? 1 : 0);
	}

	// The save path, driven by a seed instead of by the game: a virtual
	// clock, an in-memory disk, and faults at the points the disk produces
	// them. Every seed is a whole run whose invariants are checked after
	// every step, and the same seed twice has to print the same trace, so a
	// failure is replayable from the seed printed with it.
	static void TestSimulatedSave()
	{
		var traces = new Dictionary<int, string>();
		var broken = 0;
		for (var seed = 1; seed <= Simulation.SeedCount; seed++)
		{
			try
			{
				traces[seed] = Simulation.Run(seed);
			}
			catch (Exception ex)
			{
				broken++;
				Check("seed " + seed + " holds its invariants", false, ex.Message);
			}
		}
		Check("every seed's run holds the save invariants", broken == 0, broken + " seeds broke one");
		var distinct = new HashSet<string>(traces.Values);
		Check("the seeds explore different runs, not one run thirty times",
			traces.Count == Simulation.SeedCount && distinct.Count > 1,
			traces.Count + " runs, " + distinct.Count + " distinct");

		// Determinism, proven rather than claimed: one seed, two runs, the
		// same trace. A non-empty diff names a decision that came from
		// outside the seed.
		var first = Simulation.Run(Simulation.Seed);
		var second = Simulation.Run(Simulation.Seed);
		Check("the same seed replays the same run", first == second, FirstDifference(first, second));

		// And the seed is on the record, so a failure names the one value
		// that reproduces it.
		Console.WriteLine("seed " + Simulation.Seed + ": " + Simulation.StepsPerSeed
			+ " steps, deterministic; trace follows");
		Console.Write(first);
		TestMidSaveRace();
	}

	// The seeded runs above put faults in front of a save; this one puts a
	// second writer inside it, in the window between the save's read and
	// its staging write. There is no seed for it: there is one interleaving
	// and it either holds or the save is clobbering another program's.
	static void TestMidSaveRace()
	{
		try
		{
			Console.Write(Simulation.RunMidSaveRace());
		}
		catch (Exception ex)
		{
			Check("a save keeps the other program's save made mid-save", false, ex.Message);
		}
	}

	// The one window in the save where the settings file does not exist: a
	// runtime with no atomic replace deletes the destination and moves the
	// staging file into its place, and a move that fails there leaves the
	// staging file holding the only copy of the new text. Deleting it as a
	// failed save would clean up would take the mod's settings with it, so
	// the failure keeps it and names where it is.
	static void TestFailedFallbackKeepsTheOnlyCopy()
	{
		const string tomlPath = "/sim/Mods/Example/Config/Example.toml";
		// The shipped writer stages under `path + ".wrench-tmp." + pid`, so
		// the only copy of the new text is found by the prefix every writer of
		// this file stages under, not by one name.
		var staged = new List<string>();
		var files = new MemoryFileSystem(new VirtualClock());
		files.Seed(tomlPath, "Count = 12\n", new UTF8Encoding(false));

		var savedFiles = ModFileSystem.Current;
		var savedClock = ModClock.Current;
		ModFileSystem.Current = files;
		ModClock.Current = new VirtualClock();
		string error = null;
		var saved = true;
		try
		{
			var target = new TargetMod("Example", "Example", null, tomlPath, true);
			var entry = target.Entries.Find(e => e.Name == "Count");
			files.PendingNoAtomicReplace = 1;
			// Two, not one: the first is the move that puts the staged text in
			// the destination's place, the second the one that would put the old
			// text back. A save that can close its own swap cleans up after
			// itself; only a run killed between the two moves leaves the staging
			// file holding the only copy of the new text.
			files.PendingMoveFaults = 2;
			saved = target.TrySave(entry, "13", out error);
			staged = files.NamesStartingWith(Simulation.TempPrefix);
		}
		finally
		{
			ModFileSystem.Current = savedFiles;
			ModClock.Current = savedClock;
		}

		var tempPath = staged.Count == 1 ? staged[0] : null;
		Check("a save whose fallback move failed reports the failure", !saved, error ?? "");
		Check("the staging file outlives the failed save",
			staged.Count == 1, staged.Count + " staging files under "
				+ Simulation.TempPrefix + " (" + string.Join(", ", staged) + ")");
		Check("the staging file holds the text the save wrote",
			tempPath != null && files.Peek(tempPath) == "Count = 13\n",
			tempPath == null ? "(absent)" : files.Peek(tempPath));
		Check("the failure names where the new text was left",
			!saved && error != null && tempPath != null && error.Contains(tempPath),
			error ?? "");
	}

	// A save is the operation a retry lands on, twice over: the player
	// presses save again, the screen's own retry re-runs it, and a launch
	// after a crash lands on whatever the first one left. Running the same
	// save twice has to leave the file exactly where running it once did.
	static void TestSaveTwiceIsOneSave()
	{
		const string tomlPath = "/sim/Mods/Example/Config/Example.toml";
		var files = new MemoryFileSystem(new VirtualClock());
		files.Seed(tomlPath, "Count = 12\n", new UTF8Encoding(false));

		var savedFiles = ModFileSystem.Current;
		var savedClock = ModClock.Current;
		ModFileSystem.Current = files;
		ModClock.Current = new VirtualClock();
		string error = null;
		string once = null;
		var twice = false;
		try
		{
			var target = new TargetMod("Example", "Example", tomlPath, true);
			if (!target.TrySave(Find(target, "Count"), "13", out error))
			{
				Check("a save of one value lands", false, error ?? "");
				return;
			}
			once = files.Peek(tomlPath);
			// The second run reads the file the first one wrote, so its span
			// is taken from that text, as any later save's is.
			twice = target.TrySave(Find(target, "Count"), "13", out error);
		}
		finally
		{
			ModFileSystem.Current = savedFiles;
			ModClock.Current = savedClock;
		}

		Check("a save run twice succeeds", twice, error ?? "");
		Check("a save run twice leaves the file one run left",
			once == files.Peek(tomlPath), "once " + once + " twice " + files.Peek(tomlPath));
		Check("neither run left a staging file behind",
			files.NamesStartingWith(Simulation.TempPrefix).Count == 0,
			string.Join(", ", files.NamesStartingWith(Simulation.TempPrefix)));
	}

	// The one window in which a save leaves no settings file: a run killed
	// between the two moves of the no-atomic-replace fallback, which is what
	// a crash in that window looks like to the next run. The old text is at
	// the sibling name and the new one at a staging file named for a process
	// that is gone, so nothing after it finds either. Re-running has to land
	// where the first run did.
	static void TestInterruptedSwapConvergesOnRerun()
	{
		const string tomlPath = "/sim/Mods/Example/Config/Example.toml";
		var previousPath = tomlPath + TargetMod.PreviousSuffix;
		var files = new MemoryFileSystem(new VirtualClock());
		// The state a kill between the two moves leaves, built directly: the
		// old text is at the sibling, and the staging file it was staged into
		// is under a name carrying the id of a process that is not running.
		files.Seed(previousPath, "Count = 12\n", new UTF8Encoding(false));
		files.Seed(tomlPath + ".wrench-tmp.4242", "Count = 13\n", new UTF8Encoding(false));

		var savedFiles = ModFileSystem.Current;
		var savedClock = ModClock.Current;
		ModFileSystem.Current = files;
		ModClock.Current = new VirtualClock();
		string error = null;
		var recovered = false;
		var again = true;
		var landed = false;
		try
		{
			// What the screen's discovery asks on the next run.
			recovered = TargetMod.RecoverInterruptedSave(tomlPath);
			again = TargetMod.RecoverInterruptedSave(tomlPath);
			// And the save that was owed, made against the file that is back.
			var target = new TargetMod("Example", "Example", tomlPath, true);
			landed = target.TrySave(Find(target, "Count"), "13", out error);
		}
		finally
		{
			ModFileSystem.Current = savedFiles;
			ModClock.Current = savedClock;
		}

		Check("a re-run puts the settings file back", recovered,
			"nothing at " + previousPath);
		Check("the file it puts back holds the text the save was about to replace",
			files.Peek(tomlPath) == "Count = 12\n", files.Peek(tomlPath));
		Check("the sibling is gone once the file is back", !files.Exists(previousPath));
		Check("a further re-run recovers nothing and changes nothing",
			!again && files.Peek(tomlPath) == "Count = 12\n", files.Peek(tomlPath));
		Check("the interrupted save is still owed and lands on the recovered file",
			landed && files.Peek(tomlPath) == "Count = 13\n", error ?? files.Peek(tomlPath));
	}

	static TomlSettings.DocEntry Find(TargetMod target, string name)
	{
		return target.Entries == null ? null : target.Entries.Find(e => e.Name == name);
	}

	static string FirstDifference(string left, string right)
	{
		var limit = Math.Min(left.Length, right.Length);
		for (var i = 0; i < limit; i++)
		{
			if (left[i] != right[i])
				return "traces differ at " + i + ": '" + left[i] + "' vs '" + right[i] + "'";
		}
		return "traces differ in length: " + left.Length + " vs " + right.Length;
	}

	static void TestParse()
	{
		List<TomlSettings.DocEntry> doc;
		string error;
		Check("fixture parses", TomlSettings.TryReadDocument(Fixture, out doc, out error), error ?? "");
		if (doc == null)
			return;
		Check("six entries", doc.Count == 6, doc.Count.ToString());
		Check("names in file order",
			string.Join(",", doc.ConvertAll(e => e.Name))
			== "AllowThing,Count,Chance,Chance2,Label,Modes");
		Check("kinds typed from the value",
			doc[0].Kind == TomlSettings.ValueKind.Bool
			&& doc[1].Kind == TomlSettings.ValueKind.Int
			&& doc[2].Kind == TomlSettings.ValueKind.Float
			&& doc[3].Kind == TomlSettings.ValueKind.Float
			&& doc[4].Kind == TomlSettings.ValueKind.String
			&& doc[5].Kind == TomlSettings.ValueKind.Array);
		Check("normalized values",
			doc[0].Value == "false" && doc[1].Value == "12"
			&& doc[2].Value == "0.001" && doc[3].Value == "-1.5"
			&& doc[4].Value == "hi \"there\"" && doc[5].Value == "A,B");
		Check("value spans are the raw tokens",
			Raw(Fixture, doc[0]) == "false"
			&& Raw(Fixture, doc[2]) == "0.001"
			&& Raw(Fixture, doc[4]) == "\"hi \\\"there\\\"\""
			&& Raw(Fixture, doc[5]).StartsWith("[") && Raw(Fixture, doc[5]).EndsWith("]"));
		Check("contiguous comment block is the help text",
			doc[0].Comment == "Gates the thing. Off by default.\nSecond help line.");
		Check("blank line detaches the header block", !doc[0].Comment.Contains("File header"));
		Check("no comment means empty help", doc[1].Comment == "");
		Check("trailing comment is nobody's help", doc[3].Comment == "");
		Check("array's own block is its help; inner comments are not",
			doc[5].Comment == "Tokens, one per yield.");
	}

	// A value that reaches the mod on the other side of the file must be the
	// value the file holds. Normalizing through a fixed number of decimal
	// places is where that stops being true: 0.00000001 came back as 0, and
	// an exponent spelling came back as something this grammar cannot read.
	static void TestNumbers()
	{
		List<TomlSettings.DocEntry> doc;
		string error;

		string[] tokens =
		{
			"0.5", "0.001", "-1.5", "2.5", "0.00000001", "0.0000001",
			"0.123456789012345", "3.14159265358979",
			"0.000000000000000001", "1000000000000000000.0",
			"99999999.99999999",
		};
		var allExact = true;
		var allPlain = true;
		var allFloat = true;
		for (var i = 0; i < tokens.Length; i++)
		{
			var token = tokens[i];
			if (!TomlSettings.TryReadDocument("V = " + token + "\n", out doc, out error))
			{
				Console.WriteLine("  " + token + " did not parse: " + error);
				allExact = allPlain = allFloat = false;
				break;
			}
			var value = doc[0].Value;
			if (doc[0].Kind != TomlSettings.ValueKind.Float)
				allFloat = false;
			if (value.IndexOf('E') >= 0 || value.IndexOf('e') >= 0)
			{
				Console.WriteLine("  " + token + " normalized to an exponent: " + value);
				allPlain = false;
			}
			// The decoded value must read back as the identical double: the
			// span edit and the value grammar both depend on that.
			double was, now;
			double.TryParse(token, NumberStyles.Float, CultureInfo.InvariantCulture, out was);
			if (!double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out now)
				|| was != now)
			{
				Console.WriteLine("  " + token + " normalized to " + value
					+ ", which is a different number");
				allExact = false;
			}
		}
		Check("a float normalizes to the same number it was written as", allExact);
		Check("a normalized float carries no exponent", allPlain);
		Check("a normalized float keeps its kind", allFloat);

		Check("zero is one zero",
			TomlSettings.TryReadDocument("A = 0.0\n", out doc, out error)
			&& doc[0].Value == "0", doc[0].Value);
		Check("an int normalizes to its own digits",
			TomlSettings.TryReadDocument("A = 12\nB = -3\nC = 007\n", out doc, out error)
			&& doc[0].Value == "12" && doc[1].Value == "-3" && doc[2].Value == "7", error ?? "");
		Check("long.MaxValue is not truncated",
			TomlSettings.TryReadDocument("A = 9223372036854775807\n", out doc, out error)
			&& doc[0].Value == "9223372036854775807", doc[0].Value);
		// An int past long.MaxValue is refused, not wrapped into a negative
		// or silently cut to the width that fitted.
		Check("an int past long.MaxValue is refused",
			!TomlSettings.TryReadDocument("A = 99999999999999999999\n", out doc, out error));

		// An eight-hex-digit \U escape is 32 bits: read into an int it wraps,
		// and \UFFFFFFFF came back as a small positive scalar.
		Check("reject an eight-digit escape that overflows a code point",
			!TomlSettings.TryReadDocument("A = \"\\UFFFFFFFF\"\n", out doc, out error));
		Check("reject one just past the last code point",
			!TomlSettings.TryReadDocument("A = \"\\U00110000\"\n", out doc, out error));
		Check("accept the last code point",
			TomlSettings.TryReadDocument("A = \"\\U0010FFFF\"\n", out doc, out error)
			&& doc[0].Value == "\U0010FFFF", error ?? "");
	}

	static void EditCase(string name, string key, string newRaw, string expectValue)
	{
		List<TomlSettings.DocEntry> doc;
		string error;
		TomlSettings.TryReadDocument(Fixture, out doc, out error);
		var entry = doc.Find(e => e.Name == key);
		string newText;
		List<TomlSettings.DocEntry> written;
		if (!TomlEdit.TryReplaceValue(Fixture, doc, entry, newRaw, out newText, out written, out error))
		{
			Check(name, false, error);
			return;
		}
		var expected = Fixture.Substring(0, entry.ValueStart)
			+ newRaw.Trim()
			+ Fixture.Substring(entry.ValueStart + entry.ValueLength);
		List<TomlSettings.DocEntry> after;
		TomlSettings.TryReadDocument(newText, out after, out error);
		var reparsed = after.Find(e => e.Name == key);
		Check(name,
			newText == expected
			&& reparsed.Value == expectValue
			&& reparsed.Comment == entry.Comment,
			"round trip mismatch");
		// The writer hands back the parse of what it wrote, so the caller
		// never has to read the file back: it must be the same parse.
		Check(name + " (entries handed back match the written text)",
			written.Count == after.Count
			&& string.Join(";", written.ConvertAll(e => e.Name + "=" + e.Value))
			== string.Join(";", after.ConvertAll(e => e.Name + "=" + e.Value)));
	}

	static void TestEdits()
	{
		EditCase("edit bool", "AllowThing", "true", "true");
		EditCase("edit int", "Count", "40", "40");
		EditCase("edit float", "Chance", "0.5", "0.5");
		EditCase("edit int into float slot", "Chance", "1", "1");
		EditCase("edit string with escapes", "Label", TomlEdit.EncodeString("a\"b\\c\nd"), "a\"b\\c\nd");
		EditCase("edit array", "Modes", "[\"C\"]", "C");
		EditCase("edit multiline value onto one line", "Modes", "true", "true");
	}

	static void TestRejections()
	{
		List<TomlSettings.DocEntry> doc;
		string error, newText;
		TomlSettings.TryReadDocument(Fixture, out doc, out error);
		var count = doc.Find(e => e.Name == "Count");
		List<TomlSettings.DocEntry> after;
		Check("reject a non-value", !TomlEdit.TryReplaceValue(Fixture, doc, count, "nope", out newText, out after, out error));
		Check("reject trailing garbage", !TomlEdit.TryReplaceValue(Fixture, doc, count, "1 2", out newText, out after, out error));
		Check("reject a key injection", !TomlEdit.TryReplaceValue(Fixture, doc, count, "1\nInjected = 2", out newText, out after, out error));
		Check("reject a comment rider", !TomlEdit.TryReplaceValue(Fixture, doc, count, "1 # note", out newText, out after, out error));
		Check("reject an empty value", !TomlEdit.TryReplaceValue(Fixture, doc, count, "", out newText, out after, out error));
		// Text after a value is not a second key: read as one, it would be
		// written back glued to the edited value, and the mod on the other
		// side of the file would refuse what Wrench just saved.
		Check("reject text after a value", !TomlSettings.TryReadDocument("A = 0.001B = 2\n", out doc, out error));
		Check("reject trailing garbage after a string", !TomlSettings.TryReadDocument("A = \"x\" y\n", out doc, out error));
		Check("accept a comment after a value", TomlSettings.TryReadDocument("A = 1 # note\nB = 2\n", out doc, out error) && doc.Count == 2, error ?? "");

		Check("reject a table file", !TomlSettings.TryReadDocument("[table]\nA = 1\n", out doc, out error));
		// A file cut off mid-save is the ordinary way a reader is handed a
		// broken document, and the reason reaches a player on the status
		// line. It has to name the line it gave up on, not the cursor's
		// IndexOutOfRangeException, which is the one thing a player can do
		// nothing with.
		var truncated = new[]
		{
			"A", "A   ", "A = 1\nB", "A = [1, 2", "A = [1, 2 # note", "A = [",
		};
		var truncationNamed = true;
		foreach (var sample in truncated)
		{
			if (TomlSettings.TryReadDocument(sample, out doc, out error)
				|| error == null || !error.StartsWith("line ", StringComparison.Ordinal))
			{
				Console.WriteLine("  truncation of \"" + sample + "\" reported: " + error);
				truncationNamed = false;
			}
		}
		Check("a truncated file is refused with the line that stopped it", truncationNamed);
		Check("reject a duplicate key", !TomlSettings.TryReadDocument("A = 1\nA = 2\n", out doc, out error));
		Check("reject a dotted key", !TomlSettings.TryReadDocument("a.b = 1\n", out doc, out error));
		// Bare keys are case-sensitive, so two keys differing only in case are
		// two keys; a case-blind duplicate check would call a valid file
		// unreadable and hide it from the screen.
		Check("case-variant keys are distinct",
			TomlSettings.TryReadDocument("Foo = 1\nfoo = 2\n", out doc, out error)
			&& doc.Count == 2 && doc[0].Name == "Foo" && doc[1].Name == "foo", error ?? "");
		if (doc != null && doc.Count == 2)
		{
			string caseText, caseError;
			List<TomlSettings.DocEntry> caseAfter;
			Check("a case-variant edit lands on the named key only",
				TomlEdit.TryReplaceValue("Foo = 1\nfoo = 2\n", doc, doc[1], "9",
					out caseText, out caseAfter, out caseError)
				&& caseText == "Foo = 1\nfoo = 9\n",
				caseError ?? "");
		}
	}

	// Every value the writer can produce must read back, and every escape the
	// reader claims to understand must be one the writer could have produced:
	// the two are the same grammar, and a value Wrench shows but cannot write
	// back is a value it can corrupt.
	static void TestUnicodeAndEscapes()
	{
		List<TomlSettings.DocEntry> doc;
		string error, newText;
		List<TomlSettings.DocEntry> after;

		var samples = new[]
		{
			"plain ascii",
			"caf\u00e9 \u00fcber",                  // Latin-1 supplement, 2 bytes each
			"\u65e5\u672c\u8a9e\u306e\u30e9\u30d9\u30eb",          // 3 bytes per character
			"emoji \U0001F600 and \U0001F468\u200d\U0001F469\u200d\U0001F466", // astral, ZWJ sequence
			"precomposed \u00e9 and decomposed e\u0301",  // NFC vs NFD: same letters, different bytes
			"line\r\nbreak\ttab\fform\bback",
			"null\u0000 and del\u007F and esc\u001B",
			"quote\" backslash\\ end",
		};
		var allRoundTrip = true;
		for (var i = 0; i < samples.Length && allRoundTrip; i++)
		{
			var file = "Label = " + TomlEdit.EncodeString(samples[i]) + "\n";
			if (!TomlSettings.TryReadDocument(file, out doc, out error) || doc[0].Value != samples[i])
			{
				Console.WriteLine("  round trip mismatch for: " + samples[i]
					+ "\n  encoded: " + file.Trim() + "\n  error: " + error);
				allRoundTrip = false;
			}
		}
		Check("every encoded value reads back unchanged", allRoundTrip);

		Check("a non-ASCII value keeps its span and its bytes",
			TomlSettings.TryReadDocument("Label = \"caf\u00e9\"\n", out doc, out error)
			&& doc[0].Value == "caf\u00e9"
			&& doc[0].ValueStart == 8
			&& Raw("Label = \"caf\u00e9\"\n", doc[0]) == "\"caf\u00e9\"", error ?? "");

		Check("astral escapes decode to one character pair",
			TomlSettings.TryReadDocument("A = \"\\uD83D\\uDE00\"\n", out doc, out error)
			&& doc[0].Value == "\U0001F600"
			&& doc[0].Value.Length == 2, error ?? "");

		Check("eight digit escapes decode to one character pair",
			TomlSettings.TryReadDocument("A = \"\\U0001F600\"\n", out doc, out error)
			&& doc[0].Value == "\U0001F600", error ?? "");

		Check("reject an unpaired surrogate escape",
			!TomlSettings.TryReadDocument("A = \"\\uD83D\"\n", out doc, out error));
		Check("reject a half pair that is not a low surrogate",
			!TomlSettings.TryReadDocument("A = \"\\uD83D\\u0041\"\n", out doc, out error));
		Check("reject a short hex escape",
			!TomlSettings.TryReadDocument("A = \"\\u00\"\n", out doc, out error));
		Check("reject a non-hex escape",
			!TomlSettings.TryReadDocument("A = \"\\uZZZZ\"\n", out doc, out error));
		Check("reject a raw control character in a string",
			!TomlSettings.TryReadDocument("A = \"a\rb\"\n", out doc, out error));

		// An edit into a file that already holds non-ASCII leaves every other
		// byte alone: the value span is in characters, so a multi-byte key's
		// neighbours must not shift.
		var unicode = "# caf\u00e9 \u2615\nA = 1\nB = \"\u65e5\u672c\u8a9e\"\nC = 3\n";
		TomlSettings.TryReadDocument(unicode, out doc, out error);
		var b = doc.Find(e => e.Name == "B");
		Check("an edit next to non-ASCII splices the right span",
			b != null
			&& TomlEdit.TryReplaceValue(unicode, doc, b, "42", out newText, out after, out error)
			&& newText == "# caf\u00e9 \u2615\nA = 1\nB = 42\nC = 3\n", error ?? "");
	}

	static void TestCrlf()
	{
		var crlf = "# help\r\nA = 1\r\nB = 2\r\n";
		List<TomlSettings.DocEntry> doc;
		string error, newText;
		List<TomlSettings.DocEntry> after;
		Check("crlf parses", TomlSettings.TryReadDocument(crlf, out doc, out error), error ?? "");
		Check("crlf comment captured", doc[0].Comment == "help");
		var a = doc.Find(e => e.Name == "A");
		Check("crlf edit keeps line endings",
			TomlEdit.TryReplaceValue(crlf, doc, a, "7", out newText, out after, out error)
			&& newText == "# help\r\nA = 7\r\nB = 2\r\n",
			error ?? "");
	}

	static void TestModTomlPath()
	{
		var root = Path.Combine(Path.GetTempPath(), "wrench-gate", "Mods", "Example");
		string tomlPath, error;

		Check("a plain mod name resolves inside the mod folder",
			ModTomlPath.TryResolve(root, "Example", out tomlPath, out error)
			&& tomlPath == Path.Combine(root, "Config", "Example.toml"), error ?? "");

		Check("a name with a dot in it is still plain",
			ModTomlPath.TryResolve(root, "Some.Mod 2", out tomlPath, out error)
			&& tomlPath == Path.Combine(root, "Config", "Some.Mod 2.toml"), error ?? "");

		Rejected("a parent-directory name", root, "../Escape");
		Rejected("a nested path", root, "sub/Escape");
		Rejected("a backslash path", root, "..\\Escape");
		Rejected("an absolute path", root, "/etc/Config");
		Rejected("a drive-qualified name", root, "C:Config");
		Rejected("a stream name", root, "Escape:stream");
		Rejected("a current-directory name", root, ".");
		Rejected("a parent-directory token", root, "..");
		// Windows resolves these to its own devices, with any extension and
		// in any case, so a read opens the device and a save goes nowhere.
		Rejected("a reserved device name", root, "NUL");
		Rejected("a lower-case reserved device name", root, "nul");
		Rejected("a reserved device name with an extension", root, "Com1.Mod");
		Rejected("a reserved device name with trailing spaces", root, "aux  ");
		// A name carrying a line break resolves to a real file on a Linux or
		// macOS host, where the only characters the platform itself forbids
		// are NUL and the separator, and then forges a log line through the
		// name.
		Rejected("a name with a newline", root, "Example\n2026-01-01 ERROR: forged");
		Rejected("a name with a carriage return", root, "Example\rmod");
		Rejected("a name with an escape", root, "Example\u001b[2J");
		Rejected("an empty name", root, "");
		Rejected("a null name", root, null);
		Rejected("an empty mod path", "", "Example");
		Rejected("a null mod path", null, "Example");
	}

	static void Rejected(string name, string modPath, string modName)
	{
		string tomlPath, error;
		Check("reject " + name,
			!ModTomlPath.TryResolve(modPath, modName, out tomlPath, out error)
			&& tomlPath == null
			&& !string.IsNullOrEmpty(error),
			"resolved to " + (tomlPath ?? "(null)"));
	}

	static void TestShippedFile()
	{
		// The mod's own settings file must parse through the same document
		// reader the UI uses (v1 scope: Wrench eats its own dog food).
		var root = AppContext.BaseDirectory;
		while (root != null && !File.Exists(Path.Combine(root, "ModInfo.xml")))
			root = Path.GetDirectoryName(root);
		if (root == null)
		{
			Check("shipped Config/Wrench.toml parses", false, "repo root not found");
			return;
		}
		var text = File.ReadAllText(Path.Combine(root, "Config", "Wrench.toml"));
		List<TomlSettings.DocEntry> doc;
		string error;
		Check("shipped Config/Wrench.toml parses",
			TomlSettings.TryReadDocument(text, out doc, out error), error ?? "");
		Check("shipped file's keys carry help comments",
			doc != null && doc.Count > 0 && doc.TrueForAll(e => e.Comment.Length > 0));
	}

	// The file the settings screen actually edits, in every shape a mod
	// author saves it on a machine that is not this one: a byte order mark
	// (Windows editors write one), CRLF, UTF-16 and UTF-32 either way round,
	// and a file another process holds open while it watches for changes.
	static void TestFileIo()
	{
		var dir = Path.Combine(Path.GetTempPath(), "wrench-toml-gate");
		Directory.CreateDirectory(dir);
		try
		{
			var plain = "# help\nA = 1\nB = 2\n";
			var windows = "# help\r\nA = 1\r\nB = 2\r\n";
			RoundTrips(dir, "plain", new UTF8Encoding(false), plain);
			RoundTrips(dir, "bom", new UTF8Encoding(true), plain);
			RoundTrips(dir, "crlf-bom", new UTF8Encoding(true), windows);
			RoundTrips(dir, "utf16", new UnicodeEncoding(false, true), windows);
			RoundTrips(dir, "utf16be", new UnicodeEncoding(true, true), windows);
			RoundTrips(dir, "utf32", new UTF32Encoding(false, true), windows);
			RoundTrips(dir, "utf32be", new UTF32Encoding(true, true), windows);
			SharedAccessWhileOpen(dir);
			StrictDecoding(dir);
		}
		finally
		{
			Directory.Delete(dir, true);
		}
	}

	static void RoundTrips(string dir, string name, Encoding encoding, string body)
	{
		var path = Path.Combine(dir, name + ".toml");
		var preamble = encoding.GetPreamble();
		var original = preamble.Concat(encoding.GetBytes(body)).ToArray();
		File.WriteAllBytes(path, original);

		// The shipped seam, not a local copy of it: the read and the write a
		// save makes reach the disk through the same object the game uses.
		var files = new SystemFileSystem();
		Encoding read;
		var text = TomlFile.Decode(files.ReadAllBytes(path), out read);
		Check(name + ": read decodes the body", text == body);
		Check(name + ": read keeps the declared encoding", read.GetPreamble().SequenceEqual(preamble));

		files.WriteAllText(path, text, read);
		Check(name + ": write without an edit is byte-identical",
			files.ReadAllBytes(path).SequenceEqual(original));

		List<TomlSettings.DocEntry> doc;
		string error, newText;
		if (!TomlSettings.TryReadDocument(text, out doc, out error))
		{
			Check(name + ": document parses", false, error ?? "");
			return;
		}
		var entry = doc.Find(e => e.Name == "A");
		List<TomlSettings.DocEntry> after;
		Check(name + ": edit replaces the value span",
			TomlEdit.TryReplaceValue(text, doc, entry, "7", out newText, out after, out error)
			&& text.Replace("A = 1", "A = 7") == newText, error ?? "");
		files.WriteAllText(path, newText, read);
		var reread = files.ReadAllBytes(path);
		Check(name + ": edit leaves every other byte alone",
			reread.Length == original.Length
			&& reread.Take(3).SequenceEqual(original.Take(3))
			&& read.GetString(reread, read.GetPreamble().Length, reread.Length - read.GetPreamble().Length)
				== newText);
	}

	// The hot-reloading mod's watcher keeps the file open for read and
	// write while polling it; a save from the settings screen must not fail
	// with a sharing violation (Windows rejects the default share mode here).
	static void SharedAccessWhileOpen(string dir)
	{
		var path = Path.Combine(dir, "shared.toml");
		var files = new SystemFileSystem();
		files.WriteAllText(path, "A = 1\n", new UTF8Encoding(false));
		Encoding read;
		try
		{
			using (var watcher = new FileStream(path, FileMode.Open, FileAccess.ReadWrite,
				FileShare.ReadWrite | FileShare.Delete))
			{
				TomlFile.Decode(files.ReadAllBytes(path), out read);
				files.WriteAllText(path, "A = 2\n", new UTF8Encoding(false));
			}
			Check("read and write tolerate a concurrent holder", read != null && File.ReadAllText(path) == "A = 2\n");
		}
		catch (IOException ex)
		{
			Check("read and write tolerate a concurrent holder", false, ex.Message);
		}
	}

	// Bytes that are not valid in the encoding the file declares are
	// refused, not decoded into U+FFFD. A mod author who saved in a single
	// byte encoding would otherwise get a file whose comment is a row of
	// replacement characters the first time they saved one value from the
	// settings screen. The marked and the unmarked form must agree, so three
	// bytes of preamble cannot decide how forgiving the read is.
	static void StrictDecoding(string dir)
	{
		// "# caf\xE9" in latin-1: 0xE9 starts no character in UTF-8.
		var bytes = new byte[] { (byte)'#', (byte)' ', (byte)'c', (byte)'a', (byte)'f',
			0xE9, (byte)'\n', (byte)'A', (byte)' ', (byte)'1', (byte)'\n' };
		var path = Path.Combine(dir, "latin1.toml");
		File.WriteAllBytes(path, bytes);
		Check("an unmarked file with invalid UTF-8 is refused, not replaced",
			RefusesRead(path));

		var marked = Path.Combine(dir, "latin1-bom.toml");
		File.WriteAllBytes(marked, new byte[] { 0xEF, 0xBB, 0xBF }.Concat(bytes).ToArray());
		Check("a marked file with invalid UTF-8 is refused the same way",
			RefusesRead(marked));

		// A file is only as strict as the encoding its own mark names. The
		// UTF-16 and UTF-32 candidates are offered the same file, and a
		// lenient one of those loses a mod author's bytes on the first save
		// exactly as a lenient UTF-8 decoder would.
		var utf16 = Path.Combine(dir, "utf16-invalid.toml");
		// "A" is 41 00 in UTF-16LE, then a lone high surrogate (00 D8).
		File.WriteAllBytes(utf16, new byte[] { 0xFF, 0xFE, 0x41, 0x00, 0x00, 0xD8 });
		Check("a marked UTF-16 file with an unpaired surrogate is refused, not replaced",
			RefusesRead(utf16));

		var utf32 = Path.Combine(dir, "utf32-invalid.toml");
		// One UTF-32LE code point above U+10FFFF: 41 00 00 D8.
		File.WriteAllBytes(utf32, new byte[] { 0xFF, 0xFE, 0x00, 0x00, 0x41, 0x00, 0x00, 0xD8 });
		Check("a marked UTF-32 file with a code point out of range is refused, not replaced",
			RefusesRead(utf32));

		Check("a refused read leaves the file's bytes untouched",
			File.ReadAllBytes(path).SequenceEqual(bytes));
	}

	static bool RefusesRead(string path)
	{
		// Through the shipped seam, the same read the save path makes: a copy
		// of the decode here would prove nothing about the file the game opens.
		var files = new SystemFileSystem();
		Encoding read;
		try
		{
			files.ReadAllText(path, out read);
			return false;
		}
		catch (DecoderFallbackException)
		{
			return true;
		}
	}

	static string Raw(string text, TomlSettings.DocEntry entry)
	{
		return text.Substring(entry.ValueStart, entry.ValueLength);
	}
}
