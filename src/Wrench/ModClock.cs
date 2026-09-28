using System.Diagnostics;
using System.Threading;

namespace Wrench
{
	/// <summary>
	/// Elapsed time, as the parts of this mod that wait need it: the
	/// settings file's poll interval and debounce, and the pause between
	/// retries of a save's atomic replace.
	///
	/// <see cref="NowSeconds"/> must be monotonic and independent of the
	/// wall clock: a run steps it from a virtual clock in simulation and
	/// from <see cref="StopwatchClock"/> in the game, and both take the same
	/// decisions for the same sequence of events. <c>Time.unscaledTime</c>
	/// is not that source (a float loses sub-second resolution on a
	/// dedicated server with weeks of uptime, so a saved file silently
	/// stops being picked up), and <c>DateTime.Now</c> is not either (a
	/// clock step moves the deadline with it).
	/// </summary>
	internal interface IMonotonicClock
	{
		/// <summary>Seconds elapsed on this clock since it was created.</summary>
		double NowSeconds { get; }

		/// <summary>Waits before the caller tries again.</summary>
		void Sleep(int milliseconds);
	}

	/// <summary>The clock the game runs on.</summary>
	internal sealed class StopwatchClock : IMonotonicClock
	{
		readonly Stopwatch stopwatch = Stopwatch.StartNew();

		public double NowSeconds
		{
			get { return stopwatch.Elapsed.TotalSeconds; }
		}

		public void Sleep(int milliseconds)
		{
			Thread.Sleep(milliseconds);
		}
	}

	/// <summary>
	/// The one clock this mod reads, so a simulated run can put a virtual
	/// one in its place and step the poll interval, the debounce, and the
	/// replace retry without spending the real time they stand for, and
	/// reach the same decisions the game reaches.
	/// </summary>
	internal static class ModClock
	{
		public static IMonotonicClock Current { get; set; } = new StopwatchClock();
	}
}
