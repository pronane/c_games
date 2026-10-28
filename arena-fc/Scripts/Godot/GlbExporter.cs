// Arena FC - exports the in-game edited rig (skeleton + skinned mesh + materials)
// as a standard .glb that can be opened in Blender/Maya/Godot and re-imported.
using System;
using System.IO;
using System.Text;
using Godot;

namespace ArenaFC.GodotGame;

public static class GlbExporter
{
    public static (bool ok, string path, string info) Export(CharacterRig rig, string baseName)
    {
        string safe = Sanitize(baseName);
        string dir = "user://exports";
        string path = $"{dir}/{safe}.glb";
        try
        {
            DirAccess.MakeDirRecursiveAbsolute(dir);
            var doc = new GltfDocument();
            var state = new GltfState();
            Error err = doc.AppendFromScene(rig, state, 0);
            if (err != Error.Ok) return (false, path, $"AppendFromScene returned {err}");
            err = doc.WriteToFilesystem(state, path);
            if (err != Error.Ok) return (false, path, $"WriteToFilesystem returned {err}");
            using var f = Godot.FileAccess.Open(path, Godot.FileAccess.ModeFlags.Read);
            long bytes = f == null ? 0 : (long)f.GetLength();
            string abs = ProjectSettings.GlobalizePath(path);
            return (true, abs, $"{bytes / 1024.0:F1} KB · {rig.Geo.Bones.Length} bones · {rig.Geo.VertexCount} verts · {rig.Geo.TriangleCount} tris");
        }
        catch (Exception ex) { return (false, path, ex.Message); }
    }

    public static string Sanitize(string s)
    {
        var sb = new StringBuilder();
        foreach (char c in string.IsNullOrWhiteSpace(s) ? "player" : s)
            sb.Append(char.IsLetterOrDigit(c) || c is '_' or '-' ? c : '_');
        return sb.Length == 0 ? "player" : sb.ToString();
    }

    /// <summary>Reads a .glb container and reports what is inside (used by the self-test).</summary>
    public static string Inspect(string absolutePath)
    {
        using var fs = File.OpenRead(absolutePath);
        using var br = new BinaryReader(fs);
        uint magic = br.ReadUInt32();
        uint version = br.ReadUInt32();
        uint total = br.ReadUInt32();
        if (magic != 0x46546C67) return "not a GLB file";
        uint chunkLen = br.ReadUInt32();
        uint chunkType = br.ReadUInt32();
        string json = Encoding.UTF8.GetString(br.ReadBytes((int)chunkLen));
        int Count(string key) => json.Contains("\"" + key + "\"") ? 1 : 0;
        int Joints() { int n = 0, i = 0; while ((i = json.IndexOf("\"joints\"", i, StringComparison.Ordinal)) >= 0) { n++; i += 8; } return n; }
        return $"version={version} size={total}B jsonChunk={(char)(chunkType & 0xFF)}{(char)((chunkType >> 8) & 0xFF)}{(char)((chunkType >> 16) & 0xFF)}{(char)((chunkType >> 24) & 0xFF)} " +
               $"meshes={Count("meshes")} skins={Count("skins")} jointsArrays={Joints()} nodes={Count("nodes")} materials={Count("materials")} animations={Count("animations")} jsonLen={json.Length}";
    }
}
