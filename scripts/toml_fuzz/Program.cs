using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using Wrench;

// A seeded fuzz harness for the parser that reads another mod's
// Config/<Mod>.toml. That file is not this mod's: it arrives inside a
// downloaded modlet, so its bytes are untrusted input parsed in the game
// process, and the screen both reads and writes it.
//
// Every case is a mutated settings document. A fuzzer alone proves the
// presence of a bug, never its absence, so each case carries the invariants
// the screen relies on, and a failure prints the case that broke them:
//
//   - the reader never throws: a malformed file is a message on screen, not
//     a crash; a rejected document always says why;
//   - the same text parses the same way twice (no order, clock, or
//     static-state dependence between reads);
//   - every captured span is inside the text and is the raw token that
//     produced its own value, which is what an in-place edit splices on;
//   - an edit changes exactly one value span, every other byte survives, the
//     result re-parses, and the parse handed back is the parse of the text
//     written (the trust boundary the save crosses);
//   - every value the writer can produce reads back byte-identically;
//   - a mod name that resolves does so inside the mod folder, whatever the
//     name holds.
//
// The second half of that file never reaches the string cases: a modlet
// arrives as bytes, and the mark on them picks the encoding. The byte pass
// mutates byte arrays and asserts the pair across the file boundary (bytes in,
// the same bytes out), that a refusal is a refusal and never a crash, and
// that the mark decides the encoding without deciding whether the body
// decodes at all.
//
// The seed and case count are fixed, so two runs on an unchanged tree print
// the same report. Run by scripts/test_toml_fuzz.py.
static class Program
{
	const uint DefaultSeed = 0x5EED1234u;
	const int DefaultIterations = 40000;
	// Enough of a failing case to reproduce it by hand, in escaped form.
	const int MaxShownChars = 400;

	static uint random;
	static string currentInput = "";
	static int failures;
	static int thrown;
	static int accepted;
	static int refused;
	static int bytesAccepted;
	static int bytesRefused;

	static readonly string[] Alphabet =
	{
		" ", "\t", "\n", "\r", "\"", "\\", "=", "#", "[", "]", "{", "}", ",",
		"'", ".", "-", "+", "e", "E", "0", "9", "A", "Z", "_", ":", "/",
		"\u0000", "\u0001", "\u007F", "\uFFFD", "\u00E9", "\u65E5", "\U0001F600", "\uFEFF",
		"true", "false", "12", "-1.5", "0.001", "inf", "nan", "\\u", "\\U",
		"\\uD83D", "\\U0001F600", "\"\"", "[]", "a.b", " = ", "\n\n",
	};

	static readonly string[] Keys =
	{
		"AllowThing", "Count", "Chance", "Label", "Modes", "a", "A",
		"a.b", "a b", "K\u00e9y", "\u65e5\u672c", "true",
	};

	static readonly string[] Values =
	{
		"true", "false", "12", "-1.5", "0.001", "\"\"", "\"hi\"",
		"\"a\\\"b\"", "[]", "[\"A\"]", "[\"A\", \"B\",]", "1 2", "nope",
		"\"\\uD83D\\uDE00\"", "\"\\uD83D\"", "\"a\rb\"", "\"unterminated",
		"{\"k\": 1}", "0x10", "1_0", "1979-05-27",
	};

	static int Main(string[] args)
	{
		var seed = DefaultSeed;
		var iterations = DefaultIterations;
		for (var i = 0; i < args.Length; i += 2)
		{
			if (i + 1 >= args.Length)
			{
				Console.Error.WriteLine("usage: toml_fuzz [SEED] [ITERATIONS]");
				return 2;
			}
			if (args[i] == "--seed" && !uint.TryParse(args[i + 1], NumberStyles.HexNumber,
				CultureInfo.InvariantCulture, out seed))
			{
				Console.Error.WriteLine("--seed takes hexadecimal digits");
				return 2;
			}
			else if (args[i] == "--iterations"
				&& !int.TryParse(args[i + 1], NumberStyles.None, CultureInfo.InvariantCulture, out iterations))
			{
				Console.Error.WriteLine("--iterations takes a count");
				return 2;
			}
			else if (args[i] != "--seed" && args[i] != "--iterations")
			{
				Console.Error.WriteLine("unknown option: " + args[i]);
				return 2;
			}
		}
		random = seed == 0 ? 1u : seed;

		var corpus = Corpus();
		for (var i = 0; i < iterations; i++)
		{
			var text = Mutate(corpus[Next(corpus.Count)]);
			try
			{
				CheckDocument(text);
			}
			catch (Exception ex)
			{
				thrown++;
				Fail(i, "the reader threw " + ex.GetType().Name, text, ex.Message);
			}
			CheckModName(i);
		}
		for (var i = 0; i < iterations / 4; i++)
		{
			var value = RandomText(Next(12));
			try
			{
				CheckWrittenValue(i, value);
			}
			catch (Exception ex)
			{
				thrown++;
				Fail(i, "the writer threw " + ex.GetType().Name, value, ex.Message);
			}
		}

		var byteSeeds = ByteCorpus();
		for (var i = 0; i < iterations / 4; i++)
		{
			var bytes = MutateBytes(byteSeeds[Next(byteSeeds.Count)]);
			try
			{
				CheckBytes(i, bytes);
			}
			catch (Exception ex)
			{
				thrown++;
				Fail(i, "the byte pass threw " + ex.GetType().Name, EscapeBytes(bytes), ex.Message);
			}
		}

		Console.WriteLine("fuzz seed " + seed.ToString("x8", CultureInfo.InvariantCulture)
			+ ", " + iterations + " cases: "
			+ accepted + " accepted, " + refused + " refused, "
			+ failures + " invariant failures, " + thrown + " exceptions.");
		Console.WriteLine(bytesAccepted + " byte cases decoded, "
			+ bytesRefused + " refused.");
		Console.WriteLine(failures + " failures.");
		return failures > 0 || thrown > 0 ? 1 : 0;
	}

	// -- generation --------------------------------------------------------

	static uint NextBits()
	{
		random ^= random << 13;
		random ^= random >> 17;
		random ^= random << 5;
		return random;
	}

	static int Next(int bound)
	{
		return (int)(NextBits() % (uint)bound);
	}

	static string RandomText(int length)
	{
		var builder = new StringBuilder(length);
		for (var i = 0; i < length; i++)
			builder.Append(Alphabet[Next(Alphabet.Length)]);
		return builder.ToString();
	}

	static string RandomKey()
	{
		return Next(8) == 0 ? RandomText(Next(6)) : Keys[Next(Keys.Length)];
	}

	static string RandomValue()
	{
		return Next(6) == 0 ? RandomText(Next(10)) : Values[Next(Values.Length)];
	}

	/// <summary>A document shaped like the ones the screen really reads.</summary>
	static string Generated()
	{
		var builder = new StringBuilder();
		if (Next(2) == 0)
			builder.Append("# help\n");
		var count = 1 + Next(4);
		for (var i = 0; i < count; i++)
		{
			if (Next(4) == 0)
				builder.Append("# a comment\n");
			if (Next(8) == 0)
				builder.Append("# \u00e9\u65e5\n\r");
			builder.Append(RandomKey()).Append(" = ").Append(RandomValue()).Append('\n');
		}
		return builder.ToString();
	}

	/// <summary>Seeds, so the first cases reach real code paths before mutation.</summary>
	static List<string> Corpus()
	{
		var corpus = new List<string>
		{
			"# help\nA = 1\nB = 2\n",
			"A = false\n",
			"A = \"hi \\\"there\\\"\"\n",
			"Modes = [\n\t# not help\n\t\"A\", \"B\",\n]\n",
			"Chance = 0.001 # trailing note\n",
			"Label = \"caf\u00e9\"\nK\u00e9y = \"\u65e5\u672c\"\n",
			"Label = \"\\uD83D\\uDE00\"\n",
			"A = [1, 2,\n3]\r\nB = -1\r\n",
			"[table]\nA = 1\n",
			"a.b = 1\nA = 1\nA = 2\n",
			"A = \"\\uD83D\"\n",
			"AllowThing = false\n# Off by default.\n\n# Second file block.\nCount = 12\n",
		};
		// The file this mod ships, when the tree it was built from is here:
		// the shapes a maintainer actually saves.
		var root = AppContext.BaseDirectory;
		while (root != null && !File.Exists(Path.Combine(root, "ModInfo.xml")))
			root = Path.GetDirectoryName(root);
		if (root != null)
		{
			var shipped = Path.Combine(root, "Config", "Wrench.toml");
			if (File.Exists(shipped))
				corpus.Add(File.ReadAllText(shipped));
		}
		return corpus;
	}

	/// <summary>One to three edits over a seed, mixing shape and byte damage.</summary>
	static string Mutate(string seed)
	{
		var chars = seed.ToCharArray();
		var edits = 1 + Next(3);
		for (var edit = 0; edit < edits && chars.Length > 0; edit++)
		{
			// Twelve slots for eight edits, so the destructive ones (a
			// truncation, a second copy of the file) stay rare: a case that
			// still parses is what reaches the editor invariants.
			switch (Next(12))
			{
				case 0:
				{
					var text = new string(chars);
					chars = (text + Alphabet[Next(Alphabet.Length)]).ToCharArray();
					break;
				}
				case 1:
				{
					// Insert at a character offset, which is where a surrogate
					// pair can be split in half.
					var at = Next(chars.Length);
					var token = Alphabet[Next(Alphabet.Length)];
					var text = new string(chars);
					chars = (text.Substring(0, at) + token + text.Substring(at)).ToCharArray();
					break;
				}
				case 2:
				{
					var at = Next(chars.Length);
					var text = new string(chars);
					chars = (text.Substring(0, at) + text.Substring(at + 1)).ToCharArray();
					break;
				}
				case 3:
				{
					// Replace a character, a key, or a whole line.
					var at = Next(chars.Length);
					var replacement = Next(3) == 0
						? RandomKey()
						: Next(3) == 0 ? RandomValue() : Alphabet[Next(Alphabet.Length)];
					var text = new string(chars);
					chars = (text.Substring(0, at) + replacement + text.Substring(at + 1)).ToCharArray();
					break;
				}
				case 4:
				{
					// A whole new line, spliced in.
					var at = Next(chars.Length);
					var text = new string(chars);
					var line = RandomKey() + " = " + RandomValue() + "\n";
					chars = (text.Substring(0, at) + line + text.Substring(at)).ToCharArray();
					break;
				}
				case 5:
				{
					// A truncation: the shape of a file caught mid-save.
					var keep = Next(chars.Length);
					chars = new string(chars, 0, keep).ToCharArray();
					break;
				}
				case 6:
				{
					// A duplicated line: the shape of a copy-paste accident.
					var at = Next(chars.Length);
					var text = new string(chars);
					var lineEnd = text.IndexOf('\n', at);
					if (lineEnd < 0)
						lineEnd = text.Length;
					var line = text.Substring(at, lineEnd - at);
					chars = (text.Substring(0, lineEnd) + "\n" + line + text.Substring(lineEnd)).ToCharArray();
					break;
				}
				default:
				{
					// Two documents concatenated: a file that grew a second
					// copy of itself.
					var other = Generated();
					chars = (new string(chars) + other).ToCharArray();
					break;
				}
			}
		}
		if (Next(4) == 0)
			return Generated();
		return new string(chars);
	}

	// -- invariants --------------------------------------------------------

	static void CheckDocument(string text)
	{
		currentInput = text;
		List<TomlSettings.DocEntry> doc, again;
		string error;
		var ok = TomlSettings.TryReadDocument(text, out doc, out error);
		if (!ok)
		{
			refused++;
			if (string.IsNullOrEmpty(error))
				Report("a refused document gave no reason");
			return;
		}
		accepted++;
		if (doc == null)
		{
			Report("accepted with no entries");
			return;
		}
		if (doc.Count == 0)
			return; // an empty or comment-only file is a screen with nothing in it

		// Determinism: the same text, the same parse, every time. A screen
		// that re-reads a file to splice into it must land on the same spans.
		TomlSettings.TryReadDocument(text, out again, out error);
		if (again == null || !Same(doc, again))
			Report("two parses of one text disagree");

		for (var i = 0; i < doc.Count; i++)
		{
			var entry = doc[i];
			if (entry.ValueStart < 0 || entry.ValueLength < 0
				|| entry.ValueStart + entry.ValueLength > text.Length)
			{
				Report("value span falls outside the text");
				continue;
			}
			// The span is the raw token: re-parsing it alone must give the
			// same value back, which is what an in-place edit splices on.
			var raw = text.Substring(entry.ValueStart, entry.ValueLength);
			List<TomlSettings.DocEntry> probe;
			string probeError;
			if (!TomlSettings.TryReadDocument("v = " + raw, out probe, out probeError)
				|| probe.Count != 1 || probe[0].Value != entry.Value)
				Report("a captured span does not re-parse to its own value: " + Escape(raw));
		}

		CheckEdit(text, doc, Next(doc.Count));
		if (doc.Count > 1)
		{
			// A second edit, on a document that has already been edited: the
			// spans the screen re-parses are the ones the last edit produced.
			List<TomlSettings.DocEntry> written;
			string first, firstError;
			if (TomlEdit.TryReplaceValue(text, doc, doc[Next(doc.Count)], RandomRawValue(),
				out first, out written, out firstError))
				CheckEdit(first, written, Next(written.Count));
		}
	}

	static bool Same(List<TomlSettings.DocEntry> a, List<TomlSettings.DocEntry> b)
	{
		if (a.Count != b.Count)
			return false;
		for (var i = 0; i < a.Count; i++)
		{
			if (a[i].Name != b[i].Name || a[i].Value != b[i].Value || a[i].Kind != b[i].Kind
				|| a[i].ValueStart != b[i].ValueStart || a[i].ValueLength != b[i].ValueLength
				|| a[i].Comment != b[i].Comment)
				return false;
		}
		return true;
	}

	static string RandomRawValue()
	{
		return Next(4) == 0 ? TomlEdit.EncodeString(RandomText(Next(8))) : RandomValue();
	}

	/// <summary>
	/// An edit changes one value span and nothing else: the bytes before and
	/// after are the caller's own, the result parses, every other key keeps
	/// its value, and the entries handed back are the parse of what was
	/// written, so the screen never re-reads a file it just wrote.
	/// </summary>
	static void CheckEdit(string text, List<TomlSettings.DocEntry> doc, int index)
	{
		currentInput = text;
		if (doc == null || doc.Count == 0)
			return;
		var entry = doc[index];
		var raw = RandomRawValue();
		string newText, error;
		List<TomlSettings.DocEntry> written;
		if (!TomlEdit.TryReplaceValue(text, doc, entry, raw, out newText, out written, out error))
		{
			// Every value the screen offers has to be writable; anything the
			// reader accepts as a value and the writer refuses is a value the
			// screen can show and not save.
			if (TomlEdit.TryParseRawValue(raw, out _, out _))
				Report("a value the reader accepts is refused by the editor: " + Escape(raw)
					+ " (" + (error ?? "") + ")");
			return;
		}
		var expected = text.Substring(0, entry.ValueStart)
			+ raw.Trim()
			+ text.Substring(entry.ValueStart + entry.ValueLength);
		if (newText != expected)
			Report("an edit changed bytes outside the value span");

		List<TomlSettings.DocEntry> reparsed;
		string readError;
		if (!TomlSettings.TryReadDocument(newText, out reparsed, out readError))
		{
			Report("an edit the writer accepted does not parse");
			return;
		}
		if (reparsed.Count != doc.Count)
			Report("an edit changed the number of keys");
		else
		{
			for (var i = 0; i < doc.Count; i++)
			{
				if (reparsed[i].Name != doc[i].Name)
					Report("an edit changed a key name");
				else if (reparsed[i].Value != doc[i].Value && reparsed[i].ValueStart != entry.ValueStart)
					Report("an edit changed an unrelated key: " + doc[i].Name);
				else if (reparsed[i].Comment != doc[i].Comment)
					Report("an edit moved a key's help text: " + doc[i].Name);
			}
		}
		if (!Same(written, reparsed))
			Report("the parse handed back with a save is not the parse of the text written");
	}

	/// <summary>
	/// A value the writer produced has to read back as itself. This is the
	/// pair assertion across the file boundary: what the screen writes into
	/// another mod's file is what that mod's own reader will see.
	/// </summary>
	static void CheckWrittenValue(int index, string value)
	{
		if (IsUnpairedSurrogate(value))
			return; // not representable in TOML at all; not the writer's job
		var token = TomlEdit.EncodeString(value);
		List<TomlSettings.DocEntry> doc;
		string error;
		if (!TomlSettings.TryReadDocument("A = " + token + "\n", out doc, out error) || doc.Count != 1)
		{
			Report("a value the writer encoded does not parse: " + Escape(value)
				+ " as " + Escape(token));
			return;
		}
		if (doc[0].Value != value)
			Report("a value the writer encoded reads back changed: " + Escape(value)
				+ " as " + Escape(token));
	}

	static bool IsUnpairedSurrogate(string text)
	{
		for (var i = 0; i < text.Length; i++)
		{
			if (char.IsHighSurrogate(text[i]))
			{
				if (i + 1 >= text.Length || !char.IsLowSurrogate(text[i + 1]))
					return true;
				i++;
			}
			else if (char.IsLowSurrogate(text[i]))
				return true;
		}
		return false;
	}

	/// <summary>
	/// A mod name comes out of another mod's ModInfo.xml and is concatenated
	/// into a path the screen writes through. Whatever it holds, a name the
	/// resolver accepts must land inside the mod folder.
	/// </summary>
	static void CheckModName(int index)
	{
		var root = Path.Combine(Path.GetTempPath(), "wrench-fuzz", "Mods", "Example");
		var name = Next(3) == 0 ? RandomText(Next(10)) : Names[Next(Names.Length)];
		string tomlPath, error;
		bool ok;
		try
		{
			ok = ModTomlPath.TryResolve(root, name, out tomlPath, out error);
		}
		catch (Exception ex)
		{
			thrown++;
			Fail(index, "the mod name resolver threw " + ex.GetType().Name, name, ex.Message);
			return;
		}
		if (!ok)
		{
			if (tomlPath != null || string.IsNullOrEmpty(error))
				Report("a refused mod name came back with a path or no reason: " + Escape(name));
			return;
		}
		var full = Path.GetFullPath(tomlPath);
		var inside = Path.GetFullPath(Path.Combine(root, "Config") + Path.DirectorySeparatorChar);
		if (!full.StartsWith(inside, StringComparison.Ordinal))
			Report("an accepted mod name resolves outside the mod folder: " + Escape(name)
				+ " -> " + full);
	}

	static readonly string[] Names =
	{
		"Example", "Some.Mod 2", "../Escape", "sub/Escape", "..\\Escape",
		"/etc/Config", "C:Config", "Escape:stream", ".", "..", "",
		"caf\u00e9", "A B", "....//..", ".. ", " .", "\u65e5", "a\0b",
	};

	// -- the byte layer ---------------------------------------------------

	// Bytes that separate one decoder's answer from another's: the mark
	// sequences, the NUL half of a UTF-16 code unit, truncated and overlong
	// UTF-8 forms, and a surrogate half on its own.
	static readonly byte[] ByteAlphabet =
	{
		0x00, 0x09, 0x0A, 0x20, 0x22, 0x3D, 0x41, 0x61, 0x7F,
		0x80, 0x9F, 0xA0, 0xBF, 0xC0, 0xC2, 0xC3, 0xA9, 0xE0,
		0xED, 0xEF, 0xBB, 0xF0, 0xF4, 0xFE, 0xFF, 0x90,
	};

	static readonly byte[][] Marks =
	{
		new byte[] { 0xEF, 0xBB, 0xBF },
		new byte[] { 0xFF, 0xFE, 0x00, 0x00 },
		new byte[] { 0x00, 0x00, 0xFE, 0xFF },
		new byte[] { 0xFF, 0xFE },
		new byte[] { 0xFE, 0xFF },
	};

	/// <summary>
	/// Real settings bytes first: the file this mod ships, then that same
	/// text in each encoding the decoder knows, so a marked case starts from
	/// a body that is already valid rather than from noise. The encoders
	/// replace rather than throw, so a generated seed is always a byte array
	/// this harness can hand to the decoder.
	/// </summary>
	static List<byte[]> ByteCorpus()
	{
		var corpus = new List<byte[]>();
		var text = "AllowThing = true\nCount = 12\nLabel = \"café 日本\"\n";
		var root = AppContext.BaseDirectory;
		while (root != null && !File.Exists(Path.Combine(root, "ModInfo.xml")))
			root = Path.GetDirectoryName(root);
		if (root != null)
		{
			var shipped = Path.Combine(root, "Config", "Wrench.toml");
			if (File.Exists(shipped))
			{
				var bytes = File.ReadAllBytes(shipped);
				corpus.Add(bytes);
				text = new UTF8Encoding(false, false).GetString(bytes);
			}
		}
		corpus.Add(new UTF8Encoding(false, false).GetBytes(text));
		corpus.Add(WithMark(new UTF8Encoding(false, false), text));
		corpus.Add(WithMark(new UnicodeEncoding(false, false), text));
		corpus.Add(WithMark(new UnicodeEncoding(true, false), text));
		corpus.Add(WithMark(new UTF32Encoding(false, false), text));
		corpus.Add(WithMark(new UTF32Encoding(true, false), text));
		// A mark on its own, and a mark cut short: a file a writer was
		// interrupted while saving.
		foreach (var mark in Marks)
			corpus.Add(mark);
		corpus.Add(new byte[] { 0xEF, 0xBB });
		corpus.Add(new byte[] { 0xFF });
		return corpus;
	}

	static byte[] WithMark(Encoding encoding, string text)
	{
		var body = encoding.GetBytes(text);
		var mark = encoding.GetPreamble();
		if (mark.Length == 0)
			return body;
		var bytes = new byte[mark.Length + body.Length];
		Buffer.BlockCopy(mark, 0, bytes, 0, mark.Length);
		Buffer.BlockCopy(body, 0, bytes, mark.Length, body.Length);
		return bytes;
	}

	/// <summary>
	/// One to three byte edits over a seed: the same damage the string pass
	/// applies, at the level a downloaded file actually arrives in, plus
	/// whole marks spliced in and cut short.
	/// </summary>
	static byte[] MutateBytes(byte[] seed)
	{
		var bytes = new List<byte>(seed);
		var edits = 1 + Next(3);
		for (var edit = 0; edit < edits && bytes.Count > 0; edit++)
		{
			switch (Next(10))
			{
				case 0:
					bytes.Add(ByteAlphabet[Next(ByteAlphabet.Length)]);
					break;
				case 1:
				{
					var at = Next(bytes.Count);
					var mark = Next(3) == 0 ? RandomMark() : new byte[] { ByteAlphabet[Next(ByteAlphabet.Length)] };
					bytes.InsertRange(at, mark);
					break;
				}
				case 2:
					bytes.RemoveAt(Next(bytes.Count));
					break;
				case 3:
					bytes[Next(bytes.Count)] = ByteAlphabet[Next(ByteAlphabet.Length)];
					break;
				case 4:
					bytes.InsertRange(Next(bytes.Count), RandomMark());
					break;
				case 5:
				{
					// A truncation: a file caught mid-save, or a mark cut off.
					var at = Next(bytes.Count);
					bytes.RemoveRange(at, 1 + Next(bytes.Count - at));
					break;
				}
				case 6:
				{
					// A document that grew a second copy of itself.
					bytes.AddRange(RandomByteDocument());
					break;
				}
				default:
				{
					var at = Next(bytes.Count);
					var take = 1 + Next(bytes.Count - at);
					var chunk = new byte[take];
					bytes.CopyTo(at, chunk, 0, take);
					bytes.InsertRange(at, chunk);
					break;
				}
			}
		}
		return bytes.ToArray();
	}

	static byte[] RandomMark()
	{
		return Marks[Next(Marks.Length)];
	}

	static byte[] RandomByteDocument()
	{
		var text = Generated();
		switch (Next(5))
		{
			case 0: return WithMark(new UTF32Encoding(false, false), text);
			case 1: return WithMark(new UTF32Encoding(true, false), text);
			case 2: return WithMark(new UnicodeEncoding(false, false), text);
			case 3: return WithMark(new UnicodeEncoding(true, false), text);
			default: return WithMark(new UTF8Encoding(false, false), text);
		}
	}

	/// <summary>
	/// The whole file boundary in one case: bytes in, the same bytes out.
	///
	/// A settings file arrives inside a downloaded modlet, so the decoder is
	/// the first thing untrusted bytes meet. What has to hold is that a file
	/// this mod can read it can also write back byte for byte, mark included,
	/// because a save replaces the file with a re-encoding of what was read;
	/// that a file it refuses costs nothing and is refused, never a crash
	/// inside the game; and that the mark picks the encoding without changing
	/// whether the body decodes, which is what keeps a replacement character
	/// out of another mod's file.
	/// </summary>
	static void CheckBytes(int index, byte[] bytes)
	{
		currentInput = EscapeBytes(bytes);
		int preambleLength;
		var detected = TomlFile.DetectEncoding(bytes, out preambleLength);
		if (preambleLength < 0 || preambleLength > bytes.Length)
		{
			Report("the detected mark runs past the end of the file");
			return;
		}
		var mark = detected.GetPreamble();
		if (preambleLength == 0)
		{
			if (mark.Length != 0)
				Report("a file with no mark was read as carrying one");
		}
		else if (mark.Length != preambleLength || !StartsWith(bytes, mark, 0))
		{
			Report("the bytes stripped as a mark are not the detected encoding's mark");
		}

		string text;
		Encoding encoding;
		try
		{
			text = TomlFile.Decode(bytes, out encoding);
		}
		catch (DecoderFallbackException)
		{
			bytesRefused++;
			return; // a strict decoder refusing is the contract, not a failure
		}
		bytesAccepted++;

		// The pair assertion across the persistence boundary: the file this
		// mod read is the file it writes back, byte for byte.
		byte[] written;
		try
		{
			written = TomlFile.Encode(text, encoding);
		}
		catch (Exception ex)
		{
			thrown++;
			Fail(index, "the encoder threw " + ex.GetType().Name, currentInput, ex.Message);
			return;
		}
		if (written.Length != bytes.Length)
			Report("a decoded file re-encodes to a different length");
		else if (!SameBytes(written, bytes))
			Report("a decoded file does not re-encode to the bytes it was read from");

		// The same bytes twice, the same answer twice: no clock, order, or
		// static state between a read and the save that follows it.
		Encoding againEncoding;
		var again = TomlFile.Decode(bytes, out againEncoding);
		if (again != text || !SameMark(encoding, againEncoding))
			Report("two decodes of one file disagree");

		CheckMarkMakesNoDifference(bytes, preambleLength, mark);
		CheckParsedText(text);
	}

	/// <summary>
	/// Whether a 3-byte mark is on the front must not decide whether an
	/// invalid byte throws or arrives as U+FFFD, so the body and the same
	/// body behind the mark have to decode alike. Only the UTF-8 encodings
	/// can be compared this way: a UTF-16 body read on its own is not the
	/// text it holds, and a body that opens with a mark of its own is read
	/// as that mark first.
	/// </summary>
	static void CheckMarkMakesNoDifference(byte[] bytes, int preambleLength, byte[] mark)
	{
		if (mark.Length != 3 || preambleLength != 3)
			return; // the UTF-8 encoding carrying its own mark
		var body = new byte[bytes.Length - 3];
		Buffer.BlockCopy(bytes, 3, body, 0, body.Length);
		if (body.Length == 0 || StartsWithAnyMark(body))
			return;
		string plainText, markedText;
		Encoding plainEncoding, markedEncoding;
		var plainOk = TryDecode(body, out plainText, out plainEncoding);
		var markedOk = TryDecode(bytes, out markedText, out markedEncoding);
		if (plainOk != markedOk)
			Report("a byte order mark decided whether a file decodes at all");
		else if (plainOk && plainText != markedText)
			Report("a byte order mark changed the text a file decodes to");
	}

	/// <summary>
	/// What the screen then does with the text: the grammar refuses it or
	/// reads it, and a refusal says why, because that message is the only
	/// thing a player sees about a broken file.
	/// </summary>
	static void CheckParsedText(string text)
	{
		List<TomlSettings.DocEntry> doc;
		string error;
		if (TomlSettings.TryReadDocument(text, out doc, out error))
		{
			if (doc == null)
				Report("accepted with no entries");
			return;
		}
		if (string.IsNullOrEmpty(error))
			Report("a refused file gave no reason");
	}

	static bool TryDecode(byte[] bytes, out string text, out Encoding encoding)
	{
		try
		{
			text = TomlFile.Decode(bytes, out encoding);
			return true;
		}
		catch (DecoderFallbackException)
		{
			text = null;
			encoding = null;
			return false;
		}
	}

	static bool StartsWithAnyMark(byte[] bytes)
	{
		foreach (var mark in Marks)
		{
			if (StartsWith(bytes, mark, 0))
				return true;
		}
		return false;
	}

	static bool StartsWith(byte[] bytes, byte[] prefix, int offset)
	{
		if (prefix.Length == 0 || bytes.Length - offset < prefix.Length)
			return false;
		for (var i = 0; i < prefix.Length; i++)
		{
			if (bytes[offset + i] != prefix[i])
				return false;
		}
		return true;
	}

	static bool SameBytes(byte[] a, byte[] b)
	{
		if (a.Length != b.Length)
			return false;
		for (var i = 0; i < a.Length; i++)
		{
			if (a[i] != b[i])
				return false;
		}
		return true;
	}

	static bool SameMark(Encoding a, Encoding b)
	{
		if (a == null || b == null)
			return a == b;
		return SameBytes(a.GetPreamble(), b.GetPreamble());
	}

	static string EscapeBytes(byte[] bytes)
	{
		var shown = bytes.Length > 96 ? 96 : bytes.Length;
		var builder = new StringBuilder(shown * 2 + 8);
		builder.Append("0x");
		for (var i = 0; i < shown; i++)
			builder.Append(bytes[i].ToString("X2", CultureInfo.InvariantCulture));
		if (shown < bytes.Length)
			builder.Append("...");
		return builder.ToString();
	}

	// -- reporting ---------------------------------------------------------

	static void Report(string message)
	{
		failures++;
		Console.WriteLine("FAIL: " + message);
		// The input the case is standing on, so the failure is reproducible
		// from the report instead of from a debugger.
		Console.WriteLine("  input: " + Escape(currentInput));
	}

	static void Fail(int index, string message, string input, string detail)
	{
		failures++;
		Console.WriteLine("FAIL [case " + index.ToString(CultureInfo.InvariantCulture) + "]: "
			+ message + (detail.Length > 0 ? ": " + detail : ""));
		Console.WriteLine("  input: " + Escape(input));
	}

	static string Escape(string text)
	{
		var shown = text.Length > MaxShownChars ? text.Substring(0, MaxShownChars) + "..." : text;
		var builder = new StringBuilder(shown.Length + 8);
		builder.Append('"');
		foreach (var c in shown)
		{
			if (c == '"' || c == '\\')
				builder.Append('\\').Append(c);
			else if (c < ' ' || c == '\u007F')
				builder.Append("\\u").Append(((int)c).ToString("X4", CultureInfo.InvariantCulture));
			else
				builder.Append(c);
		}
		builder.Append('"');
		return builder.ToString();
	}
}
