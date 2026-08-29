using System;
using System.Collections.Generic;
using System.IO;
using Wrench;

// Offline gate for the TOML document parser and the in-place writer:
// parse captures spans, kinds, and comment blocks; an edit changes one
// value span and nothing else, byte-for-byte. Run by
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
		TestCrlf();
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
		if (!TomlEdit.TryReplaceValue(Fixture, entry, newRaw, out newText, out error))
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
		Check("reject a non-value", !TomlEdit.TryReplaceValue(Fixture, count, "nope", out newText, out error));
		Check("reject trailing garbage", !TomlEdit.TryReplaceValue(Fixture, count, "1 2", out newText, out error));
		Check("reject a key injection", !TomlEdit.TryReplaceValue(Fixture, count, "1\nInjected = 2", out newText, out error));
		Check("reject a comment rider", !TomlEdit.TryReplaceValue(Fixture, count, "1 # note", out newText, out error));
		Check("reject an empty value", !TomlEdit.TryReplaceValue(Fixture, count, "", out newText, out error));

		Check("reject a table file", !TomlSettings.TryReadDocument("[table]\nA = 1\n", out doc, out error));
		Check("reject a duplicate key", !TomlSettings.TryReadDocument("A = 1\nA = 2\n", out doc, out error));
		Check("reject a dotted key", !TomlSettings.TryReadDocument("a.b = 1\n", out doc, out error));
	}

	static void TestCrlf()
	{
		var crlf = "# help\r\nA = 1\r\nB = 2\r\n";
		List<TomlSettings.DocEntry> doc;
		string error, newText;
		Check("crlf parses", TomlSettings.TryReadDocument(crlf, out doc, out error), error ?? "");
		Check("crlf comment captured", doc[0].Comment == "help");
		var a = doc.Find(e => e.Name == "A");
		Check("crlf edit keeps line endings",
			TomlEdit.TryReplaceValue(crlf, a, "7", out newText, out error)
			&& newText == "# help\r\nA = 7\r\nB = 2\r\n",
			error ?? "");
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

	static string Raw(string text, TomlSettings.DocEntry entry)
	{
		return text.Substring(entry.ValueStart, entry.ValueLength);
	}
}
