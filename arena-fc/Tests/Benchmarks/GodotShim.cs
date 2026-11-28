// MotionDriver (Scripts/Godot) only touches Godot to log warnings; this stands in for that
// so the motion-matching cost can be benchmarked without the engine.
namespace Godot
{
    internal static class GD
    {
        public static void PushWarning(params object[] what) => System.Console.Error.WriteLine(string.Concat(what));
        public static void Print(params object[] what) => System.Console.WriteLine(string.Concat(what));
    }
}
