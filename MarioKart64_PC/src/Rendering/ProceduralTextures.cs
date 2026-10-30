using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.Runtime.InteropServices;
using MarioKart64.Core;
using MarioKart64.Tracks;

namespace MarioKart64.Rendering
{
    public static class ProceduralTextures
    {
        public static uint TexAsphalt;
        public static uint TexLuigiRoad;
        public static uint TexHighway;
        public static uint TexDirt;
        public static uint TexSand;
        public static uint TexSnow;
        public static uint TexIce;
        public static uint TexWood;
        public static uint TexCastleStone;
        public static uint TexRainbow;
        public static uint TexGrass;
        public static uint TexBoost;
        public static uint TexChecker;
        public static uint TexWater;
        public static uint TexLava;
        public static uint TexBrickWall;
        public static uint TexSponsorWall;
        public static uint TexLuigiBarrier;
        public static uint TexRockCliff;
        public static uint TexSnowWall;
        public static uint TexStartBanner;
        public static uint TexCloud;
        public static uint TexFont;

        private static bool _initialized = false;

        public static void InitializeAll()
        {
            if (_initialized) return;
            _initialized = true;

            TexAsphalt      = CreateSurfaceTex(SurfaceType.Asphalt, 0);
            TexLuigiRoad    = CreateSurfaceTex(SurfaceType.Asphalt, 2);
            TexHighway      = CreateSurfaceTex(SurfaceType.Asphalt, 1);
            TexDirt         = CreateSurfaceTex(SurfaceType.Dirt, 0);
            TexSand         = CreateSurfaceTex(SurfaceType.Sand, 0);
            TexSnow         = CreateSurfaceTex(SurfaceType.Snow, 0);
            TexIce          = CreateSurfaceTex(SurfaceType.Ice, 0);
            TexWood         = CreateSurfaceTex(SurfaceType.WoodPlanks, 0);
            TexCastleStone  = CreateSurfaceTex(SurfaceType.CastleStone, 0);
            TexRainbow      = CreateSurfaceTex(SurfaceType.RainbowNeon, 0);
            TexGrass        = CreateSurfaceTex(SurfaceType.OffRoadGrass, 0);
            TexBoost        = CreateSurfaceTex(SurfaceType.BoostPad, 0);
            TexChecker      = CreateCheckerTex();
            TexWater        = CreateLiquidTex(false);
            TexLava         = CreateLiquidTex(true);
            TexBrickWall    = CreateBrickWallTex();
            TexRockCliff    = CreateRockCliffTex();
            TexSnowWall     = CreateSnowWallTex();
            TexSponsorWall  = CreateSponsorWallTex();
            TexLuigiBarrier = CreateLuigiBarrierTex();
            TexStartBanner  = CreateStartBannerTex();
            TexCloud        = CreateCloudTex();
            TexFont         = CreateFontAtlas();

            // Also generate all SGI 3D pre-rendered Character, Prop & Item sprites!
            SgiSpriteGenerator.InitializeAll();
        }

        public static uint GetRoadTexture(SurfaceType s, bool isHighway = false)
        {
            if (isHighway && s == SurfaceType.Asphalt) return TexHighway;
            switch (s)
            {
                case SurfaceType.Asphalt:     return TexAsphalt;
                case SurfaceType.Dirt:
                case SurfaceType.OffRoadMud:  return TexDirt;
                case SurfaceType.Sand:
                case SurfaceType.OffRoadSand: return TexSand;
                case SurfaceType.Snow:
                case SurfaceType.OffRoadSnow: return TexSnow;
                case SurfaceType.Ice:         return TexIce;
                case SurfaceType.WoodPlanks:  return TexWood;
                case SurfaceType.CastleStone: return TexCastleStone;
                case SurfaceType.RainbowNeon: return TexRainbow;
                case SurfaceType.BoostPad:    return TexBoost;
                default:                      return TexGrass;
            }
        }

        private static uint UploadRgbaTexture(byte[] rgba, int w, int h, bool repeat, bool linear)
        {
            uint[] ids = new uint[1];
            Gl.glGenTextures(1, ids);
            uint id = ids[0];
            Gl.glBindTexture(Gl.GL_TEXTURE_2D, id);
            int filter = linear ? Gl.GL_LINEAR_FILTER : Gl.GL_NEAREST;
            int wrap = repeat ? Gl.GL_REPEAT : Gl.GL_CLAMP;
            Gl.glTexParameteri(Gl.GL_TEXTURE_2D, Gl.GL_TEXTURE_MIN_FILTER, filter);
            Gl.glTexParameteri(Gl.GL_TEXTURE_2D, Gl.GL_TEXTURE_MAG_FILTER, filter);
            Gl.glTexParameteri(Gl.GL_TEXTURE_2D, Gl.GL_TEXTURE_WRAP_S, wrap);
            Gl.glTexParameteri(Gl.GL_TEXTURE_2D, Gl.GL_TEXTURE_WRAP_T, wrap);
            Gl.glTexImage2D(Gl.GL_TEXTURE_2D, 0, (int)Gl.GL_RGBA, w, h, 0, Gl.GL_RGBA, Gl.GL_UNSIGNED_BYTE, rgba);
            return id;
        }

        private static uint UploadBitmap(Bitmap bmp, bool repeat, bool linear)
        {
            int w = bmp.Width, h = bmp.Height;
            BitmapData bd = bmp.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
            byte[] bgra = new byte[w * h * 4];
            Marshal.Copy(bd.Scan0, bgra, 0, bgra.Length);
            bmp.UnlockBits(bd);

            byte[] rgba = new byte[w * h * 4];
            for (int i = 0; i < bgra.Length; i += 4)
            {
                rgba[i]     = bgra[i + 2];
                rgba[i + 1] = bgra[i + 1];
                rgba[i + 2] = bgra[i + 0];
                rgba[i + 3] = bgra[i + 3];
            }
            return UploadRgbaTexture(rgba, w, h, repeat, linear);
        }

        private static int HashNoise(int x, int y, int seed)
        {
            int n = ((x & 255) * 374761393) + ((y & 255) * 668265263) + seed * 1442695041;
            n = (n ^ (n >> 13)) * 1274126177;
            return (n ^ (n >> 16)) & 0xFF;
        }

        // Smooth tileable bilinear value noise (gives authentic smooth N64 3-point filtered look!)
        private static float SmoothTileNoise(float x, float y, int period, int seed)
        {
            int ix0 = ((int)Math.Floor(x)) % period;
            if (ix0 < 0) ix0 += period;
            int iy0 = ((int)Math.Floor(y)) % period;
            if (iy0 < 0) iy0 += period;
            int ix1 = (ix0 + 1) % period;
            int iy1 = (iy0 + 1) % period;

            float fx = x - (float)Math.Floor(x);
            float fy = y - (float)Math.Floor(y);
            fx = fx * fx * (3f - 2f * fx);
            fy = fy * fy * (3f - 2f * fy);

            float v00 = HashNoise(ix0, iy0, seed) / 255f;
            float v10 = HashNoise(ix1, iy0, seed) / 255f;
            float v01 = HashNoise(ix0, iy1, seed) / 255f;
            float v11 = HashNoise(ix1, iy1, seed) / 255f;

            float nx0 = v00 + (v10 - v00) * fx;
            float nx1 = v01 + (v11 - v01) * fx;
            return nx0 + (nx1 - nx0) * fy;
        }

        private static uint CreateSurfaceTex(SurfaceType s, int asphaltVariant)
        {
            const int W = 128;
            const int H = 128;
            byte[] px = new byte[W * H * 4];

            int[,] rainbowCols = new int[7, 3]
            {
                { 255,  42,  64 },
                { 255, 148,  28 },
                { 255, 238,  38 },
                {  42, 235,  82 },
                {  42, 198, 255 },
                {  78,  96, 255 },
                { 222,  65, 255 }
            };

            for (int y = 0; y < H; y++)
            {
                for (int x = 0; x < W; x++)
                {
                    int idx = (y * W + x) * 4;
                    float macro = SmoothTileNoise(x / 16f, y / 16f, 8, (int)s + 11);
                    float mid   = SmoothTileNoise(x / 6f,  y / 6f, 16, (int)s + 37);
                    int grain   = HashNoise(x, y, (int)s + 73) - 128;
                    int r = 128, g = 128, b = 128, a = 255;

                    switch (s)
                    {
                        case SurfaceType.Asphalt:
                            if (asphaltVariant == 1)
                            {
                                // Authentic Toad's Turnpike 3-lane dusk highway asphalt (matches characters--3.png!)
                                int baseVal = (int)(56 + macro * 12 + grain * 0.03f);
                                r = baseVal; g = baseVal + 4; b = baseVal + 14;
                                if ((x >= 42 && x <= 44 || x >= 83 && x <= 85) && (y % 48) < 20)
                                {
                                    r = 185; g = 192; b = 212; // 3-lane highway white dashes!
                                }
                                else if (x >= 2 && x <= 4 || x >= 123 && x <= 125)
                                {
                                    r = 225; g = 230; b = 240; // Crisp highway white sidelines!
                                }
                            }
                            else
                            {
                                // Authentic N64 Raceway Asphalt (matches lu-1.jpg, lu-2.jpg, lu-4.png!)
                                float edgeFactor = Math.Abs((x / (float)W) - 0.5f) * 2.0f;
                                float tireGroove = (float)Math.Exp(-Math.Pow((edgeFactor - 0.38f) * 5.0f, 2.0)) * 9f;
                                int baseVal = (int)(92 + macro * 14 + mid * 6 - tireGroove + grain * 0.035f);
                                if (x >= 3 && x <= 6 || x >= 121 && x <= 124)
                                {
                                    r = 242; g = 242; b = 240; // Continuous MK64 white sideline!
                                }
                                else if (asphaltVariant == 2 && (x == 63 || x == 64) && (y % 64) < 26)
                                {
                                    r = 236; g = 238; b = 240; // Luigi Raceway subtle white dashed centerline!
                                }
                                else
                                {
                                    r = baseVal; g = baseVal + 2; b = baseVal + 6;
                                }
                            }
                            break;

                        case SurfaceType.Dirt:
                            {
                                // Rich Choco Mountain / Wario Stadium / Moo Moo Farm warm earthen dirt!
                                float rut = (float)Math.Sin(x * 0.19f + macro * 2.2f) * 9f;
                                r = (int)(164 + macro * 28 + rut + grain * 0.05f);
                                g = (int)(108 + macro * 22 + rut * 0.7f + grain * 0.04f);
                                b = (int)(58  + macro * 14 + grain * 0.03f);
                            }
                            break;

                        case SurfaceType.Sand:
                            {
                                float ripple = (float)Math.Sin(y * 0.22f + macro * 3.5f) * 10f;
                                r = (int)(236 + ripple + macro * 14);
                                g = (int)(204 + ripple * 0.85f + macro * 12);
                                b = (int)(132 + ripple * 0.6f + macro * 10);
                            }
                            break;

                        case SurfaceType.Snow:
                            {
                                r = (int)(228 + macro * 22 + mid * 6);
                                g = (int)(238 + macro * 16 + mid * 4);
                                b = 255;
                            }
                            break;

                        case SurfaceType.Ice:
                            {
                                float streak = (float)Math.Abs(Math.Sin((x * 0.7f + y * 0.4f) * 0.09f + macro * 2.5f));
                                bool glint = streak > 0.96f;
                                r = glint ? 238 : (int)(135 + macro * 36 + mid * 18);
                                g = glint ? 250 : (int)(206 + macro * 28 + mid * 14);
                                b = 255;
                            }
                            break;

                        case SurfaceType.WoodPlanks:
                            {
                                int plank = y / 16;
                                bool seam = (y % 16 == 0) || (y % 16 == 1) || (((x + plank * 37) % 64) < 2);
                                float woodGrain = (float)Math.Sin(y * 1.4f + macro * 5.0f) * 10f;
                                r = seam ? 62 : (int)(148 + woodGrain + ((plank % 3) * 7));
                                g = seam ? 40 : (int)(98  + woodGrain * 0.7f + ((plank % 3) * 5));
                                b = seam ? 24 : (int)(52  + woodGrain * 0.4f);
                            }
                            break;

                        case SurfaceType.CastleStone:
                            {
                                int row = y / 16;
                                int bx = (x + (row % 2) * 16) % 32;
                                bool mortar = (y % 16 <= 1) || (bx <= 1);
                                bool bevelHi = !mortar && ((y % 16 == 2) || (bx == 2));
                                int stoneTone = ((row * 7 + (x + (row % 2) * 16) / 32) % 5) * 5;
                                r = mortar ? 44 : (bevelHi ? 142 : (int)(98 + stoneTone + macro * 18));
                                g = mortar ? 40 : (bevelHi ? 136 : (int)(92 + stoneTone + macro * 16));
                                b = mortar ? 48 : (bevelHi ? 148 : (int)(104 + stoneTone + macro * 18));
                            }
                            break;

                        case SurfaceType.RainbowNeon:
                            {
                                int band = (x * 7) / W;
                                int inBand = (x * 7) % W;
                                bool goldTrim = (x <= 3 || x >= 124);
                                bool bandGlow = (inBand < 5 || inBand > W - 5 || (y % 32 == 0));
                                if (goldTrim)
                                {
                                    r = 255; g = 232; b = 68; a = 255;
                                }
                                else if (bandGlow)
                                {
                                    r = MathUtil.ClampInt(rainbowCols[band, 0] + 55, 0, 255);
                                    g = MathUtil.ClampInt(rainbowCols[band, 1] + 55, 0, 255);
                                    b = MathUtil.ClampInt(rainbowCols[band, 2] + 55, 0, 255);
                                    a = 238;
                                }
                                else
                                {
                                    r = rainbowCols[band, 0];
                                    g = rainbowCols[band, 1];
                                    b = rainbowCols[band, 2];
                                    a = 222;
                                }
                            }
                            break;

                        case SurfaceType.BoostPad:
                            {
                                int cy = (y + Math.Abs(x - 64)) % 32;
                                if (cy < 11) { r = 255; g = 242; b = 38; }
                                else if (cy < 20) { r = 255; g = 88; b = 22; }
                                else { r = 52; g = 55; b = 68; }
                            }
                            break;

                        default: // Lush N64 Emerald Grass!
                            {
                                float lush = macro * 34f + mid * 18f;
                                r = (int)(38 + lush * 0.65f);
                                g = (int)(152 + lush * 1.15f);
                                b = (int)(36 + lush * 0.48f);
                            }
                            break;
                    }

                    px[idx]     = (byte)MathUtil.ClampInt(r, 0, 255);
                    px[idx + 1] = (byte)MathUtil.ClampInt(g, 0, 255);
                    px[idx + 2] = (byte)MathUtil.ClampInt(b, 0, 255);
                    px[idx + 3] = (byte)MathUtil.ClampInt(a, 0, 255);
                }
            }

            return UploadRgbaTexture(px, W, H, true, true);
        }

        private static uint CreateBrickWallTex()
        {
            const int W = 128, H = 128;
            byte[] px = new byte[W * H * 4];
            for (int y = 0; y < H; y++)
            {
                int row = y / 16;
                for (int x = 0; x < W; x++)
                {
                    int idx = (y * W + x) * 4;
                    int bx = (x + (row % 2) * 16) % 32;
                    bool mortar = (y % 16 <= 1) || (bx <= 1);
                    bool hi = !mortar && ((y % 16 == 2) || (bx == 2));
                    float n = SmoothTileNoise(x / 8f, y / 8f, 16, 201);
                    int brickVar = ((row * 13 + (x + (row % 2) * 16) / 32) % 4) * 8;
                    if (mortar)
                    {
                        px[idx] = 188; px[idx + 1] = 178; px[idx + 2] = 162; px[idx + 3] = 255;
                    }
                    else
                    {
                        int r = (int)(178 + brickVar + n * 22 + (hi ? 24 : 0));
                        int g = (int)(92 + brickVar * 0.6f + n * 16 + (hi ? 18 : 0));
                        int b = (int)(58 + brickVar * 0.4f + n * 12 + (hi ? 14 : 0));
                        px[idx]     = (byte)MathUtil.ClampInt(r, 0, 255);
                        px[idx + 1] = (byte)MathUtil.ClampInt(g, 0, 255);
                        px[idx + 2] = (byte)MathUtil.ClampInt(b, 0, 255);
                        px[idx + 3] = 255;
                    }
                }
            }
            return UploadRgbaTexture(px, W, H, true, true);
        }

        private static uint CreateRockCliffTex()
        {
            const int W = 128, H = 128;
            byte[] px = new byte[W * H * 4];
            for (int y = 0; y < H; y++)
            {
                for (int x = 0; x < W; x++)
                {
                    int idx = (y * W + x) * 4;
                    float strata = (float)Math.Sin(y * 0.24f + SmoothTileNoise(x / 12f, y / 12f, 8, 307) * 4.2f);
                    float crag = SmoothTileNoise(x / 6f, y / 10f, 16, 311);
                    int r = (int)(134 + strata * 22 + crag * 34);
                    int g = (int)(94  + strata * 16 + crag * 26);
                    int b = (int)(58  + strata * 10 + crag * 18);
                    px[idx]     = (byte)MathUtil.ClampInt(r, 0, 255);
                    px[idx + 1] = (byte)MathUtil.ClampInt(g, 0, 255);
                    px[idx + 2] = (byte)MathUtil.ClampInt(b, 0, 255);
                    px[idx + 3] = 255;
                }
            }
            return UploadRgbaTexture(px, W, H, true, true);
        }

        private static uint CreateSnowWallTex()
        {
            const int W = 128, H = 128;
            byte[] px = new byte[W * H * 4];
            for (int y = 0; y < H; y++)
            {
                for (int x = 0; x < W; x++)
                {
                    int idx = (y * W + x) * 4;
                    float n = SmoothTileNoise(x / 10f, y / 10f, 12, 409);
                    float shade = 0.78f + 0.22f * (1f - y / (float)H);
                    px[idx]     = (byte)MathUtil.ClampInt((int)((195 + n * 45) * shade), 0, 255);
                    px[idx + 1] = (byte)MathUtil.ClampInt((int)((226 + n * 28) * shade), 0, 255);
                    px[idx + 2] = 255;
                    px[idx + 3] = 255;
                }
            }
            return UploadRgbaTexture(px, W, H, true, true);
        }

        private static uint CreateSponsorWallTex()
        {
            // Authentic Mario Raceway / Royal Raceway / Wario Stadium N64 Sponsor Wall (matches lu-4.png!):
            // Left half: White billboard with thin red top/bottom stripes & bold royal-blue "MARIO STAR" lettering!
            // Right half: Classic MK64 2-row Red & Yellow Checkered Corner Bumper Blocks!
            using (Bitmap bmp = new Bitmap(256, 64, PixelFormat.Format32bppArgb))
            {
                using (Graphics g = Graphics.FromImage(bmp))
                {
                    g.SmoothingMode = SmoothingMode.AntiAlias;
                    g.Clear(Color.FromArgb(255, 250, 250, 252));

                    // Left half (0..159): White "MARIO STAR" N64 Signboard with red trim bars
                    using (Brush redTrim = new SolidBrush(Color.FromArgb(255, 232, 24, 28)))
                    {
                        g.FillRectangle(redTrim, 0, 2, 160, 6);
                        g.FillRectangle(redTrim, 0, 56, 160, 6);
                    }
                    using (Font f = new Font(FontFamily.GenericSansSerif, 22f, FontStyle.Bold, GraphicsUnit.Pixel))
                    using (StringFormat sf = new StringFormat())
                    {
                        sf.Alignment = StringAlignment.Center;
                        sf.LineAlignment = StringAlignment.Center;
                        using (Brush blueText = new SolidBrush(Color.FromArgb(255, 16, 48, 225)))
                            g.DrawString("MARIO STAR", f, blueText, 80, 32, sf);
                    }

                    // Right half (160..255): 2-Row Red & Yellow MK64 Checkered Bumper Blocks!
                    using (Brush redChk = new SolidBrush(Color.FromArgb(255, 238, 22, 24)))
                    using (Brush yelChk = new SolidBrush(Color.FromArgb(255, 252, 232, 20)))
                    {
                        for (int row = 0; row < 2; row++)
                        {
                            for (int col = 0; col < 4; col++)
                            {
                                Brush cb = ((row + col) % 2 == 0) ? redChk : yelChk;
                                g.FillRectangle(cb, 160 + col * 24, row * 32, 24, 32);
                            }
                        }
                    }
                }
                return UploadBitmap(bmp, true, true);
            }
        }

        private static uint CreateLuigiBarrierTex()
        {
            // Authentic Luigi Raceway 2-Row Royal-Blue & Lime-Green Checkered Bumper + Blue Coping Rail (matches lu-2.jpg!)
            using (Bitmap bmp = new Bitmap(128, 64, PixelFormat.Format32bppArgb))
            {
                using (Graphics g = Graphics.FromImage(bmp))
                {
                    using (Brush topBlue = new SolidBrush(Color.FromArgb(255, 36, 58, 218)))
                        g.FillRectangle(topBlue, 0, 0, 128, 18);

                    using (Brush lime = new SolidBrush(Color.FromArgb(255, 48, 228, 42)))
                    using (Brush blue = new SolidBrush(Color.FromArgb(255, 24, 48, 198)))
                    {
                        for (int row = 0; row < 2; row++)
                        {
                            for (int col = 0; col < 8; col++)
                            {
                                Brush cb = ((row + col) % 2 == 0) ? lime : blue;
                                g.FillRectangle(cb, col * 16, 18 + row * 23, 16, 23);
                            }
                        }
                    }
                }
                return UploadBitmap(bmp, true, true);
            }
        }

        private static uint CreateStartBannerTex()
        {
            using (Bitmap bmp = new Bitmap(256, 64, PixelFormat.Format32bppArgb))
            {
                using (Graphics g = Graphics.FromImage(bmp))
                {
                    g.SmoothingMode = SmoothingMode.AntiAlias;
                    using (LinearGradientBrush bg = new LinearGradientBrush(
                        new Rectangle(0, 0, 256, 64),
                        Color.FromArgb(255, 248, 248, 252),
                        Color.FromArgb(255, 210, 218, 232),
                        LinearGradientMode.Vertical))
                    {
                        g.FillRectangle(bg, 0, 0, 256, 64);
                    }

                    // Left & Right Checkered Flag Panels!
                    for (int side = 0; side < 2; side++)
                    {
                        int sx = (side == 0) ? 0 : 208;
                        for (int cy = 0; cy < 8; cy++)
                        {
                            for (int cx = 0; cx < 6; cx++)
                            {
                                Brush cb = ((cx + cy) % 2 == 0) ? Brushes.Black : Brushes.White;
                                g.FillRectangle(cb, sx + cx * 8, cy * 8, 8, 8);
                            }
                        }
                    }

                    // Iconic Red + Blue + Gold MARIO KART 64 Center Emblem!
                    using (Brush redB = new SolidBrush(Color.FromArgb(255, 228, 24, 34)))
                        g.FillRectangle(redB, 48, 4, 160, 28);
                    using (Brush blueB = new SolidBrush(Color.FromArgb(255, 22, 82, 212)))
                        g.FillRectangle(blueB, 48, 32, 160, 28);
                    using (Pen goldP = new Pen(Color.FromArgb(255, 255, 212, 32), 3f))
                        g.DrawRectangle(goldP, 49, 4, 158, 56);

                    using (Font fBig = new Font(FontFamily.GenericSansSerif, 20f, FontStyle.Bold, GraphicsUnit.Pixel))
                    using (Font fSub = new Font(FontFamily.GenericSansSerif, 14f, FontStyle.Bold, GraphicsUnit.Pixel))
                    using (StringFormat sf = new StringFormat())
                    {
                        sf.Alignment = StringAlignment.Center;
                        sf.LineAlignment = StringAlignment.Center;
                        g.DrawString("MARIO KART", fBig, Brushes.Black, 129, 20, sf);
                        g.DrawString("MARIO KART", fBig, Brushes.Yellow, 128, 18, sf);
                        g.DrawString("START / FINISH", fSub, Brushes.Black, 129, 47, sf);
                        g.DrawString("START / FINISH", fSub, Brushes.White, 128, 46, sf);
                    }
                }
                return UploadBitmap(bmp, false, true);
            }
        }

        private static uint CreateCloudTex()
        {
            const int W = 128, H = 64;
            byte[] rgba = new byte[W * H * 4];
            float[,] puffs =
            {
                { 0.50f, 0.58f, 0.28f, 0.34f },
                { 0.30f, 0.50f, 0.22f, 0.26f },
                { 0.70f, 0.50f, 0.22f, 0.26f },
                { 0.18f, 0.42f, 0.15f, 0.18f },
                { 0.82f, 0.42f, 0.15f, 0.18f }
            };

            for (int y = 0; y < H; y++)
            {
                float ny = 1f - (y / (float)H);
                for (int x = 0; x < W; x++)
                {
                    float nx = x / (float)W;
                    float density = 0f;
                    for (int p = 0; p < 5; p++)
                    {
                        float dx = (nx - puffs[p, 0]) / puffs[p, 2];
                        float dy = (ny - puffs[p, 1]) / puffs[p, 3];
                        float d = 1f - (dx * dx + dy * dy);
                        if (d > density) density = d;
                    }
                    int idx = (y * W + x) * 4;
                    if (density > 0f)
                    {
                        float alpha = MathUtil.Clamp(density * 2.2f, 0f, 1f);
                        float shade = 0.84f + 0.16f * MathUtil.Clamp(ny * 1.3f, 0f, 1f);
                        rgba[idx]     = (byte)(248 * shade);
                        rgba[idx + 1] = (byte)(250 * shade);
                        rgba[idx + 2] = 255;
                        rgba[idx + 3] = (byte)(alpha * 238);
                    }
                }
            }
            return UploadRgbaTexture(rgba, W, H, false, true);
        }

        private static uint CreateCheckerTex()
        {
            const int W = 64, H = 64;
            byte[] px = new byte[W * H * 4];
            for (int y = 0; y < H; y++)
            {
                for (int x = 0; x < W; x++)
                {
                    int idx = (y * W + x) * 4;
                    bool white = ((x / 8) + (y / 8)) % 2 == 0;
                    byte c = white ? (byte)248 : (byte)24;
                    px[idx] = c; px[idx + 1] = c; px[idx + 2] = c; px[idx + 3] = 255;
                }
            }
            return UploadRgbaTexture(px, W, H, true, false);
        }

        private static uint CreateLiquidTex(bool lava)
        {
            const int W = 128, H = 128;
            byte[] px = new byte[W * H * 4];
            for (int y = 0; y < H; y++)
            {
                for (int x = 0; x < W; x++)
                {
                    int idx = (y * W + x) * 4;
                    double wv = Math.Sin(x * 0.15) + Math.Cos(y * 0.15) + Math.Sin((x + y) * 0.10);
                    if (lava)
                    {
                        px[idx]     = (byte)MathUtil.ClampInt((int)(235 + wv * 18), 0, 255);
                        px[idx + 1] = (byte)MathUtil.ClampInt((int)(92 + wv * 48), 0, 255);
                        px[idx + 2] = 18;
                        px[idx + 3] = 248;
                    }
                    else
                    {
                        px[idx]     = (byte)MathUtil.ClampInt((int)(24 + wv * 16), 0, 255);
                        px[idx + 1] = (byte)MathUtil.ClampInt((int)(152 + wv * 28), 0, 255);
                        px[idx + 2] = (byte)MathUtil.ClampInt((int)(238 + wv * 14), 0, 255);
                        px[idx + 3] = 222;
                    }
                }
            }
            return UploadRgbaTexture(px, W, H, true, true);
        }

        private static uint CreateFontAtlas()
        {
            const int AtlasW = 512;
            const int AtlasH = 256;
            const int CellW = 32;
            const int CellH = 32;

            using (Bitmap bmp = new Bitmap(AtlasW, AtlasH, PixelFormat.Format32bppArgb))
            {
                using (Graphics g = Graphics.FromImage(bmp))
                {
                    g.Clear(Color.FromArgb(0, 0, 0, 0));
                    g.SmoothingMode = SmoothingMode.AntiAlias;
                    g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;

                    using (Font font = new Font(FontFamily.GenericSansSerif, 18.5f, FontStyle.Bold, GraphicsUnit.Pixel))
                    using (StringFormat sf = new StringFormat())
                    using (Brush blackBrush = new SolidBrush(Color.FromArgb(245, 12, 12, 18)))
                    using (Brush whiteBrush = new SolidBrush(Color.FromArgb(255, 255, 255, 255)))
                    {
                        sf.Alignment = StringAlignment.Center;
                        sf.LineAlignment = StringAlignment.Center;

                        for (int ch = 32; ch < 127; ch++)
                        {
                            int cellIdx = ch - 32;
                            int col = cellIdx % 16;
                            int row = cellIdx / 16;
                            float cx = col * CellW + CellW * 0.5f;
                            float cy = row * CellH + CellH * 0.52f;
                            string s = ((char)ch).ToString();

                            for (int ox = -2; ox <= 2; ox++)
                            {
                                for (int oy = -2; oy <= 2; oy++)
                                {
                                    if (ox == 0 && oy == 0) continue;
                                    if (Math.Abs(ox) + Math.Abs(oy) > 3) continue;
                                    g.DrawString(s, font, blackBrush, cx + ox, cy + oy, sf);
                                }
                            }
                            g.DrawString(s, font, whiteBrush, cx, cy, sf);
                        }
                    }
                }
                return UploadBitmap(bmp, false, true);
            }
        }

        public static void DrawText2D(string text, float x, float y, float charHeight, Color4 topCol, Color4 botCol, bool center)
        {
            if (string.IsNullOrEmpty(text)) return;

            float advance = charHeight * 0.62f;
            float quadSize = charHeight * 1.05f;
            float startX = center ? (x - (text.Length * advance) * 0.5f) : x;

            Gl.glEnable(Gl.GL_TEXTURE_2D);
            Gl.glBindTexture(Gl.GL_TEXTURE_2D, TexFont);
            Gl.glEnable(Gl.GL_BLEND);
            Gl.glBlendFunc(Gl.GL_SRC_ALPHA, Gl.GL_ONE_MINUS_SRC_ALPHA);

            Gl.glBegin(Gl.GL_QUADS);
            for (int i = 0; i < text.Length; i++)
            {
                int ch = (int)text[i];
                if (ch < 32 || ch >= 127) ch = '?';
                int cellIdx = ch - 32;
                int col = cellIdx % 16;
                int row = cellIdx / 16;

                float u0 = (col * 32.0f + 1.0f) / 512.0f;
                float u1 = ((col + 1) * 32.0f - 1.0f) / 512.0f;
                float v0 = (row * 32.0f + 1.0f) / 256.0f;
                float v1 = ((row + 1) * 32.0f - 1.0f) / 256.0f;

                float gx0 = startX + i * advance;
                float gx1 = gx0 + quadSize;
                float gy0 = y;
                float gy1 = y + quadSize;

                Gl.Color(topCol);
                Gl.glTexCoord2f(u0, v0); Gl.glVertex2f(gx0, gy0);
                Gl.glTexCoord2f(u1, v0); Gl.glVertex2f(gx1, gy0);

                Gl.Color(botCol);
                Gl.glTexCoord2f(u1, v1); Gl.glVertex2f(gx1, gy1);
                Gl.glTexCoord2f(u0, v1); Gl.glVertex2f(gx0, gy1);
            }
            Gl.glEnd();
            Gl.glDisable(Gl.GL_TEXTURE_2D);
        }

        public static void DrawSprite2D(uint texId, float x, float y, float w, float h, Color4 tint)
        {
            Gl.glEnable(Gl.GL_TEXTURE_2D);
            Gl.glBindTexture(Gl.GL_TEXTURE_2D, texId);
            Gl.glEnable(Gl.GL_BLEND);
            Gl.glBlendFunc(Gl.GL_SRC_ALPHA, Gl.GL_ONE_MINUS_SRC_ALPHA);
            Gl.Color(tint);
            Gl.glBegin(Gl.GL_QUADS);
            Gl.glTexCoord2f(0f, 0f); Gl.glVertex2f(x, y);
            Gl.glTexCoord2f(1f, 0f); Gl.glVertex2f(x + w, y);
            Gl.glTexCoord2f(1f, 1f); Gl.glVertex2f(x + w, y + h);
            Gl.glTexCoord2f(0f, 1f); Gl.glVertex2f(x, y + h);
            Gl.glEnd();
            Gl.glDisable(Gl.GL_TEXTURE_2D);
        }

        public static void DrawSolidRect2D(float x, float y, float w, float h, Color4 col)
        {
            Gl.glDisable(Gl.GL_TEXTURE_2D);
            Gl.glEnable(Gl.GL_BLEND);
            Gl.glBlendFunc(Gl.GL_SRC_ALPHA, Gl.GL_ONE_MINUS_SRC_ALPHA);
            Gl.Color(col);
            Gl.glBegin(Gl.GL_QUADS);
            Gl.glVertex2f(x, y);
            Gl.glVertex2f(x + w, y);
            Gl.glVertex2f(x + w, y + h);
            Gl.glVertex2f(x, y + h);
            Gl.glEnd();
        }

        public static void DrawRectOutline2D(float x, float y, float w, float h, float lineWidth, Color4 col)
        {
            Gl.glDisable(Gl.GL_TEXTURE_2D);
            Gl.glLineWidth(lineWidth);
            Gl.Color(col);
            Gl.glBegin(Gl.GL_LINE_LOOP);
            Gl.glVertex2f(x, y);
            Gl.glVertex2f(x + w, y);
            Gl.glVertex2f(x + w, y + h);
            Gl.glVertex2f(x, y + h);
            Gl.glEnd();
        }
    }
}
