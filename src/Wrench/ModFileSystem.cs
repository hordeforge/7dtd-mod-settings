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

		/// <summary>When the file was last written.</summary>
		DateTime GetLastWriteTimeUtc(string path);

		/// <summary>The file's length in bytes.</summary>
		long GetLength(string path);

		/// <summary>
		/// Reads a text file while another process holds it open, which the
		/// mod whose settings are being read does for the few milliseconds
		/// of its own watch.
		/// </summary>
		string ReadAllText(string path);

		/// <summary>Reads a file's bytes, byte order mark included.</summary>
		byte[] ReadAllBytes(string path);

		/// <summary>
		/// Writes text in the given encoding, byte order mark included when
		/// that encoding has one, so a file can be written back the way it
		/// was read.
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
		/// </summary>
		const FileShare SharedAccess = FileShare.ReadWrite | FileShare.Delete;

		public bool Exists(string path)
		{
			return File.Exists(path);
		}

		public DateTime GetLastWriteTimeUtc(string path)
		{
			return File.GetLastWriteTimeUtc(path);
		}

		public long GetLength(string path)
		{
			using (var stream = File.Open(path, FileMode.Open, FileAccess.Read, SharedAccess))
				return stream.Length;
		}

		public string ReadAllText(string path)
		{
			using (var stream = File.Open(path, FileMode.Open, FileAccess.Read, SharedAccess))
			using (var reader = new StreamReader(stream))
				return reader.ReadToEnd();
		}

		public byte[] ReadAllBytes(string path)
		{
			return File.ReadAllBytes(path);
		}

		public void WriteAllText(string path, string text, Encoding encoding)
		{
			TomlFile.WriteAllText(path, text, encoding);
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
