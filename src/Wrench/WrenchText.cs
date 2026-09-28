using System;

namespace Wrench
{
	/// <summary>
	/// Every user-facing string the Mod Settings screen builds in code,
	/// read from <c>Config/Localization.csv</c> through the game's
	/// <c>Localization</c>.
	///
	/// Each call carries the English source text next to its key, because
	/// <c>Localization.Get</c> hands back the key itself (or an empty
	/// string, depending on the game version) for a key no dictionary
	/// holds. A player must read a sentence either way, never a bare key:
	/// the English fallback is what renders until a translation lands, and
	/// <c>scripts/test_localization_catalog.py</c> requires the catalog's
	/// english column and this fallback to be the same string, so they
	/// cannot drift apart silently.
	///
	/// Substitution goes through <see cref="Format"/> rather than C#
	/// concatenation: a translated sentence puts the value wherever the
	/// target language puts it, and a concatenated one cannot.
	/// </summary>
	internal static class WrenchText
	{
		/// <summary>
		/// The single substitution slot a catalog string may use. Vanilla
		/// localization uses the same <c>$n</c> form, so a string carrying
		/// one reads the way a translator expects.
		/// </summary>
		internal const string Placeholder = "$1";

		/// <summary>
		/// The translation of <paramref name="key"/>, or
		/// <paramref name="english"/> when no dictionary holds it.
		/// </summary>
		internal static string Get(string key, string english)
		{
			var value = Localization.Get(key);
			return string.IsNullOrEmpty(value) || value == key ? english : value;
		}

		/// <summary>
		/// The translation of <paramref name="key"/> with
		/// <paramref name="value"/> in its <see cref="Placeholder"/> slot.
		/// <paramref name="english"/> carries the same slot, so an
		/// untranslated key renders the finished English sentence rather
		/// than a literal <c>$1</c>.
		/// </summary>
		internal static string Format(string key, string english, string value)
		{
			return Get(key, english).Replace(Placeholder, value ?? string.Empty);
		}
	}
}
