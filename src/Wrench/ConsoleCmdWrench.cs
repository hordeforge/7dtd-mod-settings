using System.Collections.Generic;

namespace Wrench
{
	/// <summary>
	/// The mod's console command (auto-discovered via ConsoleCmdAbstract):
	/// list settings, change one for this session, or re-read the TOML now.
	/// Works in the in-game console and over dedicated-server telnet.
	/// </summary>
	public class ConsoleCmdWrench : ConsoleCmdAbstract
	{
		public override bool IsExecuteOnClient => true;

		public override string[] getCommands()
		{
			return new[] { "wrench" };
		}

		public override string getDescription()
		{
			return "Wrench (Mod Settings) settings";
		}

		public override string getHelp()
		{
			return "Usage:\n"
				+ "  wrench settings\n"
				+ "     List every setting and its current value.\n"
				+ "  wrench set <name> <value>\n"
				+ "     Change one setting for this session, until the TOML file\n"
				+ "     is re-read.\n"
				+ "  wrench reload\n"
				+ "     Re-read " + ModSettings.RelativePath + " now.\n"
				+ "\n"
				+ "Saving " + ModSettings.RelativePath + " in the installed mod\n"
				+ "folder applies without a restart. reload does that immediately.\n"
				+ "set changes this process until the file is re-read.";
		}

		public override void Execute(List<string> _params, CommandSenderInfo _senderInfo)
		{
			var subcommand = _params.Count > 0 ? _params[0].ToLowerInvariant() : "settings";

			switch (subcommand)
			{
			case "settings":
				foreach (var line in ModSettings.Describe())
					Output(line);
				return;

			case "reload":
				string reloadMessage;
				// The return is the same signal `set` reads: a reload that
				// could not read the file says so on the log as a warning,
				// where a reader filtering for warnings sees it. Logging the
				// refusal on the same line as a successful apply is how a
				// server runs on defaults without anyone being told.
				var reloaded = ModSettings.ReloadNow(out reloadMessage);
				reloadMessage = reloadMessage ?? "no settings file watched.";
				Output(reloadMessage);
				// A telnet command changes the running server and the console
				// it was typed into closes with the session: the game log is
				// what the next operator reads, so the command and its outcome
				// are said there, with who ran it.
				var reloadRecord = ModApi.LogPrefix + " " + Sender(_senderInfo)
					+ " ran 'wrench reload': " + reloadMessage;
				if (reloaded)
					Log.Out(reloadRecord);
				else
					Log.Warning(reloadRecord);
				return;

			case "set":
				if (_params.Count != 3)
				{
					Output("Usage: wrench set <name> <value>");
					// The usage line is all the console shows, and a telnet
					// console closes with the session: the one rejected
					// `wrench set` that said nothing there is the one nobody
					// finds afterwards.
					Log.Warning(ModApi.LogPrefix + " " + Sender(_senderInfo)
						+ " ran 'wrench set' with " + (_params.Count - 1)
						+ " argument(s) instead of 2 (name and value).");
					return;
				}
				string setMessage;
				var set = ModSettings.TrySet(_params[1], _params[2], out setMessage);
				Output(setMessage);
				// The name and the value are what the log records about who
				// changed what, so they are the two that go in as one line
				// each; the outcome, which this mod wrote, needs no such care.
				var recorded = " ran 'wrench set " + ModTomlPath.ForLog(_params[1]) + " "
					+ ModTomlPath.ForLog(_params[2]) + "': " + setMessage;
				if (set)
					Log.Out(ModApi.LogPrefix + " " + Sender(_senderInfo) + recorded);
				else
					Log.Warning(ModApi.LogPrefix + " " + Sender(_senderInfo) + recorded);
				return;

			default:
				Log.Warning(ModApi.LogPrefix + " " + Sender(_senderInfo) + " ran 'wrench "
					+ ModTomlPath.ForLog(subcommand) + "': unknown subcommand.");
				Output("Unknown subcommand '" + subcommand + "'. See: help wrench");
				return;
			}
		}

		/// <summary>
		/// Who ran a command, for the log line that outlives the console. The
		/// name and the arguments below it are one line each in that log:
		/// they come from a telnet session, and a raw newline in one ends the
		/// record there, so a name could write the line saying a setting was
		/// changed by someone else.
		/// </summary>
		static string Sender(CommandSenderInfo sender)
		{
			return sender == null || string.IsNullOrEmpty(sender.PlayerName)
				? "unknown sender"
				: ModTomlPath.ForLog(sender.PlayerName);
		}

		static void Output(string line)
		{
			SingletonMonoBehaviour<SdtdConsole>.Instance.Output(line);
		}
	}
}
