// Arena FC — weather system (G6).
// Wind and rain affect ball physics and player movement.
using System;

namespace ArenaFC.Core;

/// <summary>Weather conditions.</summary>
public enum WeatherType
{
    Clear,
    Windy,
    Rain,
    Storm,
}

/// <summary>
/// Weather system — wind and rain affect ball flight and player speed.
/// </summary>
public static class Weather
{
    public static WeatherType Current = WeatherType.Clear;
    public static float WindX, WindZ;
    public static bool Raining => Current == WeatherType.Rain || Current == WeatherType.Storm;

    /// <summary>Set weather for a match.</summary>
    public static void Set(WeatherType type, float windSpeed = 0f, float windDirection = 0f)
    {
        Current = type;
        WindX = MathF.Cos(windDirection) * windSpeed;
        WindZ = MathF.Sin(windDirection) * windSpeed;
    }

    /// <summary>Get player speed multiplier from weather.</summary>
    public static float PlayerSpeedMultiplier()
    {
        return Current switch
        {
            WeatherType.Rain => 0.95f,   // wet pitch, slightly slower
            WeatherType.Storm => 0.92f,  // heavy rain
            _ => 1f,
        };
    }

    /// <summary>Get ball drag multiplier from weather.</summary>
    public static float BallDragMultiplier()
    {
        return Current switch
        {
            WeatherType.Rain => 1.5f,
            WeatherType.Storm => 2.0f,
            _ => 1f,
        };
    }
}
