// Unity loader for Sprite Forge game_character.json (v11.5).
//
// Put the build folder under Assets/StreamingAssets/<name>/ (or set Directory
// to an absolute path in the inspector). Add this component to an empty
// GameObject. The sprite's pivot is the foot line, so the transform sits on
// the ground.
//
// JsonUtility reads the known event fields. A custom numeric event in a pack
// you wrote yourself is kept in the JSON but JsonUtility will not surface it;
// the Godot loader and the file itself still have it.
//
// Hitboxes are an estimate from the sprite silhouette (framedata), not authored
// collision. -1 means that event does not apply to the move.
//
// This file was checked against the stub Unity APIs in tools/unity_stub_check
// when that project is present. It has not been imported into the Unity editor
// in this repo.

using System;
using System.IO;
using UnityEngine;

namespace SpriteForge
{
    [Serializable] public class GCVec { public int x; public int y; }
    [Serializable] public class GCFrame { public int w; public int h; }
    [Serializable] public class GCEvents
    {
        public int hit_start = -1, hit_end = -1, ball_contact = -1, throw_release = -1, shoot = -1, reload = -1;
        public int[] footsteps = new int[0];
    }
    [Serializable] public class GCBox { public int frame; public string part; public int[] box; }
    [Serializable] public class GCAnim
    {
        public string name;
        public string strip;
        public int frames, fps, w, h, row;
        public bool loop;
        public GCVec pivot;
        public int ground_y;
        public string source;
        public string library;
        public GCEvents events;
        public GCBox[] hitboxes;
        public GCBox[] hurtboxes;
    }
    [Serializable] public class GCFile
    {
        public string format;
        public int version;
        public string name;
        public string character_type;
        public string game_pack;
        public string camera;
        public GCFrame frame;
        public GCVec pivot;
        public int ground_y;
        public int height_px;
        public GCAnim[] animations;
    }

    public class GameCharacter : MonoBehaviour
    {
        [Tooltip("Folder with game_character.json. Empty = StreamingAssets/<object name>.")]
        public string Directory;
        public float targetHeight = 1.8f;

        public GCFile Data { get; private set; }
        public string Current { get; private set; }
        public int Frame { get; private set; }
        public bool Done { get; private set; }

        SpriteRenderer rend;
        GCAnim playing;
        Texture2D tex;
        float time;

        void Awake()
        {
            rend = gameObject.GetComponent<SpriteRenderer>();
            if (rend == null) rend = gameObject.AddComponent<SpriteRenderer>();
        }

        void Start()
        {
            if (string.IsNullOrEmpty(Directory))
                Directory = Path.Combine(Application.streamingAssetsPath, gameObject.name);
            LoadDir(Directory);
            if (Has("idle")) Play("idle");
            else if (Data != null && Data.animations != null && Data.animations.Length > 0) Play(Data.animations[0].name);
        }

        public bool LoadDir(string dir)
        {
            Directory = dir;
            var path = Path.Combine(dir, "game_character.json");
            if (!File.Exists(path))
            {
                Debug.LogWarning("Sprite Forge: no game_character.json in " + dir);
                return false;
            }
            Data = JsonUtility.FromJson<GCFile>(File.ReadAllText(path));
            return Data != null && Data.animations != null && Data.animations.Length > 0;
        }

        public bool Has(string move)
        {
            return Find(move) != null;
        }

        public GCAnim Find(string move)
        {
            if (Data == null || Data.animations == null) return null;
            foreach (var a in Data.animations) if (a.name == move) return a;
            return null;
        }

        public void Play(string move)
        {
            var a = Find(move);
            if (a == null) return;
            playing = a;
            Current = move;
            time = 0f;
            Frame = 0;
            Done = false;
            var strip = Path.Combine(Directory, a.strip.Replace('/', Path.DirectorySeparatorChar));
            if (!File.Exists(strip))
            {
                Debug.LogWarning("Sprite Forge: missing strip " + strip);
                return;
            }
            var bytes = File.ReadAllBytes(strip);
            if (tex != null) Destroy(tex);
            tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            tex.LoadImage(bytes);
            Show();
        }

        void Update()
        {
            if (playing == null || playing.frames <= 0) return;
            float fps = playing.fps > 0 ? playing.fps : 12f;
            time += Time.deltaTime;
            int f = (int)(time * fps);
            if (playing.loop) f = ((f % playing.frames) + playing.frames) % playing.frames;
            else if (f >= playing.frames) { f = playing.frames - 1; Done = true; }
            if (f != Frame) { Frame = f; Show(); }
        }

        void Show()
        {
            if (tex == null || playing == null) return;
            int w = playing.w > 0 ? playing.w : tex.width / Math.Max(1, playing.frames);
            int h = playing.h > 0 ? playing.h : tex.height;
            // Texture2D pixels are bottom-left; the strip is stored top-left, one row.
            var rect = new Rect(Frame * w, tex.height - h, w, h);
            float ppu = h / Math.Max(0.01f, targetHeight);
            int px = playing.pivot != null ? playing.pivot.x : w / 2;
            int py = playing.pivot != null ? playing.pivot.y : playing.ground_y;
            // pivot y is from the top of the cell; Unity's sprite pivot is from the bottom, 0..1
            var pivot = new Vector2(px / (float)w, 1f - (py / (float)h));
            rend.sprite = Sprite.Create(tex, rect, pivot, ppu);
        }

        public bool EventNow(string key)
        {
            if (playing == null || playing.events == null) return false;
            var e = playing.events;
            if (key == "hit")
            {
                if (e.hit_start < 0) return false;
                int end = e.hit_end >= 0 ? e.hit_end : e.hit_start;
                return Frame >= e.hit_start && Frame <= end;
            }
            if (key == "footstep")
            {
                if (e.footsteps == null) return false;
                foreach (var s in e.footsteps) if (s == Frame) return true;
                return false;
            }
            int v = -1;
            switch (key)
            {
                case "ball_contact": v = e.ball_contact; break;
                case "throw_release": v = e.throw_release; break;
                case "shoot": v = e.shoot; break;
                case "reload": v = e.reload; break;
            }
            return v == Frame;
        }
    }
}
