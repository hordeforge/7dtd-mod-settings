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

			if (subcommand == "settings")
			{
				foreach (var line in ModSettings.Describe())
					SingletonMonoBehaviour<SdtdConsole>.Instance.Output(line);
				return;
			}

			if (subcommand == "reload")
			{
				string message;
				ModSettings.ReloadNow(out message);
				SingletonMonoBehaviour<SdtdConsole>.Instance.Output(message ?? "no settings file watched.");
				return;
			}

			if (subcommand == "set")
			{
				if (_params.Count != 3)
				{
					SingletonMonoBehaviour<SdtdConsole>.Instance.Output(
						"Usage: wrench set <name> <value>");
					return;
				}
				string message;
				ModSettings.TrySet(_params[1], _params[2], out message);
				SingletonMonoBehaviour<SdtdConsole>.Instance.Output(message);
				return;
			}

			SingletonMonoBehaviour<SdtdConsole>.Instance.Output(
				"Unknown subcommand '" + subcommand + "'. See: help wrench");
		}
	}
}
