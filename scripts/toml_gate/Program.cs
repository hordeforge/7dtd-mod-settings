using System;
using System.Collections.Generic;
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
		TestLegacyEquivalence();
		TestEdits();
		TestRejections();
		TestUnicodeAndEscapes();
		TestCrlf();
		TestFileIo();
		TestModTomlPath();
		TestShippedFile();
		Console.WriteLine(failures + " failures.");
		Environment.Exit(failures > 0 ? 1 : 0);
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

	static void TestLegacyEquivalence()
	{
		List<TomlSettings.DocEntry> doc;
		List<TomlSettings.Entry> flat;
		string error;
		TomlSettings.TryReadDocument(Fixture, out doc, out error);
		Check("TryRead still parses", TomlSettings.TryRead(Fixture, out flat, out error), error ?? "");
		Check("TryRead matches the document entries",
			flat.Count == doc.Count
			&& string.Join(";", flat.ConvertAll(e => e.Name + "=" + e.Value))
			== string.Join(";", doc.ConvertAll(e => e.Name + "=" + e.Value)));
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

		Check("reject a table file", !TomlSettings.TryReadDocument("[table]\nA = 1\n", out doc, out error));
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
			Check("a case-variant edit lands on the named key only",
				TomlEdit.TryReplaceValue("Foo = 1\nfoo = 2\n", doc[1], "9", out caseText, out caseError)
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
			&& TomlEdit.TryReplaceValue(unicode, b, "42", out newText, out error)
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
	// (Windows editors write one), CRLF, UTF-16, and a file another process
	// holds open while it watches for changes.
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
			SharedAccessWhileOpen(dir);
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

		Encoding read;
		var text = TomlFile.ReadAllText(path, out read);
		Check(name + ": read decodes the body", text == body);
		Check(name + ": read keeps the declared encoding", read.GetPreamble().SequenceEqual(preamble));

		TomlFile.WriteAllText(path, text, read);
		Check(name + ": write without an edit is byte-identical",
			File.ReadAllBytes(path).SequenceEqual(original));

		List<TomlSettings.DocEntry> doc;
		string error, newText;
		if (!TomlSettings.TryReadDocument(text, out doc, out error))
		{
			Check(name + ": document parses", false, error ?? "");
			return;
		}
		var entry = doc.Find(e => e.Name == "A");
		Check(name + ": edit replaces the value span",
			TomlEdit.TryReplaceValue(text, entry, "7", out newText, out error)
			&& text.Replace("A = 1", "A = 7") == newText, error ?? "");
		TomlFile.WriteAllText(path, newText, read);
		var reread = File.ReadAllBytes(path);
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
		TomlFile.WriteAllText(path, "A = 1\n", new UTF8Encoding(false));
		Encoding read;
		try
		{
			using (var watcher = new FileStream(path, FileMode.Open, FileAccess.ReadWrite,
				FileShare.ReadWrite | FileShare.Delete))
			{
				TomlFile.ReadAllText(path, out read);
				TomlFile.WriteAllText(path, "A = 2\n", new UTF8Encoding(false));
			}
			Check("read and write tolerate a concurrent holder", read != null && File.ReadAllText(path) == "A = 2\n");
		}
		catch (IOException ex)
		{
			Check("read and write tolerate a concurrent holder", false, ex.Message);
		}
	}

	static string Raw(string text, TomlSettings.DocEntry entry)
	{
		return text.Substring(entry.ValueStart, entry.ValueLength);
	}
}
