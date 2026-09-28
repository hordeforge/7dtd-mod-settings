using System.IO;
using System.Text;

namespace Wrench
{
	/// <summary>
	/// The one encoding this mod's own config file is read in: UTF-8, no byte
	/// order mark.
	///
	/// Without this the encoding is whatever each API defaults to, which is
	/// how a file read on one runtime is written back differently on another,
	/// and how a save turns a non-ASCII comment into replacement characters.
	/// Reading still honours a byte order mark when one is there, because a
	/// file may arrive from elsewhere.
	/// </summary>
	internal static class ModFileText
	{
		static readonly Encoding Utf8NoBom = new UTF8Encoding(false);

		/// <summary>
		/// A reader over a stream already opened for sharing, with that
		/// encoding and that byte order mark handling.
		/// </summary>
		public static StreamReader OpenText(Stream stream)
		{
			return new StreamReader(stream, Utf8NoBom, true);
		}
	}
}
