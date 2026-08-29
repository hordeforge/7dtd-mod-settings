namespace Wrench
{
	/// <summary>
	/// One row of the mod list (left column). A pooled grid child: the
	/// screen assigns it a <see cref="TargetMod"/> or hides it.
	/// </summary>
	public class XUiC_WrenchModRow : XUiController
	{
		internal XUiC_ModSettingsScreen Screen;
		internal TargetMod Target;
		internal int Index;
		internal bool IsSelectedMod;

		public override void Init()
		{
			base.Init();
			var button = GetChildById("rowButton");
			if (button != null)
				button.OnPress += OnRowPress;
		}

		void OnRowPress(XUiController _sender, int _mouseButton)
		{
			if (Screen != null && Target != null)
				Screen.SelectMod(Index);
		}

		public override bool GetBindingValueInternal(ref string _value, string _bindingName)
		{
			switch (_bindingName)
			{
			case "modname":
				_value = Target == null ? "" : Target.Mod.DisplayName;
				return true;
			case "modnote":
				_value = Target == null ? ""
					: Target.Entries == null ? "unreadable"
					: Target.HotReloads ? "applies live"
					: "restart required";
				return true;
			case "rowvisible":
				_value = (Target != null).ToString();
				return true;
			case "rowcolor":
				_value = IsSelectedMod ? "228,18,21,255" : "64,64,64,255";
				return true;
			default:
				return base.GetBindingValueInternal(ref _value, _bindingName);
			}
		}
	}

	/// <summary>
	/// One editable setting (right column). A pooled grid child: the screen
	/// assigns it a parsed entry or hides it. Booleans toggle on press;
	/// everything else edits in the text field and saves on Enter. Every
	/// save goes through <see cref="TargetMod.TrySave"/>, which validates
	/// and replaces only the value span.
	/// </summary>
	public class XUiC_WrenchSettingRow : XUiController
	{
		internal XUiC_ModSettingsScreen Screen;
		internal TargetMod Target;
		internal TomlSettings.DocEntry Entry;

		XUiC_TextInput textField;

		public override void Init()
		{
			base.Init();
			// The press wiring goes on the button view (it owns the collider),
			// never the wrapping rect: a rect gets no click events at all.
			var toggle = GetChildById("boolToggle");
			var clickable = toggle == null ? null : toggle.GetChildById("clickable");
			if (clickable != null)
				clickable.OnPress += OnTogglePress;
			var text = GetChildById("txtValue");
			if (text != null)
			{
				textField = text as XUiC_TextInput ?? text.GetChildByType<XUiC_TextInput>();
				if (textField != null)
				{
					textField.OnSubmitHandler += OnTextSubmit;
					textField.OnInputAbortedHandler += OnTextAborted;
				}
			}
		}

		internal void SetEntry(TargetMod target, TomlSettings.DocEntry entry)
		{
			Target = target;
			Entry = entry;
			if (textField != null && entry != null && entry.Kind != TomlSettings.ValueKind.Bool)
				textField.Text = EditableText(target, entry);
			RefreshBindings();
		}

		/// <summary>What the text field shows: the decoded value for strings,
		/// the raw token (collapsed to one line) for everything else.</summary>
		static string EditableText(TargetMod target, TomlSettings.DocEntry entry)
		{
			if (entry.Kind == TomlSettings.ValueKind.String)
				return entry.Value;
			var raw = target.Text.Substring(entry.ValueStart, entry.ValueLength);
			return raw.Replace("\r", "").Replace('\n', ' ').Replace('\t', ' ');
		}

		public override void OnHovered(bool _isOver)
		{
			base.OnHovered(_isOver);
			if (_isOver && Screen != null && Entry != null)
				Screen.ShowHelp(Entry);
		}

		void OnTogglePress(XUiController _sender, int _mouseButton)
		{
			if (Screen == null || Entry == null || Entry.Kind != TomlSettings.ValueKind.Bool)
				return;
			Screen.SaveEdit(Entry, Entry.Value == "true" ? "false" : "true");
		}

		void OnTextSubmit(XUiController _sender, string _text)
		{
			if (Screen == null || Entry == null)
				return;
			var raw = Entry.Kind == TomlSettings.ValueKind.String
				? TomlEdit.EncodeString(_text)
				: _text;
			if (!Screen.SaveEdit(Entry, raw) && textField != null)
				textField.Text = EditableText(Target, Entry);
		}

		void OnTextAborted(XUiController _sender)
		{
			if (textField != null && Target != null && Entry != null)
				textField.Text = EditableText(Target, Entry);
		}

		public override bool GetBindingValueInternal(ref string _value, string _bindingName)
		{
			switch (_bindingName)
			{
			case "keyname":
				_value = Entry == null ? "" : Entry.Name;
				return true;
			case "boolvalue":
				_value = Entry == null ? "" : Entry.Value;
				return true;
			case "isbool":
				_value = (Entry != null && Entry.Kind == TomlSettings.ValueKind.Bool).ToString();
				return true;
			case "istext":
				_value = (Entry != null && Entry.Kind != TomlSettings.ValueKind.Bool).ToString();
				return true;
			case "rowvisible":
				_value = (Entry != null).ToString();
				return true;
			default:
				return base.GetBindingValueInternal(ref _value, _bindingName);
			}
		}
	}
}
