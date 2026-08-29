using System.Collections.Generic;
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
		/// Validates one raw value token against the shared TOML subset
		/// grammar (a bare <c>true</c>, <c>-3</c>, <c>0.5</c>, <c>"text"</c>,
		/// or <c>[...]</c> array) and returns its normalized value.
		/// </summary>
		public static bool TryParseRawValue(string raw, out string normalized, out TomlSettings.ValueKind kind, out string error)
		{
			normalized = null;
			kind = TomlSettings.ValueKind.Bool;
			raw = (raw ?? "").Trim();
			List<TomlSettings.DocEntry> entries;
			if (!TomlSettings.TryReadDocument("v = " + raw, out entries, out error))
				return false;
			// The probe line must consume the whole token: "true # x" would
			// otherwise validate as its first word.
			if (entries.Count != 1 || entries[0].ValueLength != raw.Length)
			{
				error = "not a single value.";
				return false;
			}
			normalized = entries[0].Value;
			kind = entries[0].Kind;
			return true;
		}

		/// <summary>Encodes UI text as a TOML basic string token.</summary>
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
					builder.Append("\\t");
				else
					builder.Append(c);
			}
			builder.Append('"');
			return builder.ToString();
		}

		/// <summary>
		/// Replaces the value span of <paramref name="entry"/> (an entry of
		/// <paramref name="text"/>) with <paramref name="newRaw"/> and
		/// verifies the result: it must re-parse, keep every key, and change
		/// no other entry. On failure the original text stands.
		/// </summary>
		public static bool TryReplaceValue(string text, TomlSettings.DocEntry entry, string newRaw, out string newText, out string error)
		{
			newText = null;
			string normalized;
			TomlSettings.ValueKind kind;
			if (!TryParseRawValue(newRaw, out normalized, out kind, out error))
				return false;
			newRaw = newRaw.Trim();

			var candidate = text.Substring(0, entry.ValueStart)
				+ newRaw
				+ text.Substring(entry.ValueStart + entry.ValueLength);

			List<TomlSettings.DocEntry> before;
			List<TomlSettings.DocEntry> after;
			string parseError;
			if (!TomlSettings.TryReadDocument(text, out before, out parseError)
				|| !TomlSettings.TryReadDocument(candidate, out after, out parseError))
			{
				error = "edited file no longer parses: " + parseError;
				return false;
			}
			if (before.Count != after.Count)
			{
				error = "edit changed the number of keys.";
				return false;
			}
			for (var i = 0; i < before.Count; i++)
			{
				if (before[i].Name != after[i].Name)
				{
					error = "edit changed key '" + before[i].Name + "'.";
					return false;
				}
				var isEdited = before[i].ValueStart == entry.ValueStart;
				if (isEdited)
				{
					if (after[i].Value != normalized)
					{
						error = "edited value did not take.";
						return false;
					}
				}
				else if (before[i].Value != after[i].Value)
				{
					error = "edit changed unrelated key '" + before[i].Name + "'.";
					return false;
				}
			}
			newText = candidate;
			return true;
		}
	}
}
