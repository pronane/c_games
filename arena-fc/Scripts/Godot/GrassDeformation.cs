// Arena FC — grass deformation shader (P1 presentation).
// Pitch wear and deformation under players via vertex displacement.
// Uses a heightmap texture updated per-frame from player positions.
using Godot;

namespace ArenaFC.GodotGame;

/// <summary>
/// Grass deformation system for the pitch.
/// Tracks player positions and applies wear to the pitch shader.
/// </summary>
public partial class GrassDeformation : Node3D
{
    private Image _wearMap;
    private ImageTexture _wearTexture;
    private const int MapSize = 256;
    private const float PitchWidth = 105f;
    private const float PitchHeight = 68f;

    public void Initialize()
    {
        _wearMap = Image.Create(MapSize, MapSize, false, Image.Format.R8);
        _wearMap.Fill(new Color(0, 0, 0, 1));
        _wearTexture = ImageTexture.CreateFromImage(_wearMap);
    }

    /// <summary>Apply wear at a world position (called per player per frame).</summary>
    public void ApplyWear(Vector3 worldPos, float intensity = 0.01f)
    {
        if (_wearMap == null) return;

        // Convert world to UV
        float u = (worldPos.X / PitchWidth) + 0.5f;
        float v = (worldPos.Z / PitchHeight) + 0.5f;
        int x = (int)(u * MapSize);
        int y = (int)(v * MapSize);

        if (x < 0 || x >= MapSize || y < 0 || y >= MapSize) return;

        // Increase wear (red channel)
        Color current = _wearMap.GetPixel(x, y);
        float newWear = Mathf.Min(1.0f, current.R + intensity);
        _wearMap.SetPixel(x, y, new Color(newWear, 0, 0, 1));
    }

    /// <summary>Update the texture (call once per frame after applying wear).</summary>
    public void UpdateTexture()
    {
        if (_wearTexture != null && _wearMap != null)
        {
            _wearTexture.Update(_wearMap);
        }
    }

    /// <summary>Get the wear texture for the pitch shader.</summary>
    public Texture2D WearTexture => _wearTexture;

    /// <summary>Reset all wear (e.g., at match start).</summary>
    public void Reset()
    {
        if (_wearMap != null)
        {
            _wearMap.Fill(new Color(0, 0, 0, 1));
            UpdateTexture();
        }
    }
}
