using System;
using System.IO;
using System.Text;

namespace Wrench
{
	/// <summary>
	/// The file operations this mod's two settings paths need, behind one
	/// seam: the file <see cref="ModSettings"/> watches and re-reads, and the
	/// file <see cref="TargetMod"/> stages and swaps in.
	///
	/// A simulated run puts a filesystem of its own in
	/// <see cref="ModFileSystem.Current"/> and gets the decisions this mod
	/// makes, without the real ones: a save can lose the race to a reader
	/// the way it does on a player's disk, a write can fail half way, and a
	/// reload can happen at a chosen moment rather than whenever the
	/// scheduler gets round to it. The production implementation is the
	/// only one that touches a disk.
	/// </summary>
	internal interface IFileSystem
	{
		/// <summary>Whether the path is there.</summary>
		bool Exists(string path);

		/// <summary>
		/// The file's write time and length in one metadata read, which is
		/// all the settings watch asks for and asks for four times a second
		/// for as long as the game runs. False with a null
		/// <paramref name="error"/> means the file is simply not there, the
		/// normal state after a player deletes it; false with a reason means
		/// the metadata could not be read.
		/// </summary>
		bool TryGetStamp(string path, out DateTime writeUtc, out long length, out string error);

		/// <summary>
		/// Reads and decodes a text file whose encoding is already fixed
		/// (Wrench's own), while another process holds it open, which the mod
		/// whose settings are being read does for the few milliseconds of
		/// its own watch. A file whose bytes declare their encoding is read
		/// with <see cref="ReadAllBytes"/> and decoded with
		/// <see cref="TomlFile"/>, so the declared encoding survives the
		/// round trip.
		/// </summary>
		string ReadAllText(string path);

		/// <summary>
		/// Reads a target mod's settings file as its bytes decode them, and
		/// reports the encoding those bytes declared, so the save writes the
		/// file back the way it was read. The single-encoding read above is
		/// not enough: a byte order mark the file was saved with is stripped
		/// on read and never written back, which changes bytes outside the
		/// edited value span.
		/// </summary>
		string ReadAllText(string path, out Encoding encoding);

		/// <summary>Reads a file's bytes, byte order mark included.</summary>
		byte[] ReadAllBytes(string path);

		/// <summary>
		/// Writes text in the given encoding, byte order mark included when
		/// that encoding has one, so a file can be written back the way it
		/// was read.
		///
		/// The path is a staging name beside the file being saved, and
		/// anything already at it is unlinked before the new file is created
		/// exclusively. A leftover from a crash is gone, and a link planted
		/// there is unlinked rather than followed, which is what
		/// create-or-truncate would do. The only write this seam makes is
		/// that staged sibling, whose name is fixed and guessable by any
		/// writer in the mod folder.
		/// </summary>
		void WriteAllText(string path, string text, Encoding encoding);

		/// <summary>Swaps <paramref name="sourcePath"/> in for the destination.</summary>
		void Replace(string sourcePath, string destinationPath);

		/// <summary>Renames in place of a swap; the fallback where none exists.</summary>
		void Move(string sourcePath, string destinationPath);

		void Delete(string path);
	}

	/// <summary>The filesystem the game runs on.</summary>
	internal sealed class SystemFileSystem : IFileSystem
	{
		/// <summary>
		/// Share mode that tolerates the concurrent reader or writer: the
		/// hot-reloading mod's own save watcher holds the same file open for
		/// read and write, and the default modes fail on a sharing violation.
		/// Every open below states it, the one place a reader can fail on
		/// Windows while the mod that owns the file is reading it.
		/// </summary>
		const FileShare SharedAccess = FileShare.ReadWrite | FileShare.Delete;

		public bool Exists(string path)
		{
			return File.Exists(path);
		}

		public bool TryGetStamp(string path, out DateTime writeUtc, out long length, out string error)
		{
			writeUtc = default(DateTime);
			length = -1;
			error = null;
			try
			{
				// One FileInfo carries all three answers, so the poll that
				// runs four times a second costs one metadata read instead of
				// an existence check, a write-time read and an open of the
				// file. Nothing here is cached between calls: the watch is
				// watching for the file to change.
				var info = new FileInfo(path);
				if (!info.Exists)
					return false;
				writeUtc = info.LastWriteTimeUtc;
				length = info.Length;
				return true;
			}
			catch (Exception ex)
			{
				error = ex.Message;
				return false;
			}
		}

		public string ReadAllText(string path)
		{
			using (var stream = File.Open(path, FileMode.Open, FileAccess.Read, SharedAccess))
			using (var reader = ModFileText.OpenText(stream))
				return reader.ReadToEnd();
		}

		public string ReadAllText(string path, out Encoding encoding)
		{
			return TomlFile.ReadAllText(path, out encoding);
		}

		public byte[] ReadAllBytes(string path)
		{
			using (var stream = File.Open(path, FileMode.Open, FileAccess.Read, SharedAccess))
			using (var buffer = new MemoryStream())
			{
				stream.CopyTo(buffer);
				return buffer.ToArray();
			}
		}

		public void WriteAllText(string path, string text, Encoding encoding)
		{
			var bytes = TomlFile.Encode(text, encoding);
			// A link at the staged name is unlinked rather than followed, so
			// creating over it cannot truncate what it points at. Delete does
			// not throw when there is nothing there.
			File.Delete(path);
			using (var stream = File.Open(path, FileMode.CreateNew, FileAccess.Write, SharedAccess))
				stream.Write(bytes, 0, bytes.Length);
		}

		public void Replace(string sourcePath, string destinationPath)
		{
			File.Replace(sourcePath, destinationPath, null);
		}

		public void Move(string sourcePath, string destinationPath)
		{
			File.Move(sourcePath, destinationPath);
		}

		public void Delete(string path)
		{
			File.Delete(path);
		}
	}

	/// <summary>
	/// The one filesystem this mod reads and writes through, so a simulated
	/// run can put its own in place and drive the same code the game runs.
	/// </summary>
	internal static class ModFileSystem
	{
		public static IFileSystem Current { get; set; } = new SystemFileSystem();
	}
}
