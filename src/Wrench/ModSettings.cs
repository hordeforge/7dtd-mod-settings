using System;
using System.Collections.Generic;
using System.IO;

namespace Wrench
{
	/// <summary>
	/// This mod's own runtime settings, read from
	/// <c>Config/Wrench.toml</c> in the installed mod folder.
	///
	/// The engine's XML patcher never sees the file; the DLL reads it at
	/// <c>InitMod</c> and again whenever it is saved (a mtime/length watch
	/// polled from <c>ModEvents.UnityUpdate</c>, debounced so a half-written
	/// save is not read; both intervals are elapsed time off a monotonic
	/// clock). A reload resets to shipped defaults, then applies
	/// the file; a broken save keeps the current values. The console command
	/// (<c>wrench settings|set|reload</c>) shares the same value
	/// grammar through <see cref="TrySet"/>.
	///
	/// To add a setting: a Name constant, a default, a property, a line each
	/// in <see cref="ResetToDefaults"/>, <see cref="TrySet"/> and
	/// <see cref="Describe"/>, and a commented entry in the shipped TOML.
	///
	/// The Unity thread and the dedicated server's telnet thread both reach
	/// this class, so every static field above is read and written under
	/// <c>Gate</c>; a public entry point takes it, and the code it calls
	/// internally takes it reentrantly.
	/// </summary>
	internal static class ModSettings
	{
		public const string RelativePath = "Config/Wrench.toml";

		/// <summary>
		/// The settings file inside an installed mod folder. Built with the
		/// platform separator; <see cref="RelativePath"/> is the form shown to
		/// the player, not a path to hand to the filesystem.
		/// </summary>
		public static string ResolvePath(string modPath)
		{
			return Path.Combine(modPath, "Config", "Wrench.toml");
		}

		public const string ExampleEnabledName = "ExampleEnabled";
		public const bool ExampleEnabledDefault = false;

		/// <summary>Example setting; replace with this mod's real options.</summary>
		public static bool ExampleEnabled { get; private set; } = ExampleEnabledDefault;

		public const float FilePollIntervalSeconds = 0.25f;
		public const float FileReloadDebounceSeconds = 0.35f;

		// The Unity thread polls and reloads through ModEvents.UnityUpdate;
		// the console command below runs on the dedicated server's telnet
		// thread, which is not the Unity thread. Both touch the watched-path
		// stamps and the setting values, so every one of those accesses is
		// made under this lock. Monitor is reentrant, which is what lets the
		// reload path call TrySet while it holds it.
		static readonly object Gate = new object();

		static string watchedPath;
		static DateTime appliedWriteUtc;
		static long appliedLength = -1;
		static string appliedText;
		static DateTime seenWriteUtc;
		static long seenLength = -1;
		static double seenAt = -1d;
		static double nextPollAt;
		static string loggedProblem;

		// Elapsed time is read from the mod's one monotonic clock, not from
		// Time.unscaledTime: that one is a float, so a dedicated server with
		// weeks of uptime can no longer resolve the sub-second poll interval
		// and debounce, and a saved file silently stops being picked up.
		// Going through ModClock also keeps the interval and debounce
		// drivable by a virtual clock, so a simulated run steps them without
		// spending the real seconds they stand for.
		static double NowSeconds()
		{
			return ModClock.Current.NowSeconds;
		}

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
				Log.Warning(ModApi.LogPrefix + " no mod path available; using default settings.");
				LogCurrent("defaults");
				return;
			}

			lock (Gate)
			{
				var path = ResolvePath(mod.Path);
				// A second InitMod on a long-running server can watch a
				// different file. Every stamp below belongs to the file
				// watched until now, and a new file of the same length
				// written in the same timestamp tick would be taken for one
				// already applied, leaving the old file's values in place.
				if (!string.Equals(watchedPath, path, StringComparison.Ordinal))
				{
					ForgetStamps();
					watchedPath = path;
				}
			}
			Apply(true, true, out _);
		}

		/// <summary>
		/// Called from <c>ModEvents.UnityUpdate</c> so a save to the TOML file
		/// applies without restarting. Returns true when values were applied.
		/// </summary>
		public static bool Poll()
		{
			return Apply(false, false, out _);
		}

		/// <summary>Re-read the watched TOML immediately, ignoring the debounce.</summary>
		public static bool ReloadNow(out string message)
		{
			return Apply(true, false, out message);
		}

		/// <summary>
		/// The whole read-and-apply cycle under <see cref="Gate"/>.
		/// </summary>
		static bool Apply(bool force, bool startup, out string message)
		{
			lock (Gate)
			{
				message = null;
				if (force)
					return ReloadLocked(force, startup, out message);
				if (string.IsNullOrEmpty(watchedPath))
					return false;
				var now = NowSeconds();
				if (now < nextPollAt)
					return false;
				nextPollAt = now + FilePollIntervalSeconds;
				return ReloadLocked(force, startup, out message);
			}
		}

		/// <summary>Caller holds <see cref="Gate"/>.</summary>
		static bool ReloadLocked(bool force, bool startup, out string message)
		{
			message = null;
			if (string.IsNullOrEmpty(watchedPath))
			{
				message = "no mod path available; using default settings.";
				return false;
			}

			DateTime writeUtc;
			long length;
			string ioError;
			if (!ModFileSystem.Current.TryGetStamp(watchedPath, out writeUtc, out length, out ioError))
			{
				if (ioError == null)
				{
					if (appliedLength < 0 && !startup)
					{
						// A poll has nobody to report to, so "still on the
						// defaults" is the whole of what it needs to say. A
						// forced reload is somebody asking what is in force, and
						// the same state is a success on the path below: a file
						// that was never written is not a reload that failed.
						if (!force)
						{
							message = "defaults (no " + RelativePath + ")";
							return false;
						}
						return ApplyMissingFileDefaults(out message);
					}
					return ApplyMissingFileDefaults(out message);
				}
				var problem = "could not stat " + RelativePath + " (" + ioError + ").";
				LogProblem(problem, false);
				message = problem;
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
					seenAt = NowSeconds();
					return false;
				}
				if (NowSeconds() - seenAt < FileReloadDebounceSeconds)
					return false;
			}

			string text;
			if (!TryReadText(watchedPath, out text, out ioError))
			{
				var cause = "could not be read (" + ioError + "); ";
				if (startup)
				{
					var failure = RelativePath + " " + cause + "using default settings.";
					LogProblem(failure, true);
					LogCurrent("defaults (unreadable " + RelativePath + ")");
					message = failure;
					return false;
				}
				var problem = RelativePath + " " + cause + "keeping current settings.";
				LogProblem(problem, false);
				message = problem;
				return false;
			}

			if (!force && text == appliedText)
			{
				appliedWriteUtc = writeUtc;
				appliedLength = length;
				return false;
			}

			List<TomlSettings.DocEntry> entries;
			string error;
			if (!TomlSettings.TryReadDocument(text, out entries, out error))
			{
				// Record the rejected save as handled: the watch is on the
				// file's stamp, so the same broken content is not re-read (and
				// the same error not re-logged) on every poll until it changes.
				appliedWriteUtc = writeUtc;
				appliedLength = length;
				appliedText = text;
				var problem = error + (startup
					? "; using default settings."
					: "; keeping current settings.");
				LogProblem(problem, true);
				if (startup)
					LogCurrent("defaults");
				message = error;
				return false;
			}

			ResetToDefaults();
			for (var i = 0; i < entries.Count; i++)
			{
				if (!TrySet(entries[i].Name, entries[i].Value, out var setMessage,
					ignoreNameCase: false))
					Log.Warning(ModApi.LogPrefix + " " + RelativePath + ": " + setMessage);
			}
			appliedWriteUtc = writeUtc;
			appliedLength = length;
			appliedText = text;
			seenWriteUtc = writeUtc;
			seenLength = length;
			loggedProblem = null;
			var source = startup ? RelativePath : "reload " + RelativePath;
			LogCurrent(source);
			message = source;
			return true;
		}

		/// <summary>
		/// Records a problem with the settings file. The poll runs several
		/// times a second and an unfixed file is retried on every tick, so one
		/// line per distinct problem is logged, and again when the problem
		/// changes or a good read clears it.
		/// </summary>
		static void LogProblem(string problem, bool isError)
		{
			if (string.Equals(problem, loggedProblem, StringComparison.Ordinal))
				return;
			loggedProblem = problem;
			var line = ModApi.LogPrefix + " " + RelativePath + ": " + problem;
			if (isError)
				Log.Error(line);
			else
				Log.Warning(line);
		}

		static void ResetToDefaults()
		{
			ExampleEnabled = ExampleEnabledDefault;
		}

		/// <summary>
		/// The watched file is gone: fall back to shipped defaults and forget
		/// every stamp, so a file reappearing is read as a fresh change
		/// rather than compared against a stale signature.
		/// </summary>
		static bool ApplyMissingFileDefaults(out string message)
		{
			ResetToDefaults();
			ForgetStamps();
			LogCurrent("defaults (no " + RelativePath + ")");
			message = RelativePath + " is missing; using defaults.";
			return true;
		}

		/// <summary>
		/// Forgets the signature of the file that was applied or last seen, so
		/// the next one is read as a fresh change rather than compared against
		/// a signature of a different file. Caller holds <see cref="Gate"/>.
		/// </summary>
		static void ForgetStamps()
		{
			appliedWriteUtc = default(DateTime);
			appliedLength = -1;
			appliedText = null;
			seenWriteUtc = default(DateTime);
			seenLength = -1;
			seenAt = -1d;
			nextPollAt = -1d;
			loggedProblem = null;
		}

		static bool TryReadText(string path, out string text, out string error)
		{
			text = null;
			error = null;
			try
			{
				text = ModFileSystem.Current.ReadAllText(path);
				return true;
			}
			catch (Exception ex)
			{
				error = ex.GetType().Name + ": " + ex.Message;
				return false;
			}
		}

		/// <summary>
		/// Applies one setting by name. Shared by the file reader and the
		/// console command so both surfaces keep one name and value grammar.
		/// Unknown names and bad values fail loud and change nothing.
		///
		/// <paramref name="ignoreNameCase"/> is true for a name typed at the
		/// console and false for one read out of a TOML file: TOML keys are
		/// case sensitive, so <c>ExampleEnabled</c> and <c>exampleenabled</c>
		/// are two keys and the second one is unknown, not a second spelling
		/// of a setting.
		///
		/// Takes <see cref="Gate"/>, so a <c>wrench set</c> from the telnet
		/// thread cannot land between a reload's reset and its apply. Monitor
		/// is reentrant, so the reload path may call this while holding it.
		/// </summary>
		public static bool TrySet(string name, string value, out string message,
			bool ignoreNameCase = true)
		{
			lock (Gate)
			{
				return TrySetLocked(name, value, ignoreNameCase, out message);
			}
		}

		static bool TrySetLocked(string name, string value, bool ignoreNameCase,
			out string message)
		{
			var comparison = ignoreNameCase
				? StringComparison.OrdinalIgnoreCase
				: StringComparison.Ordinal;
			if (string.Equals(name, ExampleEnabledName, comparison))
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
			lock (Gate)
			{
				return DescribeLocked();
			}
		}

		/// <summary>Caller holds <see cref="Gate"/>.</summary>
		static string[] DescribeLocked()
		{
			return new[]
			{
				ExampleEnabledName + " = " + (ExampleEnabled ? "true" : "false"),
			};
		}

		static void LogCurrent(string source)
		{
			string[] lines;
			lock (Gate)
			{
				lines = DescribeLocked();
			}
			Log.Out(ModApi.LogPrefix + " settings (" + source + "): "
				+ string.Join(", ", lines));
		}
	}
}
