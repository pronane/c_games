using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using MarioKart64.Core;
using MarioKart64.Entities;

namespace MarioKart64.Rendering
{
    /// <summary>
    /// Authentic N64 / Silicon Graphics (SGI) 3D Pre-Rendered Sprite &amp; Portrait Raytracer.
    /// Just like the original 1996 Mario Kart 64 rendered smooth SGI Alias/PowerAnimator 3D models
    /// into multi-angle billboard sprites, this engine raytraces smooth analytic 3D ellipsoids,
    /// capsules, and yellow-rimmed slick tires with Phong specular lighting, ambient hemisphere fill,
    /// and raytraced self-shadows in parallel across CPU cores at startup.
    /// </summary>
    public static class SgiSpriteGenerator
    {
        public const int YawSteps = 16;
        public const int TotalFramesPerChar = 20; // 0..15 = 360° yaw orbit, 16..19 = rear steering lean (-2, -1, +1, +2)
        public const int KartSpriteSize = 84;

        public static uint[,] KartTextures = new uint[8, TotalFramesPerChar];
        public static uint[] PortraitTextures = new uint[8];      // Close-up 3/4-right N64 HUD portraits!
        public static uint[] FullBodySelectTextures = new uint[8]; // 3/4 front full-kart select showcase

        // SGI Raytraced Scenery & Course Hazard Sprites
        public static uint TexTreeRound;
        public static uint TexTreePine;
        public static uint TexTreePalm;
        public static uint TexCactus;
        public static uint TexLakitu;
        public static uint TexCow;
        public static uint TexPenguin;
        public static uint TexSnowman;
        public static uint TexThwomp;
        public static uint TexYoshiEgg;
        public static uint TexChainChomp;
        public static uint TexGiantMushroom;
        public static uint TexMontyMole;

        // SGI Raytraced Item Sprites (indexed by (int)ItemId, 1..14)
        public static uint[] ItemTextures = new uint[16];

        private static bool _initialized;

        private enum PrimType : byte
        {
            Ellipsoid = 0,
            Capsule = 1,
            WheelX = 2
        }

        private struct RtPrim
        {
            public PrimType Type;
            public Vec3 P1;          // Center (Ellipsoid/Wheel) or Point A (Capsule)
            public Vec3 P2;          // Radii (Ellipsoid), Point B (Capsule), or (Radius, HalfWidth, SteerRad)
            public float Radius;     // Capsule radius
            public Vec3 BoundCenter; // Precomputed bounding sphere center
            public float BoundRadSq; // Precomputed bounding sphere radius^2
            public Color4 Color;
            public float Specular;
            public float Shininess;
        }

        public static void InitializeAll()
        {
            if (_initialized) return;
            _initialized = true;

            // 8 chars * (20 kart views + 1 close-up HUD portrait) = 168 jobs in parallel!
            int framesWithPortrait = TotalFramesPerChar + 1;
            byte[][][] charPixels = new byte[8][][];
            byte[][] portraitPixels = new byte[8][];
            for (int c = 0; c < 8; c++)
            {
                charPixels[c] = new byte[TotalFramesPerChar][];
            }

            int totalKartJobs = 8 * framesWithPortrait;
            Parallel.For(0, totalKartJobs, delegate(int job)
            {
                int charIdx = job / framesWithPortrait;
                int sub = job % framesWithPortrait;
                CharacterSpec spec = CharacterRoster.Get((CharacterId)charIdx);

                if (sub < TotalFramesPerChar)
                {
                    float yawRad = 0f;
                    float steerVisual = 0f;
                    if (sub < YawSteps)
                    {
                        // sub=0 is directly behind kart (camera looking from -Z toward +Z)
                        yawRad = (sub / (float)YawSteps) * MathUtil.TWO_PI;
                    }
                    else
                    {
                        // Dedicated rear steering-lean frames (16=Hard Left, 17=Soft Left, 18=Soft Right, 19=Hard Right)
                        float[] steers = { -0.95f, -0.45f, 0.45f, 0.95f };
                        steerVisual = steers[sub - YawSteps];
                        yawRad = steerVisual * 0.22f; // Positive camOrbitYaw swings nose screen-RIGHT!
                    }

                    List<RtPrim> model = BuildKartAndDriverScene(spec, steerVisual, true);
                    charPixels[charIdx][sub] = RaytraceModel(model, KartSpriteSize, KartSpriteSize, yawRad, 0.20f, 2.28f, 0.78f);
                }
                else
                {
                    // Authentic MK64 Top-4 HUD Close-Up 3/4-Right Headshot Portrait!
                    // At camOrbitYaw = 0.70*PI, eye is at (-X, Y, +Z), so +Z nose points SCREEN-RIGHT (matches N64 HUD)!
                    List<RtPrim> headModel = BuildKartAndDriverScene(spec, 0f, false);
                    float targetY = (spec.Id == CharacterId.Bowser) ? 1.22f : 1.13f;
                    float dist = (spec.Id == CharacterId.Bowser || spec.Id == CharacterId.Toad) ? 1.36f : 1.22f;
                    portraitPixels[charIdx] = RaytraceModel(headModel, 80, 80, MathUtil.PI * 0.70f, 0.08f, dist, targetY);
                }
            });

            // Upload Character & Portrait textures on OpenGL thread
            for (int c = 0; c < 8; c++)
            {
                for (int f = 0; f < TotalFramesPerChar; f++)
                {
                    KartTextures[c, f] = UploadClampSprite(charPixels[c][f], KartSpriteSize, KartSpriteSize);
                }
                PortraitTextures[c] = UploadClampSprite(portraitPixels[c], 80, 80);
                FullBodySelectTextures[c] = KartTextures[c, 6];
            }

            // Render SGI Prop & Hazard Billboards in parallel (13 props viewed from front +Z: yaw ~ 1.16*PI)!
            byte[][] propBufs = new byte[13][];
            Parallel.For(0, 13, delegate(int pIdx)
            {
                List<RtPrim> scene = BuildPropOrHazardScene(pIdx);
                propBufs[pIdx] = RaytraceModel(scene, 80, 80, MathUtil.PI * 1.16f, 0.13f, 2.95f, 0.98f);
            });

            TexTreeRound     = UploadClampSprite(propBufs[0], 80, 80);
            TexTreePine      = UploadClampSprite(propBufs[1], 80, 80);
            TexTreePalm      = UploadClampSprite(propBufs[2], 80, 80);
            TexCactus        = UploadClampSprite(propBufs[3], 80, 80);
            TexLakitu        = UploadClampSprite(propBufs[4], 80, 80);
            TexCow           = UploadClampSprite(propBufs[5], 80, 80);
            TexPenguin       = UploadClampSprite(propBufs[6], 80, 80);
            TexSnowman       = UploadClampSprite(propBufs[7], 80, 80);
            TexThwomp        = UploadClampSprite(propBufs[8], 80, 80);
            TexYoshiEgg      = UploadClampSprite(propBufs[9], 80, 80);
            TexChainChomp    = UploadClampSprite(propBufs[10], 80, 80);
            TexGiantMushroom = UploadClampSprite(propBufs[11], 80, 80);
            TexMontyMole     = UploadClampSprite(propBufs[12], 80, 80);

            byte[][] itemBufs = new byte[15][];
            Parallel.For(1, 15, delegate(int itemIdx)
            {
                List<RtPrim> scene = BuildItemScene((ItemId)itemIdx);
                itemBufs[itemIdx] = RaytraceModel(scene, 64, 64, MathUtil.PI * 1.15f, 0.22f, 2.45f, 0.56f);
            });

            for (int i = 1; i <= 14; i++)
            {
                ItemTextures[i] = UploadClampSprite(itemBufs[i], 64, 64);
            }
        }

        public static uint GetItemTexture(ItemId id)
        {
            int idx = (int)id;
            if (idx >= 1 && idx <= 14) return ItemTextures[idx];
            return 0;
        }

        private static uint UploadClampSprite(byte[] rgba, int w, int h)
        {
            uint[] ids = new uint[1];
            Gl.glGenTextures(1, ids);
            uint id = ids[0];
            Gl.glBindTexture(Gl.GL_TEXTURE_2D, id);
            Gl.glTexParameteri(Gl.GL_TEXTURE_2D, Gl.GL_TEXTURE_MIN_FILTER, Gl.GL_LINEAR_FILTER);
            Gl.glTexParameteri(Gl.GL_TEXTURE_2D, Gl.GL_TEXTURE_MAG_FILTER, Gl.GL_LINEAR_FILTER);
            Gl.glTexParameteri(Gl.GL_TEXTURE_2D, Gl.GL_TEXTURE_WRAP_S, Gl.GL_CLAMP);
            Gl.glTexParameteri(Gl.GL_TEXTURE_2D, Gl.GL_TEXTURE_WRAP_T, Gl.GL_CLAMP);
            Gl.glTexImage2D(Gl.GL_TEXTURE_2D, 0, (int)Gl.GL_RGBA, w, h, 0, Gl.GL_RGBA, Gl.GL_UNSIGNED_BYTE, rgba);
            return id;
        }

        private static void AddEllipsoid(List<RtPrim> list, float x, float y, float z, float rx, float ry, float rz, Color4 col, float spec = 0.35f, float shin = 24f)
        {
            RtPrim p = new RtPrim();
            p.Type = PrimType.Ellipsoid;
            p.P1 = new Vec3(x, y, z);
            p.P2 = new Vec3(rx, ry, rz);
            float maxR = Math.Max(rx, Math.Max(ry, rz));
            p.BoundCenter = p.P1;
            p.BoundRadSq = maxR * maxR;
            p.Color = col;
            p.Specular = spec;
            p.Shininess = shin;
            list.Add(p);
        }

        private static void AddCapsule(List<RtPrim> list, Vec3 a, Vec3 b, float r, Color4 col, float spec = 0.4f, float shin = 28f)
        {
            RtPrim p = new RtPrim();
            p.Type = PrimType.Capsule;
            p.P1 = a;
            p.P2 = b;
            p.Radius = r;
            p.BoundCenter = (a + b) * 0.5f;
            float halfLen = (b - a).Length * 0.5f + r;
            p.BoundRadSq = halfLen * halfLen;
            p.Color = col;
            p.Specular = spec;
            p.Shininess = shin;
            list.Add(p);
        }

        private static void AddWheel(List<RtPrim> list, float x, float y, float z, float radius, float halfWidth, float steerAngle)
        {
            Color4 rubber = Color4.FromBytes(20, 22, 26);
            Color4 yellowRim = Color4.FromBytes(250, 204, 26); // Authentic MK64 yellow wheel hubs!
            Color4 darkHub = Color4.FromBytes(55, 58, 65);

            RtPrim tire = new RtPrim();
            tire.Type = PrimType.WheelX;
            tire.P1 = new Vec3(x, y, z);
            tire.P2 = new Vec3(radius, halfWidth, steerAngle);
            tire.BoundCenter = tire.P1;
            tire.BoundRadSq = radius * radius + halfWidth * halfWidth;
            tire.Color = rubber;
            tire.Specular = 0.30f;
            tire.Shininess = 16f;
            list.Add(tire);

            float outSign = (x < 0f) ? -1f : 1f;
            float sx = (float)Math.Cos(steerAngle) * outSign * (halfWidth * 0.80f);
            float sz = -(float)Math.Sin(steerAngle) * outSign * (halfWidth * 0.80f);
            AddEllipsoid(list, x + sx, y, z + sz, 0.055f, radius * 0.58f, radius * 0.58f, yellowRim, 0.75f, 42f);
            AddEllipsoid(list, x + sx * 1.15f, y, z + sz * 1.15f, 0.045f, radius * 0.24f, radius * 0.24f, darkHub, 0.6f, 32f);
        }

        // Builds the authentic N64 Chibi Character + Compact Pipe-Frame Go-Kart!
        // Note: At rear view (camOrbitYaw = 0), camera looks from -Z toward +Z, so -X is SCREEN-RIGHT and +X is SCREEN-LEFT!
        private static List<RtPrim> BuildKartAndDriverScene(CharacterSpec ch, float steer, bool includeKart)
        {
            List<RtPrim> m = new List<RtPrim>(56);

            Color4 paintA = ch.PrimaryColor;
            // In MK64, Wario drives a purple pipe-frame kart, Toad drives a blue pipe-frame kart, DK yellow/brown, Bowser gold/orange!
            if (ch.Id == CharacterId.Wario) paintA = Color4.FromBytes(148, 42, 206);
            else if (ch.Id == CharacterId.Toad) paintA = Color4.FromBytes(42, 96, 238);
            else if (ch.Id == CharacterId.DonkeyKong) paintA = Color4.FromBytes(228, 172, 28);
            else if (ch.Id == CharacterId.Bowser) paintA = Color4.FromBytes(236, 138, 24);

            Color4 chrome = Color4.FromBytes(216, 224, 236);
            Color4 darkMetal = Color4.FromBytes(46, 50, 58);
            Color4 seatCol = Color4.FromBytes(26, 30, 40);
            Color4 white = Color4.FromBytes(250, 250, 252);
            Color4 black = Color4.FromBytes(18, 18, 22);

            if (includeKart)
            {
                // === 1. COMPACT AUTHENTIC MK64 PIPE-FRAME GO-KART (matches lu-1.jpg & lu-2.jpg!) ===
                float steerAng = -steer * 0.36f;
                // Sleek upright rear & front slicks with yellow MK64 hubs!
                AddWheel(m, -0.50f, 0.27f, -0.44f, 0.27f, 0.14f, 0f);
                AddWheel(m,  0.50f, 0.27f, -0.44f, 0.27f, 0.14f, 0f);
                AddWheel(m, -0.45f, 0.23f,  0.52f, 0.23f, 0.12f, steerAng);
                AddWheel(m,  0.45f, 0.23f,  0.52f, 0.23f, 0.12f, steerAng);

                // Axles & floor pan
                AddCapsule(m, new Vec3(-0.45f, 0.23f,  0.52f), new Vec3(0.45f, 0.23f,  0.52f), 0.045f, darkMetal, 0.5f, 28f);
                AddCapsule(m, new Vec3(-0.50f, 0.27f, -0.44f), new Vec3(0.50f, 0.27f, -0.44f), 0.050f, darkMetal, 0.5f, 28f);
                AddEllipsoid(m, 0f, 0.22f, 0.05f, 0.36f, 0.08f, 0.58f, darkMetal, 0.35f, 20f);

                // Painted side pods, nose cowl & iconic U-shaped painted rear tubular bumper bar!
                AddCapsule(m, new Vec3(-0.37f, 0.23f, -0.46f), new Vec3(-0.34f, 0.22f, 0.58f), 0.068f, paintA, 0.65f, 38f);
                AddCapsule(m, new Vec3( 0.37f, 0.23f, -0.46f), new Vec3( 0.34f, 0.22f, 0.58f), 0.068f, paintA, 0.65f, 38f);
                AddCapsule(m, new Vec3(-0.32f, 0.22f,  0.68f), new Vec3( 0.32f, 0.22f, 0.68f), 0.068f, paintA, 0.65f, 38f);
                // Rear painted horizontal + vertical frame bumper right between rear tires (exact lu-1.jpg detail!)
                AddCapsule(m, new Vec3(-0.33f, 0.25f, -0.58f), new Vec3( 0.33f, 0.25f, -0.58f), 0.058f, paintA, 0.68f, 40f);
                AddCapsule(m, new Vec3(-0.16f, 0.16f, -0.58f), new Vec3(-0.16f, 0.35f, -0.56f), 0.048f, paintA, 0.68f, 40f);
                AddCapsule(m, new Vec3( 0.16f, 0.16f, -0.58f), new Vec3( 0.16f, 0.35f, -0.56f), 0.048f, paintA, 0.68f, 40f);

                // Sculpted front nose cone + white emblem circle
                AddEllipsoid(m, 0f, 0.33f, 0.52f, 0.26f, 0.15f, 0.28f, paintA, 0.70f, 44f);
                AddEllipsoid(m, 0f, 0.38f, 0.70f, 0.12f, 0.09f, 0.07f, white, 0.5f, 28f);

                // Low bucket seat & compact low silver/dark engine block (never blocks character back!)
                AddEllipsoid(m, 0f, 0.40f, -0.10f, 0.28f, 0.20f, 0.22f, seatCol, 0.2f, 12f);
                AddEllipsoid(m, 0f, 0.39f, -0.46f, 0.21f, 0.14f, 0.16f, darkMetal, 0.6f, 32f);
                AddEllipsoid(m, 0f, 0.49f, -0.44f, 0.15f, 0.08f, 0.12f, chrome, 0.88f, 56f);
                AddCapsule(m, new Vec3(-0.12f, 0.42f, -0.48f), new Vec3(-0.14f, 0.50f, -0.58f), 0.055f, darkMetal, 0.7f, 40f);
                AddCapsule(m, new Vec3( 0.12f, 0.42f, -0.48f), new Vec3( 0.14f, 0.50f, -0.58f), 0.055f, darkMetal, 0.7f, 40f);

                // Steering Column & Wheel
                AddCapsule(m, new Vec3(0f, 0.34f, 0.40f), new Vec3(0f, 0.64f, 0.20f), 0.042f, darkMetal, 0.4f, 20f);
                AddEllipsoid(m, 0f, 0.66f, 0.18f, 0.16f, 0.14f, 0.045f, black, 0.35f, 18f);
            }

            // === 2. EXPRESSIVE LARGE-HEADED SGI N64 CHARACTERS ===
            // Steering RIGHT (steer > 0) leans toward -X (screen-RIGHT)!
            float leanX = -steer * 0.13f;
            Color4 skin = ch.SkinOrSnoutColor;

            switch (ch.Id)
            {
                case CharacterId.Mario:
                case CharacterId.Luigi:
                    {
                        bool isLuigi = (ch.Id == CharacterId.Luigi);
                        float hScale = isLuigi ? 1.07f : 1.00f;
                        float wScale = isLuigi ? 0.92f : 1.03f;
                        Color4 capCol = isLuigi ? Color4.FromBytes(32, 204, 48) : Color4.FromBytes(238, 26, 28);
                        Color4 overalls = Color4.FromBytes(28, 76, 214);
                        Color4 hairBrown = Color4.FromBytes(88, 42, 16);
                        Color4 mustacheBrown = Color4.FromBytes(48, 22, 10);

                        // Plump Blue Overalls + Red/Green Shirt + Overall Straps on Back!
                        AddEllipsoid(m, leanX * 0.5f, 0.60f * hScale, -0.06f, 0.27f * wScale, 0.26f * hScale, 0.22f, overalls, 0.25f, 16f);
                        AddEllipsoid(m, leanX * 0.6f, 0.75f * hScale, -0.05f, 0.28f * wScale, 0.16f, 0.20f, capCol, 0.28f, 18f);
                        AddCapsule(m, new Vec3(leanX * 0.5f - 0.11f, 0.62f * hScale, -0.23f), new Vec3(leanX * 0.6f - 0.12f, 0.84f * hScale, -0.18f), 0.048f, overalls, 0.25f, 16f);
                        AddCapsule(m, new Vec3(leanX * 0.5f + 0.11f, 0.62f * hScale, -0.23f), new Vec3(leanX * 0.6f + 0.12f, 0.84f * hScale, -0.18f), 0.048f, overalls, 0.25f, 16f);

                        if (includeKart)
                        {
                            AddCapsule(m, new Vec3(-0.26f * wScale + leanX * 0.5f, 0.75f * hScale, -0.02f), new Vec3(-0.14f, 0.66f, 0.18f), 0.088f, capCol, 0.28f, 16f);
                            AddCapsule(m, new Vec3( 0.26f * wScale + leanX * 0.5f, 0.75f * hScale, -0.02f), new Vec3( 0.14f, 0.66f, 0.18f), 0.088f, capCol, 0.28f, 16f);
                            AddEllipsoid(m, -0.14f, 0.66f, 0.19f, 0.095f, 0.085f, 0.095f, white, 0.35f, 20f);
                            AddEllipsoid(m,  0.14f, 0.66f, 0.19f, 0.095f, 0.085f, 0.095f, white, 0.35f, 20f);
                        }

                        // Large Chibi N64 Head + Prominent Side Ears + Dark-Brown Hair Nape + Big Bulbous Nose!
                        float hy = 1.08f * hScale;
                        AddEllipsoid(m, leanX, hy, 0.00f, 0.33f * wScale, 0.31f, 0.33f, skin, 0.30f, 20f);
                        // Crisp dark-brown hair band cradling nape of neck beneath the cap!
                        AddEllipsoid(m, leanX, hy - 0.08f, -0.16f, 0.31f * wScale, 0.17f, 0.21f, hairBrown, 0.18f, 10f);
                        // Plump flesh ears sticking out cleanly on left & right (exact lu-1.jpg silhouette!)
                        AddEllipsoid(m, leanX - 0.34f * wScale, hy - 0.03f, -0.02f, 0.085f, 0.115f, 0.08f, skin, 0.28f, 16f);
                        AddEllipsoid(m, leanX + 0.34f * wScale, hy - 0.03f, -0.02f, 0.085f, 0.115f, 0.08f, skin, 0.28f, 16f);

                        // Big bulbous nose, sculpted mustache, & large N64 white eyes + blue irises!
                        AddEllipsoid(m, leanX, hy - 0.02f, 0.33f, 0.145f, 0.115f, 0.145f, skin, 0.36f, 22f);
                        AddEllipsoid(m, leanX, hy - 0.11f, 0.28f, 0.22f * wScale, 0.068f, 0.10f, mustacheBrown, 0.18f, 10f);
                        AddEllipsoid(m, leanX - 0.10f, hy + 0.06f, 0.28f, 0.068f, 0.095f, 0.04f, white, 0.5f, 24f);
                        AddEllipsoid(m, leanX + 0.10f, hy + 0.06f, 0.28f, 0.068f, 0.095f, 0.04f, white, 0.5f, 24f);
                        AddEllipsoid(m, leanX - 0.09f, hy + 0.05f, 0.31f, 0.038f, 0.060f, 0.03f, Color4.FromBytes(22, 96, 220), 0.7f, 36f);
                        AddEllipsoid(m, leanX + 0.09f, hy + 0.05f, 0.31f, 0.038f, 0.060f, 0.03f, Color4.FromBytes(22, 96, 220), 0.7f, 36f);

                        // Iconic Big Domed N64 Cloth Cap wrapping down the back of the head to the ears (lu-1.jpg!)
                        AddEllipsoid(m, leanX, hy + 0.14f, -0.04f, 0.37f * wScale, 0.27f, 0.38f, capCol, 0.44f, 28f);
                        AddEllipsoid(m, leanX, hy + 0.13f,  0.24f, 0.31f * wScale, 0.065f, 0.22f, capCol.ScaleRGB(0.82f), 0.40f, 24f);
                        AddEllipsoid(m, leanX, hy + 0.24f,  0.28f, 0.125f, 0.110f, 0.05f, white, 0.45f, 24f);
                    }
                    break;

                case CharacterId.Peach:
                    {
                        Color4 dressPink = Color4.FromBytes(255, 118, 196);
                        Color4 darkPink = Color4.FromBytes(236, 52, 150);
                        Color4 blonde = Color4.FromBytes(255, 222, 38);
                        Color4 gold = Color4.FromBytes(255, 192, 22);
                        Color4 ruby = Color4.FromBytes(242, 24, 62);
                        Color4 sapphire = Color4.FromBytes(32, 128, 250);

                        AddEllipsoid(m, leanX * 0.5f, 0.64f, -0.04f, 0.26f, 0.28f, 0.21f, dressPink, 0.42f, 28f);
                        AddEllipsoid(m, leanX * 0.5f - 0.28f, 0.77f, -0.02f, 0.13f, 0.13f, 0.13f, darkPink, 0.42f, 26f);
                        AddEllipsoid(m, leanX * 0.5f + 0.28f, 0.77f, -0.02f, 0.13f, 0.13f, 0.13f, darkPink, 0.42f, 26f);
                        if (includeKart)
                        {
                            AddCapsule(m, new Vec3(-0.25f + leanX * 0.5f, 0.75f, -0.02f), new Vec3(-0.13f, 0.66f, 0.18f), 0.068f, white, 0.38f, 22f);
                            AddCapsule(m, new Vec3( 0.25f + leanX * 0.5f, 0.75f, -0.02f), new Vec3( 0.13f, 0.66f, 0.18f), 0.068f, white, 0.38f, 22f);
                        }

                        // Large Chibi Head + Rich Golden Hair Cascade + Flared Flip-Locks + Crown!
                        AddEllipsoid(m, leanX, 1.09f, 0.03f, 0.29f, 0.29f, 0.29f, skin, 0.32f, 22f);
                        AddEllipsoid(m, leanX, 1.15f,-0.06f, 0.37f, 0.31f, 0.33f, blonde, 0.50f, 34f);
                        AddEllipsoid(m, leanX, 0.88f,-0.22f, 0.35f, 0.22f, 0.18f, blonde, 0.50f, 34f);
                        AddCapsule(m, new Vec3(leanX - 0.20f, 1.08f, -0.08f), new Vec3(leanX - 0.36f, 0.82f, -0.14f), 0.14f, blonde, 0.50f, 34f);
                        AddCapsule(m, new Vec3(leanX + 0.20f, 1.08f, -0.08f), new Vec3(leanX + 0.36f, 0.82f, -0.14f), 0.14f, blonde, 0.50f, 34f);
                        // Forehead bangs!
                        AddEllipsoid(m, leanX - 0.12f, 1.24f, 0.24f, 0.14f, 0.09f, 0.10f, blonde, 0.50f, 34f);
                        AddEllipsoid(m, leanX + 0.12f, 1.24f, 0.24f, 0.14f, 0.09f, 0.10f, blonde, 0.50f, 34f);

                        // Big Anime-N64 Eyes + Sapphire Earrings
                        AddEllipsoid(m, leanX - 0.10f, 1.10f, 0.29f, 0.055f, 0.080f, 0.03f, white, 0.5f, 24f);
                        AddEllipsoid(m, leanX + 0.10f, 1.10f, 0.29f, 0.055f, 0.080f, 0.03f, white, 0.5f, 24f);
                        AddEllipsoid(m, leanX - 0.09f, 1.10f, 0.31f, 0.035f, 0.055f, 0.03f, sapphire, 0.7f, 36f);
                        AddEllipsoid(m, leanX + 0.09f, 1.10f, 0.31f, 0.035f, 0.055f, 0.03f, sapphire, 0.7f, 36f);
                        AddEllipsoid(m, leanX - 0.31f, 1.01f, 0.04f, 0.06f, 0.06f, 0.06f, sapphire, 0.85f, 48f);
                        AddEllipsoid(m, leanX + 0.31f, 1.01f, 0.04f, 0.06f, 0.06f, 0.06f, sapphire, 0.85f, 48f);

                        // Prominent Royal Golden Crown + Gems!
                        AddEllipsoid(m, leanX, 1.43f, -0.02f, 0.20f, 0.09f, 0.20f, gold, 0.92f, 64f);
                        AddCapsule(m, new Vec3(leanX, 1.44f,  0.14f), new Vec3(leanX, 1.60f,  0.16f), 0.048f, gold, 0.92f, 64f);
                        AddCapsule(m, new Vec3(leanX, 1.44f, -0.18f), new Vec3(leanX, 1.59f, -0.20f), 0.048f, gold, 0.92f, 64f);
                        AddCapsule(m, new Vec3(leanX - 0.16f, 1.44f, -0.02f), new Vec3(leanX - 0.20f, 1.59f, -0.02f), 0.048f, gold, 0.92f, 64f);
                        AddCapsule(m, new Vec3(leanX + 0.16f, 1.44f, -0.02f), new Vec3(leanX + 0.20f, 1.59f, -0.02f), 0.048f, gold, 0.92f, 64f);
                        AddEllipsoid(m, leanX, 1.47f,  0.18f, 0.055f, 0.065f, 0.03f, ruby, 0.95f, 64f);
                        AddEllipsoid(m, leanX, 1.47f, -0.22f, 0.055f, 0.065f, 0.03f, ruby, 0.95f, 64f);
                    }
                    break;

                case CharacterId.Toad:
                    {
                        Color4 blueVest = Color4.FromBytes(34, 88, 232);
                        Color4 goldTrim = Color4.FromBytes(252, 208, 32);
                        Color4 redSpot = Color4.FromBytes(238, 26, 28);

                        // White diaper/pants + Royal Blue Vest with Gold Trim!
                        AddEllipsoid(m, leanX * 0.5f, 0.54f, -0.05f, 0.24f, 0.18f, 0.21f, white, 0.30f, 18f);
                        AddEllipsoid(m, leanX * 0.5f, 0.68f, -0.05f, 0.25f, 0.19f, 0.21f, blueVest, 0.32f, 20f);
                        AddEllipsoid(m, leanX * 0.5f, 0.58f, -0.05f, 0.26f, 0.045f, 0.22f, goldTrim, 0.5f, 28f);
                        if (includeKart)
                        {
                            AddCapsule(m, new Vec3(-0.22f + leanX * 0.5f, 0.68f, -0.02f), new Vec3(-0.13f, 0.65f, 0.18f), 0.072f, skin, 0.28f, 18f);
                            AddCapsule(m, new Vec3( 0.22f + leanX * 0.5f, 0.68f, -0.02f), new Vec3( 0.13f, 0.65f, 0.18f), 0.072f, skin, 0.28f, 18f);
                        }

                        // Cute Round Face
                        AddEllipsoid(m, leanX, 0.94f, 0.03f, 0.26f, 0.22f, 0.26f, skin, 0.30f, 20f);
                        AddEllipsoid(m, leanX - 0.08f, 0.95f, 0.26f, 0.042f, 0.075f, 0.03f, black, 0.6f, 32f);
                        AddEllipsoid(m, leanX + 0.08f, 0.95f, 0.26f, 0.042f, 0.075f, 0.03f, black, 0.6f, 32f);

                        // HUGE Puffy Snow-White Mushroom Cap (matches characters--3.png!) + 5 Large Crimson Spots!
                        AddEllipsoid(m, leanX, 1.24f, -0.02f, 0.49f, 0.36f, 0.49f, white, 0.52f, 36f);
                        AddEllipsoid(m, leanX, 1.56f, -0.02f, 0.20f, 0.07f, 0.20f, redSpot, 0.52f, 36f); // Top spot
                        AddEllipsoid(m, leanX, 1.25f, -0.44f, 0.22f, 0.21f, 0.10f, redSpot, 0.52f, 36f); // Big Rear spot!
                        AddEllipsoid(m, leanX, 1.26f,  0.40f, 0.21f, 0.20f, 0.10f, redSpot, 0.52f, 36f); // Big Front spot!
                        AddEllipsoid(m, leanX - 0.42f, 1.25f, -0.02f, 0.10f, 0.21f, 0.22f, redSpot, 0.52f, 36f); // Left spot!
                        AddEllipsoid(m, leanX + 0.42f, 1.25f, -0.02f, 0.10f, 0.21f, 0.22f, redSpot, 0.52f, 36f); // Right spot!
                    }
                    break;

                case CharacterId.Yoshi:
                    {
                        Color4 yGreen = Color4.FromBytes(56, 214, 52);
                        Color4 redSpine = Color4.FromBytes(238, 38, 32);

                        // Green Body + White Belly + Red/White Saddle Shell on Back!
                        AddEllipsoid(m, leanX * 0.5f, 0.64f, -0.05f, 0.26f, 0.27f, 0.23f, yGreen, 0.38f, 26f);
                        AddEllipsoid(m, leanX * 0.5f, 0.66f, -0.25f, 0.20f, 0.16f, 0.11f, white, 0.4f, 24f);
                        AddEllipsoid(m, leanX * 0.5f, 0.68f, -0.28f, 0.18f, 0.15f, 0.11f, redSpine, 0.55f, 36f);
                        if (includeKart)
                        {
                            AddCapsule(m, new Vec3(-0.22f + leanX * 0.5f, 0.72f, -0.02f), new Vec3(-0.13f, 0.66f, 0.18f), 0.078f, yGreen, 0.35f, 22f);
                            AddCapsule(m, new Vec3( 0.22f + leanX * 0.5f, 0.72f, -0.02f), new Vec3( 0.13f, 0.66f, 0.18f), 0.078f, yGreen, 0.35f, 22f);
                        }

                        // Large Yoshi Head, Wide Puffy White Cheeks, Tall Twin Eye Domes, Big Round Snout & 3 Red Spines!
                        AddEllipsoid(m, leanX, 1.06f, -0.03f, 0.30f, 0.28f, 0.30f, yGreen, 0.42f, 28f);
                        AddEllipsoid(m, leanX - 0.22f, 1.00f, 0.03f, 0.15f, 0.15f, 0.17f, white, 0.35f, 22f); // Plump white cheek L
                        AddEllipsoid(m, leanX + 0.22f, 1.00f, 0.03f, 0.15f, 0.15f, 0.17f, white, 0.35f, 22f); // Plump white cheek R
                        AddEllipsoid(m, leanX, 1.08f,  0.34f, 0.24f, 0.21f, 0.24f, yGreen, 0.45f, 30f);       // Big bulbous Yoshi nose!
                        AddEllipsoid(m, leanX - 0.11f, 1.31f, 0.07f, 0.11f, 0.17f, 0.11f, yGreen, 0.42f, 28f); // Tall eye dome L
                        AddEllipsoid(m, leanX + 0.11f, 1.31f, 0.07f, 0.11f, 0.17f, 0.11f, yGreen, 0.42f, 28f); // Tall eye dome R
                        AddEllipsoid(m, leanX - 0.11f, 1.32f, 0.15f, 0.075f, 0.12f, 0.05f, white, 0.6f, 32f);
                        AddEllipsoid(m, leanX + 0.11f, 1.32f, 0.15f, 0.075f, 0.12f, 0.05f, white, 0.6f, 32f);
                        AddEllipsoid(m, leanX - 0.10f, 1.32f, 0.19f, 0.035f, 0.06f, 0.03f, black, 0.6f, 32f);
                        AddEllipsoid(m, leanX + 0.10f, 1.32f, 0.19f, 0.035f, 0.06f, 0.03f, black, 0.6f, 32f);

                        // 3 Vivid Red Crest Spines down back of skull!
                        AddEllipsoid(m, leanX, 1.28f, -0.29f, 0.075f, 0.12f, 0.13f, redSpine, 0.5f, 30f);
                        AddEllipsoid(m, leanX, 1.08f, -0.34f, 0.075f, 0.12f, 0.13f, redSpine, 0.5f, 30f);
                        AddEllipsoid(m, leanX, 0.89f, -0.30f, 0.070f, 0.10f, 0.11f, redSpine, 0.5f, 30f);
                    }
                    break;

                case CharacterId.DonkeyKong:
                    {
                        Color4 fur = Color4.FromBytes(132, 66, 24);
                        Color4 darkFur = Color4.FromBytes(96, 46, 16);
                        Color4 tanMuzzle = Color4.FromBytes(228, 174, 120);
                        Color4 redTie = Color4.FromBytes(236, 26, 26);

                        // Massive Gorilla Back & Broad Deltoids
                        AddEllipsoid(m, leanX * 0.5f, 0.72f, -0.08f, 0.42f, 0.31f, 0.27f, fur, 0.28f, 16f);
                        AddEllipsoid(m, leanX * 0.5f, 0.86f, -0.06f, 0.46f, 0.22f, 0.25f, fur, 0.30f, 18f);
                        if (includeKart)
                        {
                            AddCapsule(m, new Vec3(-0.44f + leanX * 0.5f, 0.84f, 0.00f), new Vec3(-0.34f, 0.74f, 0.14f), 0.135f, fur, 0.26f, 14f);
                            AddCapsule(m, new Vec3( 0.44f + leanX * 0.5f, 0.84f, 0.00f), new Vec3( 0.34f, 0.74f, 0.14f), 0.135f, fur, 0.26f, 14f);
                            AddCapsule(m, new Vec3(-0.34f, 0.74f, 0.14f), new Vec3(-0.15f, 0.67f, 0.19f), 0.115f, darkFur, 0.25f, 14f);
                            AddCapsule(m, new Vec3( 0.34f, 0.74f, 0.14f), new Vec3( 0.15f, 0.67f, 0.19f), 0.115f, darkFur, 0.25f, 14f);
                        }

                        // Red DK Tie
                        AddEllipsoid(m, leanX * 0.6f, 0.94f, 0.00f, 0.24f, 0.055f, 0.24f, redTie, 0.4f, 24f);
                        AddCapsule(m, new Vec3(leanX * 0.5f, 0.92f, 0.22f), new Vec3(leanX * 0.5f, 0.58f, 0.27f), 0.085f, redTie, 0.42f, 24f);

                        // Iconic Smooth Conical DK Cranium + Pointed Swirl Peak + Tan Brow & Wide Ape Muzzle!
                        AddEllipsoid(m, leanX, 1.13f, -0.01f, 0.35f, 0.29f, 0.33f, fur, 0.30f, 18f);
                        AddEllipsoid(m, leanX, 1.28f, -0.02f, 0.28f, 0.24f, 0.27f, fur, 0.30f, 18f);
                        AddCapsule(m, new Vec3(leanX, 1.32f, -0.02f), new Vec3(leanX, 1.49f, 0.07f), 0.135f, fur, 0.32f, 20f);
                        AddEllipsoid(m, leanX - 0.35f, 1.13f, 0.00f, 0.085f, 0.11f, 0.075f, tanMuzzle, 0.3f, 18f);
                        AddEllipsoid(m, leanX + 0.35f, 1.13f, 0.00f, 0.085f, 0.11f, 0.075f, tanMuzzle, 0.3f, 18f);
                        AddEllipsoid(m, leanX, 1.22f,  0.26f, 0.26f, 0.09f, 0.14f, tanMuzzle, 0.32f, 18f); // Heavy furrowed brow!
                        AddEllipsoid(m, leanX, 1.05f,  0.29f, 0.28f, 0.17f, 0.22f, tanMuzzle, 0.32f, 20f); // Wide gorilla snout!
                        AddEllipsoid(m, leanX - 0.09f, 1.17f, 0.31f, 0.05f, 0.06f, 0.03f, white, 0.6f, 32f);
                        AddEllipsoid(m, leanX + 0.09f, 1.17f, 0.31f, 0.05f, 0.06f, 0.03f, white, 0.6f, 32f);
                        AddEllipsoid(m, leanX - 0.08f, 1.17f, 0.33f, 0.028f, 0.038f, 0.02f, black, 0.6f, 32f);
                        AddEllipsoid(m, leanX + 0.08f, 1.17f, 0.33f, 0.028f, 0.038f, 0.02f, black, 0.6f, 32f);
                    }
                    break;

                case CharacterId.Wario:
                    {
                        Color4 yellow = Color4.FromBytes(255, 220, 18);
                        Color4 purple = Color4.FromBytes(142, 36, 198);
                        Color4 pinkNose = Color4.FromBytes(248, 112, 146);
                        Color4 hairBrown = Color4.FromBytes(92, 52, 18);

                        // Broad Yellow Shirt Shoulders + Purple Overalls & Visible Purple Back Straps (exact lu-2.jpg!)
                        AddEllipsoid(m, leanX * 0.5f, 0.64f, -0.07f, 0.34f, 0.28f, 0.25f, purple, 0.30f, 20f);
                        AddEllipsoid(m, leanX * 0.5f, 0.80f, -0.06f, 0.38f, 0.19f, 0.24f, yellow, 0.34f, 22f);
                        AddCapsule(m, new Vec3(leanX * 0.5f - 0.14f, 0.66f, -0.27f), new Vec3(leanX * 0.5f - 0.16f, 0.90f, -0.20f), 0.055f, purple, 0.30f, 20f);
                        AddCapsule(m, new Vec3(leanX * 0.5f + 0.14f, 0.66f, -0.27f), new Vec3(leanX * 0.5f + 0.16f, 0.90f, -0.20f), 0.055f, purple, 0.30f, 20f);
                        if (includeKart)
                        {
                            AddCapsule(m, new Vec3(-0.34f + leanX * 0.5f, 0.79f, -0.02f), new Vec3(-0.16f, 0.67f, 0.18f), 0.105f, skin, 0.28f, 18f);
                            AddCapsule(m, new Vec3( 0.34f + leanX * 0.5f, 0.79f, -0.02f), new Vec3( 0.16f, 0.67f, 0.18f), 0.105f, skin, 0.28f, 18f);
                            AddEllipsoid(m, -0.16f, 0.67f, 0.19f, 0.10f, 0.085f, 0.095f, white, 0.35f, 20f);
                            AddEllipsoid(m,  0.16f, 0.67f, 0.19f, 0.10f, 0.085f, 0.095f, white, 0.35f, 20f);
                        }

                        // Large Wide Head, Big Ears, Brown Hair Nape, Bulbous Pink Nose, Zig-Zag Mustache & Big Yellow Cap!
                        float hy = 1.11f;
                        AddEllipsoid(m, leanX, hy, -0.01f, 0.37f, 0.30f, 0.34f, skin, 0.30f, 20f);
                        AddEllipsoid(m, leanX, hy - 0.08f, -0.18f, 0.34f, 0.16f, 0.20f, hairBrown, 0.20f, 12f);
                        AddEllipsoid(m, leanX - 0.38f, hy - 0.02f, -0.02f, 0.09f, 0.12f, 0.08f, skin, 0.28f, 16f);
                        AddEllipsoid(m, leanX + 0.38f, hy - 0.02f, -0.02f, 0.09f, 0.12f, 0.08f, skin, 0.28f, 16f);
                        AddEllipsoid(m, leanX, hy - 0.02f,  0.34f, 0.16f, 0.12f, 0.15f, pinkNose, 0.42f, 24f);
                        // Zig-zag black mustache + wide white grin!
                        AddCapsule(m, new Vec3(leanX - 0.28f, hy - 0.08f, 0.28f), new Vec3(leanX + 0.28f, hy - 0.08f, 0.28f), 0.052f, black, 0.2f, 10f);
                        AddEllipsoid(m, leanX, hy - 0.15f, 0.27f, 0.18f, 0.055f, 0.08f, white, 0.5f, 24f);
                        AddEllipsoid(m, leanX - 0.11f, hy + 0.06f, 0.30f, 0.065f, 0.08f, 0.04f, white, 0.5f, 24f);
                        AddEllipsoid(m, leanX + 0.11f, hy + 0.06f, 0.30f, 0.065f, 0.08f, 0.04f, white, 0.5f, 24f);
                        AddEllipsoid(m, leanX - 0.10f, hy + 0.06f, 0.33f, 0.032f, 0.045f, 0.02f, black, 0.6f, 32f);
                        AddEllipsoid(m, leanX + 0.10f, hy + 0.06f, 0.33f, 0.032f, 0.045f, 0.02f, black, 0.6f, 32f);

                        // Big Domed Bright-Yellow Wario Cap covering back of head down to ears (lu-2.jpg & characters--2.png!)
                        AddEllipsoid(m, leanX, hy + 0.15f, -0.04f, 0.41f, 0.26f, 0.40f, yellow, 0.46f, 28f);
                        AddEllipsoid(m, leanX, hy + 0.13f,  0.26f, 0.33f, 0.055f, 0.20f, white, 0.45f, 28f);
                        AddEllipsoid(m, leanX, hy + 0.24f,  0.30f, 0.12f, 0.10f, 0.05f, purple, 0.45f, 24f); // 'W' emblem!
                    }
                    break;

                case CharacterId.Bowser:
                    {
                        Color4 shellGreen = Color4.FromBytes(28, 152, 46);
                        Color4 scaleOrange = Color4.FromBytes(244, 172, 36);
                        Color4 maneRed = Color4.FromBytes(238, 36, 20);
                        Color4 ivory = Color4.FromBytes(250, 246, 228);

                        // Massive Domed Spiked Green Koopa Shell + Thick White Collar Rim!
                        AddEllipsoid(m, leanX * 0.4f, 0.78f, -0.12f, 0.44f, 0.42f, 0.34f, shellGreen, 0.45f, 30f);
                        AddEllipsoid(m, leanX * 0.4f, 0.79f, -0.03f, 0.46f, 0.43f, 0.10f, ivory, 0.35f, 22f);

                        float[,] spikeOffsets =
                        {
                            {  0.00f, 1.04f, -0.42f },
                            {  0.00f, 0.75f, -0.46f },
                            { -0.25f, 0.92f, -0.38f },
                            {  0.25f, 0.92f, -0.38f },
                            { -0.26f, 0.65f, -0.38f },
                            {  0.26f, 0.65f, -0.38f },
                            {  0.00f, 0.52f, -0.40f }
                        };
                        for (int s = 0; s < 7; s++)
                        {
                            Vec3 baseP = new Vec3(leanX * 0.4f + spikeOffsets[s, 0], spikeOffsets[s, 1], spikeOffsets[s, 2]);
                            Vec3 tipP = baseP + new Vec3(spikeOffsets[s, 0] * 0.42f, 0.07f, -0.19f);
                            AddEllipsoid(m, baseP.X, baseP.Y, baseP.Z, 0.095f, 0.095f, 0.06f, scaleOrange, 0.4f, 20f);
                            AddCapsule(m, baseP, tipP, 0.070f, ivory, 0.68f, 42f);
                        }

                        if (includeKart)
                        {
                            AddCapsule(m, new Vec3(-0.38f + leanX * 0.4f, 0.84f, -0.02f), new Vec3(-0.17f, 0.68f, 0.19f), 0.125f, scaleOrange, 0.35f, 22f);
                            AddCapsule(m, new Vec3( 0.38f + leanX * 0.4f, 0.84f, -0.02f), new Vec3( 0.17f, 0.68f, 0.19f), 0.125f, scaleOrange, 0.35f, 22f);
                            AddEllipsoid(m, -0.24f, 0.75f, 0.12f, 0.14f, 0.14f, 0.07f, black, 0.5f, 28f);
                            AddEllipsoid(m,  0.24f, 0.75f, 0.12f, 0.14f, 0.14f, 0.07f, black, 0.5f, 28f);
                        }

                        // Large Bowser Head, Wide Tan Snout, Red Eyebrows, Blazing Red Mohawk & Curved Ivory Horns (lu-1.jpg #1!)
                        AddEllipsoid(m, leanX * 0.7f, 1.22f, 0.05f, 0.34f, 0.29f, 0.33f, shellGreen, 0.38f, 24f);
                        AddEllipsoid(m, leanX * 0.7f, 1.15f, 0.32f, 0.28f, 0.19f, 0.24f, scaleOrange, 0.38f, 24f);
                        AddCapsule(m, new Vec3(leanX * 0.7f - 0.20f, 1.32f, 0.28f), new Vec3(leanX * 0.7f - 0.05f, 1.28f, 0.32f), 0.055f, maneRed, 0.4f, 24f);
                        AddCapsule(m, new Vec3(leanX * 0.7f + 0.20f, 1.32f, 0.28f), new Vec3(leanX * 0.7f + 0.05f, 1.28f, 0.32f), 0.055f, maneRed, 0.4f, 24f);
                        AddEllipsoid(m, leanX * 0.7f - 0.12f, 1.25f, 0.31f, 0.055f, 0.065f, 0.04f, Color4.FromBytes(255, 235, 60), 0.7f, 36f);
                        AddEllipsoid(m, leanX * 0.7f + 0.12f, 1.25f, 0.31f, 0.055f, 0.065f, 0.04f, Color4.FromBytes(255, 235, 60), 0.7f, 36f);
                        AddEllipsoid(m, leanX * 0.7f, 1.46f,-0.06f, 0.19f, 0.22f, 0.28f, maneRed, 0.45f, 28f);
                        AddCapsule(m, new Vec3(leanX * 0.7f - 0.24f, 1.36f, 0.02f), new Vec3(leanX * 0.7f - 0.38f, 1.60f, -0.06f), 0.072f, ivory, 0.7f, 42f);
                        AddCapsule(m, new Vec3(leanX * 0.7f + 0.24f, 1.36f, 0.02f), new Vec3(leanX * 0.7f + 0.38f, 1.60f, -0.06f), 0.072f, ivory, 0.7f, 42f);
                    }
                    break;
            }

            return m;
        }

        private static List<RtPrim> BuildPropOrHazardScene(int kind)
        {
            List<RtPrim> m = new List<RtPrim>(18);
            Color4 wood = Color4.FromBytes(112, 66, 28);
            Color4 white = Color4.FromBytes(250, 250, 252);
            Color4 black = Color4.FromBytes(20, 20, 26);

            switch (kind)
            {
                case 0: // Iconic MK64 3-Tier Stacked Beehive Topiary Tree (matches lu-1.jpg right side!)
                    AddCapsule(m, new Vec3(0f, 0.05f, 0f), new Vec3(0f, 0.72f, 0f), 0.15f, wood, 0.15f, 8f);
                    AddEllipsoid(m, 0f, 0.92f, 0f, 0.80f, 0.36f, 0.80f, Color4.FromBytes(32, 168, 32), 0.32f, 18f);
                    AddEllipsoid(m, 0f, 1.32f, 0f, 0.65f, 0.34f, 0.65f, Color4.FromBytes(44, 192, 38), 0.34f, 20f);
                    AddEllipsoid(m, 0f, 1.68f, 0f, 0.45f, 0.30f, 0.45f, Color4.FromBytes(62, 212, 48), 0.36f, 22f);
                    break;

                case 1: // Snowy Frappe Pine Tree
                    AddCapsule(m, new Vec3(0f, 0.05f, 0f), new Vec3(0f, 0.75f, 0f), 0.16f, wood, 0.15f, 8f);
                    AddEllipsoid(m, 0f, 0.85f, 0f, 0.78f, 0.35f, 0.78f, Color4.FromBytes(36, 128, 72), 0.25f, 14f);
                    AddEllipsoid(m, 0f, 1.28f, 0f, 0.58f, 0.34f, 0.58f, Color4.FromBytes(44, 145, 84), 0.25f, 14f);
                    AddEllipsoid(m, 0f, 1.68f, 0f, 0.38f, 0.32f, 0.38f, white, 0.45f, 24f);
                    break;

                case 2: // Tropical Koopa Beach Palm Tree with Coconuts
                    AddCapsule(m, new Vec3(-0.12f, 0.05f, 0f), new Vec3(0.10f, 1.52f, 0f), 0.14f, Color4.FromBytes(148, 98, 48), 0.25f, 12f);
                    Color4 frond = Color4.FromBytes(48, 192, 58);
                    AddEllipsoid(m, -0.45f, 1.62f,  0.0f, 0.52f, 0.14f, 0.22f, frond, 0.4f, 22f);
                    AddEllipsoid(m,  0.58f, 1.62f,  0.0f, 0.52f, 0.14f, 0.22f, frond, 0.4f, 22f);
                    AddEllipsoid(m,  0.10f, 1.65f,  0.48f, 0.22f, 0.14f, 0.52f, frond, 0.4f, 22f);
                    AddEllipsoid(m,  0.10f, 1.65f, -0.48f, 0.22f, 0.14f, 0.52f, frond, 0.4f, 22f);
                    AddEllipsoid(m,  0.08f, 1.46f,  0.12f, 0.12f, 0.12f, 0.12f, wood, 0.3f, 16f);
                    break;

                case 3: // Saguaro Desert Cactus
                    Color4 cact = Color4.FromBytes(46, 162, 62);
                    AddCapsule(m, new Vec3(0f, 0.1f, 0f), new Vec3(0f, 1.75f, 0f), 0.22f, cact, 0.3f, 18f);
                    AddCapsule(m, new Vec3(0f, 0.95f, 0f), new Vec3(-0.48f, 1.05f, 0f), 0.15f, cact, 0.3f, 18f);
                    AddCapsule(m, new Vec3(-0.48f, 1.05f, 0f), new Vec3(-0.48f, 1.52f, 0f), 0.15f, cact, 0.3f, 18f);
                    AddCapsule(m, new Vec3(0f, 0.78f, 0f), new Vec3( 0.48f, 0.88f, 0f), 0.15f, cact, 0.3f, 18f);
                    AddCapsule(m, new Vec3( 0.48f, 0.88f, 0f), new Vec3( 0.48f, 1.38f, 0f), 0.15f, cact, 0.3f, 18f);
                    break;

                case 4: // Lakitu on Fluffy White Cloud!
                    AddEllipsoid(m,  0.00f, 0.55f, 0.0f, 0.62f, 0.36f, 0.45f, white, 0.3f, 18f);
                    AddEllipsoid(m, -0.38f, 0.52f, 0.05f, 0.35f, 0.28f, 0.35f, white, 0.3f, 18f);
                    AddEllipsoid(m,  0.38f, 0.52f, 0.05f, 0.35f, 0.28f, 0.35f, white, 0.3f, 18f);
                    AddEllipsoid(m,  0.00f, 1.05f, 0.0f, 0.32f, 0.30f, 0.32f, Color4.FromBytes(250, 212, 52), 0.4f, 24f);
                    AddEllipsoid(m,  0.00f, 1.28f,-0.04f, 0.33f, 0.16f, 0.33f, Color4.FromBytes(45, 185, 62), 0.4f, 24f);
                    AddEllipsoid(m, -0.11f, 1.10f, 0.28f, 0.11f, 0.11f, 0.05f, white, 0.8f, 48f);
                    AddEllipsoid(m,  0.11f, 1.10f, 0.28f, 0.11f, 0.11f, 0.05f, white, 0.8f, 48f);
                    break;

                case 5: // Black & White Moo Moo Cow
                    AddEllipsoid(m, 0f, 0.78f, 0f, 0.52f, 0.42f, 0.68f, white, 0.25f, 14f);
                    AddEllipsoid(m, 0.18f, 0.92f, 0.10f, 0.38f, 0.30f, 0.32f, black, 0.25f, 14f);
                    AddEllipsoid(m, -0.22f, 0.82f, -0.22f, 0.34f, 0.28f, 0.30f, black, 0.25f, 14f);
                    AddEllipsoid(m, 0f, 1.05f, 0.68f, 0.32f, 0.28f, 0.28f, white, 0.25f, 14f);
                    AddEllipsoid(m, 0f, 0.92f, 0.92f, 0.26f, 0.16f, 0.14f, Color4.FromBytes(252, 178, 188), 0.35f, 20f);
                    AddCapsule(m, new Vec3(-0.32f, 0.1f, 0.38f), new Vec3(-0.32f, 0.65f, 0.38f), 0.10f, white, 0.2f, 10f);
                    AddCapsule(m, new Vec3( 0.32f, 0.1f, 0.38f), new Vec3( 0.32f, 0.65f, 0.38f), 0.10f, white, 0.2f, 10f);
                    break;

                case 6: // Authentic Deep-Navy Sherbet Land Penguin (matches characters--2.png!)
                    Color4 navy = Color4.FromBytes(16, 26, 108);
                    AddEllipsoid(m, 0f, 0.86f, 0f, 0.52f, 0.72f, 0.48f, navy, 0.35f, 22f);
                    AddEllipsoid(m, 0f, 0.74f, 0.18f, 0.38f, 0.54f, 0.34f, Color4.FromBytes(215, 220, 228), 0.30f, 18f);
                    AddCapsule(m, new Vec3(-0.44f, 1.05f, 0f), new Vec3(-0.68f, 0.48f, -0.08f), 0.12f, navy, 0.35f, 20f);
                    AddCapsule(m, new Vec3( 0.44f, 1.05f, 0f), new Vec3( 0.68f, 0.48f, -0.08f), 0.12f, navy, 0.35f, 20f);
                    AddEllipsoid(m, -0.20f, 0.16f, 0.22f, 0.18f, 0.08f, 0.26f, Color4.FromBytes(242, 152, 22), 0.35f, 18f);
                    AddEllipsoid(m,  0.20f, 0.16f, 0.22f, 0.18f, 0.08f, 0.26f, Color4.FromBytes(242, 152, 22), 0.35f, 18f);
                    AddCapsule(m, new Vec3(0f, 1.24f, 0.36f), new Vec3(0f, 1.20f, 0.68f), 0.11f, Color4.FromBytes(255, 202, 24), 0.5f, 28f);
                    AddEllipsoid(m, -0.15f, 1.32f, 0.38f, 0.08f, 0.09f, 0.05f, white, 0.6f, 32f);
                    AddEllipsoid(m,  0.15f, 1.32f, 0.38f, 0.08f, 0.09f, 0.05f, white, 0.6f, 32f);
                    AddEllipsoid(m, -0.15f, 1.32f, 0.42f, 0.04f, 0.05f, 0.03f, black, 0.6f, 32f);
                    AddEllipsoid(m,  0.15f, 1.32f, 0.42f, 0.04f, 0.05f, 0.03f, black, 0.6f, 32f);
                    break;

                case 7: // Frappe Snowland Snowman
                    AddEllipsoid(m, 0f, 0.62f, 0f, 0.62f, 0.56f, 0.62f, white, 0.35f, 20f);
                    AddEllipsoid(m, 0f, 1.38f, 0f, 0.44f, 0.40f, 0.44f, white, 0.35f, 20f);
                    AddEllipsoid(m, 0f, 1.06f, 0f, 0.48f, 0.10f, 0.48f, Color4.FromBytes(235, 38, 38), 0.3f, 16f);
                    AddCapsule(m, new Vec3(0f, 1.38f, 0.38f), new Vec3(0f, 1.36f, 0.68f), 0.07f, Color4.FromBytes(255, 132, 22), 0.4f, 20f);
                    AddEllipsoid(m, 0f, 1.82f, 0f, 0.28f, 0.22f, 0.28f, Color4.FromBytes(220, 42, 42), 0.4f, 24f);
                    break;

                case 8: // Bowser's Castle Spiked Blue Thwomp
                    Color4 thBlue = Color4.FromBytes(62, 128, 232);
                    AddEllipsoid(m, 0f, 1.05f, 0f, 0.72f, 0.85f, 0.48f, thBlue, 0.45f, 28f);
                    for (int s = 0; s < 4; s++)
                    {
                        float sy = 0.45f + s * 0.40f;
                        AddEllipsoid(m, -0.78f, sy, 0f, 0.18f, 0.12f, 0.14f, Color4.FromBytes(165, 205, 255), 0.6f, 36f);
                        AddEllipsoid(m,  0.78f, sy, 0f, 0.18f, 0.12f, 0.14f, Color4.FromBytes(165, 205, 255), 0.6f, 36f);
                    }
                    AddEllipsoid(m, -0.22f, 1.22f, 0.44f, 0.14f, 0.12f, 0.06f, Color4.FromBytes(255, 62, 42), 0.7f, 40f);
                    AddEllipsoid(m,  0.22f, 1.22f, 0.44f, 0.14f, 0.12f, 0.06f, Color4.FromBytes(255, 62, 42), 0.7f, 40f);
                    break;

                case 9: // Giant Spotted Yoshi Egg
                    Color4 spotG = Color4.FromBytes(58, 212, 68);
                    AddEllipsoid(m, 0f, 1.05f, 0f, 0.72f, 0.92f, 0.72f, white, 0.55f, 38f);
                    AddEllipsoid(m,  0.00f, 1.15f, 0.66f, 0.24f, 0.26f, 0.12f, spotG, 0.55f, 38f);
                    AddEllipsoid(m, -0.52f, 0.85f, 0.35f, 0.18f, 0.24f, 0.20f, spotG, 0.55f, 38f);
                    AddEllipsoid(m,  0.52f, 1.30f, 0.32f, 0.18f, 0.24f, 0.20f, spotG, 0.55f, 38f);
                    break;

                case 10: // Rainbow Road Chain Chomp!
                    AddEllipsoid(m, 0f, 1.00f, 0f, 0.82f, 0.82f, 0.82f, Color4.FromBytes(28, 30, 42), 0.85f, 56f);
                    AddEllipsoid(m, -0.26f, 1.28f, 0.68f, 0.16f, 0.16f, 0.08f, white, 0.7f, 40f);
                    AddEllipsoid(m,  0.26f, 1.28f, 0.68f, 0.16f, 0.16f, 0.08f, white, 0.7f, 40f);
                    AddEllipsoid(m,  0.00f, 0.82f, 0.74f, 0.52f, 0.18f, 0.16f, white, 0.6f, 32f);
                    AddEllipsoid(m,  0.00f, 0.72f, 0.68f, 0.45f, 0.16f, 0.16f, Color4.FromBytes(225, 38, 45), 0.4f, 20f);
                    break;

                case 11: // Mario Raceway Giant Red Spotted Toadstool Mushroom
                    AddCapsule(m, new Vec3(0f, 0.1f, 0f), new Vec3(0f, 0.95f, 0f), 0.38f, Color4.FromBytes(248, 232, 202), 0.25f, 16f);
                    AddEllipsoid(m, 0f, 1.38f, 0f, 0.88f, 0.56f, 0.88f, Color4.FromBytes(235, 36, 36), 0.52f, 36f);
                    AddEllipsoid(m, 0f, 1.48f, 0.72f, 0.26f, 0.24f, 0.16f, white, 0.5f, 32f);
                    AddEllipsoid(m, -0.62f, 1.42f, 0.25f, 0.22f, 0.24f, 0.22f, white, 0.5f, 32f);
                    AddEllipsoid(m,  0.62f, 1.42f, 0.25f, 0.22f, 0.24f, 0.22f, white, 0.5f, 32f);
                    break;

                default: // Moo Moo Farm Monty Mole (matches characters--4.png!)
                    Color4 moleBrown = Color4.FromBytes(162, 74, 22);
                    AddEllipsoid(m, 0f, 0.22f, 0f, 0.72f, 0.16f, 0.72f, Color4.FromBytes(72, 42, 18), 0.15f, 8f); // Dirt hole ring!
                    AddEllipsoid(m, 0f, 0.82f, 0f, 0.56f, 0.62f, 0.52f, moleBrown, 0.32f, 18f);
                    AddEllipsoid(m, 0f, 0.68f, 0.18f, 0.42f, 0.44f, 0.38f, white, 0.30f, 16f); // Plump white belly!
                    AddEllipsoid(m, 0f, 1.02f, 0.46f, 0.22f, 0.16f, 0.20f, Color4.FromBytes(235, 168, 98), 0.35f, 20f);
                    AddEllipsoid(m, 0f, 1.06f, 0.62f, 0.10f, 0.08f, 0.08f, black, 0.5f, 28f);
                    AddCapsule(m, new Vec3(-0.24f, 1.18f, 0.42f), new Vec3(0.24f, 1.18f, 0.42f), 0.075f, black, 0.6f, 32f); // Cool mole shades!
                    AddCapsule(m, new Vec3(-0.48f, 0.85f, 0.15f), new Vec3(-0.68f, 0.72f, 0.32f), 0.11f, white, 0.4f, 20f); // White claws!
                    AddCapsule(m, new Vec3( 0.48f, 0.85f, 0.15f), new Vec3( 0.68f, 0.72f, 0.32f), 0.11f, white, 0.4f, 20f);
                    break;
            }
            return m;
        }

        private static List<RtPrim> BuildItemScene(ItemId id)
        {
            List<RtPrim> m = new List<RtPrim>(14);
            Color4 white = Color4.FromBytes(250, 250, 252);
            Color4 black = Color4.FromBytes(22, 22, 26);

            switch (id)
            {
                case ItemId.GreenShell:
                    AddEllipsoid(m, 0f, 0.58f, 0f, 0.62f, 0.46f, 0.62f, Color4.FromBytes(36, 198, 56), 0.65f, 44f);
                    AddEllipsoid(m, 0f, 0.44f, 0f, 0.66f, 0.14f, 0.66f, white, 0.45f, 28f);
                    break;

                case ItemId.TripleGreenShells:
                    for (int k = 0; k < 3; k++)
                    {
                        float ox = (k == 0) ? 0f : (k == 1 ? -0.38f : 0.38f);
                        float oz = (k == 0) ? 0.25f : -0.18f;
                        AddEllipsoid(m, ox, 0.55f, oz, 0.38f, 0.30f, 0.38f, Color4.FromBytes(36, 198, 56), 0.65f, 44f);
                        AddEllipsoid(m, ox, 0.45f, oz, 0.41f, 0.10f, 0.41f, white, 0.45f, 28f);
                    }
                    break;

                case ItemId.RedShell:
                    AddEllipsoid(m, 0f, 0.58f, 0f, 0.62f, 0.46f, 0.62f, Color4.FromBytes(235, 34, 34), 0.65f, 44f);
                    AddEllipsoid(m, 0f, 0.44f, 0f, 0.66f, 0.14f, 0.66f, white, 0.45f, 28f);
                    break;

                case ItemId.TripleRedShells:
                    for (int k = 0; k < 3; k++)
                    {
                        float ox = (k == 0) ? 0f : (k == 1 ? -0.38f : 0.38f);
                        float oz = (k == 0) ? 0.25f : -0.18f;
                        AddEllipsoid(m, ox, 0.55f, oz, 0.38f, 0.30f, 0.38f, Color4.FromBytes(235, 34, 34), 0.65f, 44f);
                        AddEllipsoid(m, ox, 0.45f, oz, 0.41f, 0.10f, 0.41f, white, 0.45f, 28f);
                    }
                    break;

                case ItemId.SpinyBlueShell:
                    AddEllipsoid(m, 0f, 0.58f, 0f, 0.64f, 0.48f, 0.64f, Color4.FromBytes(38, 108, 252), 0.72f, 48f);
                    AddEllipsoid(m, 0f, 0.44f, 0f, 0.68f, 0.14f, 0.68f, white, 0.45f, 28f);
                    AddCapsule(m, new Vec3(0f, 0.92f, 0f), new Vec3(0f, 1.24f, 0f), 0.10f, white, 0.6f, 36f);
                    AddCapsule(m, new Vec3(-0.34f, 0.82f, 0f), new Vec3(-0.52f, 1.08f, 0f), 0.09f, white, 0.6f, 36f);
                    AddCapsule(m, new Vec3( 0.34f, 0.82f, 0f), new Vec3( 0.52f, 1.08f, 0f), 0.09f, white, 0.6f, 36f);
                    break;

                case ItemId.Banana:
                    {
                        Color4 yel = Color4.FromBytes(255, 226, 28);
                        AddCapsule(m, new Vec3(0f, 0.45f, 0f), new Vec3(0.05f, 1.12f, 0f), 0.22f, yel, 0.5f, 32f);
                        AddCapsule(m, new Vec3(0f, 0.45f, 0f), new Vec3(-0.34f, 0.15f, 0.15f), 0.14f, yel, 0.5f, 32f);
                        AddCapsule(m, new Vec3(0f, 0.45f, 0f), new Vec3( 0.34f, 0.15f, 0.15f), 0.14f, yel, 0.5f, 32f);
                        AddCapsule(m, new Vec3(0f, 0.45f, 0f), new Vec3( 0.00f, 0.15f,-0.32f), 0.14f, yel, 0.5f, 32f);
                        AddEllipsoid(m, -0.06f, 0.78f, 0.20f, 0.045f, 0.07f, 0.03f, black, 0.5f, 24f);
                        AddEllipsoid(m,  0.08f, 0.78f, 0.20f, 0.045f, 0.07f, 0.03f, black, 0.5f, 24f);
                    }
                    break;

                case ItemId.TripleBananas:
                    for (int b = 0; b < 5; b++)
                    {
                        float ox = (b - 2) * 0.24f;
                        AddCapsule(m, new Vec3(ox, 0.22f, 0f), new Vec3(ox * 0.6f, 0.92f, 0.08f), 0.13f, Color4.FromBytes(255, 226, 28), 0.5f, 32f);
                    }
                    break;

                case ItemId.Mushroom:
                    AddCapsule(m, new Vec3(0f, 0.16f, 0f), new Vec3(0f, 0.55f, 0f), 0.26f, Color4.FromBytes(248, 232, 204), 0.3f, 18f);
                    AddEllipsoid(m, 0f, 0.74f, 0f, 0.60f, 0.40f, 0.60f, Color4.FromBytes(238, 34, 34), 0.58f, 40f);
                    AddEllipsoid(m, 0f, 0.80f, 0.48f, 0.20f, 0.18f, 0.12f, white, 0.5f, 32f);
                    AddEllipsoid(m, -0.44f, 0.76f, 0.14f, 0.16f, 0.18f, 0.18f, white, 0.5f, 32f);
                    AddEllipsoid(m,  0.44f, 0.76f, 0.14f, 0.16f, 0.18f, 0.18f, white, 0.5f, 32f);
                    break;

                case ItemId.TripleMushrooms:
                    for (int k = 0; k < 3; k++)
                    {
                        float ox = (k == 0) ? 0f : (k == 1 ? -0.36f : 0.36f);
                        float oz = (k == 0) ? 0.22f : -0.16f;
                        AddCapsule(m, new Vec3(ox, 0.18f, oz), new Vec3(ox, 0.46f, oz), 0.16f, Color4.FromBytes(248, 232, 204), 0.3f, 18f);
                        AddEllipsoid(m, ox, 0.62f, oz, 0.38f, 0.26f, 0.38f, Color4.FromBytes(238, 34, 34), 0.58f, 40f);
                        AddEllipsoid(m, ox, 0.66f, oz + 0.30f, 0.13f, 0.12f, 0.08f, white, 0.5f, 32f);
                    }
                    break;

                case ItemId.GoldenMushroom:
                    {
                        Color4 gold = Color4.FromBytes(255, 204, 24);
                        AddCapsule(m, new Vec3(0f, 0.14f, 0f), new Vec3(0f, 0.52f, 0f), 0.25f, Color4.FromBytes(245, 212, 118), 0.7f, 44f);
                        AddEllipsoid(m, 0f, 0.70f, 0f, 0.58f, 0.38f, 0.58f, gold, 0.92f, 64f);
                        AddEllipsoid(m, 0f, 1.06f, 0f, 0.22f, 0.10f, 0.22f, Color4.FromBytes(255, 236, 95), 0.95f, 64f);
                    }
                    break;

                case ItemId.SuperStar:
                    {
                        Color4 starGold = Color4.FromBytes(255, 218, 25);
                        AddEllipsoid(m, 0f, 0.58f, 0f, 0.36f, 0.36f, 0.22f, starGold, 0.85f, 56f);
                        for (int p = 0; p < 5; p++)
                        {
                            float ang = p * MathUtil.TWO_PI / 5f;
                            float px = (float)Math.Sin(ang) * 0.65f;
                            float py = 0.58f + (float)Math.Cos(ang) * 0.65f;
                            AddCapsule(m, new Vec3(0f, 0.58f, 0f), new Vec3(px, py, 0f), 0.15f, starGold, 0.85f, 56f);
                        }
                        AddEllipsoid(m, -0.10f, 0.62f, 0.20f, 0.045f, 0.10f, 0.03f, black, 0.5f, 24f);
                        AddEllipsoid(m,  0.10f, 0.62f, 0.20f, 0.045f, 0.10f, 0.03f, black, 0.5f, 24f);
                    }
                    break;

                case ItemId.Thunderbolt:
                    {
                        Color4 bolt = Color4.FromBytes(255, 234, 28);
                        AddCapsule(m, new Vec3( 0.22f, 1.15f, 0f), new Vec3(-0.14f, 0.62f, 0f), 0.14f, bolt, 0.9f, 60f);
                        AddCapsule(m, new Vec3(-0.14f, 0.62f, 0f), new Vec3( 0.16f, 0.60f, 0f), 0.13f, bolt, 0.9f, 60f);
                        AddCapsule(m, new Vec3( 0.16f, 0.60f, 0f), new Vec3(-0.20f, 0.06f, 0f), 0.12f, bolt, 0.9f, 60f);
                    }
                    break;

                case ItemId.FakeItemBox:
                    AddEllipsoid(m, 0f, 0.58f, 0f, 0.56f, 0.56f, 0.56f, Color4.FromBytes(235, 48, 128), 0.78f, 52f);
                    AddCapsule(m, new Vec3(-0.12f, 0.78f, 0.48f), new Vec3(0.12f, 0.62f, 0.50f), 0.08f, white, 0.7f, 40f);
                    AddEllipsoid(m, 0f, 0.36f, 0.48f, 0.08f, 0.08f, 0.05f, white, 0.7f, 40f);
                    break;

                default: // Boo Ghost!
                    AddEllipsoid(m, 0f, 0.62f, 0f, 0.56f, 0.54f, 0.56f, white, 0.45f, 28f);
                    AddCapsule(m, new Vec3(-0.46f, 0.62f, 0.05f), new Vec3(-0.72f, 0.75f, 0.18f), 0.14f, white, 0.45f, 28f);
                    AddCapsule(m, new Vec3( 0.46f, 0.62f, 0.05f), new Vec3( 0.72f, 0.75f, 0.18f), 0.14f, white, 0.45f, 28f);
                    AddEllipsoid(m, -0.15f, 0.74f, 0.48f, 0.07f, 0.09f, 0.04f, black, 0.5f, 24f);
                    AddEllipsoid(m,  0.15f, 0.74f, 0.48f, 0.07f, 0.09f, 0.04f, black, 0.5f, 24f);
                    AddEllipsoid(m,  0.00f, 0.46f, 0.50f, 0.18f, 0.14f, 0.12f, Color4.FromBytes(245, 58, 78), 0.5f, 28f);
                    break;
            }

            return m;
        }

        private static byte[] RaytraceModel(
            List<RtPrim> prims,
            int width,
            int height,
            float camOrbitYaw,
            float camElevRad,
            float camDist,
            float targetCenterY)
        {
            byte[] rgba = new byte[width * height * 4];
            RtPrim[] arr = prims.ToArray();
            if (arr.Length == 0) return rgba;

            Vec3 sceneCenter = new Vec3(0f, targetCenterY, 0f);
            float maxModelR = 0.1f;
            for (int i = 0; i < arr.Length; i++)
            {
                float d = (arr[i].BoundCenter - sceneCenter).Length + (float)Math.Sqrt(arr[i].BoundRadSq);
                if (d > maxModelR) maxModelR = d;
            }
            float sceneRadSq = (maxModelR + 0.05f) * (maxModelR + 0.05f);

            float ce = (float)Math.Cos(camElevRad);
            float se = (float)Math.Sin(camElevRad);
            Vec3 eye = new Vec3(
                -(float)Math.Sin(camOrbitYaw) * ce * camDist,
                targetCenterY + se * camDist,
                -(float)Math.Cos(camOrbitYaw) * ce * camDist);

            Vec3 target = new Vec3(0f, targetCenterY, 0f);
            Vec3 fwd = (target - eye).Normalized();
            Vec3 right = Vec3.Cross(fwd, Vec3.Up).Normalized();
            Vec3 up = Vec3.Cross(right, fwd).Normalized();

            // Rich SGI PowerAnimator 3-Point Studio Lighting!
            Vec3 sunDir = (right * 0.38f + up * 0.80f - fwd * 0.46f).Normalized();
            float fovScale = 0.55f;
            Vec3 eyeToScene = sceneCenter - eye;
            float eyeToSceneLenSq = Vec3.Dot(eyeToScene, eyeToScene);

            int totalPix = width * height;
            int[] primHitMap = new int[totalPix];
            float[] p1R = new float[totalPix];
            float[] p1G = new float[totalPix];
            float[] p1B = new float[totalPix];

            for (int py = 0; py < height; py++)
            {
                float ndcY = 1.0f - 2.0f * ((py + 0.5f) / height);
                for (int px = 0; px < width; px++)
                {
                    int idx = py * width + px;
                    float ndcX = 2.0f * ((px + 0.5f) / width) - 1.0f;
                    Vec3 rayDir = (fwd + right * (ndcX * fovScale) + up * (ndcY * fovScale)).Normalized();

                    float projScene = Vec3.Dot(eyeToScene, rayDir);
                    if (eyeToSceneLenSq - projScene * projScene > sceneRadSq)
                    {
                        primHitMap[idx] = -1;
                        continue;
                    }

                    float sr, sg, sb;
                    int hIdx = ShadeRay(arr, eye, rayDir, sunDir, out sr, out sg, out sb);
                    primHitMap[idx] = hIdx;
                    if (hIdx >= 0)
                    {
                        p1R[idx] = sr;
                        p1G[idx] = sg;
                        p1B[idx] = sb;
                    }
                }
            }

            // Pass 2: 2x2 Supersample any silhouette edge OR primitive-seam pixel!
            for (int py = 0; py < height; py++)
            {
                for (int px = 0; px < width; px++)
                {
                    int idx = py * width + px;
                    int cHit = primHitMap[idx];
                    bool needAA = false;
                    if (px > 0 && primHitMap[idx - 1] != cHit) needAA = true;
                    else if (px + 1 < width && primHitMap[idx + 1] != cHit) needAA = true;
                    else if (py > 0 && primHitMap[idx - width] != cHit) needAA = true;
                    else if (py + 1 < height && primHitMap[idx + width] != cHit) needAA = true;

                    int outIdx = idx * 4;
                    if (!needAA)
                    {
                        if (cHit >= 0)
                        {
                            rgba[outIdx]     = (byte)(p1R[idx] * 255f);
                            rgba[outIdx + 1] = (byte)(p1G[idx] * 255f);
                            rgba[outIdx + 2] = (byte)(p1B[idx] * 255f);
                            rgba[outIdx + 3] = 255;
                        }
                        continue;
                    }

                    float accumR = 0f, accumG = 0f, accumB = 0f, accumA = 0f;
                    for (int sy = 0; sy < 2; sy++)
                    {
                        float ndcY = 1.0f - 2.0f * ((py + (sy + 0.5f) * 0.5f) / height);
                        for (int sx = 0; sx < 2; sx++)
                        {
                            float ndcX = 2.0f * ((px + (sx + 0.5f) * 0.5f) / width) - 1.0f;
                            Vec3 rayDir = (fwd + right * (ndcX * fovScale) + up * (ndcY * fovScale)).Normalized();
                            float sr, sg, sb;
                            if (ShadeRay(arr, eye, rayDir, sunDir, out sr, out sg, out sb) >= 0)
                            {
                                accumR += sr;
                                accumG += sg;
                                accumB += sb;
                                accumA += 1.0f;
                            }
                        }
                    }

                    if (accumA > 0f)
                    {
                        float invHits = 1.0f / accumA;
                        rgba[outIdx]     = (byte)(accumR * invHits * 255f);
                        rgba[outIdx + 1] = (byte)(accumG * invHits * 255f);
                        rgba[outIdx + 2] = (byte)(accumB * invHits * 255f);
                        rgba[outIdx + 3] = (byte)((accumA * 0.25f) * 255f);
                    }
                }
            }

            return rgba;
        }

        private static int ShadeRay(RtPrim[] arr, Vec3 eye, Vec3 rayDir, Vec3 sunDir, out float outR, out float outG, out float outB)
        {
            outR = outG = outB = 0f;
            float hitT;
            Vec3 hitNormal;
            int hitIdx = TraceScene(arr, eye, rayDir, out hitT, out hitNormal);
            if (hitIdx < 0) return -1;

            RtPrim hp = arr[hitIdx];
            Vec3 hitPos = eye + rayDir * hitT;

            float shT;
            Vec3 shN;
            int shIdx = TraceScene(arr, hitPos + hitNormal * 0.015f, sunDir, out shT, out shN);
            float shadow = (shIdx >= 0) ? 0.56f : 1.0f;

            float nDotL = Math.Max(0f, Vec3.Dot(hitNormal, sunDir)) * shadow;
            float hemi = 0.36f + 0.16f * hitNormal.Y;
            float oneMinusRim = Math.Max(0f, 1.0f - Math.Abs(Vec3.Dot(hitNormal, -rayDir)));
            float rim = oneMinusRim * oneMinusRim * oneMinusRim * 0.15f;

            Vec3 halfVec = (sunDir - rayDir).Normalized();
            float spec = 0f;
            if (nDotL > 0f && hp.Specular > 0.01f)
            {
                spec = (float)Math.Pow(Math.Max(0f, Vec3.Dot(hitNormal, halfVec)), hp.Shininess) * hp.Specular * shadow;
            }

            float lit = hemi + nDotL * 0.76f;
            outR = MathUtil.Clamp(hp.Color.R * lit + spec + rim * 0.55f, 0f, 1f);
            outG = MathUtil.Clamp(hp.Color.G * lit + spec + rim * 0.60f, 0f, 1f);
            outB = MathUtil.Clamp(hp.Color.B * lit + spec + rim * 0.70f, 0f, 1f);
            return hitIdx;
        }

        private static int TraceScene(RtPrim[] prims, Vec3 ro, Vec3 rd, out float bestT, out Vec3 bestNormal)
        {
            bestT = 1e9f;
            bestNormal = Vec3.Up;
            int bestIdx = -1;

            for (int i = 0; i < prims.Length; i++)
            {
                RtPrim p = prims[i];
                float ocX = p.BoundCenter.X - ro.X;
                float ocY = p.BoundCenter.Y - ro.Y;
                float ocZ = p.BoundCenter.Z - ro.Z;
                float proj = ocX * rd.X + ocY * rd.Y + ocZ * rd.Z;
                float distSq = (ocX * ocX + ocY * ocY + ocZ * ocZ) - proj * proj;
                if (distSq > p.BoundRadSq) continue;

                float t = 0f;
                Vec3 n = Vec3.Zero;
                bool hit = false;

                switch (p.Type)
                {
                    case PrimType.Ellipsoid:
                        hit = IntersectEllipsoid(ro, rd, p.P1, p.P2, out t, out n);
                        break;
                    case PrimType.Capsule:
                        hit = IntersectCapsule(ro, rd, p.P1, p.P2, p.Radius, out t, out n);
                        break;
                    case PrimType.WheelX:
                        hit = IntersectWheel(ro, rd, p.P1, p.P2.X, p.P2.Y, p.P2.Z, out t, out n);
                        break;
                }

                if (hit && t > 0.001f && t < bestT)
                {
                    bestT = t;
                    bestNormal = n;
                    bestIdx = i;
                }
            }
            return bestIdx;
        }

        private static bool IntersectEllipsoid(Vec3 ro, Vec3 rd, Vec3 center, Vec3 radii, out float t, out Vec3 normal)
        {
            t = 0f;
            normal = Vec3.Up;
            float invX = 1.0f / radii.X;
            float invY = 1.0f / radii.Y;
            float invZ = 1.0f / radii.Z;

            Vec3 oc = new Vec3((ro.X - center.X) * invX, (ro.Y - center.Y) * invY, (ro.Z - center.Z) * invZ);
            Vec3 d = new Vec3(rd.X * invX, rd.Y * invY, rd.Z * invZ);

            float a = Vec3.Dot(d, d);
            float b = Vec3.Dot(oc, d);
            float c = Vec3.Dot(oc, oc) - 1.0f;
            float disc = b * b - a * c;
            if (disc < 0f) return false;

            float s = (float)Math.Sqrt(disc);
            float tHit = (-b - s) / a;
            if (tHit <= 0.001f) tHit = (-b + s) / a;
            if (tHit <= 0.001f) return false;

            t = tHit;
            Vec3 hp = ro + rd * tHit - center;
            normal = new Vec3(hp.X * invX * invX, hp.Y * invY * invY, hp.Z * invZ * invZ).Normalized();
            return true;
        }

        private static bool IntersectCapsule(Vec3 ro, Vec3 rd, Vec3 pa, Vec3 pb, float r, out float t, out Vec3 normal)
        {
            t = 0f;
            normal = Vec3.Up;
            Vec3 ba = pb - pa;
            Vec3 oa = ro - pa;

            float baba = Vec3.Dot(ba, ba);
            float bard = Vec3.Dot(ba, rd);
            float baoa = Vec3.Dot(ba, oa);
            float rdoa = Vec3.Dot(rd, oa);
            float oaoa = Vec3.Dot(oa, oa);

            float a = baba - bard * bard;
            float b = baba * rdoa - baoa * bard;
            float c = baba * oaoa - baoa * baoa - r * r * baba;
            float h = b * b - a * c;

            if (h >= 0f)
            {
                float tCand = (-b - (float)Math.Sqrt(h)) / Math.Max(1e-6f, a);
                float y = baoa + tCand * bard;
                if (y > 0f && y < baba && tCand > 0.001f)
                {
                    t = tCand;
                    Vec3 axisPt = pa + ba * (y / baba);
                    normal = ((ro + rd * tCand) - axisPt).Normalized();
                    return true;
                }

                float tA, tB;
                Vec3 nA, nB;
                bool hitA = IntersectEllipsoid(ro, rd, pa, new Vec3(r, r, r), out tA, out nA);
                bool hitB = IntersectEllipsoid(ro, rd, pb, new Vec3(r, r, r), out tB, out nB);
                if (hitA && (!hitB || tA <= tB)) { t = tA; normal = nA; return true; }
                if (hitB) { t = tB; normal = nB; return true; }
            }
            return false;
        }

        private static bool IntersectWheel(Vec3 ro, Vec3 rd, Vec3 center, float radius, float halfW, float steerYaw, out float t, out Vec3 normal)
        {
            t = 0f;
            normal = Vec3.Up;

            float cs = (float)Math.Cos(-steerYaw);
            float sn = (float)Math.Sin(-steerYaw);
            Vec3 relO = ro - center;
            Vec3 lo = new Vec3(relO.X * cs - relO.Z * sn, relO.Y, relO.X * sn + relO.Z * cs);
            Vec3 ld = new Vec3(rd.X * cs - rd.Z * sn, rd.Y, rd.X * sn + rd.Z * cs);

            float best = 1e9f;
            Vec3 bestLocalN = Vec3.Up;
            bool found = false;

            float a = ld.Y * ld.Y + ld.Z * ld.Z;
            if (a > 1e-6f)
            {
                float b = lo.Y * ld.Y + lo.Z * ld.Z;
                float c = lo.Y * lo.Y + lo.Z * lo.Z - radius * radius;
                float disc = b * b - a * c;
                if (disc >= 0f)
                {
                    float s = (float)Math.Sqrt(disc);
                    float t0 = (-b - s) / a;
                    if (t0 > 0.001f)
                    {
                        float hx = lo.X + ld.X * t0;
                        if (Math.Abs(hx) <= halfW)
                        {
                            best = t0;
                            bestLocalN = new Vec3(0f, lo.Y + ld.Y * t0, lo.Z + ld.Z * t0).Normalized();
                            found = true;
                        }
                    }
                }
            }

            if (Math.Abs(ld.X) > 1e-5f)
            {
                for (int side = -1; side <= 1; side += 2)
                {
                    float planeX = side * halfW;
                    float tc = (planeX - lo.X) / ld.X;
                    if (tc > 0.001f && tc < best)
                    {
                        float hy = lo.Y + ld.Y * tc;
                        float hz = lo.Z + ld.Z * tc;
                        float r2 = hy * hy + hz * hz;
                        if (r2 <= radius * radius)
                        {
                            best = tc;
                            float edgeCurve = (float)Math.Sqrt(r2) / radius;
                            bestLocalN = new Vec3(side * 0.90f, (hy / radius) * 0.42f * edgeCurve, (hz / radius) * 0.42f * edgeCurve).Normalized();
                            found = true;
                        }
                    }
                }
            }

            if (!found) return false;
            t = best;
            float rcs = (float)Math.Cos(steerYaw);
            float rsn = (float)Math.Sin(steerYaw);
            normal = new Vec3(bestLocalN.X * rcs - bestLocalN.Z * rsn, bestLocalN.Y, bestLocalN.X * rsn + bestLocalN.Z * rcs).Normalized();
            return true;
        }
    }
}
