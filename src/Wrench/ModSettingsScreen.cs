using System.Collections.Generic;

namespace Wrench
{
	/// <summary>
	/// The "Mod Settings" options page (window <c>wrenchModSettings</c> in
	/// <c>Config/XUi_Menu/windows.xml</c>), reachable from the options menu
	/// both in game and from the main menu.
	///
	/// Subclasses <see cref="XUiC_OptionsDialogBase"/> for the options-frame
	/// plumbing: the paging selector selection, back/ESC handling, and the
	/// hovered-description panel (fed through this controller's own
	/// CustomAttributes, which the vanilla <c>options_descriptions</c>
	/// template falls back to when no vanilla option entry is hovered).
	///
	/// Left: every installed mod with a Config/&lt;Mod&gt;.toml. Right: the
	/// selected mod's keys, edited in place through
	/// <see cref="TargetMod.TrySave"/>. After a save to a hot-reloading mod
	/// the game log is watched for that mod's reload line, so the status
	/// says whether the file was actually re-read; a mod that never logs
	/// one gets an explicit "not confirmed" status rather than an endless
	/// "waiting".
	/// </summary>
	public class XUiC_ModSettingsScreen : XUiC_OptionsDialogBase
	{
		// A settings component that polls the file every few seconds should
		// log its re-read well inside this. Past it the wait is over: the
		// status must not keep promising a reload that never arrived.
		const float RELOAD_CONFIRM_SECONDS = 10f;

		internal List<TargetMod> targets = new List<TargetMod>();
		internal TargetMod selected;
		XUiC_WrenchModRow[] modRows = new XUiC_WrenchModRow[0];
		XUiC_WrenchSettingRow[] settingRows = new XUiC_WrenchSettingRow[0];

		// The log callback runs on whatever thread logged, the latch is
		// written from the Unity thread, and the pair is read and written as
		// one unit: a reload line landing between the marker swap and the
		// latch clear would otherwise be dropped, and a non-volatile marker
		// could be seen stale by the callback. One lock, no ordering guess.
		readonly object reloadGate = new object();
		bool reloadSeen;
		string watchedReloadMarker;
		// The mod the marker and the latch belong to, not whatever is selected
		// when the line (or the timeout) lands: the player can pick another mod
		// between the save and the mod's reload, and that other mod is the one
		// that never re-read.
		TargetMod watchedReloadTarget;
		float reloadWait;

		// Log.LogCallbacks is a static event, so a subscription keeps this
		// screen (and every TargetMod and parsed entry it holds) alive until
		// it is unhooked, and each extra registration runs OnLogLine once
		// more per line. OnOpen is the only subscriber and OnClose the only
		// unhook, so an open that is not matched by its close would double
		// the handler and retain the screen for the rest of the session.
		bool watchingLog;

		// Nothing here uses the vanilla unsaved-changes model: every edit is
		// written (or refused) immediately.
		public override bool SupportsDefaults
		{
			get { return false; }
		}

		public override void Init()
		{
			base.Init();
			modRows = GetChildrenByType<XUiC_WrenchModRow>();
			settingRows = GetChildrenByType<XUiC_WrenchSettingRow>();
			for (var i = 0; i < modRows.Length; i++)
			{
				modRows[i].Screen = this;
				modRows[i].Index = i;
			}
			foreach (var row in settingRows)
				row.Screen = this;
		}

		public override void OnOpen()
		{
			base.OnOpen();
			// A reload line seen while the screen was closed belongs to the
			// previous opening: targets are re-discovered below, so carrying
			// the latch over would stamp a fresh TargetMod "applied live" for
			// a save that never happened.
			DisarmReloadWatch();
			watchedReloadTarget = null;
			var keep = selected == null ? null : selected.Name;
			targets = TargetModDiscovery.Discover();
			var index = targets.FindIndex(t => t.Name == keep);
			PopulateModRows();
			SelectMod(index < 0 ? 0 : index);
			// Subscribed last: OnClose is the only unhook, so a failure
			// while opening must not leave this screen on the log callback.
			if (!watchingLog)
			{
				Log.LogCallbacks += OnLogLine;
				watchingLog = true;
			}
		}

		public override void OnClose()
		{
			if (watchingLog)
			{
				Log.LogCallbacks -= OnLogLine;
				watchingLog = false;
			}
			DisarmReloadWatch();
			watchedReloadTarget = null;
			base.OnClose();
		}

		public override void Update(float _dt)
		{
			var reloaded = TakeReloadSeen();
			if (reloaded)
			{
				SetWatchedSaveState(TargetMod.ESaveState.AppliedLive);
			}
			else if (IsWatchingReload())
			{
				reloadWait += _dt;
				if (reloadWait >= RELOAD_CONFIRM_SECONDS)
				{
					DisarmReloadWatch();
					SetWatchedSaveState(TargetMod.ESaveState.SaveUnconfirmed);
				}
			}
			base.Update(_dt);
		}

		/// <summary>Moves the watched mod out of the pending state, then stops watching it.</summary>
		void SetWatchedSaveState(TargetMod.ESaveState state)
		{
			var target = watchedReloadTarget;
			watchedReloadTarget = null;
			if (target != null && target.SaveState == TargetMod.ESaveState.Saved)
				target.SaveState = state;
			if (target == selected)
				IsDirty = true;
		}

		internal void SelectMod(int index)
		{
			selected = (index >= 0 && index < targets.Count) ? targets[index] : null;
			// A reload line still in flight belongs to the mod selected until
			// now; attributing it to the new selection would mark the wrong
			// mod as applied live.
			DisarmReloadWatch();
			for (var i = 0; i < modRows.Length; i++)
			{
				modRows[i].IsSelectedMod = modRows[i].Target != null && modRows[i].Target == selected;
				modRows[i].RefreshBindings();
			}
			PopulateSettingRows();
			IsDirty = true;
			RefreshBindingsSelfAndChildren();
		}

		internal bool SaveEdit(TomlSettings.DocEntry entry, string newRaw)
		{
			if (selected == null)
				return false;
			var mod = selected;
			var saved = mod.TrySave(entry, newRaw, out _);
			// One save, one watch: a refused save, or one to a mod that only
			// takes effect on a restart, disarms the watch entirely, so a line
			// from an earlier save cannot stamp the next mod as "applied live"
			// or resurrect it over the failure just recorded. The Anvil
			// component logs the re-read; until that line arrives the status
			// stays at "saved".
			var watching = saved && mod.HotReloads;
			ArmReloadWatch(watching ? mod.ReloadLogMarker : null);
			watchedReloadTarget = watching ? mod : null;
			reloadWait = 0f;
			// Spans moved with the edit: rebind rows to the re-parsed
			// entries (also restores the file value after a refused edit).
			PopulateSettingRows();
			IsDirty = true;
			RefreshBindingsSelfAndChildren();
			return saved;
		}

		internal void ShowHelp(TomlSettings.DocEntry entry)
		{
			CustomAttributes["caption"] = entry.Name;
			CustomAttributes["description"] = entry.Comment.Length > 0
				? entry.Comment
				: WrenchText.Get("wrenchNoComment", "(no comment in the settings file)");
			CustomAttributes["applies_after"] =
				(selected != null && !selected.HotReloads)
					? WrenchText.Get("wrenchAppliesAfterRestart", "restart")
					: "";
			IsDirty = true;
		}

		void ArmReloadWatch(string marker)
		{
			lock (reloadGate)
			{
				watchedReloadMarker = marker;
				reloadSeen = false;
			}
		}

		void DisarmReloadWatch()
		{
			ArmReloadWatch(null);
		}

		/// <summary>True while a mod's reload line is still being waited for.</summary>
		bool IsWatchingReload()
		{
			lock (reloadGate)
			{
				return watchedReloadMarker != null;
			}
		}

		/// <summary>
		/// Takes the latch and disarms the watch in one step, so a reload line
		/// arriving now belongs to the next arm, not to the one just consumed.
		/// </summary>
		bool TakeReloadSeen()
		{
			lock (reloadGate)
			{
				var seen = reloadSeen;
				reloadSeen = false;
				watchedReloadMarker = null;
				return seen;
			}
		}

		void OnLogLine(string _message, string _trace, UnityEngine.LogType _type)
		{
			lock (reloadGate)
			{
				if (watchedReloadMarker != null
					&& _message != null
					&& _message.Contains(watchedReloadMarker))
					reloadSeen = true;
			}
		}

		void PopulateModRows()
		{
			for (var i = 0; i < modRows.Length; i++)
			{
				modRows[i].Target = i < targets.Count ? targets[i] : null;
				modRows[i].RefreshBindings();
			}
			if (targets.Count > modRows.Length)
				Log.Warning(ModApi.LogPrefix + " " + targets.Count + " mods with settings but only "
					+ modRows.Length + " list rows; the rest are not shown.");
		}

		void PopulateSettingRows()
		{
			var entries = selected?.Entries;
			for (var i = 0; i < settingRows.Length; i++)
			{
				var entry = entries != null && i < entries.Count ? entries[i] : null;
				settingRows[i].SetEntry(selected, entry);
			}
			if (entries != null && entries.Count > settingRows.Length)
				Log.Warning(ModApi.LogPrefix + " " + selected.Name + " has " + entries.Count
					+ " settings but only " + settingRows.Length + " rows; the rest are not shown.");
		}

		public override bool GetBindingValueInternal(ref string _value, string _bindingName)
		{
			switch (_bindingName)
			{
			case "selmodname":
				_value = selected == null ? "" : selected.DisplayName;
				return true;
			case "selmodfile":
				_value = selected == null ? "" : "Config/" + selected.TomlFileName;
				return true;
			case "selmodstatus":
				_value = StatusLine();
				return true;
			case "servernote":
				var cm = SingletonMonoBehaviour<ConnectionManager>.Instance;
				_value = (cm != null && cm.IsConnected && cm.IsClient && !cm.IsServer).ToString();
				return true;
			case "nomods":
				_value = (targets.Count == 0).ToString();
				return true;
			case "noentries":
				_value = (selected == null || selected.Entries == null
					|| selected.Entries.Count == 0).ToString();
				return true;
			default:
				return base.GetBindingValueInternal(ref _value, _bindingName);
			}
		}

		string StatusLine()
		{
			if (selected == null)
				return WrenchText.Get("wrenchNoMods",
					"No installed mod ships a Config/<Mod>.toml settings file, "
					+ "so there is nothing to edit here.");
			if (selected.Entries == null)
				return WrenchText.Format("wrenchStatusUnreadable",
					"Unreadable, not editable: $1", selected.Error);
			switch (selected.SaveState)
			{
			case TargetMod.ESaveState.Saved:
				return selected.HotReloads
					? WrenchText.Get("wrenchStatusSavedWaiting",
						"Saved. Waiting for the mod to re-read the file...")
					: WrenchText.Get("wrenchStatusSavedRestart",
						"Saved. Takes effect after a restart.");
			case TargetMod.ESaveState.AppliedLive:
				return WrenchText.Get("wrenchStatusAppliedLive",
					"Saved. The mod re-read the file and applied it.");
			case TargetMod.ESaveState.SaveUnconfirmed:
				return WrenchText.Get("wrenchStatusUnconfirmed",
					"Saved, but the mod has not re-read the file yet. If the change "
					+ "does not take effect, restart the game.");
			case TargetMod.ESaveState.SaveFailed:
				return WrenchText.Format("wrenchStatusSaveFailed",
					"Save failed: $1", selected.SaveError);
			default:
				return selected.HotReloads
					? WrenchText.Get("wrenchStatusLiveHint",
						"Edits apply live: the mod re-reads the file on save.")
					: WrenchText.Get("wrenchStatusRestartHint",
						"Edits take effect after a restart.");
			}
		}
	}
}
