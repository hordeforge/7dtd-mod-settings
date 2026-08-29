using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace Wrench
{
	/// <summary>
	/// This mod's own runtime settings, read from
	/// <c>Config/Wrench.toml</c> in the installed mod folder.
	///
	/// The engine's XML patcher never sees the file; the DLL reads it at
	/// <c>InitMod</c> and again whenever it is saved (a mtime/length watch
	/// polled from <c>ModEvents.UnityUpdate</c>, debounced so a half-written
	/// save is not read). A reload resets to shipped defaults, then applies
	/// the file; a broken save keeps the current values. The console command
	/// (<c>wrench settings|set|reload</c>) shares the same value
	/// grammar through <see cref="TrySet"/>.
	///
	/// To add a setting: a Name constant, a default, a property, a line each
	/// in <see cref="ResetToDefaults"/>, <see cref="TrySet"/> and
	/// <see cref="Describe"/>, and a commented entry in the shipped TOML.
	/// </summary>
	internal static class ModSettings
	{
		public const string RelativePath = "Config/Wrench.toml";

		public const string ExampleEnabledName = "ExampleEnabled";
		public const bool ExampleEnabledDefault = false;

		/// <summary>Example setting; replace with this mod's real options.</summary>
		public static bool ExampleEnabled { get; private set; } = ExampleEnabledDefault;

		/// <summary>Raised after a file read applied values (startup or reload).</summary>
		public static event Action Applied;

		public const float FilePollIntervalSeconds = 0.25f;
		public const float FileReloadDebounceSeconds = 0.35f;

		static string watchedPath;
		static DateTime appliedWriteUtc;
		static long appliedLength = -1;
		static string appliedText;
		static DateTime seenWriteUtc;
		static long seenLength = -1;
		static float seenAt = -1f;
		static float nextPollAt;

		/// <summary>
		/// Reads the settings file if it is there. A missing file is the normal
		/// case for a fresh install, not an error: the shipped defaults stand
		/// and one line says so, because a silent no-op here would look exactly
		/// like a file that was read and had no effect. After this, a save to
		/// the same file is picked up without a restart (<see cref="Poll"/> /
		/// <c>wrench reload</c>).
		/// </summary>
		public static void Load(Mod mod)
		{
			if (mod == null || string.IsNullOrEmpty(mod.Path))
			{
				Debug.LogWarning("[Wrench] no mod path available; using default settings.");
				LogCurrent("defaults");
				return;
			}

			watchedPath = Path.Combine(mod.Path, RelativePath);
			string message;
			ReloadFromWatchedFile(true, true, out message);
			_ = message;
		}

		/// <summary>
		/// Called from <c>ModEvents.UnityUpdate</c> so a save to the TOML file
		/// applies without restarting. Returns true when values were applied.
		/// </summary>
		public static bool Poll()
		{
			if (string.IsNullOrEmpty(watchedPath))
				return false;
			var now = Time.unscaledTime;
			if (now < nextPollAt)
				return false;
			nextPollAt = now + FilePollIntervalSeconds;
			string message;
			return ReloadFromWatchedFile(false, false, out message);
		}

		/// <summary>Re-read the watched TOML immediately, ignoring the debounce.</summary>
		public static bool ReloadNow(out string message)
		{
			return ReloadFromWatchedFile(true, false, out message);
		}

		static bool ReloadFromWatchedFile(bool force, bool startup, out string message)
		{
			message = null;
			if (string.IsNullOrEmpty(watchedPath))
			{
				message = "no mod path available; using default settings.";
				return false;
			}

			if (!SdFile.Exists(watchedPath))
			{
				if (appliedLength < 0 && !startup)
				{
					message = "defaults (no " + RelativePath + ")";
					return false;
				}
				ResetToDefaults();
				appliedWriteUtc = default(DateTime);
				appliedLength = -1;
				appliedText = null;
				seenWriteUtc = default(DateTime);
				seenLength = -1;
				LogCurrent("defaults (no " + RelativePath + ")");
				message = RelativePath + " is missing; using defaults.";
				Applied?.Invoke();
				return true;
			}

			DateTime writeUtc;
			long length;
			if (!TryStamp(watchedPath, out writeUtc, out length))
			{
				message = "could not stat " + RelativePath + ".";
				return false;
			}

			if (!force && writeUtc == appliedWriteUtc && length == appliedLength)
				return false;

			if (!force)
			{
				if (writeUtc != seenWriteUtc || length != seenLength)
				{
					seenWriteUtc = writeUtc;
					seenLength = length;
					seenAt = Time.unscaledTime;
					return false;
				}
				if (Time.unscaledTime - seenAt < FileReloadDebounceSeconds)
					return false;
			}

			string text;
			if (!TryReadText(watchedPath, out text))
			{
				if (startup)
				{
					LogCurrent("defaults (unreadable " + RelativePath + ")");
					message = RelativePath + " could not be read; using defaults.";
					return false;
				}
				message = RelativePath + " could not be read; keeping current settings.";
				return false;
			}

			if (!force && text == appliedText)
			{
				appliedWriteUtc = writeUtc;
				appliedLength = length;
				return false;
			}

			List<TomlSettings.Entry> entries;
			string error;
			if (!TomlSettings.TryRead(text, out entries, out error))
			{
				if (startup)
				{
					Debug.LogError("[Wrench] " + RelativePath + ": " + error + "; using default settings.");
					LogCurrent("defaults");
					message = error;
					return false;
				}
				Debug.LogError("[Wrench] " + RelativePath + ": " + error + "; keeping current settings.");
				message = error;
				return false;
			}

			ResetToDefaults();
			for (var i = 0; i < entries.Count; i++)
			{
				if (!TrySet(entries[i].Name, entries[i].Value, out var setMessage))
					Debug.LogWarning("[Wrench] " + RelativePath + ": " + setMessage);
			}
			appliedWriteUtc = writeUtc;
			appliedLength = length;
			appliedText = text;
			seenWriteUtc = writeUtc;
			seenLength = length;
			var source = startup ? RelativePath : "reload " + RelativePath;
			LogCurrent(source);
			message = source;
			Applied?.Invoke();
			return true;
		}

		static void ResetToDefaults()
		{
			ExampleEnabled = ExampleEnabledDefault;
		}

		static bool TryStamp(string path, out DateTime writeUtc, out long length)
		{
			writeUtc = default(DateTime);
			length = -1;
			try
			{
				writeUtc = SdFile.GetLastWriteTimeUtc(path);
				using (var stream = SdFile.Open(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
					length = stream.Length;
				return true;
			}
			catch (Exception)
			{
				return false;
			}
		}

		static bool TryReadText(string path, out string text)
		{
			text = null;
			try
			{
				using (var stream = SdFile.Open(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
				using (var reader = new StreamReader(stream))
					text = reader.ReadToEnd();
				return true;
			}
			catch (Exception)
			{
				return false;
			}
		}

		/// <summary>
		/// Applies one setting by name. Shared by the file reader and the
		/// console command so both surfaces keep one name and value grammar.
		/// Unknown names and bad values fail loud and change nothing.
		/// </summary>
		public static bool TrySet(string name, string value, out string message)
		{
			if (string.Equals(name, ExampleEnabledName, StringComparison.OrdinalIgnoreCase))
			{
				bool parsed;
				if (!TryParseBool(value, out parsed))
				{
					message = ExampleEnabledName + " must be true or false, not '" + value + "'.";
					return false;
				}
				ExampleEnabled = parsed;
				message = ExampleEnabledName + " = " + (parsed ? "true" : "false");
				return true;
			}

			message = "unknown setting '" + name + "'.";
			return false;
		}

		static bool TryParseBool(string value, out bool parsed)
		{
			parsed = false;
			if (string.Equals(value, "true", StringComparison.OrdinalIgnoreCase))
			{
				parsed = true;
				return true;
			}
			return string.Equals(value, "false", StringComparison.OrdinalIgnoreCase);
		}

		/// <summary>One line per setting, for the console command.</summary>
		public static string[] Describe()
		{
			return new[]
			{
				ExampleEnabledName + " = " + (ExampleEnabled ? "true" : "false"),
			};
		}

		static void LogCurrent(string source)
		{
			Debug.Log("[Wrench] settings (" + source + "): "
				+ string.Join(", ", Describe()));
		}
	}
}
