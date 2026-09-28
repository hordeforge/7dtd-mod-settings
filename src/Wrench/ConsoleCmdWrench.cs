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
				ModSettings.ReloadNow(out reloadMessage);
				reloadMessage = reloadMessage ?? "no settings file watched.";
				Output(reloadMessage);
				// A telnet command changes the running server and the console
				// it was typed into closes with the session: the game log is
				// what the next operator reads, so the command and its outcome
				// are said there, with who ran it.
				Log.Out(ModApi.LogPrefix + " " + Sender(_senderInfo)
					+ " ran 'wrench reload': " + reloadMessage);
				return;

			case "set":
				if (_params.Count != 3)
				{
					Output("Usage: wrench set <name> <value>");
					return;
				}
				string setMessage;
				var set = ModSettings.TrySet(_params[1], _params[2], out setMessage);
				Output(setMessage);
				if (set)
					Log.Out(ModApi.LogPrefix + " " + Sender(_senderInfo) + " ran 'wrench set "
						+ _params[1] + " " + _params[2] + "': " + setMessage);
				else
					Log.Warning(ModApi.LogPrefix + " " + Sender(_senderInfo)
						+ " ran 'wrench set " + _params[1] + " " + _params[2] + "': " + setMessage);
				return;

			default:
				Log.Warning(ModApi.LogPrefix + " " + Sender(_senderInfo) + " ran 'wrench "
					+ subcommand + "': unknown subcommand.");
				Output("Unknown subcommand '" + subcommand + "'. See: help wrench");
				return;
			}
		}

		/// <summary>Who ran a command, for the log line that outlives the console.</summary>
		static string Sender(CommandSenderInfo sender)
		{
			return sender == null || string.IsNullOrEmpty(sender.PlayerName)
				? "unknown sender"
				: sender.PlayerName;
		}

		static void Output(string line)
		{
			SingletonMonoBehaviour<SdtdConsole>.Instance.Output(line);
		}
	}
}
