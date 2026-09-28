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

		/// <summary>Removes a name, whether or not anything is there.</summary>
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
			return TomlFile.Decode(ReadAllBytes(path), out encoding);
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

		/// <summary>
		/// The only writes this seam makes are staged siblings, and a staged
		/// name any writer in the mod folder can guess is created exclusively:
		/// a name already there is removed first, which unlinks a symlink
		/// planted there rather than following it, and a create-or-truncate
		/// would write through that link into whatever it points at. The
		/// removal also keeps a staging file left behind by a crash from
		/// refusing every save after it.
		/// </summary>
		public void WriteAllText(string path, string text, Encoding encoding)
		{
			var bytes = TomlFile.Encode(text, encoding);
			// The path this is called with is the staged sibling of a target
			// in another mod's folder, and its name is predictable, so it is
			// created exclusively: create-or-truncate follows whatever a link
			// left there and writes the settings text through it. A link at
			// the staged name is unlinked rather than followed, so creating
			// over it cannot truncate what it points at. A staged file still
			// there is not a save in progress (nothing reads it, and a save
			// that was interrupted already reported itself failed), and a
			// staging file a crash left behind would otherwise refuse every
			// save after it, so it goes first. Delete does not throw when
			// there is nothing there.
			File.Delete(path);
			using (var stream = File.Open(path, FileMode.CreateNew, FileAccess.Write, SharedAccess))
			{
				stream.Write(bytes, 0, bytes.Length);
				// The write is not done until it is on the disk, and this is
				// the only place that can say so: a flush that fails is a save
				// that would stage a file short of the text it was verified
				// against, so it throws here, before the replace makes that
				// file the mod's settings.
				stream.Flush(true);
			}
		}

		public void Replace(string sourcePath, string destinationPath)
		{
			File.Replace(sourcePath, destinationPath, null);
		}

		/// <summary>
		/// Renames in place of a swap, where the platform has no atomic
		/// replace. The destination is removed first because a rename will not
		/// land on an existing name; the window that leaves is the one the
		/// comment on the fallback already names.
		/// </summary>
		public void Move(string sourcePath, string destinationPath)
		{
			File.Delete(destinationPath);
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
