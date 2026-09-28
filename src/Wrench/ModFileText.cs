using System.IO;
using System.Text;

namespace Wrench
{
	/// <summary>
	/// The one encoding every mod config file is read and written in: UTF-8,
	/// no byte order mark.
	///
	/// Without this the encoding is whatever each API defaults to, which is
	/// how a file read on one runtime is written back differently on another,
	/// and how a save turns a non-ASCII comment in another mod's config into
	/// replacement characters. Reading still honours a byte order mark when
	/// one is there, because a file may arrive from elsewhere; what goes back
	/// out is always plain UTF-8, which is what the TOML grammar on the other
	/// side expects.
	/// </summary>
	internal static class ModFileText
	{
		static readonly Encoding Utf8NoBom = new UTF8Encoding(false);

		public static string ReadAllText(string path)
		{
			return File.ReadAllText(path, Utf8NoBom);
		}

		public static void WriteAllText(string path, string text)
		{
			File.WriteAllText(path, text, Utf8NoBom);
		}

		/// <summary>
		/// A reader over a stream already opened for sharing, with the same
		/// encoding and the same byte order mark handling.
		/// </summary>
		public static StreamReader OpenText(Stream stream)
		{
			return new StreamReader(stream, Utf8NoBom, true);
		}
	}
}
