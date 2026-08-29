using System;
using System.Collections.Generic;
using Wrench;
using ZdtdPlaytest;

namespace WrenchPlaytest
{
	public sealed class ModApi : IModApi
	{
		public void InitMod(Mod _modInstance)
		{
			Log.Out("[WrenchPlaytest] InitMod");
		}
	}

	/// <summary>
	/// Live proof of the Mod Settings screen against AtomicDoomsday, the
	/// reference consumer: the options tab exists, discovery lists Atomic
	/// (hot-reload) and Wrench itself (dog food), and an in-place RaidMode
	/// edit through the real screen controller is re-read by Atomic's own
	/// settings watch (the screen's status turns applied-live only after
	/// Atomic's reload log line). The file is then restored byte-for-byte.
	/// </summary>
	public sealed class WrenchScenarios : IScenarioProvider
	{
		const string Suite = "wrench-mod-settings";
		const string GroupName = "wrenchModSettings";

		public IEnumerable<string> SuiteIds => new[] { Suite };

		static XUiC_ModSettingsScreen Screen()
		{
			var group = LocalPlayerUI.primaryUI?.xui?.FindWindowGroupByName(GroupName);
			return group?.GetChildByType<XUiC_ModSettingsScreen>();
		}

		static TargetMod Target(string modName)
		{
			var screen = Screen();
			return screen?.targets?.Find(t => t.Mod.Name == modName);
		}

		public void AppendSuite(List<CaseDef> queue, string suite, int lap)
		{
			if (!string.Equals(suite, Suite, StringComparison.OrdinalIgnoreCase))
				return;
			var label = Suite + (lap > 0 ? "#" + lap : "");

			// Shared across the cases below, in queue order.
			string originalToml = null;

			queue.Add(CaseDef.Live(label, "options_tab_present", new[] { "ui", "xui" },
				assert: ctx =>
				{
					var xui = LocalPlayerUI.primaryUI?.xui;
					var group = xui?.FindWindowGroupByName(GroupName);
					var paging = xui?.FindWindowGroupByName("optionsPaging");
					var selector = paging?.GetChildByType<XUiC_WindowSelector>();
					var hasButton = false;
					if (selector != null)
					{
						foreach (var button in selector.buttons)
						{
							if (button.ViewComponent.ID == GroupName)
								hasButton = true;
						}
					}
					ctx.Detail = "group=" + (group != null) + " tabButton=" + hasButton;
					return group != null && hasButton;
				}, timeout: 10f, fail: "XUi_Menu patches did not apply"));

			queue.Add(CaseDef.Live(label, "open_and_discover", new[] { "ui", "discovery" },
				act: ctx => LocalPlayerUI.primaryUI.windowManager.Open(GroupName, _bModal: true),
				wait: ctx => Screen() != null && Screen().targets.Count > 0,
				assert: ctx =>
				{
					var atomic = Target("AtomicDoomsday");
					var self = Target("Wrench");
					ctx.Detail = "targets=" + Screen().targets.Count
						+ " atomic=" + (atomic != null)
						+ " atomicHot=" + (atomic != null && atomic.HotReloads)
						+ " atomicParsed=" + (atomic != null && atomic.Entries != null)
						+ " self=" + (self != null);
					return atomic != null && atomic.HotReloads && atomic.Entries != null
						&& self != null && self.HotReloads;
				}, timeout: 15f, fail: "discovery missing AtomicDoomsday or Wrench"));

			queue.Add(CaseDef.Live(label, "edit_raidmode_applies_live", new[] { "write-back", "hot-reload" },
				act: ctx =>
				{
					var screen = Screen();
					var index = screen.targets.FindIndex(t => t.Mod.Name == "AtomicDoomsday");
					screen.SelectMod(index);
					originalToml = screen.selected.Text;
					var entry = screen.selected.Entries.Find(e => e.Name == "RaidMode");
					if (!screen.SaveEdit(entry, "true"))
						ctx.Detail = "SaveEdit refused: " + screen.selected.SaveError;
				},
				wait: ctx => Target("AtomicDoomsday") != null
					&& Target("AtomicDoomsday").SaveState == TargetMod.ESaveState.AppliedLive,
				assert: ctx =>
				{
					var atomic = Target("AtomicDoomsday");
					var entry = atomic.Entries.Find(e => e.Name == "RaidMode");
					ctx.Detail = "state=" + atomic.SaveState + " RaidMode=" + entry.Value;
					return entry.Value == "true";
				}, timeout: 20f, fail: "Atomic never logged the settings reload"));

			queue.Add(CaseDef.Live(label, "restore_raidmode_byte_identical", new[] { "write-back", "round-trip" },
				act: ctx =>
				{
					var screen = Screen();
					var entry = screen.selected.Entries.Find(e => e.Name == "RaidMode");
					if (!screen.SaveEdit(entry, "false"))
						ctx.Detail = "SaveEdit refused: " + screen.selected.SaveError;
				},
				wait: ctx => Target("AtomicDoomsday") != null
					&& Target("AtomicDoomsday").SaveState == TargetMod.ESaveState.AppliedLive,
				assert: ctx =>
				{
					var atomic = Target("AtomicDoomsday");
					var identical = atomic.Text == originalToml;
					ctx.Detail = "state=" + atomic.SaveState + " byteIdentical=" + identical;
					return identical;
				}, timeout: 20f, fail: "restore did not reproduce the original file"));

			queue.Add(CaseDef.Staged(label, "wrench_screen_staged", new[] { "ui", "capture" },
				stage: ctx =>
				{
					var screen = Screen();
					if (screen == null)
						return false;
					var index = screen.targets.FindIndex(t => t.Mod.Name == "AtomicDoomsday");
					screen.SelectMod(index);
					ctx.Detail = "mod settings screen open on AtomicDoomsday";
					return LocalPlayerUI.primaryUI.windowManager.IsWindowOpen(GroupName);
				},
				holdSeconds: 20f));

			queue.Add(CaseDef.Live(label, "close_screen", new[] { "ui" },
				act: ctx => LocalPlayerUI.primaryUI.windowManager.Close(GroupName),
				assert: ctx => !LocalPlayerUI.primaryUI.windowManager.IsWindowOpen(GroupName),
				timeout: 10f, fail: "screen did not close"));
		}
	}
}
