using System;
using System.IO;
using System.Text;

namespace Wrench
{
	/// <summary>
	/// Byte-faithful text I/O for a mod's <c>Config/&lt;Mod&gt;.toml</c>.
	///
	/// <see cref="File"/>/<see cref="StreamReader"/> defaults get two things
	/// wrong on the platform most players run. A byte-order mark the file was
	/// saved with is stripped on read and never written back, so the first
	/// edit changes bytes outside the edited span, which is exactly what
	/// ADR 0001 forbids. And <c>File.ReadAllText</c> and
	/// <c>File.WriteAllText</c> open with <see cref="FileShare.Read"/>,
	/// which fails with a sharing violation on Windows while the
	/// hot-reloading mod's own save watcher holds the same file open for
	/// read and write (the mode <c>ModSettings</c> polls with). Both sides
	/// here share that tolerant mode.
	/// </summary>
	internal static class TomlFile
	{
		/// <summary>Share mode that tolerates a concurrent reader or writer.</summary>
		const FileShare SharedAccess = FileShare.ReadWrite | FileShare.Delete;

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
		/// Reads a settings file, reporting the encoding its bytes declared
		/// so <see cref="WriteAllText"/> can write the same file back.
		/// </summary>
		public static string ReadAllText(string path, out Encoding encoding)
		{
			byte[] bytes;
			using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, SharedAccess))
			using (var buffer = new MemoryStream())
			{
				stream.CopyTo(buffer);
				bytes = buffer.ToArray();
			}
			int preambleLength;
			encoding = DetectEncoding(bytes, out preambleLength);
			return encoding.GetString(bytes, preambleLength, bytes.Length - preambleLength);
		}

		/// <summary>
		/// Writes a settings file in the encoding it was read with, byte
		/// order mark included when it had one.
		/// </summary>
		public static void WriteAllText(string path, string text, Encoding encoding)
		{
			byte[] preamble = encoding.GetPreamble();
			var body = encoding.GetBytes(text);
			using (var stream = new FileStream(path, FileMode.Create, FileAccess.Write, SharedAccess))
			{
				if (preamble.Length > 0)
					stream.Write(preamble, 0, preamble.Length);
				stream.Write(body, 0, body.Length);
			}
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
