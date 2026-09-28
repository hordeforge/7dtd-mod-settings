using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Wrench
{
	/// <summary>
	/// In-place edits of another mod's <c>Config/&lt;Mod&gt;.toml</c>.
	///
	/// The only mutation is replacing one key's raw value span (captured by
	/// <see cref="TomlSettings.TryReadDocument"/>) with a new raw token, so
	/// comments, ordering, and layout survive byte-for-byte. Every edit is
	/// verified by re-parsing the result before it is handed back; a file
	/// the parser rejects is never written to (ADR 0001).
	/// </summary>
	internal static class TomlEdit
	{
		/// <summary>
		/// What the user has to type. The value grammar is the whole
		/// vocabulary here, and the parse error of the probe line would quote
		/// a line number of text the user never saw.
		/// </summary>
		const string ValueHint = "Enter a value: true, 12, 0.5, \"text\", or [a, b].";

		/// <summary>
		/// Validates one raw value token against the shared TOML subset
		/// grammar (a bare <c>true</c>, <c>-3</c>, <c>0.5</c>, <c>"text"</c>,
		/// or <c>[...]</c> array) and returns its normalized value.
		/// </summary>
		public static bool TryParseRawValue(string raw, out string normalized, out string error)
		{
			normalized = null;
			raw = (raw ?? "").Trim();
			List<TomlSettings.DocEntry> entries;
			if (!TomlSettings.TryReadDocument("v = " + raw, out entries, out error))
			{
				error = ValueHint;
				return false;
			}
			// The probe line must consume the whole token: "true # x" would
			// otherwise validate as its first word.
			if (entries.Count != 1 || entries[0].ValueLength != raw.Length)
			{
				error = ValueHint + " One value per key.";
				return false;
			}
			normalized = entries[0].Value;
			return true;
		}

		/// <summary>
		/// Encodes UI text as a TOML basic string token.
		///
		/// Every control character is escaped, not just the two that read
		/// well: a bare CR, NUL, or ESC written literally is not a legal
		/// TOML basic string, and the mod on the other side of this file
		/// would refuse the whole document over a value Wrench itself
		/// produced. Tab is the one control character TOML allows raw.
		/// </summary>
		public static string EncodeString(string text)
		{
			var builder = new StringBuilder(text.Length + 2);
			builder.Append('"');
			foreach (var c in text)
			{
				if (c == '"' || c == '\\')
					builder.Append('\\').Append(c);
				else if (c == '\n')
					builder.Append("\\n");
				else if (c == '\t')
					builder.Append(c);
				else if (c == '\b')
					builder.Append("\\b");
				else if (c == '\f')
					builder.Append("\\f");
				else if (c == '\r')
					builder.Append("\\r");
				else if (c < ' ' || c == '\u007F')
					builder.Append("\\u").Append(((int)c).ToString("X4", CultureInfo.InvariantCulture));
				else
					builder.Append(c);
			}
			builder.Append('"');
			return builder.ToString();
		}

		/// <summary>
		/// Replaces the value span of <paramref name="entry"/> (an entry of
		/// <paramref name="text"/>, taken from <paramref name="before"/>, the
		/// caller's own parse of that text) with <paramref name="newRaw"/> and
		/// verifies the result: it must re-parse, keep every key, and change
		/// no other entry. On failure the original text stands.
		///
		/// The verified parse of the result is handed back as
		/// <paramref name="after"/>, so the caller holds the new state without
		/// reading and re-parsing the file it just wrote.
		/// </summary>
		public static bool TryReplaceValue(string text, List<TomlSettings.DocEntry> before, TomlSettings.DocEntry entry, string newRaw, out string newText, out List<TomlSettings.DocEntry> after, out string error)
		{
			newText = null;
			after = null;
			string normalized;
			if (!TryParseRawValue(newRaw, out normalized, out error))
				return false;
			newRaw = newRaw.Trim();

			var candidate = text.Substring(0, entry.ValueStart)
				+ newRaw
				+ text.Substring(entry.ValueStart + entry.ValueLength);

			string parseError;
			List<TomlSettings.DocEntry> parsed;
			if (!TomlSettings.TryReadDocument(candidate, out parsed, out parseError))
			{
				error = "edited file no longer parses: " + parseError;
				return false;
			}
			if (before.Count != parsed.Count)
			{
				error = "edit changed the number of keys.";
				return false;
			}
			for (var i = 0; i < before.Count; i++)
			{
				if (before[i].Name != parsed[i].Name)
				{
					error = "edit changed key '" + before[i].Name + "'.";
					return false;
				}
				var isEdited = before[i].ValueStart == entry.ValueStart;
				if (isEdited)
				{
					if (parsed[i].Value != normalized)
					{
						error = "edited value did not take.";
						return false;
					}
				}
				else if (before[i].Value != parsed[i].Value)
				{
					error = "edit changed unrelated key '" + before[i].Name + "'.";
					return false;
				}
			}
			newText = candidate;
			after = parsed;
			return true;
		}
	}
}
