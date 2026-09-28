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
	///
	/// <see cref="TryReadDocument"/> is the same grammar with capture: each
	/// entry also carries its raw value span in the text, its value kind, and
	/// the comment block directly above the key (contiguous <c>#</c> lines;
	/// a blank line breaks the block; a comment trailing a value on the same
	/// line belongs to no key). The Mod Settings screen edits other mods'
	/// TOML files through these spans so everything outside the edited value
	/// survives byte-for-byte (<see cref="TomlEdit"/>).
	/// </summary>
	internal static class TomlSettings
	{
		internal enum ValueKind
		{
			Bool,
			Int,
			Float,
			String,
			Array,
		}

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

		internal sealed class DocEntry
		{
			public readonly string Name;
			/// <summary>Normalized value, in the TrySet grammar.</summary>
			public readonly string Value;
			public readonly ValueKind Kind;
			/// <summary>Start of the raw value token in the file text.</summary>
			public readonly int ValueStart;
			public readonly int ValueLength;
			/// <summary>Comment block directly above the key, '#' stripped; "" when none.</summary>
			public readonly string Comment;

			public DocEntry(string name, string value, ValueKind kind, int valueStart, int valueLength, string comment)
			{
				Name = name;
				Value = value;
				Kind = kind;
				ValueStart = valueStart;
				ValueLength = valueLength;
				Comment = comment;
			}
		}

		public static bool TryRead(string text, out List<Entry> entries, out string error)
		{
			entries = new List<Entry>();
			List<DocEntry> doc;
			if (!TryReadDocument(text, out doc, out error))
				return false;
			for (var i = 0; i < doc.Count; i++)
				entries.Add(new Entry(doc[i].Name, doc[i].Value));
			return true;
		}

		public static bool TryReadDocument(string text, out List<DocEntry> entries, out string error)
		{
			entries = new List<DocEntry>();
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
			/// <summary>The largest Unicode scalar value, U+10FFFF.</summary>
			const long MaxCodePoint = 0x10FFFF;

			/// <summary>
			readonly string text;
			int index;
			int line = 1;

			// Comment-block capture. Comments consumed inside a value (a
			// multiline array) or on the value's own closing line must not
			// leak into the next key's help block.
			readonly List<string> pendingComment = new List<string>();
			bool captureComments = true;
			bool lineHadContent;

			public Reader(string text)
			{
				this.text = text;
			}

			public bool ReadFile(out List<DocEntry> entries, out string error)
			{
				entries = new List<DocEntry>();
				error = null;
					// Keys are case-sensitive, exactly as TOML defines them: `Foo` and
				// `foo` are two keys, and treating them as one refuses a file that
				// is perfectly valid. The in-place writer and the by-name
				// relocation compare them the same way.
				var seen = new HashSet<string>(StringComparer.Ordinal);
				SkipIgnorable();
				while (!AtEnd)
				{
					if (Peek == '[')
					{
						error = "line " + line + ": tables are not a settings key.";
						return false;
					}

					var comment = string.Join("\n", pendingComment);
					pendingComment.Clear();

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
					var valueStart = index;
					string value;
					ValueKind kind;
					captureComments = false;
					var ok = ReadValue(out value, out kind, out error);
					if (!ok)
						return false;
					var valueLength = index - valueStart;
					if (!seen.Add(name))
					{
						error = "line " + line + ": duplicate key '" + name + "'.";
						return false;
					}
					entries.Add(new DocEntry(name, value, kind, valueStart, valueLength, comment));
					// Nothing but a comment may follow a value on its line.
					// `A = 0.001B = 2` read as two keys here would be written
					// back as `A = trueB = 2`, which the mod on the other side
					// of the file refuses, so a value spliced in place cannot
					// leave text the writer did not put there.
					SkipSpaces();
					if (!AtEnd && Peek != '#' && Peek != '\n' && Peek != '\r')
					{
						error = "line " + line + ": unexpected text after the value.";
						return false;
					}
					// A comment trailing the value on its own line is not the
					// next key's block; capture resumes on the next line.
					SkipRestOfLine();
					captureComments = true;
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

			bool ReadValue(out string value, out ValueKind kind, out string error)
			{
				value = null;
				kind = ValueKind.Bool;
				error = null;
				if (AtEnd)
				{
					error = "line " + line + ": missing value.";
					return false;
				}
				if (Peek == '"')
				{
					kind = ValueKind.String;
					return ReadBasicString(out value, out error);
				}
				if (Peek == '[')
				{
					kind = ValueKind.Array;
					return ReadArray(out value, out error);
				}
				if (Peek == 't' || Peek == 'f')
				{
					kind = ValueKind.Bool;
					return ReadBoolean(out value, out error);
				}
				if (Peek == '+' || Peek == '-' || IsDigit(Peek))
					return ReadNumber(out value, out kind, out error);

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
						// A raw control character (anything but tab) is not a
						// legal basic string, so the mod on the other side
						// would refuse the file Wrench just showed as
						// editable. Refusing it here keeps what the reader
						// accepts exactly what the writer can produce.
						if (c < ' ' && c != '\t' || c == '\u007F')
						{
							error = "line " + line + ": raw control character in string.";
							return false;
						}
						builder.Append(c);
						continue;
					}
					if (AtEnd)
					{
						error = "line " + line + ": unterminated string escape.";
						return false;
					}
					if (!ReadEscape(builder, out error))
						return false;
				}
				error = "line " + line + ": unterminated string.";
				return false;
			}

			/// <summary>
			/// One backslash escape of a basic string, the full TOML set, so
			/// a file the writer produced reads back unchanged and a file
			/// shipping <c>\f</c> or <c>"\u00e9"</c> is not refused wholesale.
			/// </summary>
			bool ReadEscape(StringBuilder builder, out string error)
			{
				error = null;
				var escaped = Next();
				if (escaped == 'n')
					builder.Append('\n');
				else if (escaped == 't')
					builder.Append('\t');
				else if (escaped == 'b')
					builder.Append('\b');
				else if (escaped == 'f')
					builder.Append('\f');
				else if (escaped == 'r')
					builder.Append('\r');
				else if (escaped == '\\' || escaped == '"')
					builder.Append(escaped);
				else if (escaped == 'u' || escaped == 'U')
				{
					if (!ReadEscapedCodePoint(escaped == 'u' ? 4 : 8, builder, out error))
						return false;
				}
				else
				{
					error = "line " + line + ": unsupported string escape.";
					return false;
				}
				return true;
			}

			/// <summary>
			/// The code point of a <c>\u</c>/<c>\U</c> escape, which may be a
			/// surrogate pair. An unpaired half is refused rather than
			/// appended: it is not a character, and every UTF-8 encoder
			/// downstream would silently turn it into U+FFFD.
			/// </summary>
			bool ReadEscapedCodePoint(int digits, StringBuilder builder, out string error)
			{
				error = null;
				long codePoint;
				if (!TryReadHex(digits, out codePoint))
				{
					error = "line " + line + ": malformed string escape; "
						+ digits + " hex digits expected.";
					return false;
				}
				if (digits == 4 && IsHighSurrogate((char)codePoint))
				{
					long low;
					if (index + 6 > text.Length || text[index] != '\\' || text[index + 1] != 'u'
						|| !TryReadHexAt(index + 2, 4, out low) || !IsLowSurrogate((char)low))
					{
						error = "line " + line + ": unpaired surrogate in string escape.";
						return false;
					}
					builder.Append((char)codePoint).Append((char)low);
					return true;
				}
				if (codePoint > MaxCodePoint
					|| (codePoint >= 0xD800 && codePoint <= 0xDFFF))
				{
					error = "line " + line + ": escape is not a Unicode scalar value.";
					return false;
				}
				if (codePoint <= 0xFFFF)
				{
					builder.Append((char)codePoint);
					return true;
				}
				builder.Append((char)(0xD800 + ((codePoint - 0x10000) >> 10)));
				builder.Append((char)(0xDC00 + ((codePoint - 0x10000) & 0x3FF)));
				return true;
			}

			/// <summary>
			/// Reads hex digits at the cursor and moves past them; nothing is
			/// consumed on a short or non-hex remainder, so the caller's
			/// error points at the escape it rejected. The accumulator is
		/// 64-bit because a <c>\U</c> escape is eight hex digits: folded
		/// into an <c>int</c> it wraps silently, and <c>\UFFFFFFFF</c>
		/// would read back as a small positive scalar instead of being
		/// refused.
			/// </summary>
			bool TryReadHex(int digits, out long value)
			{
				return TryReadHexAt(index, digits, out value);
			}

			/// <summary>
			/// As <see cref="TryReadHex"/>, from an offset: the caller has
			/// already looked at the bytes between.
			/// </summary>
			bool TryReadHexAt(int at, int digits, out long value)
			{
				value = 0;
				if (at < 0 || at + digits > text.Length)
					return false;
				for (var i = 0; i < digits; i++)
				{
					int nibble;
					var c = text[at + i];
					if (c >= '0' && c <= '9')
						nibble = c - '0';
					else if (c >= 'a' && c <= 'f')
						nibble = c - 'a' + 10;
					else if (c >= 'A' && c <= 'F')
						nibble = c - 'A' + 10;
					else
						return false;
					value = (value << 4) | (uint)nibble;
				}
				index = at + digits;
				return true;
			}

			static bool IsHighSurrogate(char c)
			{
				return c >= '\uD800' && c <= '\uDBFF';
			}

			static bool IsLowSurrogate(char c)
			{
				return c >= '\uDC00' && c <= '\uDFFF';
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
					if (!ReadValue(out item, out _, out error))
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

			bool ReadNumber(out string value, out ValueKind kind, out string error)
			{
				value = null;
				kind = ValueKind.Int;
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
					kind = ValueKind.Float;
					double parsed;
					if (!double.TryParse(token, NumberStyles.Float, CultureInfo.InvariantCulture, out parsed))
					{
						error = "line " + line + ": invalid number '" + token + "'.";
						return false;
					}
					if (double.IsNaN(parsed) || double.IsInfinity(parsed))
					{
						error = "line " + line + ": number '" + token
							+ "' is out of range for a 64-bit float.";
						return false;
					}
					value = FormatFloat(parsed);
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

			/// <summary>
			/// A parsed float back to a value token this same grammar reads
			/// as the identical double.
			///
			/// A fixed number of decimal places is not that: seven of them
			/// turn 0.00000001 into 0, and the row then shows and writes a
			/// setting the file never held. The shortest round-trip form
			/// ("R") is exact, but it may use exponent notation, which this
			/// grammar has no reader for, so that spelling is expanded to
			/// plain digits here. Zero and -0 both normalize to "0": TOML
			/// has one zero, and this text is the decoded value, not the
			/// file's raw token.
			/// </summary>
			static string FormatFloat(double value)
			{
				if (value == 0d)
					return "0";
				var text = value.ToString("R", CultureInfo.InvariantCulture);
				var exponent = text.IndexOfAny(new[] { 'E', 'e' });
				if (exponent < 0)
					return text;
				return ExpandExponent(text, exponent);
			}

			/// <summary>
			/// "1.5E-07" as "0.00000015": the mantissa's digits with the
			/// decimal point moved by the exponent, so the result carries no
			/// exponent this grammar cannot read back.
			/// </summary>
			static string ExpandExponent(string text, int exponentAt)
			{
				var exponent = int.Parse(text.Substring(exponentAt + 1),
					NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture);
				var mantissa = text.Substring(0, exponentAt);
				var negative = mantissa.StartsWith("-", StringComparison.Ordinal);
				if (negative)
					mantissa = mantissa.Substring(1);
				var point = mantissa.IndexOf('.');
				var digits = point < 0 ? mantissa : mantissa.Remove(point, 1);
				// Where the decimal point lands among `digits` once the
				// exponent has moved it: past both ends needs zero padding.
				var position = (point < 0 ? digits.Length : point) + exponent;
				string body;
				if (position <= 0)
					body = "0." + new string('0', -position) + digits;
				else if (position >= digits.Length)
					body = digits + new string('0', position - digits.Length);
				else
					body = digits.Substring(0, position) + "." + digits.Substring(position);
				return negative ? "-" + body : body;
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

			// Consumes spaces and an optional comment trailing a value, up to
			// (not including) the newline, so it is never captured as the
			// next key's comment block. Accepts exactly what SkipIgnorable
			// would have; the grammar is unchanged.
			void SkipRestOfLine()
			{
				SkipSpaces();
				if (!AtEnd && Peek == '#')
					while (!AtEnd && Peek != '\n')
						index++;
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
						var start = index + 1;
						while (!AtEnd && Peek != '\n')
							index++;
						if (captureComments)
							pendingComment.Add(text.Substring(start, index - start).Trim());
						lineHadContent = true;
						continue;
					}
					if (Peek == '\n')
					{
						if (!lineHadContent && captureComments)
							pendingComment.Clear();
						lineHadContent = false;
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
