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
	/// says whether the file was actually re-read.
	/// </summary>
	public class XUiC_ModSettingsScreen : XUiC_OptionsDialogBase
	{
		internal List<TargetMod> targets = new List<TargetMod>();
		internal TargetMod selected;
		XUiC_WrenchModRow[] modRows = new XUiC_WrenchModRow[0];
		XUiC_WrenchSettingRow[] settingRows = new XUiC_WrenchSettingRow[0];

		// Written from the log callback (any thread), consumed in Update.
		volatile bool reloadSeen;
		string watchedReloadMarker;

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
			Log.LogCallbacks += OnLogLine;
			var keep = selected == null ? null : selected.Mod.Name;
			targets = TargetMod.Discover();
			var index = targets.FindIndex(t => t.Mod.Name == keep);
			PopulateModRows();
			SelectMod(index < 0 ? 0 : index);
		}

		public override void OnClose()
		{
			Log.LogCallbacks -= OnLogLine;
			watchedReloadMarker = null;
			base.OnClose();
		}

		public override void Update(float _dt)
		{
			if (reloadSeen)
			{
				reloadSeen = false;
				watchedReloadMarker = null;
				if (selected != null && selected.SaveState == TargetMod.ESaveState.Saved)
					selected.SaveState = TargetMod.ESaveState.AppliedLive;
				IsDirty = true;
			}
			base.Update(_dt);
		}

		internal void SelectMod(int index)
		{
			selected = (index >= 0 && index < targets.Count) ? targets[index] : null;
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
			if (saved && mod.HotReloads)
			{
				// The Anvil component logs the re-read; until that line
				// arrives the status stays at "saved".
				watchedReloadMarker = mod.ReloadLogMarker;
				reloadSeen = false;
			}
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
				: "(no comment in the settings file)";
			CustomAttributes["applies_after"] =
				(selected != null && !selected.HotReloads) ? "restart" : "";
			IsDirty = true;
		}

		void OnLogLine(string _message, string _trace, UnityEngine.LogType _type)
		{
			var marker = watchedReloadMarker;
			if (marker != null && _message != null && _message.Contains(marker))
				reloadSeen = true;
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
			var entries = selected == null ? null : selected.Entries;
			for (var i = 0; i < settingRows.Length; i++)
			{
				var entry = entries != null && i < entries.Count ? entries[i] : null;
				settingRows[i].SetEntry(selected, entry);
			}
			if (entries != null && entries.Count > settingRows.Length)
				Log.Warning(ModApi.LogPrefix + " " + selected.Mod.Name + " has " + entries.Count
					+ " settings but only " + settingRows.Length + " rows; the rest are not shown.");
		}

		public override bool GetBindingValueInternal(ref string _value, string _bindingName)
		{
			switch (_bindingName)
			{
			case "selmodname":
				_value = selected == null ? "" : selected.Mod.DisplayName;
				return true;
			case "selmodfile":
				_value = selected == null ? "" : "Config/" + selected.Mod.Name + ".toml";
				return true;
			case "selmodstatus":
				_value = StatusLine();
				return true;
			case "servernote":
				var cm = SingletonMonoBehaviour<ConnectionManager>.Instance;
				_value = (cm != null && cm.IsConnected && cm.IsClient && !cm.IsServer).ToString();
				return true;
			case "hasmods":
				_value = (targets.Count > 0).ToString();
				return true;
			default:
				return base.GetBindingValueInternal(ref _value, _bindingName);
			}
		}

		string StatusLine()
		{
			if (selected == null)
				return "No installed mod ships a Config/<Mod>.toml settings file.";
			if (selected.Entries == null)
				return "Unreadable, not editable: " + selected.Error;
			switch (selected.SaveState)
			{
			case TargetMod.ESaveState.Saved:
				return selected.HotReloads
					? "Saved. Waiting for the mod to re-read the file..."
					: "Saved. Takes effect after a restart.";
			case TargetMod.ESaveState.AppliedLive:
				return "Saved. The mod re-read the file and applied it.";
			case TargetMod.ESaveState.SaveFailed:
				return "Save failed: " + selected.SaveError;
			default:
				return selected.HotReloads
					? "Edits apply live: the mod re-reads the file on save."
					: "Edits take effect after a restart.";
			}
		}
	}
}
