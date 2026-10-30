using System;
using System.Collections.Generic;
using MarioKart64.Core;
using MarioKart64.Entities;
using MarioKart64.Tracks;

namespace MarioKart64.Rendering
{
    public sealed class SceneRenderer : IDisposable
    {
        private uint _trackDisplayList = 0;
        private TrackData _cachedTrack = null;

        public void InvalidateDisplayList()
        {
            if (_trackDisplayList != 0)
            {
                try { Gl.glDeleteLists(_trackDisplayList, 1); } catch { }
                _trackDisplayList = 0;
            }
            _cachedTrack = null;
        }

        private void EnsureTrackCompiled(TrackData track)
        {
            if (_cachedTrack == track && _trackDisplayList != 0) return;
            InvalidateDisplayList();
            _cachedTrack = track;
            _trackDisplayList = Gl.glGenLists(1);
            Gl.glNewList(_trackDisplayList, Gl.GL_COMPILE);
            BuildStaticTrackGeometry(track);
            Gl.glEndList();
        }

        public void RenderViewport(
            int vx, int vy, int vw, int vh,
            Vec3 camEye, Vec3 camTarget,
            TrackData track,
            Kart[] karts,
            List<WorldItemEntity> worldItems,
            List<CourseHazard> hazards,
            float globalTime,
            float lightningFlashTimer)
        {
            if (vw <= 4 || vh <= 4) return;
            EnsureTrackCompiled(track);

            Gl.glViewport(vx, vy, vw, vh);
            Gl.glEnable(Gl.GL_SCISSOR_TEST);
            Gl.glScissor(vx, vy, vw, vh);

            Color4 skyTop = track.SkyTopColor;
            Color4 skyHoriz = track.SkyHorizonColor;
            if (lightningFlashTimer > 0f)
            {
                skyTop = Color4.Lerp(skyTop, new Color4(1f, 1f, 1f, 1f), lightningFlashTimer);
                skyHoriz = Color4.Lerp(skyHoriz, new Color4(1f, 1f, 1f, 1f), lightningFlashTimer);
            }

            Gl.glClearColor(skyHoriz.R, skyHoriz.G, skyHoriz.B, 1.0f);
            Gl.glClearDepth(1.0);
            Gl.glClear(Gl.GL_COLOR_BUFFER_BIT | Gl.GL_DEPTH_BUFFER_BIT);

            // Setup 3D Perspective Camera
            Gl.glMatrixMode(Gl.GL_PROJECTION);
            Gl.glLoadIdentity();
            Gl.Perspective(60.0f, vw / (float)vh, 0.8f, 980.0f);

            Gl.glMatrixMode(Gl.GL_MODELVIEW);
            Gl.glLoadIdentity();
            Gl.LookAt(camEye, camTarget, Vec3.Up);

            Vec3 camFwd = (camTarget - camEye).NormalizedXZ();
            if (camFwd.LengthSq < 0.001f) camFwd = new Vec3(0f, 0f, 1f);
            Vec3 camScreenRight = Vec3.Cross(camFwd, Vec3.Up).Normalized();

            // 1. True 3D N64 Sky Dome, Rolling Hills/Mountains, Skyscrapers & Fluffy Clouds (Depth Write Off)
            Render3DSkyAndHorizon(camEye, track, skyTop, skyHoriz, globalTime);

            // 2. Enable Depth + Authentic N64 Linear Distance Fog
            Gl.glEnable(Gl.GL_DEPTH_TEST);
            Gl.glDepthFunc(Gl.GL_LEQUAL);
            Gl.glDepthMask(1);

            Gl.glEnable(Gl.GL_FOG);
            Gl.glFogi(Gl.GL_FOG_MODE, (int)Gl.GL_LINEAR);
            Gl.glFogf(Gl.GL_FOG_START, track.FogStart);
            Gl.glFogf(Gl.GL_FOG_END, track.FogEnd);
            float[] fogCol = new float[] { track.FogColor.R, track.FogColor.G, track.FogColor.B, 1.0f };
            Gl.glFogfv(Gl.GL_FOG_COLOR, fogCol);

            // 3. Render Infinite Ground / Animated Water / Boiling Lava Plane
            RenderInfiniteGroundAndLiquid(track, camEye, globalTime);

            // 4. Execute Compiled Display List for Road, Beveled Curbs, Textured Walls, Gantry & 3D Landmarks
            if (_trackDisplayList != 0)
            {
                Gl.glCallList(_trackDisplayList);
            }

            // 5. Render SGI Scenery Billboards (Trees, Palms, Pines, Cacti, Cows, Giant Mushrooms, Hot-Air Balloon)
            RenderBillboardProps(track, camEye, camScreenRight, globalTime);

            // 6. Render Spinning Rainbow '?' Item Boxes
            RenderItemBoxes(track, globalTime);

            // 7. Render Dynamic Course Hazards (Kalimari Train, Highway Traffic, SGI Thwomps, Penguins, Yoshi Egg, Chomps)
            RenderCourseHazards(hazards, camScreenRight, globalTime);

            // 8. Render Active SGI World Items (Shells, Bananas, Fake Item Boxes)
            RenderWorldItems(worldItems, camScreenRight, globalTime);

            // 9. Render All Karts & Drivers (Back-to-Front sorted relative to camera for crisp alpha blending!)
            int kartCount = karts.Length;
            int[] order = new int[kartCount];
            float[] distSq = new float[kartCount];
            for (int i = 0; i < kartCount; i++)
            {
                order[i] = i;
                distSq[i] = (karts[i].Position - camEye).LengthSq;
            }
            for (int i = 0; i < kartCount - 1; i++)
            {
                for (int j = i + 1; j < kartCount; j++)
                {
                    if (distSq[j] > distSq[i])
                    {
                        float td = distSq[i]; distSq[i] = distSq[j]; distSq[j] = td;
                        int ti = order[i]; order[i] = order[j]; order[j] = ti;
                    }
                }
            }
            for (int i = 0; i < kartCount; i++)
            {
                KartModelRenderer.RenderKart(karts[order[i]], camEye, camScreenRight, globalTime, track.IsBattleArena);
            }

            // 10. Weather Particles (Frappe Snowland Snowflakes!)
            if (track.IsSnowing)
            {
                RenderSnowfall(camEye, globalTime);
            }

            Gl.glDisable(Gl.GL_FOG);
            Gl.glDisable(Gl.GL_SCISSOR_TEST);
        }

        private void Render3DSkyAndHorizon(Vec3 eye, TrackData track, Color4 topCol, Color4 horizCol, float time)
        {
            Gl.glDisable(Gl.GL_DEPTH_TEST);
            Gl.glDepthMask(0);
            Gl.glDisable(Gl.GL_FOG);
            Gl.glDisable(Gl.GL_TEXTURE_2D);

            const int Segs = 40;
            const float SkyR = 680f;

            // Upper Sky Dome Cylinder + Zenith Cap
            Gl.glBegin(Gl.GL_TRIANGLE_FAN);
            Gl.Color(topCol);
            Gl.glVertex3f(eye.X, eye.Y + 420f, eye.Z);
            for (int i = 0; i <= Segs; i++)
            {
                float a = (i / (float)Segs) * MathUtil.TWO_PI;
                Gl.glVertex3f(eye.X + (float)Math.Cos(a) * SkyR, eye.Y + 190f, eye.Z + (float)Math.Sin(a) * SkyR);
            }
            Gl.glEnd();

            Gl.glBegin(Gl.GL_TRIANGLE_STRIP);
            for (int i = 0; i <= Segs; i++)
            {
                float a = (i / (float)Segs) * MathUtil.TWO_PI;
                float x = eye.X + (float)Math.Cos(a) * SkyR;
                float z = eye.Z + (float)Math.Sin(a) * SkyR;
                Gl.Color(topCol);
                Gl.glVertex3f(x, eye.Y + 195f, z);
                Gl.Color(horizCol);
                Gl.glVertex3f(x, eye.Y - 12f, z);
            }
            Gl.glEnd();

            // Lower Horizon Fill
            Color4 lowCol = track.HasVoidAbyss ? topCol.ScaleRGB(0.45f) : track.GroundPlaneColor;
            Gl.glBegin(Gl.GL_TRIANGLE_STRIP);
            for (int i = 0; i <= Segs; i++)
            {
                float a = (i / (float)Segs) * MathUtil.TWO_PI;
                float x = eye.X + (float)Math.Cos(a) * SkyR;
                float z = eye.Z + (float)Math.Sin(a) * SkyR;
                Gl.Color(horizCol);
                Gl.glVertex3f(x, eye.Y - 12f, z);
                Gl.Color(lowCol);
                Gl.glVertex3f(x, eye.Y - 260f, z);
            }
            Gl.glEnd();

            // Night Starfield (Rainbow Road, Toad's Turnpike, Banshee Boardwalk, Wario Stadium, Skyscraper)
            if (track.IsNightSky)
            {
                Gl.glPointSize(2.6f);
                Gl.glBegin(Gl.GL_POINTS);
                for (int i = 0; i < 140; i++)
                {
                    float a = (i * 2.39996f) % MathUtil.TWO_PI;
                    float elev = 12f + (i * 19.7f) % 185f;
                    float r = 610f;
                    float twinkle = 0.55f + 0.45f * (float)Math.Sin(time * 4.2f + i);
                    if (track.Id == CourseId.RainbowRoad && (i % 3 == 0))
                        Gl.Color(Color4.Rainbow(i * 0.7f + time * 1.8f).WithAlpha(twinkle));
                    else
                        Gl.glColor4f(twinkle, twinkle, 1.0f, 1.0f);
                    Gl.glVertex3f(eye.X + (float)Math.Cos(a) * r, eye.Y + elev, eye.Z + (float)Math.Sin(a) * r);
                }
                Gl.glEnd();
            }

            // Toad's Turnpike / Skyscraper Glowing Night City Skyline!
            if (track.Id == CourseId.ToadsTurnpike || track.Id == CourseId.Skyscraper)
            {
                float cityR = 560f;
                for (int i = 0; i < 36; i++)
                {
                    float a0 = (i / 36f) * MathUtil.TWO_PI;
                    float a1 = ((i + 0.72f) / 36f) * MathUtil.TWO_PI;
                    float bh = 28f + ((i * 37) % 68);
                    float x0 = eye.X + (float)Math.Cos(a0) * cityR, z0 = eye.Z + (float)Math.Sin(a0) * cityR;
                    float x1 = eye.X + (float)Math.Cos(a1) * cityR, z1 = eye.Z + (float)Math.Sin(a1) * cityR;
                    Gl.Color(Color4.FromBytes(22, 28, 48));
                    Gl.glBegin(Gl.GL_QUADS);
                    Gl.glVertex3f(x0, eye.Y - 18f, z0); Gl.glVertex3f(x1, eye.Y - 18f, z1);
                    Gl.glVertex3f(x1, eye.Y + bh,  z1); Gl.glVertex3f(x0, eye.Y + bh,  z0);
                    Gl.glEnd();

                    // Lit yellow/cyan office windows
                    Gl.Color((i % 2 == 0) ? Color4.FromBytes(255, 224, 98) : Color4.FromBytes(115, 215, 255));
                    Gl.glPointSize(2.5f);
                    Gl.glBegin(Gl.GL_POINTS);
                    for (float wy = 4f; wy < bh - 6f; wy += 11f)
                    {
                        Gl.glVertex3f((x0 + x1) * 0.5f, eye.Y + wy, (z0 + z1) * 0.5f);
                    }
                    Gl.glEnd();
                }
            }
            else if (!track.HasVoidAbyss || track.Id == CourseId.YoshiValley)
            {
                // Layer 1: Distant Mountain Peaks Ring (Blue/Violet/Ochre N64 Alpine Backdrop!)
                Color4 farPeak = Color4.Lerp(horizCol, Color4.FromBytes(78, 108, 168), 0.55f);
                Color4 farBase = Color4.Lerp(horizCol, track.GroundPlaneColor, 0.35f);
                if (track.Id == CourseId.KalimariDesert) { farPeak = Color4.FromBytes(205, 112, 62); farBase = Color4.FromBytes(228, 168, 105); }
                else if (track.Id == CourseId.FrappeSnowland || track.Id == CourseId.SherbetLand) { farPeak = Color4.FromBytes(248, 252, 255); farBase = Color4.FromBytes(165, 198, 238); }
                else if (track.Id == CourseId.BowsersCastle) { farPeak = Color4.FromBytes(92, 36, 28); farBase = Color4.FromBytes(165, 58, 24); }

                float mR = 590f;
                Gl.glBegin(Gl.GL_TRIANGLE_STRIP);
                for (int i = 0; i <= 48; i++)
                {
                    float a = (i / 48f) * MathUtil.TWO_PI;
                    float h = 34f + 36f * (float)Math.Abs(Math.Sin(a * 3.0f + 0.4f)) + 22f * (float)Math.Abs(Math.Cos(a * 5.0f));
                    float x = eye.X + (float)Math.Cos(a) * mR;
                    float z = eye.Z + (float)Math.Sin(a) * mR;
                    Gl.Color(farPeak);
                    Gl.glVertex3f(x, eye.Y + h, z);
                    Gl.Color(farBase);
                    Gl.glVertex3f(x, eye.Y - 16f, z);
                }
                Gl.glEnd();

                // Layer 2: Closer Lush Rolling N64 Foothills!
                Color4 hillTop = Color4.Lerp(track.GroundPlaneColor, Color4.FromBytes(82, 196, 68), 0.45f);
                if (track.Id == CourseId.KalimariDesert || track.Id == CourseId.ChocoMountain) hillTop = track.GroundPlaneColor.ScaleRGB(0.88f);
                else if (track.Id == CourseId.FrappeSnowland || track.Id == CourseId.SherbetLand) hillTop = Color4.FromBytes(222, 238, 255);
                Color4 hillBot = track.GroundPlaneColor.ScaleRGB(0.76f);

                float hR = 510f;
                Gl.glBegin(Gl.GL_TRIANGLE_STRIP);
                for (int i = 0; i <= 48; i++)
                {
                    float a = (i / 48f) * MathUtil.TWO_PI;
                    float h = 14f + 20f * (float)(0.5 + 0.5 * Math.Sin(a * 4.0f + 1.2f)) + 10f * (float)Math.Cos(a * 7.0f);
                    float x = eye.X + (float)Math.Cos(a) * hR;
                    float z = eye.Z + (float)Math.Sin(a) * hR;
                    Gl.Color(hillTop);
                    Gl.glVertex3f(x, eye.Y + h, z);
                    Gl.Color(hillBot);
                    Gl.glVertex3f(x, eye.Y - 18f, z);
                }
                Gl.glEnd();
            }

            // Fluffy Drifting N64 Clouds on Daytime/Sunset Tracks!
            if (!track.IsNightSky && ProceduralTextures.TexCloud != 0)
            {
                Gl.glEnable(Gl.GL_TEXTURE_2D);
                Gl.glBindTexture(Gl.GL_TEXTURE_2D, ProceduralTextures.TexCloud);
                Gl.glEnable(Gl.GL_BLEND);
                Gl.glBlendFunc(Gl.GL_SRC_ALPHA, Gl.GL_ONE_MINUS_SRC_ALPHA);

                float cR = 470f;
                for (int c = 0; c < 14; c++)
                {
                    float a = (c / 14f) * MathUtil.TWO_PI + time * 0.008f;
                    float cy = eye.Y + 68f + (c % 3) * 26f;
                    Vec3 center = new Vec3(eye.X + (float)Math.Cos(a) * cR, cy, eye.Z + (float)Math.Sin(a) * cR);
                    Vec3 tang = new Vec3(-(float)Math.Sin(a), 0f, (float)Math.Cos(a));
                    float cw = 68f + (c % 2) * 22f;
                    float ch = 32f + (c % 2) * 10f;

                    Gl.glColor4f(1f, 1f, 1f, 0.92f);
                    Gl.glBegin(Gl.GL_QUADS);
                    Gl.glTexCoord2f(0f, 1f); Gl.Vertex(center - tang * cw);
                    Gl.glTexCoord2f(1f, 1f); Gl.Vertex(center + tang * cw);
                    Gl.glTexCoord2f(1f, 0f); Gl.Vertex(center + tang * cw + new Vec3(0f, ch, 0f));
                    Gl.glTexCoord2f(0f, 0f); Gl.Vertex(center - tang * cw + new Vec3(0f, ch, 0f));
                    Gl.glEnd();
                }
                Gl.glDisable(Gl.GL_TEXTURE_2D);
            }

            Gl.glDepthMask(1);
        }

        private void RenderInfiniteGroundAndLiquid(TrackData track, Vec3 camEye, float time)
        {
            if (track.HasVoidAbyss && !track.HasWaterPlane && !track.HasLavaPlane)
            {
                return;
            }

            float planeY = (track.HasWaterPlane || track.HasLavaPlane) ? track.LiquidPlaneY : -2.6f;
            uint tex = ProceduralTextures.TexGrass;
            float uvAnim = 0f;

            if (track.HasLavaPlane)
            {
                tex = ProceduralTextures.TexLava;
                uvAnim = time * 0.28f;
            }
            else if (track.HasWaterPlane)
            {
                tex = ProceduralTextures.TexWater;
                uvAnim = time * 0.18f;
            }
            else if (track.Id == CourseId.KalimariDesert) tex = ProceduralTextures.TexSand;
            else if (track.Id == CourseId.FrappeSnowland) tex = ProceduralTextures.TexSnow;
            else if (track.Id == CourseId.ChocoMountain || track.Id == CourseId.WarioStadium) tex = ProceduralTextures.TexDirt;

            Gl.glEnable(Gl.GL_TEXTURE_2D);
            Gl.glBindTexture(Gl.GL_TEXTURE_2D, tex);
            Gl.glColor4f(1f, 1f, 1f, 1f);

            float R = 900f;
            float cx = (float)Math.Floor(camEye.X / 36.0) * 36f;
            float cz = (float)Math.Floor(camEye.Z / 36.0) * 36f;
            float uvScale = 50f;

            Gl.glBegin(Gl.GL_QUADS);
            Gl.glTexCoord2f(-uvScale + uvAnim, -uvScale + uvAnim); Gl.glVertex3f(cx - R, planeY, cz - R);
            Gl.glTexCoord2f( uvScale + uvAnim, -uvScale + uvAnim); Gl.glVertex3f(cx + R, planeY, cz - R);
            Gl.glTexCoord2f( uvScale + uvAnim,  uvScale + uvAnim); Gl.glVertex3f(cx + R, planeY, cz + R);
            Gl.glTexCoord2f(-uvScale + uvAnim,  uvScale + uvAnim); Gl.glVertex3f(cx - R, planeY, cz + R);
            Gl.glEnd();
            Gl.glDisable(Gl.GL_TEXTURE_2D);
        }

        private uint SelectCourseWallTexture(TrackData track, bool isSponsorBarrier)
        {
            switch (track.Id)
            {
                case CourseId.LuigiRaceway:
                case CourseId.MarioRaceway:
                case CourseId.RoyalRaceway:
                case CourseId.WarioStadium:
                    return isSponsorBarrier ? ProceduralTextures.TexSponsorWall : ProceduralTextures.TexBrickWall;

                case CourseId.FrappeSnowland:
                case CourseId.SherbetLand:
                    return ProceduralTextures.TexSnowWall;

                case CourseId.BowsersCastle:
                case CourseId.BansheeBoardwalk:
                    return ProceduralTextures.TexCastleStone;

                case CourseId.ChocoMountain:
                case CourseId.KalimariDesert:
                case CourseId.KoopaTroopaBeach:
                case CourseId.YoshiValley:
                case CourseId.DKsJungleParkway:
                    return ProceduralTextures.TexRockCliff;

                default:
                    return ProceduralTextures.TexBrickWall;
            }
        }

        private void BuildStaticTrackGeometry(TrackData track)
        {
            if (track.IsBattleArena)
            {
                BuildBattleArenaGeometry(track);
                return;
            }

            if (track.Segments == null || track.Segments.Length == 0) return;

            // 1. Primary Road Spline Ribbon, Beveled Curbs, Textured Shoulders, Sponsor Walls, Bridges, & Tunnels
            BuildSplineMesh(track, track.Segments, true);

            // 2. Branch / Shortcut Splines (Koopa Rock Cave, Peach Castle Drive, Yoshi Valley Maze Bridges!)
            for (int b = 0; b < track.Branches.Count; b++)
            {
                BuildSplineMesh(track, track.Branches[b].Segments, false);
            }

            // 3. Kalimari Desert Wooden Ties, Gravel Bed & Steel Rails!
            if (track.Id == CourseId.KalimariDesert && track.HazardSpecs.Count > 0 && track.HazardSpecs[0].CustomLoop != null)
            {
                BuildRailroadTrackLoop(track.HazardSpecs[0].CustomLoop);
            }

            // 4. Authentic MK64 Checkered Steel Truss Start/Finish Gantry!
            BuildFinishBannerArch(track.Segments[0], track.Id == CourseId.RainbowRoad);

            // 5. Architectural 3D Course Landmarks!
            Gl.glDisable(Gl.GL_TEXTURE_2D);
            for (int p = 0; p < track.Props.Count; p++)
            {
                RenderStaticLandmarkGeometry(track.Props[p]);
            }
        }

        private void BuildSplineMesh(TrackData track, TrackSegment[] segs, bool closedLoop)
        {
            int count = segs.Length;
            int limit = closedLoop ? count : (count - 1);
            bool isHighway = (track.Id == CourseId.ToadsTurnpike);
            bool hasRaisedFloorCurbs = (track.Id == CourseId.BowsersCastle || track.Id == CourseId.WarioStadium);

            for (int i = 0; i < limit; i++)
            {
                TrackSegment s0 = segs[i];
                TrackSegment s1 = segs[(i + 1) % count];
                TrackSegment sPrev = segs[(i - 1 + count) % count];

                Vec3 l0 = s0.Center - s0.Right * s0.HalfWidth;
                Vec3 r0 = s0.Center + s0.Right * s0.HalfWidth;
                Vec3 l1 = s1.Center - s1.Right * s1.HalfWidth;
                Vec3 r1 = s1.Center + s1.Right * s1.HalfWidth;

                bool isFinish = (s0.Flags & SegmentFlags.CheckerFinish) != 0;
                uint roadTex = isFinish
                    ? ProceduralTextures.TexChecker
                    : ((track.Id == CourseId.LuigiRaceway && s0.RoadSurface == SurfaceType.Asphalt)
                        ? ProceduralTextures.TexLuigiRoad
                        : ProceduralTextures.GetRoadTexture(s0.RoadSurface, isHighway));

                Gl.glEnable(Gl.GL_TEXTURE_2D);
                Gl.glBindTexture(Gl.GL_TEXTURE_2D, roadTex);
                if (s0.RoadSurface == SurfaceType.RainbowNeon)
                {
                    Gl.glEnable(Gl.GL_BLEND);
                    Gl.glBlendFunc(Gl.GL_SRC_ALPHA, Gl.GL_ONE_MINUS_SRC_ALPHA);
                }

                float v0 = i * 0.28f;
                float v1 = (i + 1) * 0.28f;
                float uMax = isFinish ? 3.5f : 1.0f;
                if (isFinish) { v0 = 0f; v1 = 1f; }

                // Subtle N64 hill slope lighting!
                float slopeShade = MathUtil.Clamp(1.0f + s0.Forward.Y * 0.35f, 0.84f, 1.12f);
                Gl.glColor4f(slopeShade, slopeShade, slopeShade, 1f);
                Gl.glBegin(Gl.GL_QUADS);
                Gl.glTexCoord2f(0f,   v0); Gl.Vertex(l0);
                Gl.glTexCoord2f(uMax, v0); Gl.Vertex(r0);
                Gl.glTexCoord2f(uMax, v1); Gl.Vertex(r1);
                Gl.glTexCoord2f(0f,   v1); Gl.Vertex(l1);
                Gl.glEnd();
                Gl.glDisable(Gl.GL_TEXTURE_2D);

                // Clean MK64 Road Edges: Asphalt raceways/highways already have crisp painted sidelines (lu-1.jpg / characters--3.png),
                // and dirt/sand/snow/ice courses have natural edges; raised floor curbs appear on Bowser's Castle & Wario Stadium!
                Vec3 cl0 = l0;
                Vec3 cl1 = l1;
                Vec3 cr0 = r0;
                Vec3 cr1 = r1;
                if (hasRaisedFloorCurbs)
                {
                    Color4 curbCol = ((i % 2) == 0) ? track.CurbColorA : track.CurbColorB;
                    float curbW = 1.05f;
                    cl0 = l0 - s0.Right * curbW + new Vec3(0f, 0.14f, 0f);
                    cl1 = l1 - s1.Right * curbW + new Vec3(0f, 0.14f, 0f);
                    cr0 = r0 + s0.Right * curbW + new Vec3(0f, 0.14f, 0f);
                    cr1 = r1 + s1.Right * curbW + new Vec3(0f, 0.14f, 0f);

                    Gl.Color(curbCol);
                    Gl.glBegin(Gl.GL_QUADS);
                    Gl.Vertex(cl0); Gl.Vertex(l0); Gl.Vertex(l1); Gl.Vertex(cl1);
                    Gl.Vertex(r0); Gl.Vertex(cr0); Gl.Vertex(cr1); Gl.Vertex(r1);
                    Gl.glEnd();
                }

                // Bridge Deck Side Fascia & Twin Outer Support Piers (clear of any underpass road below!)
                if ((s0.Flags & SegmentFlags.Bridge) != 0 && track.Id != CourseId.RainbowRoad)
                {
                    uint bridgeTex = (s0.RoadSurface == SurfaceType.WoodPlanks) ? ProceduralTextures.TexWood : ProceduralTextures.TexCastleStone;
                    Gl.glEnable(Gl.GL_TEXTURE_2D);
                    Gl.glBindTexture(Gl.GL_TEXTURE_2D, bridgeTex);
                    Gl.glColor4f(0.85f, 0.85f, 0.85f, 1f);
                    Gl.glBegin(Gl.GL_QUADS);
                    Gl.glTexCoord2f(0f, 0f); Gl.Vertex(cl0);
                    Gl.glTexCoord2f(1f, 0f); Gl.Vertex(cl1);
                    Gl.glTexCoord2f(1f, 1f); Gl.Vertex(cl1 - new Vec3(0f, 1.8f, 0f));
                    Gl.glTexCoord2f(0f, 1f); Gl.Vertex(cl0 - new Vec3(0f, 1.8f, 0f));

                    Gl.glTexCoord2f(0f, 0f); Gl.Vertex(cr0);
                    Gl.glTexCoord2f(1f, 0f); Gl.Vertex(cr1);
                    Gl.glTexCoord2f(1f, 1f); Gl.Vertex(cr1 - new Vec3(0f, 1.8f, 0f));
                    Gl.glTexCoord2f(0f, 1f); Gl.Vertex(cr0 - new Vec3(0f, 1.8f, 0f));
                    Gl.glEnd();
                    Gl.glDisable(Gl.GL_TEXTURE_2D);

                    if (i % 10 == 0 && s0.Center.Y > 4.5f)
                    {
                        Color4 pier = track.WallColor.ScaleRGB(0.72f);
                        float pierTop = s0.Center.Y - 1.85f;
                        float pierBot = -6.0f;
                        float pMidY = (pierTop + pierBot) * 0.5f;
                        float pHalfH = (pierTop - pierBot) * 0.5f;
                        Vec3 pL = cl0 + new Vec3(0f, 0f, 0f);
                        Vec3 pR = cr0 + new Vec3(0f, 0f, 0f);
                        KartModelRenderer.DrawBox(pL.X, pMidY, pL.Z, 1.1f, pHalfH, 1.1f, pier, pier);
                        KartModelRenderer.DrawBox(pR.X, pMidY, pR.Z, 1.1f, pHalfH, 1.1f, pier, pier);
                    }
                }

                // Left & Right Edge Shoulders / Sponsor Barriers / Canyon Cliffs / Fences
                BuildEdgeDetail(track, s0, s1, cl0, cl1, -s0.Right, -s1.Right, s0.LeftEdge, i, false);
                BuildEdgeDetail(track, s0, s1, cr0, cr1,  s0.Right,  s1.Right, s0.RightEdge, i, true);

                // Overhead Arched Tunnel / Mario Warp Pipe / Sherbet Ice Cavern / Luigi Brick Tunnel Portal!
                if ((s0.Flags & SegmentFlags.Tunnel) != 0)
                {
                    bool isTunnelPortal = (sPrev.Flags & SegmentFlags.Tunnel) == 0;
                    BuildTunnelArchSegment(track, s0, cl0, cl1, cr0, cr1, i, isTunnelPortal);
                }
            }
        }

        private void BuildTunnelArchSegment(TrackData track, TrackSegment s0, Vec3 cl0, Vec3 cl1, Vec3 cr0, Vec3 cr1, int segIdx, bool isTunnelPortal)
        {
            float h = 9.4f;
            Vec3 mid0 = (cl0 + cr0) * 0.5f;
            Vec3 mid1 = (cl1 + cr1) * 0.5f;
            Vec3 tl0 = cl0 + new Vec3(0f, h * 0.72f, 0f);
            Vec3 tl1 = cl1 + new Vec3(0f, h * 0.72f, 0f);
            Vec3 tr0 = cr0 + new Vec3(0f, h * 0.72f, 0f);
            Vec3 tr1 = cr1 + new Vec3(0f, h * 0.72f, 0f);
            Vec3 crown0 = mid0 + new Vec3(0f, h, 0f);
            Vec3 crown1 = mid1 + new Vec3(0f, h, 0f);

            // Iconic Luigi Raceway Tan Brick Tunnel Portal Building + Giant Overhead Jumbotron TV Screen (lu-1.jpg & lu-2.jpg!)
            if (isTunnelPortal && track.Id == CourseId.LuigiRaceway)
            {
                Vec3 pL = cl0 - s0.Right * 9.0f;
                Vec3 pR = cr0 + s0.Right * 9.0f;
                float topY = crown0.Y + 11.5f;
                Gl.glEnable(Gl.GL_TEXTURE_2D);
                Gl.glBindTexture(Gl.GL_TEXTURE_2D, ProceduralTextures.TexBrickWall);
                Gl.glColor4f(0.95f, 0.88f, 0.78f, 1f);
                Gl.glBegin(Gl.GL_QUADS);
                // Left brick tower pier
                Gl.glTexCoord2f(0f, 3f); Gl.Vertex(pL);
                Gl.glTexCoord2f(1f, 3f); Gl.Vertex(cl0);
                Gl.glTexCoord2f(1f, 0f); Gl.Vertex(new Vec3(cl0.X, topY, cl0.Z));
                Gl.glTexCoord2f(0f, 0f); Gl.Vertex(new Vec3(pL.X, topY, pL.Z));
                // Right brick tower pier
                Gl.glTexCoord2f(0f, 3f); Gl.Vertex(cr0);
                Gl.glTexCoord2f(1f, 3f); Gl.Vertex(pR);
                Gl.glTexCoord2f(1f, 0f); Gl.Vertex(new Vec3(pR.X, topY, pR.Z));
                Gl.glTexCoord2f(0f, 0f); Gl.Vertex(new Vec3(cr0.X, topY, cr0.Z));
                // Upper brick parapet over tunnel arch
                Gl.glTexCoord2f(0f, 1.5f); Gl.Vertex(new Vec3(pL.X, crown0.Y - 0.5f, pL.Z));
                Gl.glTexCoord2f(4f, 1.5f); Gl.Vertex(new Vec3(pR.X, crown0.Y - 0.5f, pR.Z));
                Gl.glTexCoord2f(4f, 0f);   Gl.Vertex(new Vec3(pR.X, topY, pR.Z));
                Gl.glTexCoord2f(0f, 0f);   Gl.Vertex(new Vec3(pL.X, topY, pL.Z));
                Gl.glEnd();
                Gl.glDisable(Gl.GL_TEXTURE_2D);

                // Giant Black MK64 Luigi TV Jumbotron Screen mounted on the brick facade above the tunnel mouth!
                Vec3 scrC = new Vec3(mid0.X, crown0.Y + 5.4f, mid0.Z) - s0.Forward * 0.45f;
                Vec3 scrL = scrC - s0.Right * 10.5f;
                Vec3 scrR = scrC + s0.Right * 10.5f;
                Gl.Color(Color4.FromBytes(210, 214, 224));
                Gl.glBegin(Gl.GL_QUADS);
                Gl.Vertex(scrL - new Vec3(0f, 4.4f, 0f)); Gl.Vertex(scrR - new Vec3(0f, 4.4f, 0f));
                Gl.Vertex(scrR + new Vec3(0f, 4.4f, 0f)); Gl.Vertex(scrL + new Vec3(0f, 4.4f, 0f));
                Gl.glEnd();
                Vec3 scrFrontL = scrL - s0.Forward * 0.15f;
                Vec3 scrFrontR = scrR - s0.Forward * 0.15f;
                Gl.Color(Color4.FromBytes(14, 18, 26));
                Gl.glBegin(Gl.GL_QUADS);
                Gl.Vertex(scrFrontL - new Vec3(0f, 3.8f, 0f)); Gl.Vertex(scrFrontR - new Vec3(0f, 3.8f, 0f));
                Gl.Vertex(scrFrontR + new Vec3(0f, 3.8f, 0f)); Gl.Vertex(scrFrontL + new Vec3(0f, 3.8f, 0f));
                Gl.glEnd();
            }

            if (track.Id == CourseId.SherbetLand && segIdx % 4 == 0)
            {
                // Giant Shimmering Ice Cavern Pillars inside Sherbet Land's Penguin Cave (characters--2.png!)
                Vec3 pilPos = Vec3.Lerp(cl0, cr0, (segIdx % 8 == 0) ? 0.26f : 0.74f);
                Color4 iceTop = Color4.FromBytes(218, 244, 255);
                Color4 iceBot = Color4.FromBytes(135, 198, 246);
                KartModelRenderer.DrawBox(pilPos.X, pilPos.Y + h * 0.48f, pilPos.Z, 1.55f, h * 0.48f, 1.55f, iceTop, iceBot);
            }

            if (track.Id == CourseId.MarioRaceway)
            {
                // Iconic Glossy Emerald-Green MK64 Warp Pipe Tunnel!
                Color4 pipeSide = Color4.FromBytes(26, 178, 52);
                Color4 pipeHi = Color4.FromBytes(72, 224, 88);
                Color4 pipeCrown = Color4.FromBytes(18, 132, 38);
                Gl.glDisable(Gl.GL_TEXTURE_2D);
                Gl.glBegin(Gl.GL_QUADS);
                Gl.Color(pipeSide);  Gl.Vertex(cl0); Gl.Vertex(cl1); Gl.Color(pipeHi);    Gl.Vertex(tl1); Gl.Vertex(tl0);
                Gl.Color(pipeSide);  Gl.Vertex(cr0); Gl.Vertex(cr1); Gl.Color(pipeHi);    Gl.Vertex(tr1); Gl.Vertex(tr0);
                Gl.Color(pipeHi);    Gl.Vertex(tl0); Gl.Vertex(tl1); Gl.Color(pipeCrown); Gl.Vertex(crown1); Gl.Vertex(crown0);
                Gl.Color(pipeCrown); Gl.Vertex(crown0); Gl.Vertex(crown1); Gl.Color(pipeHi); Gl.Vertex(tr1); Gl.Vertex(tr0);
                Gl.glEnd();
                return;
            }

            uint tTex = SelectCourseWallTexture(track, false);
            Gl.glEnable(Gl.GL_TEXTURE_2D);
            Gl.glBindTexture(Gl.GL_TEXTURE_2D, tTex);
            float u0 = (segIdx % 4) * 0.25f;
            float u1 = u0 + 0.25f;

            if (track.Id == CourseId.SherbetLand) Gl.glColor4f(0.68f, 0.86f, 1.0f, 1f);
            else Gl.glColor4f(0.88f, 0.88f, 0.90f, 1f);
            Gl.glBegin(Gl.GL_QUADS);
            Gl.glTexCoord2f(u0, 1f); Gl.Vertex(cl0); Gl.glTexCoord2f(u1, 1f); Gl.Vertex(cl1);
            Gl.glTexCoord2f(u1, 0f); Gl.Vertex(tl1); Gl.glTexCoord2f(u0, 0f); Gl.Vertex(tl0);

            Gl.glTexCoord2f(u0, 1f); Gl.Vertex(cr0); Gl.glTexCoord2f(u1, 1f); Gl.Vertex(cr1);
            Gl.glTexCoord2f(u1, 0f); Gl.Vertex(tr1); Gl.glTexCoord2f(u0, 0f); Gl.Vertex(tr0);

            if (track.Id == CourseId.SherbetLand) Gl.glColor4f(0.36f, 0.58f, 0.88f, 1f);
            else Gl.glColor4f(0.62f, 0.62f, 0.68f, 1f);
            Gl.glTexCoord2f(u0, 0f); Gl.Vertex(tl0); Gl.glTexCoord2f(u1, 0f); Gl.Vertex(tl1);
            Gl.glTexCoord2f(u1, 1f); Gl.Vertex(crown1); Gl.glTexCoord2f(u0, 1f); Gl.Vertex(crown0);

            Gl.glTexCoord2f(u0, 1f); Gl.Vertex(crown0); Gl.glTexCoord2f(u1, 1f); Gl.Vertex(crown1);
            Gl.glTexCoord2f(u1, 0f); Gl.Vertex(tr1); Gl.glTexCoord2f(u0, 0f); Gl.Vertex(tr0);
            Gl.glEnd();
            Gl.glDisable(Gl.GL_TEXTURE_2D);

            // Warm yellow tunnel ceiling lamps every 3 segments (except natural caves)!
            if (segIdx % 3 == 0 && track.Id != CourseId.SherbetLand && track.Id != CourseId.KoopaTroopaBeach)
            {
                KartModelRenderer.DrawBox(crown0.X, crown0.Y - 0.18f, crown0.Z, 1.1f, 0.14f, 0.45f,
                    Color4.FromBytes(255, 244, 158), Color4.FromBytes(255, 210, 68));
            }
        }

        private void BuildEdgeDetail(TrackData track, TrackSegment s0, TrackSegment s1, Vec3 e0, Vec3 e1, Vec3 out0, Vec3 out1, EdgeBehavior edge, int segIdx, bool isRightSide)
        {
            if (edge == EdgeBehavior.OffRoadShoulder)
            {
                float sw = 20.0f;
                float bankY = (track.Id == CourseId.WarioStadium || track.Id == CourseId.RoyalRaceway) ? 1.85f : 0.45f;
                Vec3 o0 = e0 + out0 * sw + new Vec3(0f, bankY, 0f);
                Vec3 o1 = e1 + out1 * sw + new Vec3(0f, bankY, 0f);

                Gl.glEnable(Gl.GL_TEXTURE_2D);
                Gl.glBindTexture(Gl.GL_TEXTURE_2D, ProceduralTextures.GetRoadTexture(s0.OffRoadSurface, false));
                Gl.glColor4f(1f, 1f, 1f, 1f);
                Gl.glBegin(Gl.GL_QUADS);
                Gl.glTexCoord2f(0f,   segIdx * 0.35f);       Gl.Vertex(e0 - new Vec3(0f, 0.08f, 0f));
                Gl.glTexCoord2f(2.4f, segIdx * 0.35f);       Gl.Vertex(o0);
                Gl.glTexCoord2f(2.4f, (segIdx + 1) * 0.35f); Gl.Vertex(o1);
                Gl.glTexCoord2f(0f,   (segIdx + 1) * 0.35f); Gl.Vertex(e1 - new Vec3(0f, 0.08f, 0f));
                Gl.glEnd();

                // Connect elevated shoulders smoothly down to the ground plane (rolling hills / dunes / beaches)!
                if (o0.Y > -0.2f || o1.Y > -0.2f)
                {
                    Vec3 b0 = new Vec3(o0.X + out0.X * 14f, -0.60f, o0.Z + out0.Z * 14f);
                    Vec3 b1 = new Vec3(o1.X + out1.X * 14f, -0.60f, o1.Z + out1.Z * 14f);
                    Gl.glColor4f(0.86f, 0.86f, 0.86f, 1f);
                    Gl.glBegin(Gl.GL_QUADS);
                    Gl.glTexCoord2f(0f,   segIdx * 0.35f);       Gl.Vertex(o0);
                    Gl.glTexCoord2f(2.0f, segIdx * 0.35f);       Gl.Vertex(b0);
                    Gl.glTexCoord2f(2.0f, (segIdx + 1) * 0.35f); Gl.Vertex(b1);
                    Gl.glTexCoord2f(0f,   (segIdx + 1) * 0.35f); Gl.Vertex(o1);
                    Gl.glEnd();
                }
                Gl.glDisable(Gl.GL_TEXTURE_2D);

                if (track.Id == CourseId.MooMooFarm)
                {
                    // Authentic Moo Moo Farm Crisp WHITE 2-Rail Ranch Fence close along the grass verge (characters--4.png!)
                    Vec3 f0 = e0 + out0 * 3.8f;
                    Vec3 f1 = e1 + out1 * 3.8f;
                    Color4 whiteFence = Color4.FromBytes(246, 248, 254);
                    Color4 shadeFence = Color4.FromBytes(205, 212, 224);
                    Gl.Color(whiteFence);
                    Gl.glBegin(Gl.GL_QUADS);
                    Gl.Vertex(f0 + new Vec3(0f, 0.45f, 0f)); Gl.Vertex(f1 + new Vec3(0f, 0.45f, 0f));
                    Gl.Vertex(f1 + new Vec3(0f, 0.72f, 0f)); Gl.Vertex(f0 + new Vec3(0f, 0.72f, 0f));
                    Gl.Vertex(f0 + new Vec3(0f, 1.12f, 0f)); Gl.Vertex(f1 + new Vec3(0f, 1.12f, 0f));
                    Gl.Vertex(f1 + new Vec3(0f, 1.40f, 0f)); Gl.Vertex(f0 + new Vec3(0f, 1.40f, 0f));
                    Gl.glEnd();
                    if (segIdx % 2 == 0)
                    {
                        KartModelRenderer.DrawBox(f0.X, f0.Y + 0.85f, f0.Z, 0.18f, 0.85f, 0.18f, whiteFence, shadeFence);
                    }
                }
                else if (track.Id == CourseId.LuigiRaceway)
                {
                    // Authentic Luigi Raceway Steep Brown Earth/Rock Retaining Cliff (lu-1.jpg!)
                    Gl.glEnable(Gl.GL_TEXTURE_2D);
                    Gl.glBindTexture(Gl.GL_TEXTURE_2D, ProceduralTextures.TexRockCliff);
                    Gl.glColor4f(1.0f, 0.88f, 0.74f, 1f);
                    float wh = 10.5f;
                    Vec3 top0 = o0 + out0 * 3.2f + new Vec3(0f, wh, 0f);
                    Vec3 top1 = o1 + out1 * 3.2f + new Vec3(0f, wh, 0f);
                    Gl.glBegin(Gl.GL_QUADS);
                    Gl.glTexCoord2f((segIdx % 4) * 0.25f, 2f);       Gl.Vertex(o0);
                    Gl.glTexCoord2f((segIdx % 4) * 0.25f + 0.25f, 2f); Gl.Vertex(o1);
                    Gl.glTexCoord2f((segIdx % 4) * 0.25f + 0.25f, 0f); Gl.Vertex(top1);
                    Gl.glTexCoord2f((segIdx % 4) * 0.25f, 0f);       Gl.Vertex(top0);
                    Gl.glEnd();
                    Gl.glDisable(Gl.GL_TEXTURE_2D);
                }
                else if (track.Id != CourseId.KoopaTroopaBeach && track.Id != CourseId.KalimariDesert && track.Id != CourseId.SherbetLand)
                {
                    // Textured N64 "MARIO STAR" + Red/Yellow Checkered Sponsor Barrier (lu-4.png!) or Scenic Retaining Wall!
                    uint wallTex = SelectCourseWallTexture(track, true);
                    float wh = (wallTex == ProceduralTextures.TexSponsorWall) ? 2.4f : 4.2f;
                    float u0 = (segIdx % 4) * 0.25f;
                    float u1 = u0 + 0.25f;
                    if (isRightSide) { float tU = u0; u0 = 1f - tU; u1 = u0 - 0.25f; }

                    Gl.glEnable(Gl.GL_TEXTURE_2D);
                    Gl.glBindTexture(Gl.GL_TEXTURE_2D, wallTex);
                    Gl.glColor4f(1f, 1f, 1f, 1f);
                    Gl.glBegin(Gl.GL_QUADS);
                    Gl.glTexCoord2f(u0, 1f); Gl.Vertex(o0);
                    Gl.glTexCoord2f(u1, 1f); Gl.Vertex(o1);
                    Gl.glTexCoord2f(u1, 0f); Gl.Vertex(o1 + new Vec3(0f, wh, 0f));
                    Gl.glTexCoord2f(u0, 0f); Gl.Vertex(o0 + new Vec3(0f, wh, 0f));
                    Gl.glEnd();
                    Gl.glDisable(Gl.GL_TEXTURE_2D);
                }
            }
            else if (edge == EdgeBehavior.Guardrail)
            {
                if (track.Id == CourseId.LuigiRaceway)
                {
                    // Authentic Luigi Raceway Royal-Blue & Lime-Green 2-Row Checkered Corner Bumper (lu-2.jpg!)
                    Gl.glEnable(Gl.GL_TEXTURE_2D);
                    Gl.glBindTexture(Gl.GL_TEXTURE_2D, ProceduralTextures.TexLuigiBarrier);
                    Gl.glColor4f(1f, 1f, 1f, 1f);
                    float u0 = (segIdx % 2) * 0.5f;
                    float u1 = u0 + 0.5f;
                    Gl.glBegin(Gl.GL_QUADS);
                    Gl.glTexCoord2f(u0, 1f); Gl.Vertex(e0);
                    Gl.glTexCoord2f(u1, 1f); Gl.Vertex(e1);
                    Gl.glTexCoord2f(u1, 0f); Gl.Vertex(e1 + new Vec3(0f, 1.95f, 0f));
                    Gl.glTexCoord2f(u0, 0f); Gl.Vertex(e0 + new Vec3(0f, 1.95f, 0f));
                    Gl.glEnd();
                    Gl.glDisable(Gl.GL_TEXTURE_2D);
                }
                else
                {
                    // Corrugated White Steel Highway W-Beam (characters--3.png!), Golden Neon Rail, or Wooden Pier Rail!
                    Color4 railCol = (track.Id == CourseId.RainbowRoad)
                        ? Color4.FromBytes(255, 228, 48)
                        : ((track.Id == CourseId.BansheeBoardwalk || track.Id == CourseId.YoshiValley)
                            ? Color4.FromBytes(148, 98, 52)
                            : Color4.FromBytes(244, 246, 252));
                    Gl.Color(railCol);
                    Gl.glBegin(Gl.GL_QUADS);
                    Gl.Vertex(e0 + new Vec3(0f, 0.52f, 0f)); Gl.Vertex(e1 + new Vec3(0f, 0.52f, 0f));
                    Gl.Vertex(e1 + new Vec3(0f, 0.82f, 0f)); Gl.Vertex(e0 + new Vec3(0f, 0.82f, 0f));
                    Gl.Vertex(e0 + new Vec3(0f, 0.94f, 0f)); Gl.Vertex(e1 + new Vec3(0f, 0.94f, 0f));
                    Gl.Vertex(e1 + new Vec3(0f, 1.24f, 0f)); Gl.Vertex(e0 + new Vec3(0f, 1.24f, 0f));
                    Gl.glEnd();
                    if (segIdx % 2 == 0)
                    {
                        KartModelRenderer.DrawBox(e0.X, e0.Y + 0.68f, e0.Z, 0.16f, 0.68f, 0.16f, railCol.ScaleRGB(0.85f), railCol.ScaleRGB(0.68f));
                    }
                }
            }
            else if (edge == EdgeBehavior.SolidWall && (s0.Flags & SegmentFlags.Tunnel) == 0)
            {
                bool isCanyon = (track.Id == CourseId.ChocoMountain || track.Id == CourseId.YoshiValley ||
                                 track.Id == CourseId.KoopaTroopaBeach || track.Id == CourseId.DKsJungleParkway ||
                                 track.Id == CourseId.KalimariDesert || track.Id == CourseId.LuigiRaceway);
                float wh = isCanyon ? 11.5f : ((track.Id == CourseId.ToadsTurnpike) ? 1.85f : 5.2f);
                Vec3 topOffset = isCanyon ? (out0 * 3.0f + new Vec3(0f, wh, 0f)) : new Vec3(0f, wh, 0f);
                Vec3 topOffset1 = isCanyon ? (out1 * 3.0f + new Vec3(0f, wh, 0f)) : new Vec3(0f, wh, 0f);

                uint wallTex = (track.Id == CourseId.MarioRaceway || track.Id == CourseId.WarioStadium)
                    ? ProceduralTextures.TexSponsorWall
                    : ((track.Id == CourseId.LuigiRaceway) ? ProceduralTextures.TexRockCliff : SelectCourseWallTexture(track, false));

                float u0 = (segIdx % 4) * 0.25f;
                float u1 = u0 + 0.25f;
                if (isRightSide) { float tU = u0; u0 = 1f - tU; u1 = u0 - 0.25f; }
                float vTop = 0f;
                float vBot = (wallTex == ProceduralTextures.TexSponsorWall) ? 1f : 2f;

                Gl.glEnable(Gl.GL_TEXTURE_2D);
                Gl.glBindTexture(Gl.GL_TEXTURE_2D, wallTex);
                if (track.Id == CourseId.LuigiRaceway) Gl.glColor4f(1.0f, 0.88f, 0.74f, 1f);
                else Gl.glColor4f(1f, 1f, 1f, 1f);
                Gl.glBegin(Gl.GL_QUADS);
                Gl.glTexCoord2f(u0, vBot); Gl.Vertex(e0);
                Gl.glTexCoord2f(u1, vBot); Gl.Vertex(e1);
                Gl.glTexCoord2f(u1, vTop); Gl.Vertex(e1 + topOffset1);
                Gl.glTexCoord2f(u0, vTop); Gl.Vertex(e0 + topOffset);
                Gl.glEnd();
                Gl.glDisable(Gl.GL_TEXTURE_2D);
            }
        }

        private void BuildRailroadTrackLoop(Vec3[] loop)
        {
            Gl.glDisable(Gl.GL_TEXTURE_2D);
            int n = loop.Length;
            for (int i = 0; i < n; i++)
            {
                Vec3 p0 = loop[i];
                Vec3 p1 = loop[(i + 1) % n];
                Vec3 fwd = (p1 - p0).NormalizedXZ();
                Vec3 r = new Vec3(fwd.Z, 0f, -fwd.X);

                Gl.Color(Color4.FromBytes(102, 82, 66));
                Gl.glBegin(Gl.GL_QUADS);
                Gl.Vertex(p0 - r * 2.5f); Gl.Vertex(p0 + r * 2.5f);
                Gl.Vertex(p1 + r * 2.5f); Gl.Vertex(p1 - r * 2.5f);
                Gl.glEnd();

                Gl.Color(Color4.FromBytes(198, 204, 214));
                Gl.glBegin(Gl.GL_QUADS);
                Gl.Vertex(p0 - r * 1.3f + new Vec3(0f, 0.08f, 0f)); Gl.Vertex(p0 - r * 1.0f + new Vec3(0f, 0.08f, 0f));
                Gl.Vertex(p1 - r * 1.0f + new Vec3(0f, 0.08f, 0f)); Gl.Vertex(p1 - r * 1.3f + new Vec3(0f, 0.08f, 0f));

                Gl.Vertex(p0 + r * 1.0f + new Vec3(0f, 0.08f, 0f)); Gl.Vertex(p0 + r * 1.3f + new Vec3(0f, 0.08f, 0f));
                Gl.Vertex(p1 + r * 1.3f + new Vec3(0f, 0.08f, 0f)); Gl.Vertex(p1 + r * 1.0f + new Vec3(0f, 0.08f, 0f));
                Gl.glEnd();
            }
        }

        private void BuildFinishBannerArch(TrackSegment startSeg, bool isRainbow)
        {
            Vec3 l = startSeg.Center - startSeg.Right * (startSeg.HalfWidth + 1.3f);
            Vec3 r = startSeg.Center + startSeg.Right * (startSeg.HalfWidth + 1.3f);
            Vec3 fwd = startSeg.Forward * 0.65f;

            Color4 pole = isRainbow ? Color4.FromBytes(255, 224, 52) : Color4.FromBytes(232, 236, 245);
            Gl.glDisable(Gl.GL_TEXTURE_2D);
            KartModelRenderer.DrawBox(l.X, l.Y + 5.2f, l.Z, 0.62f, 5.2f, 0.62f, pole, pole.ScaleRGB(0.78f));
            KartModelRenderer.DrawBox(r.X, r.Y + 5.2f, r.Z, 0.62f, 5.2f, 0.62f, pole, pole.ScaleRGB(0.78f));
            // Top steel crossbeam cap
            Gl.Color(pole.ScaleRGB(0.85f));
            Gl.glBegin(Gl.GL_QUADS);
            Gl.Vertex(l + new Vec3(0f, 10.5f, 0f) - fwd); Gl.Vertex(r + new Vec3(0f, 10.5f, 0f) - fwd);
            Gl.Vertex(r + new Vec3(0f, 10.5f, 0f) + fwd); Gl.Vertex(l + new Vec3(0f, 10.5f, 0f) + fwd);
            Gl.glEnd();

            // Double-sided Textured MARIO KART Start/Finish Banner!
            Gl.glEnable(Gl.GL_TEXTURE_2D);
            Gl.glBindTexture(Gl.GL_TEXTURE_2D, ProceduralTextures.TexStartBanner);
            Gl.glColor4f(1f, 1f, 1f, 1f);
            Gl.glBegin(Gl.GL_QUADS);
            // Front face (facing starting grid!)
            Gl.glTexCoord2f(0f, 1f); Gl.Vertex(l + new Vec3(0f, 7.4f, 0f) - fwd);
            Gl.glTexCoord2f(1f, 1f); Gl.Vertex(r + new Vec3(0f, 7.4f, 0f) - fwd);
            Gl.glTexCoord2f(1f, 0f); Gl.Vertex(r + new Vec3(0f, 10.4f, 0f) - fwd);
            Gl.glTexCoord2f(0f, 0f); Gl.Vertex(l + new Vec3(0f, 10.4f, 0f) - fwd);
            // Rear face
            Gl.glTexCoord2f(1f, 1f); Gl.Vertex(l + new Vec3(0f, 7.4f, 0f) + fwd);
            Gl.glTexCoord2f(0f, 1f); Gl.Vertex(r + new Vec3(0f, 7.4f, 0f) + fwd);
            Gl.glTexCoord2f(0f, 0f); Gl.Vertex(r + new Vec3(0f, 10.4f, 0f) + fwd);
            Gl.glTexCoord2f(1f, 0f); Gl.Vertex(l + new Vec3(0f, 10.4f, 0f) + fwd);
            Gl.glEnd();
            Gl.glDisable(Gl.GL_TEXTURE_2D);
        }

        private void BuildBattleArenaGeometry(TrackData track)
        {
            uint arenaTex = (track.Id == CourseId.BlockFort || track.Id == CourseId.DoubleDeck)
                ? ProceduralTextures.TexBrickWall
                : ProceduralTextures.TexCastleStone;

            for (int i = 0; i < track.ArenaPlatforms.Count; i++)
            {
                ArenaPlatform p = track.ArenaPlatforms[i];
                if (p.IsHazardFloor) continue;
                Vec3 c = (p.Min + p.Max) * 0.5f;
                Vec3 h = (p.Max - p.Min) * 0.5f;

                Gl.glEnable(Gl.GL_TEXTURE_2D);
                Gl.glBindTexture(Gl.GL_TEXTURE_2D, arenaTex);
                KartModelRenderer.DrawBox(c.X, c.Y, c.Z, h.X, h.Y, h.Z, p.Color, p.Color.ScaleRGB(0.82f));
                Gl.glDisable(Gl.GL_TEXTURE_2D);
            }

            for (int i = 0; i < track.ArenaRamps.Count; i++)
            {
                ArenaRamp r = track.ArenaRamps[i];
                Vec3 dir = (r.EndCenter - r.StartCenter);
                Vec3 right = new Vec3(dir.Z, 0f, -dir.X).Normalized() * r.HalfWidth;
                Gl.Color(r.Color);
                Gl.glBegin(Gl.GL_QUADS);
                Gl.Vertex(r.StartCenter - right);
                Gl.Vertex(r.StartCenter + right);
                Gl.Vertex(r.EndCenter + right);
                Gl.Vertex(r.EndCenter - right);
                Gl.glEnd();
            }
        }

        private bool IsBillboardProp(PropKind k)
        {
            return k == PropKind.TreeRound || k == PropKind.TreePine || k == PropKind.TreePalm ||
                   k == PropKind.Cactus || k == PropKind.MooMooCow || k == PropKind.GiantMushroom ||
                   k == PropKind.SnowMarioStatue;
        }

        private void RenderBillboardProps(TrackData track, Vec3 camEye, Vec3 camScreenRight, float time)
        {
            for (int i = 0; i < track.Props.Count; i++)
            {
                TrackProp p = track.Props[i];
                if (p.Kind == PropKind.HotAirBalloon)
                {
                    // Iconic Luigi Raceway Bobbing Striped 3D Hot-Air Balloon!
                    float bobY = p.Position.Y + (float)Math.Sin(time * 1.4f) * 2.2f;
                    Gl.glDisable(Gl.GL_TEXTURE_2D);
                    KartModelRenderer.DrawShadedEllipsoid(p.Position.X, bobY + 8.5f, p.Position.Z, 6.2f * p.Scale, 7.8f * p.Scale, 6.2f * p.Scale,
                        8, 14, Color4.FromBytes(58, 212, 72), Color4.FromBytes(248, 248, 252));
                    KartModelRenderer.DrawBox(p.Position.X, bobY, p.Position.Z, 1.3f * p.Scale, 1.0f * p.Scale, 1.3f * p.Scale,
                        Color4.FromBytes(148, 96, 48), Color4.FromBytes(112, 70, 34));
                    continue;
                }

                if (!IsBillboardProp(p.Kind)) continue;

                uint tex = 0;
                float bw = 6.5f * p.Scale;
                float bh = 7.2f * p.Scale;
                switch (p.Kind)
                {
                    case PropKind.TreeRound:       tex = SgiSpriteGenerator.TexTreeRound; bw = 7.8f * p.Scale; bh = 8.4f * p.Scale; break;
                    case PropKind.TreePine:        tex = SgiSpriteGenerator.TexTreePine;  bw = 7.5f * p.Scale; bh = 8.8f * p.Scale; break;
                    case PropKind.TreePalm:        tex = SgiSpriteGenerator.TexTreePalm;  bw = 8.8f * p.Scale; bh = 9.4f * p.Scale; break;
                    case PropKind.Cactus:          tex = SgiSpriteGenerator.TexCactus;    bw = 5.4f * p.Scale; bh = 6.8f * p.Scale; break;
                    case PropKind.MooMooCow:       tex = SgiSpriteGenerator.TexCow;       bw = 4.4f * p.Scale; bh = 4.2f * p.Scale; break;
                    case PropKind.GiantMushroom:   tex = SgiSpriteGenerator.TexGiantMushroom; bw = 11.5f * p.Scale; bh = 11.5f * p.Scale; break;
                    case PropKind.SnowMarioStatue: tex = SgiSpriteGenerator.TexSnowman;   bw = 8.5f * p.Scale; bh = 9.5f * p.Scale; break;
                }
                KartModelRenderer.DrawBillboard(p.Position - new Vec3(0f, bh * 0.12f, 0f), bw, bh, tex, camScreenRight, new Color4(1f, 1f, 1f, 1f));
            }
        }

        private void RenderStaticLandmarkGeometry(TrackProp p)
        {
            if (IsBillboardProp(p.Kind) || p.Kind == PropKind.HotAirBalloon) return;

            Gl.glPushMatrix();
            Gl.glTranslatef(p.Position.X, p.Position.Y, p.Position.Z);
            Gl.glRotatef(p.YawRad * MathUtil.RAD2DEG, 0f, 1f, 0f);
            Gl.glScalef(p.Scale, p.Scale, p.Scale);

            switch (p.Kind)
            {
                case PropKind.RedBarn:
                    KartModelRenderer.DrawBox(0f, 4.2f, 0f, 6.0f, 4.2f, 7.5f, p.Tint, p.Tint.ScaleRGB(0.82f));
                    KartModelRenderer.DrawBox(0f, 9.6f, 0f, 4.4f, 1.6f, 7.8f, Color4.FromBytes(245, 245, 248), p.Tint);
                    // Silo next to Barn!
                    KartModelRenderer.DrawShadedEllipsoid(7.8f, 5.5f, -2.0f, 2.2f, 5.5f, 2.2f, 6, 10, Color4.FromBytes(235, 238, 244), Color4.FromBytes(175, 182, 195));
                    break;

                case PropKind.LuigiJumbotron:
                    KartModelRenderer.DrawBox(-7.5f, 6.5f, 0f, 0.65f, 6.5f, 0.65f, Color4.FromBytes(195, 202, 212), Color4.FromBytes(145, 152, 165));
                    KartModelRenderer.DrawBox( 7.5f, 6.5f, 0f, 0.65f, 6.5f, 0.65f, Color4.FromBytes(195, 202, 212), Color4.FromBytes(145, 152, 165));
                    KartModelRenderer.DrawBox( 0.0f, 13.5f, 0f, 8.8f, 3.2f, 0.75f, Color4.FromBytes(32, 38, 52), p.Tint);
                    break;

                case PropKind.KoopaRock:
                    KartModelRenderer.DrawShadedEllipsoid(0f, 9.5f, 0f, 13f, 10.5f, 15f, 7, 12, Color4.FromBytes(62, 182, 68), p.Tint.ScaleRGB(0.78f));
                    break;

                case PropKind.WarpPipeArch:
                    KartModelRenderer.DrawBox(-9.5f, 4.8f, 0f, 1.3f, 4.8f, 1.3f, p.Tint, p.Tint.ScaleRGB(0.8f));
                    KartModelRenderer.DrawBox( 9.5f, 4.8f, 0f, 1.3f, 4.8f, 1.3f, p.Tint, p.Tint.ScaleRGB(0.8f));
                    KartModelRenderer.DrawBox( 0.0f, 9.8f, 0f, 11.0f, 1.2f, 1.5f, p.Tint, p.Tint.ScaleRGB(0.85f));
                    break;

                case PropKind.PeachCastle:
                    {
                        Color4 wall = Color4.FromBytes(250, 242, 232);
                        Color4 roof = Color4.FromBytes(236, 52, 92);
                        KartModelRenderer.DrawBox(0f, 6.5f, 0f, 12.0f, 6.5f, 9.5f, wall, wall.ScaleRGB(0.92f));
                        KartModelRenderer.DrawBox(0f, 16.0f, 0f, 4.8f, 6.0f, 4.8f, wall, wall);
                        KartModelRenderer.DrawShadedEllipsoid(0f, 24.0f, 0f, 5.4f, 4.2f, 5.4f, 5, 10, roof, roof.ScaleRGB(0.78f));
                        KartModelRenderer.DrawBox(-10.5f, 9.0f, 7.0f, 2.6f, 9.0f, 2.6f, wall, wall.ScaleRGB(0.9f));
                        KartModelRenderer.DrawBox( 10.5f, 9.0f, 7.0f, 2.6f, 9.0f, 2.6f, wall, wall.ScaleRGB(0.9f));
                        KartModelRenderer.DrawShadedEllipsoid(-10.5f, 19.8f, 7.0f, 3.2f, 3.0f, 3.2f, 5, 8, roof, roof.ScaleRGB(0.78f));
                        KartModelRenderer.DrawShadedEllipsoid( 10.5f, 19.8f, 7.0f, 3.2f, 3.0f, 3.2f, 5, 8, roof, roof.ScaleRGB(0.78f));
                        // Peach stained-glass window emblem!
                        KartModelRenderer.DrawBox(0f, 15.5f, 4.9f, 1.8f, 2.6f, 0.2f, Color4.FromBytes(255, 152, 212), Color4.FromBytes(95, 195, 255));
                    }
                    break;

                case PropKind.BowserStatue:
                    KartModelRenderer.DrawBox(0f, 4.5f, 0f, 3.8f, 4.5f, 3.8f, p.Tint, p.Tint.ScaleRGB(0.72f));
                    KartModelRenderer.DrawShadedEllipsoid(0f, 10.2f, 1.2f, 2.8f, 2.4f, 3.2f, 5, 8, p.Tint, Color4.FromBytes(255, 95, 22));
                    KartModelRenderer.DrawShadedEllipsoid(0f, 9.6f, 4.5f, 1.2f, 0.9f, 2.4f, 4, 6, Color4.FromBytes(255, 238, 65), Color4.FromBytes(255, 68, 18));
                    break;

                case PropKind.HauntedHouse:
                    KartModelRenderer.DrawBox(0f, 9.5f, 0f, 10.0f, 3.2f, 3.6f, p.Tint, p.Tint.ScaleRGB(0.7f));
                    KartModelRenderer.DrawBox(0f, 14.0f, 0f, 6.5f, 2.5f, 3.6f, Color4.FromBytes(42, 32, 58), p.Tint);
                    break;

                case PropKind.NeonConstellation:
                    KartModelRenderer.DrawShadedEllipsoid(0f, 0f, 0f, 4.8f, 4.8f, 0.6f, 6, 10, new Color4(1f, 1f, 1f, 1f), p.Tint);
                    break;

                case PropKind.Grandstand:
                    // Tiered Spectator Bleachers + White Canopy + Giant 3D Mario/Luigi Cap on Roof (matches lu-4.png!)
                    KartModelRenderer.DrawBox(0f, 3.2f, 0f, 5.4f, 3.2f, 14.0f, Color4.FromBytes(48, 52, 68), Color4.FromBytes(28, 32, 44));
                    KartModelRenderer.DrawBox(0f, 7.6f, 0f, 5.8f, 0.55f, 14.6f, Color4.FromBytes(245, 248, 255), Color4.FromBytes(210, 218, 232));
                    // Giant 3D Mario/Luigi Cap Dome + Visor + White Emblem Circle!
                    KartModelRenderer.DrawShadedEllipsoid(0f, 10.6f, 0f, 5.6f, 3.4f, 6.4f, 6, 12, p.Tint, p.Tint.ScaleRGB(0.76f));
                    KartModelRenderer.DrawShadedEllipsoid(-3.8f, 8.8f, 0f, 3.4f, 0.85f, 4.8f, 5, 10, p.Tint.ScaleRGB(0.88f), p.Tint.ScaleRGB(0.68f));
                    KartModelRenderer.DrawShadedEllipsoid(-4.8f, 10.6f, 0f, 0.65f, 1.45f, 1.65f, 5, 8, Color4.FromBytes(252, 252, 255), Color4.FromBytes(232, 236, 245));
                    break;

                case PropKind.StreetLight:
                    KartModelRenderer.DrawBox(0f, 4.4f, 0f, 0.22f, 4.4f, 0.22f, Color4.FromBytes(130, 136, 148), Color4.FromBytes(95, 100, 112));
                    KartModelRenderer.DrawBox(1.1f, 8.6f, 0f, 1.2f, 0.28f, 0.42f, p.Tint, p.Tint);
                    break;

                case PropKind.RailCrossingGate:
                    KartModelRenderer.DrawBox(0f, 2.6f, 0f, 0.30f, 2.6f, 0.30f, Color4.FromBytes(238, 238, 242), Color4.FromBytes(180, 180, 185));
                    KartModelRenderer.DrawBox(0f, 4.5f, 0f, 0.95f, 0.45f, 0.45f, p.Tint, p.Tint);
                    break;

                case PropKind.TorchPillar:
                    KartModelRenderer.DrawBox(0f, 2.2f, 0f, 0.48f, 2.2f, 0.48f, Color4.FromBytes(98, 90, 84), Color4.FromBytes(75, 70, 65));
                    KartModelRenderer.DrawShadedEllipsoid(0f, 4.8f, 0f, 0.65f, 0.95f, 0.65f, 4, 6, Color4.FromBytes(255, 245, 85), p.Tint);
                    break;
            }
            Gl.glPopMatrix();
        }

        private void RenderItemBoxes(TrackData track, float time)
        {
            Gl.glDisable(Gl.GL_TEXTURE_2D);
            Gl.glEnable(Gl.GL_BLEND);
            Gl.glBlendFunc(Gl.GL_SRC_ALPHA, Gl.GL_ONE_MINUS_SRC_ALPHA);

            for (int i = 0; i < track.ItemBoxes.Count; i++)
            {
                ItemBoxSpawn b = track.ItemBoxes[i];
                if (!b.Active) continue;

                float bob = (float)Math.Sin(time * 3.8f + i) * 0.26f;
                Gl.glPushMatrix();
                Gl.glTranslatef(b.Position.X, b.Position.Y + bob, b.Position.Z);
                Gl.glRotatef(time * 95f + i * 25f, 0f, 1f, 0f);
                Gl.glRotatef(35f, 1f, 0f, 1f);

                // Authentic N64 Multi-Colored Rainbow Crystal Octahedron + Bright White '?' Core (characters--2.png & characters--4.png!)
                float r = 1.15f;
                Color4 cTop = Color4.Rainbow(time * 4.5f + i * 0.9f).WithAlpha(0.78f);
                Color4 cBot = Color4.Rainbow(time * 4.5f + i * 0.9f + 3.1f).WithAlpha(0.78f);
                Color4 c0   = Color4.Rainbow(time * 4.5f + i * 0.9f + 0.8f).WithAlpha(0.78f);
                Color4 c1   = Color4.Rainbow(time * 4.5f + i * 0.9f + 2.1f).WithAlpha(0.78f);
                Color4 c2   = Color4.Rainbow(time * 4.5f + i * 0.9f + 3.8f).WithAlpha(0.78f);
                Color4 c3   = Color4.Rainbow(time * 4.5f + i * 0.9f + 5.1f).WithAlpha(0.78f);

                KartModelRenderer.DrawBox(0f, 0.18f, 0f, 0.24f, 0.34f, 0.24f, new Color4(1f, 1f, 1f, 0.98f), new Color4(1f, 0.98f, 0.55f, 0.98f));
                KartModelRenderer.DrawBox(0f, -0.34f, 0f, 0.16f, 0.12f, 0.16f, new Color4(1f, 1f, 1f, 0.98f), new Color4(1f, 1f, 1f, 0.98f));

                Gl.glBegin(Gl.GL_TRIANGLES);
                Gl.Color(cTop); Gl.glVertex3f(0f, r, 0f); Gl.Color(c0); Gl.glVertex3f(r, 0f, 0f);  Gl.Color(c1); Gl.glVertex3f(0f, 0f, r);
                Gl.Color(cTop); Gl.glVertex3f(0f, r, 0f); Gl.Color(c1); Gl.glVertex3f(0f, 0f, r);  Gl.Color(c2); Gl.glVertex3f(-r, 0f, 0f);
                Gl.Color(cTop); Gl.glVertex3f(0f, r, 0f); Gl.Color(c2); Gl.glVertex3f(-r, 0f, 0f); Gl.Color(c3); Gl.glVertex3f(0f, 0f, -r);
                Gl.Color(cTop); Gl.glVertex3f(0f, r, 0f); Gl.Color(c3); Gl.glVertex3f(0f, 0f, -r); Gl.Color(c0); Gl.glVertex3f(r, 0f, 0f);

                Gl.Color(cBot); Gl.glVertex3f(0f, -r, 0f); Gl.Color(c1); Gl.glVertex3f(0f, 0f, r);  Gl.Color(c0); Gl.glVertex3f(r, 0f, 0f);
                Gl.Color(cBot); Gl.glVertex3f(0f, -r, 0f); Gl.Color(c2); Gl.glVertex3f(-r, 0f, 0f); Gl.Color(c1); Gl.glVertex3f(0f, 0f, r);
                Gl.Color(cBot); Gl.glVertex3f(0f, -r, 0f); Gl.Color(c3); Gl.glVertex3f(0f, 0f, -r); Gl.Color(c2); Gl.glVertex3f(-r, 0f, 0f);
                Gl.Color(cBot); Gl.glVertex3f(0f, -r, 0f); Gl.Color(c0); Gl.glVertex3f(r, 0f, 0f);  Gl.Color(c3); Gl.glVertex3f(0f, 0f, -r);
                Gl.glEnd();
                Gl.glPopMatrix();
            }
        }

        private void RenderCourseHazards(List<CourseHazard> hazards, Vec3 camScreenRight, float time)
        {
            for (int i = 0; i < hazards.Count; i++)
            {
                CourseHazard h = hazards[i];

                // SGI Sprite Hazards!
                if (h.Spec.Kind == HazardKind.SnowmanMine)
                {
                    KartModelRenderer.DrawBillboard(h.Position - new Vec3(0f, 0.35f, 0f), 4.0f, 4.4f, SgiSpriteGenerator.TexSnowman, camScreenRight, new Color4(1f, 1f, 1f, 1f));
                    continue;
                }
                if (h.Spec.Kind == HazardKind.SlidingPenguin)
                {
                    KartModelRenderer.DrawBillboard(h.Position - new Vec3(0f, 0.30f, 0f), 4.6f, 5.0f, SgiSpriteGenerator.TexPenguin, camScreenRight, new Color4(1f, 1f, 1f, 1f));
                    continue;
                }
                if (h.Spec.Kind == HazardKind.MontyMole)
                {
                    if (h.ActiveCollider)
                        KartModelRenderer.DrawBillboard(h.Position - new Vec3(0f, 0.22f, 0f), 2.7f, 2.7f, SgiSpriteGenerator.TexMontyMole, camScreenRight, new Color4(1f, 1f, 1f, 1f));
                    continue;
                }
                if (h.Spec.Kind == HazardKind.StompingThwomp)
                {
                    KartModelRenderer.DrawBillboard(h.Position - new Vec3(0f, 0.35f, 0f), 5.2f, 5.4f, SgiSpriteGenerator.TexThwomp, camScreenRight, new Color4(1f, 1f, 1f, 1f));
                    continue;
                }
                if (h.Spec.Kind == HazardKind.GiantYoshiEgg)
                {
                    KartModelRenderer.DrawBillboard(h.Position - new Vec3(0f, 0.45f, 0f), 6.2f, 6.8f, SgiSpriteGenerator.TexYoshiEgg, camScreenRight, new Color4(1f, 1f, 1f, 1f));
                    continue;
                }
                if (h.Spec.Kind == HazardKind.ChainChomp)
                {
                    KartModelRenderer.DrawBillboard(h.Position - new Vec3(0f, 0.35f, 0f), 4.8f, 4.8f, SgiSpriteGenerator.TexChainChomp, camScreenRight, new Color4(1f, 1f, 1f, 1f));
                    continue;
                }

                // 3D Vehicle / Dynamic Hazards (Steam Train, Highway Traffic, Falling Boulders)
                Gl.glDisable(Gl.GL_TEXTURE_2D);
                Gl.glPushMatrix();
                Gl.glTranslatef(h.Position.X, h.Position.Y, h.Position.Z);
                Gl.glRotatef(h.Yaw * MathUtil.RAD2DEG, 0f, 1f, 0f);

                switch (h.Spec.Kind)
                {
                    case HazardKind.KalimariTrain:
                        if (h.Spec.PatrolRadius < 0.5f)
                        {
                            // Classic MK64 Western Steam Locomotive!
                            KartModelRenderer.DrawBox(0f, 1.4f, 0f, 2.2f, 0.8f, 4.8f, Color4.FromBytes(198, 36, 34), Color4.FromBytes(165, 28, 28));
                            KartModelRenderer.DrawShadedEllipsoid(0f, 2.8f, 0.8f, 1.8f, 1.6f, 3.4f, 6, 10, Color4.FromBytes(48, 52, 60), Color4.FromBytes(26, 28, 34));
                            KartModelRenderer.DrawBox(0f, 3.6f, -2.4f, 2.3f, 1.6f, 1.8f, Color4.FromBytes(218, 42, 38), Color4.FromBytes(182, 32, 30));
                            KartModelRenderer.DrawBox(0f, 4.9f, 2.8f, 0.65f, 1.3f, 0.65f, Color4.FromBytes(238, 192, 38), Color4.FromBytes(45, 45, 52));
                        }
                        else
                        {
                            KartModelRenderer.DrawBox(0f, 2.4f, 0f, 2.15f, 2.0f, 4.2f, Color4.FromBytes(175, 54, 42), Color4.FromBytes(142, 42, 34));
                            KartModelRenderer.DrawBox(0f, 2.9f, 0f, 2.22f, 0.55f, 3.4f, Color4.FromBytes(255, 232, 142), Color4.FromBytes(245, 212, 112));
                        }
                        break;

                    case HazardKind.HighwayTruck:
                        // Iconic Toad's Turnpike Cyan/Yellow Tanker & Cargo Truck (matches characters--3.png!)
                        KartModelRenderer.DrawBox(0f, 1.35f, -0.8f, 2.25f, 0.55f, 4.6f, Color4.FromBytes(215, 224, 236), Color4.FromBytes(148, 158, 172));
                        KartModelRenderer.DrawShadedEllipsoid(0f, 2.75f, -1.1f, 2.15f, 1.55f, 4.2f, 6, 12, Color4.FromBytes(58, 224, 245), Color4.FromBytes(32, 168, 212));
                        KartModelRenderer.DrawBox(0f, 2.70f, -1.1f, 2.22f, 0.28f, 4.0f, Color4.FromBytes(252, 226, 42), Color4.FromBytes(236, 184, 24));
                        KartModelRenderer.DrawBox(0f, 1.95f,  4.4f, 2.05f, 1.60f, 1.4f, Color4.FromBytes(244, 248, 255), Color4.FromBytes(188, 198, 218));
                        KartModelRenderer.DrawBox(-1.4f, 1.1f, 5.85f, 0.35f, 0.25f, 0.1f, Color4.FromBytes(255, 250, 185), Color4.FromBytes(255, 250, 185));
                        KartModelRenderer.DrawBox( 1.4f, 1.1f, 5.85f, 0.35f, 0.25f, 0.1f, Color4.FromBytes(255, 250, 185), Color4.FromBytes(255, 250, 185));
                        break;

                    case HazardKind.HighwayBus:
                        KartModelRenderer.DrawBox(0f, 2.2f, 0f, 2.1f, 1.9f, 5.0f, Color4.FromBytes(252, 196, 36), Color4.FromBytes(226, 164, 24));
                        KartModelRenderer.DrawBox(0f, 2.7f, 0.4f, 2.16f, 0.55f, 4.1f, Color4.FromBytes(178, 228, 255), Color4.FromBytes(145, 198, 238));
                        break;

                    case HazardKind.HighwayCar:
                        KartModelRenderer.DrawBox(0f, 0.9f, 0f, 1.6f, 0.7f, 2.6f, Color4.FromBytes(235, 48, 56), Color4.FromBytes(198, 36, 42));
                        KartModelRenderer.DrawBox(0f, 1.6f, -0.2f, 1.35f, 0.55f, 1.4f, Color4.FromBytes(178, 228, 255), Color4.FromBytes(145, 198, 238));
                        break;

                    case HazardKind.MontyMole:
                        if (h.ActiveCollider)
                            KartModelRenderer.DrawShadedEllipsoid(0f, 0.75f, 0f, 0.95f, 0.95f, 0.95f, 5, 8, Color4.FromBytes(162, 102, 48), Color4.FromBytes(118, 70, 32));
                        break;

                    case HazardKind.FallingBoulder:
                        KartModelRenderer.DrawShadedEllipsoid(0f, 0f, 0f, 2.05f, 2.05f, 2.05f, 6, 10, Color4.FromBytes(148, 102, 62), Color4.FromBytes(92, 60, 36));
                        break;

                    case HazardKind.SwoopingBat:
                        KartModelRenderer.DrawBox(0f, 0f, 0f, 1.4f, 0.32f, 0.52f, Color4.FromBytes(138, 56, 198), Color4.FromBytes(88, 32, 138));
                        break;

                    case HazardKind.LeapingCheepCheep:
                        KartModelRenderer.DrawShadedEllipsoid(0f, 0f, 0f, 1.5f, 1.4f, 1.9f, 5, 8, Color4.FromBytes(248, 68, 58), Color4.FromBytes(252, 246, 236));
                        break;
                }

                Gl.glPopMatrix();
            }
        }

        private void RenderWorldItems(List<WorldItemEntity> items, Vec3 camScreenRight, float time)
        {
            for (int i = 0; i < items.Count; i++)
            {
                WorldItemEntity it = items[i];
                uint tex = SgiSpriteGenerator.ItemTextures[(int)ItemId.Banana];
                float sz = 1.45f;
                switch (it.Kind)
                {
                    case WorldItemKind.Banana:         tex = SgiSpriteGenerator.ItemTextures[(int)ItemId.Banana]; sz = 1.45f; break;
                    case WorldItemKind.FakeItemBox:    tex = SgiSpriteGenerator.ItemTextures[(int)ItemId.FakeItemBox]; sz = 1.95f; break;
                    case WorldItemKind.GreenShell:     tex = SgiSpriteGenerator.ItemTextures[(int)ItemId.GreenShell]; sz = 1.55f; break;
                    case WorldItemKind.RedShell:       tex = SgiSpriteGenerator.ItemTextures[(int)ItemId.RedShell]; sz = 1.55f; break;
                    case WorldItemKind.SpinyBlueShell: tex = SgiSpriteGenerator.ItemTextures[(int)ItemId.SpinyBlueShell]; sz = 1.75f; break;
                }
                KartModelRenderer.DrawBillboard(it.Position - new Vec3(0f, sz * 0.16f, 0f), sz, sz, tex, camScreenRight, new Color4(1f, 1f, 1f, 1f));
            }
        }

        private void RenderSnowfall(Vec3 eye, float time)
        {
            Gl.glDisable(Gl.GL_TEXTURE_2D);
            Gl.glPointSize(3.0f);
            Gl.Color(new Color4(1f, 1f, 1f, 0.85f));
            Gl.glBegin(Gl.GL_POINTS);
            for (int i = 0; i < 90; i++)
            {
                float ox = ((i * 17.3f + time * 3.0f) % 60f) - 30f;
                float oz = ((i * 29.7f) % 60f) - 30f;
                float oy = 18f - ((i * 7.1f + time * 9.5f) % 20f);
                Gl.glVertex3f(eye.X + ox, eye.Y + oy, eye.Z + oz);
            }
            Gl.glEnd();
        }

        public void Dispose()
        {
            InvalidateDisplayList();
        }
    }
}
