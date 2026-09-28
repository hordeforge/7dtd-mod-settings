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
				error = "the mod name '" + modName + "' is not a plain file name.";
				return false;
			}

			try
			{
				var root = Path.GetFullPath(modPath);
				var configDir = Path.Combine(root, "Config") + Path.DirectorySeparatorChar;
				var candidate = Path.GetFullPath(Path.Combine(configDir, modName + ".toml"));
				if (!candidate.StartsWith(configDir, StringComparison.Ordinal))
				{
					error = "the mod name '" + modName + "' resolves outside the mod folder.";
					return false;
				}
				tomlPath = candidate;
				return true;
			}
			catch (Exception ex)
			{
				error = "could not resolve the mod folder (" + ex.Message + ").";
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
		/// Whether the name names one file inside a directory: no directory
		/// separator, no drive or stream colon, no character the platform
		/// forbids in a file name, and no name Windows reserves for a device.
		/// The separators and the device names are checked on every platform
		/// because .NET only reports the host's own, and a settings file
		/// written on the machine that downloaded the mod is the machine that
		/// runs it. Reading such a file there opens the device instead of the
		/// file, and a save to it goes nowhere.
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
