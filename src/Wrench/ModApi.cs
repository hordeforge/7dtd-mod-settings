using HarmonyLib;
using System.Runtime.CompilerServices;
using System.Reflection;

[assembly: InternalsVisibleTo("WrenchPlaytest")]

namespace Wrench
{
    public class ModApi : IModApi
    {
        public const string LogPrefix = "[Wrench]";

        public void InitMod(Mod _modInstance)
        {
            // Fast and defensive: log, never throw if recoverable. One
            // failing Harmony target must not kill the whole mod — prefer
            // per-patch try/catch when patches become optional.
            Log.Out($"{LogPrefix} InitMod");
            ModSettings.Load(_modInstance);
            // Re-reads Config/Wrench.toml when it is saved, via the
            // engine's UnityUpdate event (client and dedicated) — no restart,
            // no Harmony patch.
            ModEvents.UnityUpdate.RegisterHandler(OnUnityUpdate);
            new Harmony("com.ywy50.wrench")
                .PatchAll(Assembly.GetExecutingAssembly());
        }

        static void OnUnityUpdate(ref ModEvents.SUnityUpdateData data)
        {
            ModSettings.Poll();
        }
    }
}
