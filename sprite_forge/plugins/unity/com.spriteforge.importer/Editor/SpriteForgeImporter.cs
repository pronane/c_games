// Sprite Forge Studio v9 - Unity editor importer.
// Tools > Sprite Forge > Import Build Folder...  (a Sprite Forge output folder copied under Assets/)
//   atlas.json (one character)  or  pack.json (forge.py atlas: several characters, trimmed)
// -> sprites sliced with the pivot at the feet, maps/atlas_normal.png as the _NormalMap secondary texture (URP 2D lights),
//    <name>_data.asset (SpriteForgeCharacterData: moves + frame data), Anim/<move>.anim + <name>.controller,
//    <name>.prefab (SpriteRenderer + Animator + SpriteForgeCharacter with hurt / hit colliders).
#pragma warning disable 0612, 0618   // TextureImporter.spritesheet: still works in 2021-6000; the newer data provider needs com.unity.2d.sprite
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace SpriteForge.Editor
{
    public static class SpriteForgeImporter
    {
        public static float PixelsPerUnit = 100f;

        [MenuItem("Tools/Sprite Forge/Import Build Folder...")]
        static void Menu()
        {
            var abs = EditorUtility.OpenFolderPanel("Sprite Forge build folder (atlas.json or pack.json)", Application.dataPath, "");
            if (string.IsNullOrEmpty(abs)) return;
            abs = abs.Replace('\\', '/');
            var data = Application.dataPath.Replace('\\', '/');
            if (!abs.StartsWith(data)) { EditorUtility.DisplayDialog("Sprite Forge", "Copy the build folder into this project's Assets/ first.", "OK"); return; }
            var made = ImportFolder("Assets" + abs.Substring(data.Length));
            EditorUtility.DisplayDialog("Sprite Forge", "Imported:\n" + string.Join("\n", made.ToArray()), "OK");
        }

        // batch mode: Unity -batchmode -quit -projectPath P -executeMethod SpriteForge.Editor.SpriteForgeImporter.ImportFromCommandLine -sfFolder Assets/chars/hero
        public static void ImportFromCommandLine()
        {
            var args = System.Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++)
                if (args[i] == "-sfFolder") Debug.Log("Sprite Forge: " + string.Join(", ", ImportFolder(args[i + 1]).ToArray()));
        }

        public static List<string> ImportFolder(string folder)
        {
            folder = folder.TrimEnd('/');
            if (File.Exists(folder + "/atlas.json")) return ImportAtlas(folder);
            if (File.Exists(folder + "/pack.json")) return ImportPack(folder);
            Debug.LogError("Sprite Forge: no atlas.json or pack.json in " + folder);
            return new List<string>();
        }

        class FrameRef { public string key; public int page; public Rect px; public Vector2 pivot; }

        // slice one page; rects in Sprite Forge pixels (y down) -> Unity (y up)
        static Dictionary<string, Sprite> Slice(string pngPath, List<FrameRef> frames, string normalPath)
        {
            AssetDatabase.ImportAsset(pngPath, ImportAssetOptions.ForceSynchronousImport);
            var ti = (TextureImporter)AssetImporter.GetAtPath(pngPath);
            int texW, texH;
            ti.GetSourceTextureWidthAndHeight(out texW, out texH);
            ti.textureType = TextureImporterType.Sprite;
            ti.spriteImportMode = SpriteImportMode.Multiple;
            ti.spritePixelsPerUnit = PixelsPerUnit;
            ti.alphaIsTransparency = true;
            ti.mipmapEnabled = false;
            ti.textureCompression = TextureImporterCompression.Uncompressed;
            ti.maxTextureSize = 8192;
            var metas = new List<SpriteMetaData>();
            foreach (var f in frames)
            {
                var m = new SpriteMetaData();
                m.name = f.key.Replace('/', '_');
                m.rect = new Rect(f.px.x, texH - f.px.y - f.px.height, f.px.width, f.px.height);
                m.alignment = (int)SpriteAlignment.Custom;
                m.pivot = f.pivot;
                metas.Add(m);
            }
            ti.spritesheet = metas.ToArray();
            if (!string.IsNullOrEmpty(normalPath) && File.Exists(normalPath))
            {
                AssetDatabase.ImportAsset(normalPath, ImportAssetOptions.ForceSynchronousImport);
                var ni = (TextureImporter)AssetImporter.GetAtPath(normalPath);
                ni.textureType = TextureImporterType.Default;   // already a tangent-space RGB normal map (OpenGL, +Y up)
                ni.sRGBTexture = false; ni.mipmapEnabled = false; ni.maxTextureSize = 8192;
                ni.textureCompression = TextureImporterCompression.Uncompressed;
                ni.SaveAndReimport();
                var nt = AssetDatabase.LoadAssetAtPath<Texture2D>(normalPath);
                ti.secondarySpriteTextures = new[] { new SecondarySpriteTexture { name = "_NormalMap", texture = nt } };
            }
            ti.SaveAndReimport();
            var outd = new Dictionary<string, Sprite>();
            foreach (var o in AssetDatabase.LoadAllAssetsAtPath(pngPath))
            {
                var s = o as Sprite;
                if (s != null) outd[s.name] = s;
            }
            return outd;
        }

        static List<string> ImportAtlas(string folder)
        {
            var js = SFJson.Parse(File.ReadAllText(folder + "/atlas.json"));
            var meta = SFJson.O(js, "meta");
            string name = SFJson.S(meta, "name", Path.GetFileName(folder));
            var images = SFJson.Has(meta, "images") ? SFJson.L(meta, "images").Select(x => x.ToString()).ToList() : new List<string> { SFJson.S(meta, "image", "atlas.png") };
            var normals = new List<string>();
            if (File.Exists(folder + "/maps/maps.json"))
            {
                var mj = SFJson.Parse(File.ReadAllText(folder + "/maps/maps.json"));
                var files = SFJson.O(mj, "files");
                if (files.ContainsKey("normal")) normals = ((List<object>)files["normal"]).Select(x => folder + "/maps/" + x).ToList();
            }
            var frames = SFJson.O(js, "frames");
            var perPage = new Dictionary<int, List<FrameRef>>();
            foreach (var kv in frames)
            {
                var fr = kv.Value;
                var r = SFJson.O(fr, "frame");
                var src = SFJson.O(fr, "sourceSize");
                var ss = SFJson.O(fr, "spriteSourceSize");
                var pv = SFJson.O(fr, "pivot");
                float w = (float)SFJson.N(r, "w"), h = (float)SFJson.N(r, "h");
                // pivot (normalised in the untrimmed cell, y down) -> normalised in this sprite rect, y up
                float px = (float)(SFJson.N(pv, "x") * SFJson.N(src, "w") - SFJson.N(ss, "x"));
                float py = (float)(SFJson.N(pv, "y") * SFJson.N(src, "h") - SFJson.N(ss, "y"));
                var f = new FrameRef { key = kv.Key, page = (int)SFJson.N(fr, "page"), px = new Rect((float)SFJson.N(r, "x"), (float)SFJson.N(r, "y"), w, h),
                                       pivot = new Vector2(px / w, 1f - py / h) };
                if (!perPage.ContainsKey(f.page)) perPage[f.page] = new List<FrameRef>();
                perPage[f.page].Add(f);
            }
            var sprites = new Dictionary<string, Sprite>();
            foreach (var kv in perPage)
                foreach (var s in Slice(folder + "/" + images[kv.Key], kv.Value, kv.Key < normals.Count ? normals[kv.Key] : null))
                    sprites[s.Key] = s.Value;
            var cell = new Vector2((float)SFJson.N(meta, "frame_w"), (float)SFJson.N(meta, "frame_h"));
            var piv = SFJson.O(meta, "pivot");
            var pivot = new Vector2((float)SFJson.N(piv, "x"), (float)SFJson.N(piv, "y"));
            var moves = new List<KeyValuePair<string, object>>(SFJson.O(js, "animations"));
            object fd = File.Exists(folder + "/framedata.json") ? SFJson.Parse(File.ReadAllText(folder + "/framedata.json")) : null;
            return Build(folder, name, cell, pivot, moves, k => sprites.ContainsKey(k) ? sprites[k] : null, fd);
        }

        static List<string> ImportPack(string folder)
        {
            var js = SFJson.Parse(File.ReadAllText(folder + "/pack.json"));
            var meta = SFJson.O(js, "meta");
            var images = SFJson.L(meta, "images").Select(x => x.ToString()).ToList();
            var chars = SFJson.O(meta, "characters");
            var frames = SFJson.O(js, "frames");
            var perPage = new Dictionary<int, List<FrameRef>>();
            foreach (var kv in frames)
            {
                var fr = kv.Value;
                var r = SFJson.O(fr, "frame"); var ss = SFJson.O(fr, "spriteSourceSize");
                var cm = SFJson.O(chars, kv.Key.Split('/')[0]); var cp = SFJson.O(cm, "pivot");
                float w = (float)SFJson.N(r, "w"), h = (float)SFJson.N(r, "h");
                float px = (float)(SFJson.N(cp, "x") - SFJson.N(ss, "x")), py = (float)(SFJson.N(cp, "y") - SFJson.N(ss, "y"));
                var f = new FrameRef { key = kv.Key, page = (int)SFJson.N(fr, "page"), px = new Rect((float)SFJson.N(r, "x"), (float)SFJson.N(r, "y"), w, h),
                                       pivot = new Vector2(px / w, 1f - py / h) };
                if (!perPage.ContainsKey(f.page)) perPage[f.page] = new List<FrameRef>();
                perPage[f.page].Add(f);
            }
            var sprites = new Dictionary<string, Sprite>();
            foreach (var kv in perPage)
                foreach (var s in Slice(folder + "/" + images[kv.Key], kv.Value, null)) sprites[s.Key] = s.Value;
            var made = new List<string>();
            var anims = SFJson.O(js, "animations");
            foreach (var ch in chars)
            {
                var moves = anims.Where(a => SFJson.S(a.Value, "character") == ch.Key)
                                 .Select(a => new KeyValuePair<string, object>(SFJson.S(a.Value, "move"), a.Value)).ToList();
                var cp = SFJson.O(ch.Value, "pivot");
                made.AddRange(Build(folder, ch.Key, new Vector2((float)SFJson.N(ch.Value, "frame_w"), (float)SFJson.N(ch.Value, "frame_h")),
                                    new Vector2((float)SFJson.N(cp, "x"), (float)SFJson.N(cp, "y")), moves,
                                    k => sprites.ContainsKey(k.Replace('/', '_')) ? sprites[k.Replace('/', '_')] : null, null));
            }
            return made;
        }

        static List<string> Build(string folder, string name, Vector2 cell, Vector2 pivotPx, List<KeyValuePair<string, object>> moves,
                                  System.Func<string, Sprite> sprite, object framedata)
        {
            var made = new List<string>();
            var data = ScriptableObject.CreateInstance<SpriteForgeCharacterData>();
            data.characterName = name; data.pixelsPerUnit = PixelsPerUnit; data.cellSize = cell;
            Dictionary<string, object> fdMoves = framedata != null ? SFJson.O(framedata, "moves") : null;
            Directory.CreateDirectory(folder + "/Anim");
            var ctrlPath = folder + "/" + name + ".controller";
            var ctrl = AnimatorController.CreateAnimatorControllerAtPath(ctrlPath);
            var sm = ctrl.layers[0].stateMachine;
            foreach (var mv in moves)
            {
                var a = mv.Value;
                var m = new SFMove { name = mv.Key, fps = (float)SFJson.N(a, "fps", 12), loop = SFJson.B(a, "loop") };
                var fnames = SFJson.L(a, "frames").Select(x => x.ToString()).ToList();
                object fdm = fdMoves != null && fdMoves.ContainsKey(mv.Key) ? fdMoves[mv.Key] : null;
                if (fdm != null)
                {
                    m.attack = SFJson.B(fdm, "attack"); m.startup = (int)SFJson.N(fdm, "startup"); m.active = (int)SFJson.N(fdm, "active");
                    m.recovery = (int)SFJson.N(fdm, "recovery"); m.damage = (int)SFJson.N(fdm, "damage");
                    m.hitstun = (int)SFJson.N(fdm, "hitstun"); m.blockstun = (int)SFJson.N(fdm, "blockstun");
                }
                for (int i = 0; i < fnames.Count; i++)
                {
                    var f = new SFFrame { sprite = sprite(fnames[i]) };
                    if (fdm != null && i < SFJson.L(fdm, "frames").Count)
                    {
                        var ff = SFJson.L(fdm, "frames")[i];
                        foreach (var b in SFJson.L(ff, "hurt")) f.hurt.Add(Box(b, pivotPx));
                        foreach (var b in SFJson.L(ff, "hit")) f.hit.Add(Box(b, pivotPx));
                    }
                    m.frames.Add(f);
                }
                data.moves.Add(m);
                // Mecanim clip
                var clip = new AnimationClip { frameRate = m.fps, name = m.name };
                var bind = EditorCurveBinding.PPtrCurve("", typeof(SpriteRenderer), "m_Sprite");
                var keys = new List<ObjectReferenceKeyframe>();
                for (int i = 0; i < m.frames.Count; i++) keys.Add(new ObjectReferenceKeyframe { time = i / m.fps, value = m.frames[i].sprite });
                keys.Add(new ObjectReferenceKeyframe { time = m.frames.Count / m.fps, value = m.frames[m.frames.Count - 1].sprite });
                AnimationUtility.SetObjectReferenceCurve(clip, bind, keys.ToArray());
                var st = AnimationUtility.GetAnimationClipSettings(clip);
                st.loopTime = m.loop;
                AnimationUtility.SetAnimationClipSettings(clip, st);
                var cp = folder + "/Anim/" + name + "_" + m.name + ".anim";
                AssetDatabase.CreateAsset(clip, cp);
                var state = sm.AddState(m.name);
                state.motion = clip;
                if (m.name == "idle") sm.defaultState = state;
            }
            var dp = folder + "/" + name + "_data.asset";
            AssetDatabase.CreateAsset(data, dp); made.Add(dp); made.Add(ctrlPath);
            var go = new GameObject(name);
            var sr = go.AddComponent<SpriteRenderer>();
            if (data.moves.Count > 0 && data.moves[0].frames.Count > 0) sr.sprite = data.moves[0].frames[0].sprite;
            go.AddComponent<Animator>().runtimeAnimatorController = ctrl;
            var ch = go.AddComponent<SpriteForgeCharacter>();
            ch.data = data;
            go.GetComponent<Animator>().enabled = false;     // SpriteForgeCharacter drives the frames; enable the Animator to use Mecanim instead
            var pp = folder + "/" + name + ".prefab";
            PrefabUtility.SaveAsPrefabAsset(go, pp);
            Object.DestroyImmediate(go);
            made.Add(pp);
            AssetDatabase.SaveAssets();
            return made;
        }

        static SFBox Box(object b, Vector2 pivotPx)
        {
            var bx = SFJson.L(b, "box").Select(x => (float)(double)x).ToArray();
            float ppu = PixelsPerUnit;
            // pixels (y down, origin top-left of the cell) -> units relative to the feet pivot, y up
            var r = new Rect((bx[0] - pivotPx.x) / ppu, (pivotPx.y - bx[1] - bx[3]) / ppu, bx[2] / ppu, bx[3] / ppu);
            return new SFBox { part = SFJson.Has(b, "part") ? SFJson.S(b, "part") : "", rect = r };
        }
    }
}
