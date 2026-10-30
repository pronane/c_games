using System;
using MarioKart64.Core;
using MarioKart64.Entities;
using MarioKart64.Rendering;
using MarioKart64.Tracks;

namespace MarioKart64.Game
{
    public static class HudRenderer
    {
        public static void RenderPlayerHud(
            int vx, int vy, int vw, int vh,
            Kart player,
            Kart[] allKarts,
            TrackData track,
            GameMode mode,
            float raceTime,
            float countdownTimer,
            bool raceStarted,
            float globalTime,
            bool compactSplitScreen)
        {
            Gl.glViewport(vx, vy, vw, vh);
            Gl.glDisable(Gl.GL_DEPTH_TEST);
            Gl.glDisable(Gl.GL_FOG);

            float virtW = 960f;
            float virtH = 540f;

            Gl.glMatrixMode(Gl.GL_PROJECTION);
            Gl.glLoadIdentity();
            Gl.glOrtho(0, virtW, virtH, 0, -1, 1);
            Gl.glMatrixMode(Gl.GL_MODELVIEW);
            Gl.glLoadIdentity();

            Color4 goldTop   = Color4.FromBytes(255, 238, 52);
            Color4 orangeBot = Color4.FromBytes(236, 98, 16);
            Color4 limeTop   = Color4.FromBytes(198, 255, 52);
            Color4 limeBot   = Color4.FromBytes(58, 208, 36);
            Color4 pinkTop   = Color4.FromBytes(250, 208, 255);
            Color4 pinkBot   = Color4.FromBytes(208, 86, 238);
            Color4 whiteTop  = new Color4(1f, 1f, 1f, 1f);
            Color4 silverBot = Color4.FromBytes(188, 204, 228);

            // 1. Authentic MK64 Top-Center Black Item Box with Crisp Silver-White Bevel Border!
            ItemId shownItem = (player.RouletteTimer > 0f) ? player.RouletteDisplayItem : player.HeldItem;
            if (shownItem == ItemId.None && player.OrbitItemCount > 0)
            {
                shownItem = player.ActiveOrbitType;
            }

            if (shownItem != ItemId.None || player.RouletteTimer > 0f)
            {
                float boxW = compactSplitScreen ? 62f : 72f;
                float boxH = compactSplitScreen ? 56f : 64f;
                float boxX = (virtW - boxW) * 0.5f;
                float boxY = 12f;

                ProceduralTextures.DrawSolidRect2D(boxX - 2f, boxY - 2f, boxW + 4f, boxH + 4f, new Color4(0.18f, 0.20f, 0.25f, 0.92f));
                ProceduralTextures.DrawSolidRect2D(boxX, boxY, boxW, boxH, new Color4(0.02f, 0.02f, 0.04f, 0.94f));
                Color4 borderCol = (player.RouletteTimer > 0f) ? Color4.Rainbow(globalTime * 11f) : new Color4(0.94f, 0.96f, 1.0f, 0.95f);
                ProceduralTextures.DrawRectOutline2D(boxX, boxY, boxW, boxH, 2.5f, borderCol);

                if (shownItem != ItemId.None)
                {
                    uint itemTex = SgiSpriteGenerator.ItemTextures[(int)shownItem];
                    if (itemTex != 0)
                    {
                        ProceduralTextures.DrawSprite2D(itemTex, boxX + 6f, boxY + 3f, boxW - 12f, boxH - 6f, whiteTop);
                    }

                    if (player.OrbitItemCount > 0)
                    {
                        ProceduralTextures.DrawText2D("x" + player.OrbitItemCount, boxX + boxW - 24f, boxY + boxH - 21f, 17f, whiteTop, goldTop, false);
                    }
                    else if (shownItem == ItemId.TripleMushrooms && player.RemainingSubUses > 0)
                    {
                        ProceduralTextures.DrawText2D("x" + player.RemainingSubUses, boxX + boxW - 24f, boxY + boxH - 21f, 17f, whiteTop, goldTop, false);
                    }
                }
            }

            // 2. Top-Left MK64 Close-Up Driver Portrait Column + Lavender/Pink LAP 1/3!
            if (track.IsBattleArena)
            {
                ProceduralTextures.DrawText2D("BALLOONS", 24f, 16f, 21f, goldTop, orangeBot, false);
                for (int b = 0; b < player.Balloons; b++)
                {
                    ProceduralTextures.DrawSolidRect2D(26f + b * 26f, 44f, 18f, 20f, player.Character.PrimaryColor);
                    ProceduralTextures.DrawRectOutline2D(26f + b * 26f, 44f, 18f, 20f, 1.5f, whiteTop);
                }
            }
            else
            {
                bool showTower = (!compactSplitScreen && mode != GameMode.TimeTrials && !track.HideRankingsQuestionMark && allKarts != null);
                float lapX = showTower ? 96f : 26f;

                ProceduralTextures.DrawText2D("LAP", lapX, 22f, compactSplitScreen ? 18f : 20f, whiteTop, pinkTop, false);
                string lapNums = string.Format("{0}/{1}", MathUtil.ClampInt(player.Lap, 1, track.LapCount), track.LapCount);
                ProceduralTextures.DrawText2D(lapNums, lapX + 54f, 15f, compactSplitScreen ? 24f : 29f, pinkTop, pinkBot, false);

                if (player.Lap == track.LapCount && !player.FinishedRace && raceStarted)
                {
                    if ((((int)(globalTime * 5f)) & 1) == 0)
                        ProceduralTextures.DrawText2D("FINAL LAP!", lapX, 50f, 18f, Color4.FromBytes(255, 85, 85), goldTop, false);
                }

                // Authentic MK64 Top-4 Close-Up 3/4-Right Headshot Portraits on Dark Charcoal Background!
                if (showTower)
                {
                    for (int rank = 1; rank <= 4; rank++)
                    {
                        Kart rk = null;
                        for (int i = 0; i < allKarts.Length; i++)
                        {
                            if (allKarts[i].RaceRank == rank) { rk = allKarts[i]; break; }
                        }
                        if (rk == null) continue;

                        float px = 22f;
                        float py = 34f + (rank - 1) * 58f;
                        float pw = 56f;
                        float ph = 52f;
                        bool isMe = (rk == player);

                        // Dark N64 portrait background + close-up SGI character headshot!
                        ProceduralTextures.DrawSolidRect2D(px, py, pw, ph, new Color4(0.07f, 0.08f, 0.11f, 0.92f));
                        uint port = SgiSpriteGenerator.PortraitTextures[((int)rk.Character.Id) & 7];
                        if (port != 0)
                        {
                            ProceduralTextures.DrawSprite2D(port, px + 3f, py + 2f, pw - 6f, ph - 4f, whiteTop);
                        }

                        Color4 border = rk.Character.PrimaryColor;
                        if (rk.Character.Id == CharacterId.Wario) border = Color4.FromBytes(165, 58, 220);
                        else if (rk.Character.Id == CharacterId.Toad) border = Color4.FromBytes(48, 108, 248);

                        ProceduralTextures.DrawRectOutline2D(px, py, pw, ph, 3.0f, border);
                        if (isMe && (((int)(globalTime * 8f)) & 1) == 0)
                        {
                            ProceduralTextures.DrawRectOutline2D(px - 2f, py - 2f, pw + 4f, ph + 4f, 1.8f, goldTop);
                        }

                        // Bold white-on-black rank digit in bottom-left corner of portrait box!
                        ProceduralTextures.DrawText2D(rank.ToString(), px + 4f, py + ph - 22f, 20f, whiteTop, silverBot, false);
                    }
                }
            }

            // 3. Top-Right MK64 Lime "TIME" + Golden-Orange Race Digits ("00'27\"09")!
            if (!compactSplitScreen)
            {
                ProceduralTextures.DrawText2D("TIME", virtW - 278f, 16f, 25f, limeTop, limeBot, false);
                ProceduralTextures.DrawText2D(GameConfig.FormatRaceTime(raceTime), virtW - 196f, 16f, 25f, goldTop, orangeBot, false);
                if (mode == GameMode.TimeTrials && (int)track.Id < 16)
                {
                    string rec = "BEST " + GameConfig.FormatRaceTime(GameConfig.Instance.BestCourseSeconds[(int)track.Id]);
                    ProceduralTextures.DrawText2D(rec, virtW - 268f, 45f, 18f, whiteTop, silverBot, false);
                }
            }

            // 4. Bottom-Left Giant Golden-Orange MK64 Rank Numeral ("1st" .. "8th" or "?" on Yoshi Valley)!
            if (!track.IsBattleArena && mode != GameMode.TimeTrials)
            {
                if (track.HideRankingsQuestionMark && !player.FinishedRace)
                {
                    ProceduralTextures.DrawText2D("?", 34f, virtH - 88f, compactSplitScreen ? 46f : 62f, goldTop, orangeBot, false);
                }
                else
                {
                    string numPart = player.RaceRank.ToString();
                    string sufPart = OrdinalSuffix(player.RaceRank);
                    float szBig = compactSplitScreen ? 46f : 62f;
                    float szSuf = compactSplitScreen ? 26f : 34f;
                    ProceduralTextures.DrawText2D(numPart, 30f, virtH - 88f, szBig, goldTop, orangeBot, false);
                    ProceduralTextures.DrawText2D(sufPart, 30f + szBig * 0.62f, virtH - 64f, szSuf, goldTop, orangeBot, false);
                }
            }

            // 5. Bottom-Right MK64 Curved Analog Speedometer (lu-1.jpg!) + Floating Ribbon Minimap (lu-2.jpg!)
            float kmh = Math.Abs(player.ForwardSpeed * 1.95f);
            if (GameConfig.Instance.ShowMinimap && !compactSplitScreen && !track.IsBattleArena && track.Segments != null)
            {
                RenderCourseMinimap(virtW - 156f, virtH - 188f, 134f, 148f, track, allKarts, player);
            }

            if (GameConfig.Instance.ShowSpeedometer && !compactSplitScreen)
            {
                float spX = GameConfig.Instance.ShowMinimap ? (virtW - 268f) : (virtW - 122f);
                float spY = virtH - 76f;
                RenderAnalogSpeedometer(spX, spY, kmh, player);
            }

            // 6. Lakitu on Fluffy Cloud + Starting Signal Lights (3 - 2 - 1 - GO!)
            if (!raceStarted && countdownTimer > -0.8f)
            {
                float bob = (float)Math.Sin(globalTime * 4.5f) * 6f;
                if (SgiSpriteGenerator.TexLakitu != 0)
                {
                    ProceduralTextures.DrawSprite2D(SgiSpriteGenerator.TexLakitu, virtW * 0.5f - 128f, 118f + bob, 92f, 92f, whiteTop);
                }
                RenderLakituStartLights(virtW * 0.5f + 12f, 126f + bob, countdownTimer);
            }
            else if (raceStarted && raceTime < 1.15f)
            {
                ProceduralTextures.DrawText2D("GO!!", virtW * 0.5f, 138f, 52f, limeTop, limeBot, true);
            }

            // 7. Wrong-Way / Lakitu Rescue Warning
            if (player.IsGoingWrongWay && (((int)(globalTime * 6f)) & 1) == 0)
            {
                if (SgiSpriteGenerator.TexLakitu != 0)
                    ProceduralTextures.DrawSprite2D(SgiSpriteGenerator.TexLakitu, virtW * 0.5f - 180f, 178f, 64f, 64f, whiteTop);
                ProceduralTextures.DrawText2D("REVERSE!", virtW * 0.5f + 15f, 195f, 32f, Color4.FromBytes(255, 58, 58), goldTop, true);
            }
            if (player.LakituRescueTimer > 0f)
            {
                ProceduralTextures.DrawText2D("LAKITU RESCUE...", virtW * 0.5f, 202f, 26f, whiteTop, goldTop, true);
            }

            // 8. Finish Banner
            if (player.FinishedRace)
            {
                string finText = (mode == GameMode.TimeTrials)
                    ? "FINISH! " + GameConfig.FormatRaceTime(player.FinishTimeSeconds)
                    : ("FINISH! " + FormatOrdinal(player.RaceRank) + " PLACE!");
                ProceduralTextures.DrawSolidRect2D(virtW * 0.5f - 230f, virtH * 0.42f - 10f, 460f, 64f, new Color4(0f, 0f, 0f, 0.72f));
                ProceduralTextures.DrawText2D(finText, virtW * 0.5f, virtH * 0.42f + 4f, 34f, goldTop, orangeBot, true);
            }
        }

        private static void RenderAnalogSpeedometer(float cx, float cy, float kmh, Kart player)
        {
            // Authentic MK64 Semi-Circular White Tick Arc + Glowing Red Needle (matches lu-1.jpg!)
            float r = 56f;
            Gl.glDisable(Gl.GL_TEXTURE_2D);

            // Outer white tick marks along left-to-top arc (angles 135° .. 295° in screen space)
            Gl.glLineWidth(2.0f);
            Gl.glBegin(Gl.GL_LINES);
            for (int t = 0; t <= 20; t++)
            {
                float frac = t / 20f;
                float ang = (135f + frac * 155f) * MathUtil.DEG2RAD;
                float ca = (float)Math.Cos(ang);
                float sa = (float)Math.Sin(ang);
                float inner = (t % 4 == 0) ? (r - 10f) : (r - 5f);
                Gl.Color(new Color4(0.96f, 0.98f, 1.0f, 0.86f));
                Gl.glVertex2f(cx + ca * inner, cy + sa * inner);
                Gl.glVertex2f(cx + ca * r, cy + sa * r);
            }

            // Glowing red needle!
            float needleFrac = MathUtil.Clamp(kmh / 120f, 0f, 1.08f);
            float nAng = (135f + needleFrac * 155f) * MathUtil.DEG2RAD;
            Gl.Color(Color4.FromBytes(255, 38, 28));
            Gl.glVertex2f(cx, cy);
            Gl.glVertex2f(cx + (float)Math.Cos(nAng) * (r - 6f), cy + (float)Math.Sin(nAng) * (r - 6f));
            Gl.glVertex2f(cx, cy + 2f);
            Gl.glVertex2f(cx + (float)Math.Cos(nAng) * (r - 6f), cy + 2f + (float)Math.Sin(nAng) * (r - 6f));
            Gl.glEnd();

            ProceduralTextures.DrawText2D(((int)kmh) + " Km/h", cx - 18f, cy + 12f, 15f, new Color4(1f, 1f, 1f, 0.92f), new Color4(0.85f, 0.9f, 1f, 0.92f), false);
            if (player.IsDrifting && player.MiniTurboStage >= 2)
            {
                ProceduralTextures.DrawText2D("TURBO!", cx - 22f, cy - 22f, 15f, Color4.FromBytes(255, 92, 32), Color4.FromBytes(255, 220, 42), false);
            }
        }

        private static void RenderLakituStartLights(float cx, float cy, float countdownRemaining)
        {
            ProceduralTextures.DrawSolidRect2D(cx - 34f, cy - 10f, 68f, 118f, new Color4(0.10f, 0.12f, 0.16f, 0.90f));
            ProceduralTextures.DrawRectOutline2D(cx - 34f, cy - 10f, 68f, 118f, 2.5f, Color4.FromBytes(255, 215, 45));

            bool r1 = countdownRemaining <= 2.95f && countdownRemaining > 0.0f;
            bool r2 = countdownRemaining <= 1.95f && countdownRemaining > 0.0f;
            bool r3 = countdownRemaining <= 0.95f && countdownRemaining > 0.0f;
            bool go = countdownRemaining <= 0.0f;

            Color4 redOn  = Color4.FromBytes(255, 42, 42);
            Color4 redOff = Color4.FromBytes(68, 22, 22);
            Color4 goOn   = Color4.FromBytes(55, 245, 255);
            Color4 goOff  = Color4.FromBytes(20, 58, 65);

            ProceduralTextures.DrawSolidRect2D(cx - 16f, cy,       32f, 20f, r1 ? redOn : redOff);
            ProceduralTextures.DrawSolidRect2D(cx - 16f, cy + 26f, 32f, 20f, r2 ? redOn : redOff);
            ProceduralTextures.DrawSolidRect2D(cx - 16f, cy + 52f, 32f, 20f, r3 ? redOn : redOff);
            ProceduralTextures.DrawSolidRect2D(cx - 20f, cy + 78f, 40f, 22f, go ? goOn  : goOff);
        }

        private static void RenderCourseMinimap(float x, float y, float w, float h, TrackData track, Kart[] karts, Kart player)
        {
            float minX = float.MaxValue, maxX = float.MinValue;
            float minZ = float.MaxValue, maxZ = float.MinValue;

            for (int i = 0; i < track.Segments.Length; i += 2)
            {
                Vec3 c = track.Segments[i].Center;
                if (c.X < minX) minX = c.X;
                if (c.X > maxX) maxX = c.X;
                if (c.Z < minZ) minZ = c.Z;
                if (c.Z > maxZ) maxZ = c.Z;
            }

            float spanX = Math.Max(10f, maxX - minX);
            float spanZ = Math.Max(10f, maxZ - minZ);
            float scale = Math.Min((w - 16f) / spanX, (h - 16f) / spanZ);
            float ox = x + (w - spanX * scale) * 0.5f;
            float oy = y + (h - spanZ * scale) * 0.5f;

            // Floating black-outlined white (or Sherbet ice-blue!) MK64 course ribbon!
            Gl.glDisable(Gl.GL_TEXTURE_2D);
            Gl.glLineWidth(6.5f);
            Gl.Color(new Color4(0.06f, 0.08f, 0.14f, 0.86f));
            Gl.glBegin(Gl.GL_LINE_LOOP);
            for (int i = 0; i < track.Segments.Length; i += 2)
            {
                Vec3 c = track.Segments[i].Center;
                Gl.glVertex2f(ox + (maxX - c.X) * scale, oy + (maxZ - c.Z) * scale);
            }
            Gl.glEnd();

            Gl.glLineWidth(3.5f);
            Color4 ribCol = (track.Id == CourseId.SherbetLand)
                ? Color4.FromBytes(88, 128, 255)
                : new Color4(0.96f, 0.98f, 1.0f, 0.96f);
            Gl.Color(ribCol);
            Gl.glBegin(Gl.GL_LINE_LOOP);
            for (int i = 0; i < track.Segments.Length; i += 2)
            {
                Vec3 c = track.Segments[i].Center;
                Gl.glVertex2f(ox + (maxX - c.X) * scale, oy + (maxZ - c.Z) * scale);
            }
            Gl.glEnd();

            // Checkered finish line marker
            Vec3 f0 = track.Segments[0].Center;
            ProceduralTextures.DrawSolidRect2D(ox + (maxX - f0.X) * scale - 4.5f, oy + (maxZ - f0.Z) * scale - 2f, 9f, 3.5f, Color4.FromBytes(30, 30, 35));

            // Colored black-ringed MK64 racer dots!
            for (int i = 0; i < karts.Length; i++)
            {
                Kart k = karts[i];
                float kx = ox + (maxX - k.Position.X) * scale;
                float ky = oy + (maxZ - k.Position.Z) * scale;
                float sz = (k == player) ? 7.5f : 5.5f;
                ProceduralTextures.DrawSolidRect2D(kx - sz * 0.5f - 1.2f, ky - sz * 0.5f - 1.2f, sz + 2.4f, sz + 2.4f, new Color4(0.05f, 0.05f, 0.08f, 0.95f));
                Color4 dotCol = (k == player) ? k.Character.PrimaryColor : Color4.FromBytes(232, 62, 225);
                if (k == player)
                {
                    ProceduralTextures.DrawSolidRect2D(kx - sz * 0.5f, ky - sz * 0.5f, sz, sz, dotCol);
                }
                else
                {
                    ProceduralTextures.DrawSolidRect2D(kx - sz * 0.5f, ky - sz * 0.5f, sz, sz, k.Character.PrimaryColor);
                }
            }
        }

        private static string OrdinalSuffix(int rank)
        {
            switch (rank)
            {
                case 1: return "st";
                case 2: return "nd";
                case 3: return "rd";
                default: return "th";
            }
        }

        public static string FormatOrdinal(int rank)
        {
            return rank + OrdinalSuffix(rank);
        }
    }
}
