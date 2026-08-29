using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Wrench
{
	/// <summary>
	/// A TOML subset reader for <c>Config/Wrench.toml</c>.
	///
	/// Supports bare keys, booleans, integers, floats, basic strings, and
	/// arrays of those (including multiline arrays and <c>#</c> comments).
	/// Tables, dotted keys, dates, and multiline strings are rejected so a
	/// file that is not this mod's settings cannot be mistaken for one.
	/// Array values are joined with commas so <see cref="ModSettings.TrySet"/>
	/// can keep one value grammar with the console command.
	/// </summary>
	internal static class TomlSettings
	{
		internal sealed class Entry
		{
			public readonly string Name;
			public readonly string Value;

			public Entry(string name, string value)
			{
				Name = name;
				Value = value;
			}
		}

		public static bool TryRead(string text, out List<Entry> entries, out string error)
		{
			entries = new List<Entry>();
			error = null;
			if (text == null)
			{
				error = "settings text is missing.";
				return false;
			}

			try
			{
				var reader = new Reader(text);
				return reader.ReadFile(out entries, out error);
			}
			catch (Exception ex)
			{
				error = ex.Message;
				return false;
			}
		}

		sealed class Reader
		{
			readonly string text;
			int index;
			int line = 1;

			public Reader(string text)
			{
				this.text = text;
			}

			public bool ReadFile(out List<Entry> entries, out string error)
			{
				entries = new List<Entry>();
				error = null;
				var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
				SkipIgnorable();
				while (!AtEnd)
				{
					if (Peek == '[')
					{
						error = "line " + line + ": tables are not a settings key.";
						return false;
					}

					string name;
					if (!ReadBareKey(out name, out error))
						return false;
					SkipSpaces();
					if (Peek != '=')
					{
						error = "line " + line + ": expected '=' after '" + name + "'.";
						return false;
					}
					index++;
					SkipSpaces();
					string value;
					if (!ReadValue(out value, out error))
						return false;
					if (!seen.Add(name))
					{
						error = "line " + line + ": duplicate key '" + name + "'.";
						return false;
					}
					entries.Add(new Entry(name, value));
					SkipIgnorable();
				}
				return true;
			}

			bool ReadBareKey(out string name, out string error)
			{
				name = null;
				error = null;
				if (AtEnd || !IsBareKeyChar(Peek, true))
				{
					error = "line " + line + ": expected a setting name.";
					return false;
				}
				var start = index;
				index++;
				while (!AtEnd && IsBareKeyChar(Peek, false))
					index++;
				name = text.Substring(start, index - start);
				return true;
			}

			bool ReadValue(out string value, out string error)
			{
				value = null;
				error = null;
				if (AtEnd)
				{
					error = "line " + line + ": missing value.";
					return false;
				}
				if (Peek == '"')
					return ReadBasicString(out value, out error);
				if (Peek == '[')
					return ReadArray(out value, out error);
				if (Peek == 't' || Peek == 'f')
					return ReadBoolean(out value, out error);
				if (Peek == '+' || Peek == '-' || IsDigit(Peek))
					return ReadNumber(out value, out error);

				error = "line " + line + ": unsupported value.";
				return false;
			}

			bool ReadBasicString(out string value, out string error)
			{
				value = null;
				error = null;
				index++;
				var builder = new StringBuilder();
				while (!AtEnd)
				{
					var c = Next();
					if (c == '"')
					{
						value = builder.ToString();
						return true;
					}
					if (c == '\n')
					{
						error = "line " + line + ": unterminated string.";
						return false;
					}
					if (c != '\\')
					{
						builder.Append(c);
						continue;
					}
					if (AtEnd)
					{
						error = "line " + line + ": unterminated string escape.";
						return false;
					}
					var escaped = Next();
					if (escaped == 'n')
						builder.Append('\n');
					else if (escaped == 't')
						builder.Append('\t');
					else if (escaped == '\\' || escaped == '"')
						builder.Append(escaped);
					else
					{
						error = "line " + line + ": unsupported string escape.";
						return false;
					}
				}
				error = "line " + line + ": unterminated string.";
				return false;
			}

			bool ReadArray(out string value, out string error)
			{
				value = null;
				error = null;
				index++;
				var parts = new List<string>();
				SkipIgnorable();
				while (!AtEnd && Peek != ']')
				{
					string item;
					if (!ReadValue(out item, out error))
						return false;
					parts.Add(item);
					SkipIgnorable();
					if (Peek == ',')
					{
						index++;
						SkipIgnorable();
					}
					else if (Peek != ']')
					{
						error = "line " + line + ": expected ',' or ']' in array.";
						return false;
					}
				}
				if (AtEnd || Peek != ']')
				{
					error = "line " + line + ": unterminated array.";
					return false;
				}
				index++;
				value = string.Join(",", parts);
				return true;
			}

			bool ReadBoolean(out string value, out string error)
			{
				value = null;
				error = null;
				if (MatchWord("true"))
				{
					value = "true";
					return true;
				}
				if (MatchWord("false"))
				{
					value = "false";
					return true;
				}
				error = "line " + line + ": expected true or false.";
				return false;
			}

			bool ReadNumber(out string value, out string error)
			{
				value = null;
				error = null;
				var start = index;
				if (Peek == '+' || Peek == '-')
					index++;
				if (AtEnd || !IsDigit(Peek))
				{
					error = "line " + line + ": expected a number.";
					return false;
				}
				while (!AtEnd && IsDigit(Peek))
					index++;
				var isFloat = false;
				if (!AtEnd && Peek == '.')
				{
					isFloat = true;
					index++;
					if (AtEnd || !IsDigit(Peek))
					{
						error = "line " + line + ": expected digits after '.'.";
						return false;
					}
					while (!AtEnd && IsDigit(Peek))
						index++;
				}
				var token = text.Substring(start, index - start);
				if (isFloat)
				{
					double parsed;
					if (!double.TryParse(token, NumberStyles.Float, CultureInfo.InvariantCulture, out parsed))
					{
						error = "line " + line + ": invalid number '" + token + "'.";
						return false;
					}
					value = parsed.ToString("0.#######", CultureInfo.InvariantCulture);
					return true;
				}

				long integer;
				if (!long.TryParse(token, NumberStyles.Integer, CultureInfo.InvariantCulture, out integer))
				{
					error = "line " + line + ": invalid number '" + token + "'.";
					return false;
				}
				value = integer.ToString(CultureInfo.InvariantCulture);
				return true;
			}

			bool MatchWord(string word)
			{
				if (index + word.Length > text.Length)
					return false;
				if (string.Compare(text, index, word, 0, word.Length, StringComparison.Ordinal) != 0)
					return false;
				var after = index + word.Length;
				if (after < text.Length && IsBareKeyChar(text[after], false))
					return false;
				index = after;
				return true;
			}

			void SkipIgnorable()
			{
				while (!AtEnd)
				{
					SkipSpaces();
					if (AtEnd)
						return;
					if (Peek == '#')
					{
						while (!AtEnd && Peek != '\n')
							index++;
						continue;
					}
					if (Peek == '\n')
					{
						index++;
						line++;
						continue;
					}
					if (Peek == '\r')
					{
						index++;
						continue;
					}
					return;
				}
			}

			void SkipSpaces()
			{
				while (!AtEnd && (Peek == ' ' || Peek == '\t'))
					index++;
			}

			bool AtEnd
			{
				get { return index >= text.Length; }
			}

			char Peek
			{
				get { return text[index]; }
			}

			char Next()
			{
				var c = text[index++];
				if (c == '\n')
					line++;
				return c;
			}

			static bool IsDigit(char c)
			{
				return c >= '0' && c <= '9';
			}

			static bool IsBareKeyChar(char c, bool first)
			{
				if (c >= 'A' && c <= 'Z')
					return true;
				if (c >= 'a' && c <= 'z')
					return true;
				if (!first && IsDigit(c))
					return true;
				return c == '_' || c == '-';
			}
		}
	}
}
