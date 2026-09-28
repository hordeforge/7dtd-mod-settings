using System;
using System.Text;

namespace Wrench
{
	/// <summary>
	/// Byte-faithful coding for a mod's <c>Config/&lt;Mod&gt;.toml</c>: the
	/// bytes a file is in become text, and the same text becomes those bytes
	/// again, mark included.
	///
	/// Pure by contract: it takes and returns bytes and never names a path, so
	/// the one filesystem this mod reads and writes through
	/// (<see cref="ModFileSystem"/>) is the only code that opens a file. A
	/// read and a write of the same save then reach the same disk, which is
	/// what lets a simulated run drive a save end to end.
	///
	/// The defaults of <c>File.ReadAllText</c> and <c>File.WriteAllText</c>
	/// get two things wrong on the platform most players run. A byte order
	/// mark the file was saved with is stripped on read and never written
	/// back, so the first edit changes bytes outside the edited span, which
	/// ADR 0001 forbids. And both open with <c>FileShare.Read</c>, which fails
	/// with a sharing violation on Windows while the hot-reloading mod's own
	/// save watcher holds the same file open for read and write (the mode
	/// <c>ModSettings</c> polls with), so the share mode lives with the opens
	/// in <see cref="SystemFileSystem"/>.
	/// </summary>
	internal static class TomlFile
	{
		static readonly Encoding[] KnownEncodings =
		{
			new UTF8Encoding(true),
			// UTF-32LE's mark starts with UTF-16LE's, so it is tested first.
			new UTF32Encoding(false, true),
			new UTF32Encoding(true, true),
			new UnicodeEncoding(false, true),
			new UnicodeEncoding(true, true),
		};

		/// <summary>
		/// Decodes a settings file's bytes, reporting the encoding its mark
		/// declared so <see cref="Encode"/> can write the same file back.
		/// </summary>
		public static string Decode(byte[] bytes, out Encoding encoding)
		{
			int preambleLength;
			encoding = DetectEncoding(bytes, out preambleLength);
			return encoding.GetString(bytes, preambleLength, bytes.Length - preambleLength);
		}

		/// <summary>
		/// Encodes a settings file in the encoding it was decoded with, byte
		/// order mark included when it had one.
		/// </summary>
		public static byte[] Encode(string text, Encoding encoding)
		{
			var preamble = encoding.GetPreamble();
			var body = encoding.GetBytes(text);
			if (preamble.Length == 0)
				return body;
			var bytes = new byte[preamble.Length + body.Length];
			Buffer.BlockCopy(preamble, 0, bytes, 0, preamble.Length);
			Buffer.BlockCopy(body, 0, bytes, preamble.Length, body.Length);
			return bytes;
		}

		/// <summary>
		/// The encoding whose byte order mark the bytes start with, and how
		/// long that mark is. No mark means UTF-8 without one, the encoding
		/// every other reader of these files assumes.
		/// </summary>
		static Encoding DetectEncoding(byte[] bytes, out int preambleLength)
		{
			foreach (var candidate in KnownEncodings)
			{
				var preamble = candidate.GetPreamble();
				if (StartsWith(bytes, preamble))
				{
					preambleLength = preamble.Length;
					return candidate;
				}
			}
			preambleLength = 0;
			return new UTF8Encoding(false);
		}

		static bool StartsWith(byte[] bytes, byte[] prefix)
		{
			if (prefix.Length == 0 || bytes.Length < prefix.Length)
				return false;
			for (var i = 0; i < prefix.Length; i++)
			{
				if (bytes[i] != prefix[i])
					return false;
			}
			return true;
		}
	}
}
