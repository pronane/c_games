// Sprite Forge Studio v9 - plays a character's moves straight from SpriteForgeCharacterData (no Animator needed;
// the importer also writes AnimationClips + an AnimatorController if you prefer Mecanim) and keeps hurt / hit
// BoxCollider2D children in step with the frame data.
using System;
using System.Collections.Generic;
using UnityEngine;

namespace SpriteForge
{
    [RequireComponent(typeof(SpriteRenderer))]
    public class SpriteForgeCharacter : MonoBehaviour
    {
        public SpriteForgeCharacterData data;
        public string startMove = "idle";
        public bool facingLeft;
        public bool drawBoxes = true;
        public bool driveColliders = true;

        public event Action<string, int, Rect> HitActive;   // move, frame, hit rect (world units, local space)
        public event Action<string> MoveFinished;

        public string Move { get; private set; }
        public int Frame { get; private set; }

        SpriteRenderer _sr;
        SFMove _mv;
        float _t;
        readonly List<BoxCollider2D> _hurt = new List<BoxCollider2D>();
        readonly List<BoxCollider2D> _hit = new List<BoxCollider2D>();
        Transform _hurtRoot, _hitRoot;

        void Awake()
        {
            _sr = GetComponent<SpriteRenderer>();
            _hurtRoot = Child("Hurtbox");
            _hitRoot = Child("Hitbox");
        }

        void Start()
        {
            if (data != null) Play(startMove);
        }

        Transform Child(string n)
        {
            var t = transform.Find(n);
            if (t == null)
            {
                t = new GameObject(n).transform;
                t.SetParent(transform, false);
            }
            return t;
        }

        public void Play(string move, bool restart = true)
        {
            if (data == null) return;
            var m = data.Find(move);
            if (m == null || m.frames.Count == 0) { Debug.LogWarning("Sprite Forge: no move " + move); return; }
            if (!restart && m == _mv) return;
            _mv = m; Move = move; _t = 0f; SetFrame(0);
        }

        void Update()
        {
            if (_mv == null) return;
            _t += Time.deltaTime;
            int f = Mathf.FloorToInt(_t * _mv.fps);
            if (f >= _mv.frames.Count)
            {
                if (_mv.loop) { _t %= _mv.Duration; f = Mathf.FloorToInt(_t * _mv.fps) % _mv.frames.Count; }
                else { f = _mv.frames.Count - 1; if (Frame != f) SetFrame(f); var n = Move; _mv = null; if (MoveFinished != null) MoveFinished(n); return; }
            }
            if (f != Frame) SetFrame(f);
        }

        public void SetFrame(int f)
        {
            Frame = f;
            var fr = _mv.frames[f];
            _sr.sprite = fr.sprite;
            _sr.flipX = facingLeft;
            if (driveColliders)
            {
                Apply(_hurt, _hurtRoot, fr.hurt, false);
                Apply(_hit, _hitRoot, fr.hit, true);
            }
            if (fr.hit.Count > 0 && HitActive != null) HitActive(Move, f, Mirror(fr.hit[0].rect));
        }

        Rect Mirror(Rect r)
        {
            if (!facingLeft) return r;
            return new Rect(-r.x - r.width, r.y, r.width, r.height);
        }

        void Apply(List<BoxCollider2D> pool, Transform root, List<SFBox> boxes, bool trigger)
        {
            while (pool.Count < boxes.Count)
            {
                var c = root.gameObject.AddComponent<BoxCollider2D>();
                c.isTrigger = true;
                pool.Add(c);
            }
            for (int i = 0; i < pool.Count; i++)
            {
                bool on = i < boxes.Count;
                pool[i].enabled = on;
                if (!on) continue;
                var r = Mirror(boxes[i].rect);
                pool[i].offset = r.center;
                pool[i].size = r.size;
            }
        }

        void OnDrawGizmos()
        {
            if (!drawBoxes || _mv == null || Frame >= _mv.frames.Count) return;
            var fr = _mv.frames[Frame];
            Gizmos.color = new Color(0.2f, 0.6f, 1f, 0.9f);
            foreach (var b in fr.hurt) DrawRect(Mirror(b.rect));
            Gizmos.color = new Color(1f, 0.2f, 0.2f, 0.9f);
            foreach (var b in fr.hit) DrawRect(Mirror(b.rect));
        }

        void DrawRect(Rect r)
        {
            var c = transform.TransformPoint(r.center);
            var s = transform.TransformVector(r.size);
            Gizmos.DrawWireCube(c, new Vector3(s.x, s.y, 0.01f));
        }
    }
}
