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
		/// Whether the name names one file inside a directory: no directory
		/// separator, no drive or stream colon, no character the platform
		/// forbids in a file name, and not a relative-path token. The
		/// separators are checked on every platform because .NET only
		/// reports the host's own, and a settings file written on the
		/// machine that downloaded the mod is the machine that runs it.
		/// </summary>
		static bool IsPlainName(string name)
		{
			if (name == "." || name == "..")
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
	}
}
