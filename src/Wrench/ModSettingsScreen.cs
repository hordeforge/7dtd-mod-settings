using System;
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
		const double ReloadConfirmSeconds = 10d;

		// The status line says one of four things, and reading which one
		// costs a player the same sentence every time, so the line is tinted
		// by what it says: a save that landed, a save that landed and was
		// applied, a save still waiting on the mod, and a save refused. The
		// red is the row outline's own (ModSettingsRows.SELECTED_ROW_COLOR),
		// the neutral is the [lightGrey] the line used to be, and the other
		// two carry no meaning in the palette: nothing else in the window is
		// green or amber, so neither reads as a row or a border.
		internal const string STATUS_NEUTRAL_COLOR = "211,211,211,255";
		internal const string STATUS_GOOD_COLOR = "138,198,63,255";
		internal const string STATUS_WAITING_COLOR = "255,183,77,255";
		internal const string STATUS_BAD_COLOR = "228,18,21,255";

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
		// What the fixed row pools could not show: mods with settings beyond
		// the mod list, and a mod's settings beyond the setting list. Both are
		// logged for the operator, and both say so on the status line too,
		// because a player looking at a list that stops short would otherwise
		// read the stop as the end of the file.
		int unlistedMods;
		int unshownSettings;
		// The wait is measured on the mod's one clock (ModClock), not by
		// summing the frame delta the update loop is handed: that delta is the
		// game's own frame time, and a frame the game does not advance (a
		// paused or time-scaled one, and the options screen is opened from the
		// pause menu) carries none of it, so a countdown built from it never
		// reaches its own end while the player is reading the screen.
		double reloadStartedAt;

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
			// a save that never happened. A watch still open at this point was
			// ended by the close above, so this only settles one that outlived
			// the screen; it never arms a new one.
			StopReloadWatch();
			// A mod is identified by its installed folder, which its settings
			// file is resolved from, not by the name its ModInfo carries: two
			// installed mods can ship the same name, and reopening on the name
			// would land the player on a different mod's settings.
			var keep = selected == null ? null : selected.ModPath;
			targets = TargetModDiscovery.Discover();
			var index = targets.FindIndex(t => t.ModPath == keep);
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
			StopReloadWatch();
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
				if (ModClock.Current.NowSeconds - reloadStartedAt >= ReloadConfirmSeconds)
					StopReloadWatch();
			}
			base.Update(_dt);
		}

		/// <summary>
		/// Settles the save the watch was waiting for, and detaches the mod
		/// it belonged to. The marker is not disarmed here: a reload line
		/// still in flight belongs to this watch until
		/// <see cref="TakeReloadSeen"/> or <see cref="StopReloadWatch"/>
		/// takes it.
		/// </summary>
		void SetWatchedSaveState(TargetMod.ESaveState state)
		{
			var target = watchedReloadTarget;
			watchedReloadTarget = null;
			if (target != null && target.SaveState == TargetMod.ESaveState.Saved)
				target.SaveState = state;
			// The half of the save that lands in the file and the half that
			// takes effect are separate events: the target's own watch either
			// re-read the file or never did, and that is an operator's question
			// long after this screen is closed.
			if (target == null)
				return;
			if (state == TargetMod.ESaveState.AppliedLive)
				Log.Out(ModApi.LogPrefix + " " + target.Name + " re-read " + target.TomlPath
					+ " after the save; the change is live.");
			else
				Log.Warning(ModApi.LogPrefix + " " + target.Name + " was not seen re-reading "
					+ target.TomlPath + " after the save; the change takes effect on the "
					+ "next restart.");
			if (target == selected)
				IsDirty = true;
		}

		internal void SelectMod(int index)
		{
			selected = (index >= 0 && index < targets.Count) ? targets[index] : null;
			// A reload line still in flight belongs to the mod selected until
			// now; attributing it to the new selection would mark the wrong
			// mod as applied live. It is settled as unconfirmed rather than
			// dropped, for the reason <see cref="StopReloadWatch"/> gives.
			StopReloadWatch();
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
			var saved = mod.TrySave(entry, newRaw, out var error);
			// The screen is the only thing that sees this outcome, and it is
			// gone the moment the player closes it, so the write is said in the
			// game log where an operator reading the server finds it: which
			// mod, which key, the value written, the file it landed in, and
			// whether it did. A settings file is the whole integration surface
			// with another mod, so a silent write is a change nobody can trace.
			if (saved)
				Log.Out(ModApi.LogPrefix + " saved " + mod.Name + " " + entry.Name + " = "
					+ newRaw + " in " + mod.TomlPath);
			else
				Log.Warning(ModApi.LogPrefix + " could not save " + mod.Name + " " + entry.Name
					+ " = " + newRaw + " in " + mod.TomlPath + ": " + error);
			// One save, one watch: a refused save, or one to a mod that only
			// takes effect on a restart, disarms the watch entirely, so a line
			// from an earlier save cannot stamp the next mod as "applied live"
			// or resurrect it over the failure just recorded. The Anvil
			// component logs the re-read; until that line arrives the status
			// stays at "saved".
			var watching = saved && mod.HotReloads && !ReloadMarkerShared(mod);
			ArmReloadWatch(watching ? mod.ReloadLogMarker : null);
			watchedReloadTarget = watching ? mod : null;
			if (saved && mod.HotReloads && !watching)
			{
				// The marker is the settings file's own name, and that name
				// comes out of a ModInfo two installed mods can carry alike, so
				// one mod's re-read line is byte-for-byte the one this save is
				// waiting for. Watching it would say "applied live" about a mod
				// that never read the file, and the wait is ended here instead
				// of being left to time out on a line that cannot be told apart.
				mod.SaveState = TargetMod.ESaveState.SaveUnconfirmed;
				Log.Warning(ModApi.LogPrefix + " " + mod.Name + " ships a settings file "
					+ "named " + mod.TomlFileName + ", which another installed mod ships too, "
					+ "so its re-read cannot be told apart in the log; the change is saved in "
					+ mod.TomlPath + " and reported unconfirmed.");
			}
			reloadStartedAt = ModClock.Current.NowSeconds;
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

		/// <summary>
		/// Whether another listed mod ships a settings file of the same name, so
		/// the one reload line in the log is not this mod's alone. The marker
		/// is built from the name in the mod's ModInfo, which two installed
		/// mods can carry alike even though their folders differ; the folder
		/// is what tells the two settings files apart, and the line the
		/// settings component logs carries no part of it.
		///
		/// The list is every mod discovered in the current opening, so this
		/// answers for the set the player is looking at. It is walked per save
		/// rather than memoized: the list is rebuilt on every opening and a
		/// table of markers would be a second thing to keep coherent with it.
		/// </summary>
		bool ReloadMarkerShared(TargetMod mod)
		{
			var marker = mod.ReloadLogMarker;
			for (var i = 0; i < targets.Count; i++)
			{
				if (targets[i] != mod
					&& string.Equals(targets[i].ReloadLogMarker, marker,
						StringComparison.Ordinal))
					return true;
			}
			return false;
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

		/// <summary>
		/// Ends a wait that is not going to be answered, and says so.
		///
		/// Dropping the watch on its own leaves the mod it belonged to at
		/// <see cref="TargetMod.ESaveState.Saved"/>, which the status line
		/// reads as "waiting for the mod to re-read the file" for the rest of
		/// the session: the player changed mod or closed the screen between the
		/// save and the reload, and nothing else ever resolves that save. The
		/// game log loses the same line, so an operator never learns whether the
		/// write took effect. A wait ended without a reload line is a save whose
		/// application was never confirmed, which is what
		/// <see cref="TargetMod.ESaveState.SaveUnconfirmed"/> says.
		///
		/// A no-op when no save is being waited for, so the closing screen
		/// never logs a save it did not make.
		/// </summary>
		void StopReloadWatch()
		{
			DisarmReloadWatch();
			SetWatchedSaveState(TargetMod.ESaveState.SaveUnconfirmed);
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
			unlistedMods = targets.Count > modRows.Length
				? targets.Count - modRows.Length
				: 0;
			if (unlistedMods > 0)
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
			unshownSettings = entries != null && entries.Count > settingRows.Length
				? entries.Count - settingRows.Length
				: 0;
			if (unshownSettings > 0)
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
			case "statuscolor":
				_value = StatusColor();
				return true;
			case "servernote":
				var cm = SingletonMonoBehaviour<ConnectionManager>.Instance;
				_value = (cm != null && cm.IsConnected && cm.IsClient && !cm.IsServer).ToString();
				return true;
			case "nomods":
				_value = (targets.Count == 0).ToString();
				return true;
			case "noentries":
				// Only a mod that was selected and has nothing in it. Not when
				// no mod is selected: `nomods` already says, on both sides,
				// that there is nothing here, and "this mod's settings file has
				// no keys in it" is false of no mod at all, so the label would
				// repeat the left column under a heading about "this mod".
				_value = (selected != null && selected.Entries != null
					&& selected.Entries.Count == 0).ToString();
				return true;
			// A file that will not parse is a different dead end from a file
			// with no keys in it, and the empty state above says the wrong one
			// of the two: "this mod has nothing to edit here" is false of a
			// mod whose settings are all there and unreadable.
			case "noreadable":
				_value = (selected != null && selected.Entries == null).ToString();
				return true;
			default:
				return base.GetBindingValueInternal(ref _value, _bindingName);
			}
		}

		string StatusLine()
		{
			return BaseStatusLine() + PooledOutOfViewSentence();
		}

		/// <summary>
		/// What the selected mod's state is, in one sentence. A list that
		/// stops short is a different fact and is said separately, so a
		/// player never reads a save outcome as a statement about the whole
		/// file.
		/// </summary>
		string BaseStatusLine()
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
				// The screen is opened on a list of values the player is
				// about to change, and both things that change one are
				// invisible until used: the field saves on Enter, and the
				// button beside a boolean flips it. The neutral line is the
				// one shown before the first save, which is the moment the
				// player has to find out how, so it names both.
				return selected.HotReloads
					? WrenchText.Get("wrenchStatusLiveHint",
						"Press Enter to save, or the button on the right to flip true/false. "
						+ "Edits apply live: the mod re-reads the file on save.")
					: WrenchText.Get("wrenchStatusRestartHint",
						"Press Enter to save, or the button on the right to flip true/false. "
						+ "Edits take effect after a restart.");
			}
		}

		/// <summary>
		/// What the fixed row pools left out, said on the same line, or an
		/// empty string when they showed everything.
		/// </summary>
		string PooledOutOfViewSentence()
		{
			var sentence = "";
			if (unshownSettings > 0)
				sentence += " " + WrenchText.Format("wrenchStatusUnshownSettings",
					"$1 more settings in this file are past the end of the list "
					+ "and cannot be edited here.", unshownSettings.ToString());
			if (unlistedMods > 0)
				sentence += " " + WrenchText.Format("wrenchStatusUnlistedMods",
					"$1 more installed mods have a settings file and are not listed here.",
					unlistedMods.ToString());
			return sentence;
		}

		/// <summary>
		/// The status line's tint, decided by the same switch the sentence is
		/// decided by, so the two can never disagree. What the row pools left
		/// out is appended to the sentence without a tint of its own: it is a
		/// fact about the list, not about the save.
		/// </summary>
		string StatusColor()
		{
			if (selected == null)
				return STATUS_NEUTRAL_COLOR;
			if (selected.Entries == null)
				return STATUS_BAD_COLOR;
			switch (selected.SaveState)
			{
			case TargetMod.ESaveState.Saved:
				return STATUS_WAITING_COLOR;
			case TargetMod.ESaveState.AppliedLive:
				return STATUS_GOOD_COLOR;
			case TargetMod.ESaveState.SaveUnconfirmed:
				return STATUS_WAITING_COLOR;
			case TargetMod.ESaveState.SaveFailed:
				return STATUS_BAD_COLOR;
			default:
				return STATUS_NEUTRAL_COLOR;
			}
		}
	}
}
