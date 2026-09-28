using System;
using System.IO;

namespace Wrench
{
	/// <summary>
	/// The settings file of one installed mod:
	/// <c>&lt;mod folder&gt;/Config/&lt;Mod Name&gt;.toml</c>.
	///
	/// The mod name is not this mod's to choose: it comes out of another
	/// mod's <c>ModInfo.xml</c>, which any downloaded modlet carries, and it
	/// is concatenated into a path the screen both reads and writes. A name
	/// holding a directory part would put that write outside the mod
	/// folder. So the name is checked for being one plain file name, and
	/// the composed path must then still resolve inside the mod folder:
	/// the second check is what makes the first a guarantee.
	/// </summary>
	internal static class ModTomlPath
	{
		/// <summary>
		/// The mod's settings file, or false with the reason. Never throws:
		/// a mod folder the runtime hands over can be a path .NET refuses.
		/// </summary>
		public static bool TryResolve(string modPath, string modName, out string tomlPath, out string error)
		{
			tomlPath = null;
			error = null;
			if (string.IsNullOrEmpty(modPath))
			{
				error = "no mod path available.";
				return false;
			}
			if (string.IsNullOrEmpty(modName))
			{
				error = "the mod has no name.";
				return false;
			}
			if (!IsPlainName(modName))
			{
				error = "the mod name '" + ForLog(modName) + "' is not a plain file name.";
				return false;
			}

			try
			{
				var root = Path.GetFullPath(modPath);
				var configDir = Path.Combine(root, "Config") + Path.DirectorySeparatorChar;
				var candidate = Path.GetFullPath(Path.Combine(configDir, modName + ".toml"));
				if (!candidate.StartsWith(configDir, StringComparison.Ordinal))
				{
					error = "the mod name '" + ForLog(modName) + "' resolves outside the mod folder.";
					return false;
				}
				tomlPath = candidate;
				return true;
			}
			catch (Exception ex)
			{
				error = "could not resolve the mod folder (" + ex.GetType().Name + ": "
					+ ex.Message + ").";
				return false;
			}
		}

		/// <summary>
		/// The names Windows reserves for its own devices. A file called
		/// <c>AUX.toml</c> or <c>NUL.toml</c> cannot exist there: the name is
		/// the device however it is spelled, with any extension, and
		/// <see cref="Path.GetInvalidFileNameChars"/> lists none of them.
		/// </summary>
		static readonly string[] ReservedDeviceNames =
		{
			"CON", "PRN", "AUX", "NUL",
			"COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
			"LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
		};

		/// <summary>
		/// A name or an argument as it goes into the game log: one line, with
		/// every other control character spelled out. Both reach the log from
		/// outside this mod (a mod's own ModInfo name, a telnet session's
		/// words), and a raw newline in either ends the record there: whatever
		/// follows is read by whoever reads the log next as a line of its own,
		/// so a name can write the line saying another mod was skipped for a
		/// reason it never had. The log is a security record, so a value that
		/// lands in it has to stay a value.
		/// </summary>
		internal static string ForLog(string value)
		{
			if (string.IsNullOrEmpty(value))
				return "";
			var builder = new System.Text.StringBuilder(value.Length);
			foreach (var c in value)
			{
				if (c == '\\' || c == '\r' || c == '\n')
					builder.Append("\\").Append(c == '\r' ? 'r' : 'n');
				else if (c < ' ' || c == (char)0x7F)
					builder.Append("\\u").Append(((int)c).ToString("X4",
						System.Globalization.CultureInfo.InvariantCulture));
				else
					builder.Append(c);
			}
			return builder.ToString();
		}

		/// <summary>
		/// Whether the name names one file inside a directory: no directory
		/// separator, no drive or stream colon, no character the platform
		/// forbids in a file name, no control character, not a
		/// relative-path token, and no name Windows reserves for a device.
		/// The separators and the device names are checked on every platform
		/// because .NET only reports the host's own, and a settings file
		/// written on the machine that downloaded the mod is the machine
		/// that runs it. Reading such a file there opens the device instead of
		/// the file, and a save to it goes nowhere.
		///
		/// Control characters are refused on every platform too, for a reason
		/// <see cref="Path.GetInvalidFileNameChars"/> does not cover: a Linux
		/// or macOS host reports only NUL and the separator, so a name holding
		/// a newline would resolve to a real file whose name then goes into a
		/// log line and the reload-marker match, and a newline in either
		/// forges a line the reader takes for one of its own.
		/// </summary>
		static bool IsPlainName(string name)
		{
			if (name == "." || name == "..")
				return false;
			if (IsReservedDeviceName(name))
				return false;
			var invalid = Path.GetInvalidFileNameChars();
			for (var i = 0; i < name.Length; i++)
			{
				var c = name[i];
				if (c == '/' || c == '\\' || c == ':')
					return false;
				if (c < ' ' || c == (char)0x7f)
					return false;
				if (Array.IndexOf(invalid, c) >= 0)
					return false;
			}
			return true;
		}

		/// <summary>
		/// Whether the name is one of Windows' device names, extension
		/// included: <c>NUL</c>, <c>nul</c> and <c>Nul.Mod</c> are all the
		/// null device, because the name before the first dot is the device.
		/// </summary>
		static bool IsReservedDeviceName(string name)
		{
			var dot = name.IndexOf('.');
			var stem = (dot < 0 ? name : name.Substring(0, dot)).TrimEnd(' ');
			for (var i = 0; i < ReservedDeviceNames.Length; i++)
			{
				if (string.Equals(stem, ReservedDeviceNames[i], StringComparison.OrdinalIgnoreCase))
					return true;
			}
			return false;
		}
	}
}
