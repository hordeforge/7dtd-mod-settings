using System.IO;
using System.Text;

namespace Wrench
{
	/// <summary>
	/// The one encoding Wrench's own <c>Config/Wrench.toml</c> is read and
	/// written in: UTF-8, no byte order mark. Another mod's settings file
	/// keeps the encoding its bytes declare; that is <see cref="TomlFile"/>.
	///
	/// Without this the encoding is whatever each API defaults to, which is
	/// how a file read on one runtime is written back differently on another,
	/// and how a save turns a non-ASCII comment in this mod's config into
	/// replacement characters. Reading still honours a byte order mark when
	/// one is there, because a file may arrive from elsewhere; what goes back
	/// out is always plain UTF-8, which is what the TOML grammar on the other
	/// side expects.
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
