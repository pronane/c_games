// Sprite Forge Studio v9 - character data asset (moves, sprites, frame data). Written by the editor importer.
using System;
using System.Collections.Generic;
using UnityEngine;

namespace SpriteForge
{
    [Serializable]
    public class SFBox
    {
        public string part;      // hurt: head / body / legs; hit: "" 
        public Rect rect;        // in world units relative to the feet pivot, y up (Sprite Forge sprites face right)
    }

    [Serializable]
    public class SFFrame
    {
        public Sprite sprite;
        public List<SFBox> hurt = new List<SFBox>();
        public List<SFBox> hit = new List<SFBox>();
    }

    [Serializable]
    public class SFMove
    {
        public string name;
        public float fps = 12f;
        public bool loop;
        public bool attack;
        public int startup, active, recovery, damage, hitstun, blockstun;
        public List<SFFrame> frames = new List<SFFrame>();
        public float Duration { get { return frames.Count / Mathf.Max(1f, fps); } }
    }

    [CreateAssetMenu(menuName = "Sprite Forge/Character Data")]
    public class SpriteForgeCharacterData : ScriptableObject
    {
        public string characterName;
        public float pixelsPerUnit = 100f;
        public Vector2 cellSize;
        public bool framedataEstimated = true;   // measured from the sprite silhouettes by Sprite Forge - tune by hand
        public List<SFMove> moves = new List<SFMove>();

        public SFMove Find(string move)
        {
            for (int i = 0; i < moves.Count; i++)
                if (moves[i].name == move) return moves[i];
            return null;
        }
    }
}
