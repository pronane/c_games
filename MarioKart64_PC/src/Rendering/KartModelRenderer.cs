using System;
using MarioKart64.Core;
using MarioKart64.Entities;

namespace MarioKart64.Rendering
{
    public static class KartModelRenderer
    {
        public static void DrawBox(float cx, float cy, float cz, float hx, float hy, float hz, Color4 topCol, Color4 sideCol)
        {
            float x0 = cx - hx, x1 = cx + hx;
            float y0 = cy - hy, y1 = cy + hy;
            float z0 = cz - hz, z1 = cz + hz;
            Color4 darkSide = sideCol.ScaleRGB(0.76f);

            Gl.glBegin(Gl.GL_QUADS);
            // Top
            Gl.Color(topCol);
            Gl.glVertex3f(x0, y1, z0); Gl.glVertex3f(x0, y1, z1);
            Gl.glVertex3f(x1, y1, z1); Gl.glVertex3f(x1, y1, z0);
            // Bottom
            Gl.Color(darkSide);
            Gl.glVertex3f(x0, y0, z0); Gl.glVertex3f(x1, y0, z0);
            Gl.glVertex3f(x1, y0, z1); Gl.glVertex3f(x0, y0, z1);
            // Front (+Z)
            Gl.Color(sideCol);
            Gl.glVertex3f(x0, y0, z1); Gl.glVertex3f(x1, y0, z1);
            Gl.glVertex3f(x1, y1, z1); Gl.glVertex3f(x0, y1, z1);
            // Back (-Z)
            Gl.Color(darkSide);
            Gl.glVertex3f(x1, y0, z0); Gl.glVertex3f(x0, y0, z0);
            Gl.glVertex3f(x0, y1, z0); Gl.glVertex3f(x1, y1, z0);
            // Left (-X)
            Gl.Color(sideCol.ScaleRGB(0.88f));
            Gl.glVertex3f(x0, y0, z0); Gl.glVertex3f(x0, y0, z1);
            Gl.glVertex3f(x0, y1, z1); Gl.glVertex3f(x0, y1, z0);
            // Right (+X)
            Gl.glVertex3f(x1, y0, z1); Gl.glVertex3f(x1, y0, z0);
            Gl.glVertex3f(x1, y1, z0); Gl.glVertex3f(x1, y1, z1);
            Gl.glEnd();
        }

        public static void DrawShadedEllipsoid(float cx, float cy, float cz, float rx, float ry, float rz, int stacks, int slices, Color4 topCol, Color4 botCol)
        {
            for (int i = 0; i < stacks; i++)
            {
                float v0 = i / (float)stacks;
                float v1 = (i + 1) / (float)stacks;
                float phi0 = (v0 - 0.5f) * MathUtil.PI;
                float phi1 = (v1 - 0.5f) * MathUtil.PI;
                float y0 = (float)Math.Sin(phi0) * ry;
                float y1 = (float)Math.Sin(phi1) * ry;
                float c0 = (float)Math.Cos(phi0);
                float c1 = (float)Math.Cos(phi1);
                Color4 col0 = Color4.Lerp(botCol, topCol, v0);
                Color4 col1 = Color4.Lerp(botCol, topCol, v1);

                Gl.glBegin(Gl.GL_TRIANGLE_STRIP);
                for (int j = 0; j <= slices; j++)
                {
                    float th = (j / (float)slices) * MathUtil.TWO_PI;
                    float cs = (float)Math.Cos(th);
                    float sn = (float)Math.Sin(th);
                    Gl.Color(col1);
                    Gl.glVertex3f(cx + cs * c1 * rx, cy + y1, cz + sn * c1 * rz);
                    Gl.Color(col0);
                    Gl.glVertex3f(cx + cs * c0 * rx, cy + y0, cz + sn * c0 * rz);
                }
                Gl.glEnd();
            }
        }

        // Renders a crisp camera-facing SGI sprite billboard in 3D space with alpha-testing so transparent texels never occlude Z!
        public static void DrawBillboard(Vec3 bottomCenter, float width, float height, uint texId, Vec3 camScreenRight, Color4 tint, float rollRad = 0f)
        {
            if (texId == 0) return;

            Vec3 right = camScreenRight;
            Vec3 up = Vec3.Up;
            if (Math.Abs(rollRad) > 0.001f)
            {
                float cr = (float)Math.Cos(rollRad);
                float sr = (float)Math.Sin(rollRad);
                Vec3 nr = right * cr + up * sr;
                Vec3 nu = up * cr - right * sr;
                right = nr;
                up = nu;
            }

            Vec3 halfR = right * (width * 0.5f);
            Vec3 bl = bottomCenter - halfR;
            Vec3 br = bottomCenter + halfR;
            Vec3 tr = br + up * height;
            Vec3 tl = bl + up * height;

            Gl.glEnable(Gl.GL_TEXTURE_2D);
            Gl.glBindTexture(Gl.GL_TEXTURE_2D, texId);
            Gl.glEnable(Gl.GL_BLEND);
            Gl.glBlendFunc(Gl.GL_SRC_ALPHA, Gl.GL_ONE_MINUS_SRC_ALPHA);
            Gl.glEnable(Gl.GL_ALPHA_TEST);
            Gl.glAlphaFunc(Gl.GL_GREATER, 0.08f);

            Gl.Color(tint);
            Gl.glBegin(Gl.GL_QUADS);
            Gl.glTexCoord2f(0f, 1f); Gl.Vertex(bl);
            Gl.glTexCoord2f(1f, 1f); Gl.Vertex(br);
            Gl.glTexCoord2f(1f, 0f); Gl.Vertex(tr);
            Gl.glTexCoord2f(0f, 0f); Gl.Vertex(tl);
            Gl.glEnd();

            Gl.glDisable(Gl.GL_ALPHA_TEST);
            Gl.glDisable(Gl.GL_TEXTURE_2D);
        }

        public static void RenderKart(Kart k, Vec3 camEye, Vec3 camScreenRight, float globalTime, bool isBattleMode)
        {
            if (k.IsEliminated) return;
            if (k.PostHitInvulnTimer > 0f && (((int)(k.PostHitInvulnTimer * 18f)) & 1) == 1)
            {
                return;
            }

            float uniformScale = (k.ShrinkTimer > 0f) ? 0.56f : 1.0f;
            float scaleY = (k.SquashedTimer > 0f) ? 0.30f : 1.0f;
            float alpha = (k.BooTimer > 0f) ? 0.44f : 1.0f;

            // 1. Soft Elliptical N64 Contact Shadow on Asphalt
            Gl.glDisable(Gl.GL_TEXTURE_2D);
            Gl.glEnable(Gl.GL_BLEND);
            Gl.glBlendFunc(Gl.GL_SRC_ALPHA, Gl.GL_ONE_MINUS_SRC_ALPHA);
            Gl.glDepthMask(0);
            Gl.glPushMatrix();
            Gl.glTranslatef(k.Position.X, k.Position.Y + 0.04f, k.Position.Z);
            Gl.glRotatef(k.Yaw * MathUtil.RAD2DEG, 0f, 1f, 0f);
            Gl.Color(new Color4(0f, 0f, 0f, 0.46f * alpha));
            Gl.glBegin(Gl.GL_TRIANGLE_FAN);
            Gl.glVertex3f(0f, 0f, 0f);
            for (int i = 0; i <= 14; i++)
            {
                float ang = (i / 14f) * MathUtil.TWO_PI;
                Gl.glVertex3f((float)Math.Cos(ang) * 1.18f * uniformScale, 0f, (float)Math.Sin(ang) * 1.38f * uniformScale);
            }
            Gl.glEnd();
            Gl.glPopMatrix();
            Gl.glDepthMask(1);

            // 2. Select Multi-Angle SGI Character + Pipe-Frame Go-Kart Sprite!
            float effYaw = k.Yaw;
            if (k.SpinOutTimer > 0f)
            {
                effYaw += (1.08f - k.SpinOutTimer) * 11.8f;
            }

            Vec3 kartFwd = new Vec3((float)Math.Sin(effYaw), 0f, (float)Math.Cos(effYaw));
            Vec3 kartScreenRight = Vec3.Cross(kartFwd, Vec3.Up);
            Vec3 toCam = camEye - k.Position;
            float cZ = Vec3.Dot(toCam, kartFwd);
            float cS = Vec3.Dot(toCam, kartScreenRight);

            float relAngle = (float)Math.Atan2(cS, -cZ);
            if (relAngle < 0f) relAngle += MathUtil.TWO_PI;

            int frameIdx;
            bool isRearView = (relAngle < 0.30f || relAngle > (MathUtil.TWO_PI - 0.30f)) && k.SpinOutTimer <= 0f;
            float visualSteer = k.VisualSteerLean + (k.IsDrifting ? k.DriftDirection * 0.45f : 0f);

            if (isRearView && Math.Abs(visualSteer) > 0.20f)
            {
                // Use dedicated SGI rear steering-lean frames (16..19) for responsive player/CPU cornering!
                if (visualSteer < -0.62f) frameIdx = 16;
                else if (visualSteer < 0f) frameIdx = 17;
                else if (visualSteer < 0.62f) frameIdx = 18;
                else frameIdx = 19;
            }
            else
            {
                frameIdx = ((int)Math.Round((relAngle / MathUtil.TWO_PI) * SgiSpriteGenerator.YawSteps)) % SgiSpriteGenerator.YawSteps;
            }

            int charIdx = ((int)k.Character.Id) & 7;
            uint spriteTex = SgiSpriteGenerator.KartTextures[charIdx, frameIdx];

            Color4 tint = new Color4(1f, 1f, 1f, alpha);
            if (k.StarmanTimer > 0f)
            {
                Color4 rb = Color4.Rainbow(globalTime * 15f);
                tint = new Color4(0.45f + rb.R * 0.55f, 0.45f + rb.G * 0.55f, 0.45f + rb.B * 0.55f, alpha);
            }

            float rollRad = k.VisualSteerLean * (k.IsDrifting ? 0.06f : 0.025f);
            if (k.TumbleTimer > 0f)
            {
                rollRad += k.TumblePitch * 0.65f;
            }

            float quadW = 2.85f * uniformScale;
            float quadH = 2.85f * uniformScale * scaleY;
            Vec3 quadBottom = k.Position - new Vec3(0f, quadH * 0.16f, 0f);
            DrawBillboard(quadBottom, quadW, quadH, spriteTex, camScreenRight, tint, rollRad);

            // 3. Authentic MK64 Soft White Engine Exhaust Puff (lu-1.jpg / characters--3.png!) + Twin Boost Flames!
            if (k.BoostTimer > 0f || k.StarmanTimer > 0f)
            {
                Gl.glDisable(Gl.GL_TEXTURE_2D);
                float flick = 0.28f + 0.14f * (float)Math.Sin(globalTime * 52f);
                Vec3 rearL = k.Position - kartFwd * (0.95f * uniformScale) - kartScreenRight * (0.26f * uniformScale) + new Vec3(0f, 0.48f * uniformScale, 0f);
                Vec3 rearR = k.Position - kartFwd * (0.95f * uniformScale) + kartScreenRight * (0.26f * uniformScale) + new Vec3(0f, 0.48f * uniformScale, 0f);
                Color4 core = new Color4(1.0f, 0.96f, 0.38f, 0.92f);
                Color4 outer = new Color4(1.0f, 0.36f, 0.08f, 0.88f);
                DrawShadedEllipsoid(rearL.X, rearL.Y, rearL.Z, 0.17f, 0.17f, flick, 4, 6, core, outer);
                DrawShadedEllipsoid(rearR.X, rearR.Y, rearR.Z, 0.17f, 0.17f, flick, 4, 6, core, outer);
            }
            else if (k.ForwardSpeed > 6f && alpha > 0.5f)
            {
                float puffPhase = (globalTime * 14f + k.SlotIndex * 1.7f) % 1.0f;
                float pr = (0.16f + puffPhase * 0.18f) * uniformScale;
                float pa = (1f - puffPhase) * 0.52f;
                Vec3 ep = k.Position - kartFwd * ((0.78f + puffPhase * 0.55f) * uniformScale) + new Vec3(0f, (0.58f + puffPhase * 0.25f) * uniformScale, 0f);
                DrawBillboard(ep - new Vec3(0f, pr, 0f), pr * 2.4f, pr * 1.8f, ProceduralTextures.TexCloud, camScreenRight, new Color4(1f, 1f, 1f, pa));
            }

            // 4. Authentic MK64 3-Stage Power-Slide Tire Smoke (White -> Yellow -> Red-Orange)!
            if (k.IsDrifting && k.IsGrounded)
            {
                Gl.glDisable(Gl.GL_TEXTURE_2D);
                Color4 sTop = new Color4(0.98f, 0.98f, 1.0f, 0.86f);
                Color4 sBot = new Color4(0.80f, 0.82f, 0.88f, 0.82f);
                if (k.MiniTurboStage == 1)
                {
                    sTop = new Color4(1.0f, 0.95f, 0.28f, 0.92f);
                    sBot = new Color4(0.95f, 0.68f, 0.12f, 0.88f);
                }
                else if (k.MiniTurboStage >= 2)
                {
                    sTop = new Color4(1.0f, 0.45f, 0.14f, 0.96f);
                    sBot = new Color4(0.92f, 0.16f, 0.08f, 0.92f);
                }

                for (int p = 0; p < 2; p++)
                {
                    float side = (p == 0) ? -0.78f : 0.78f;
                    float puff = (0.24f + 0.10f * (float)Math.Sin(globalTime * 38f + p * 2.1f)) * uniformScale;
                    Vec3 sp = k.Position - kartFwd * (0.95f * uniformScale) + kartScreenRight * (side * uniformScale) + new Vec3(0f, 0.24f, 0f);
                    DrawShadedEllipsoid(sp.X, sp.Y, sp.Z, puff, puff * 0.85f, puff, 4, 6, sTop, sBot);
                }
            }

            // 5. Sherbet Land Translucent Ice Cube Encasement!
            if (k.RescuedInIceCube)
            {
                Gl.glDisable(Gl.GL_TEXTURE_2D);
                Color4 ice = new Color4(0.65f, 0.92f, 1.0f, 0.50f);
                DrawBox(k.Position.X, k.Position.Y + 0.95f, k.Position.Z, 1.30f, 1.00f, 1.40f, ice, ice);
            }

            // 6. Lakitu Rescue Cloud Hovering Overhead!
            if (k.LakituRescueTimer > 0f)
            {
                Vec3 lakPos = k.Position + new Vec3(0f, 2.35f + 0.15f * (float)Math.Sin(globalTime * 8f), 0f);
                DrawBillboard(lakPos, 2.1f, 2.1f, SgiSpriteGenerator.TexLakitu, camScreenRight, new Color4(1f, 1f, 1f, 1f));
            }

            // 7. MK64 Banana-Brake Saved Musical Note Popup!
            if (k.SavedNoteTimer > 0f)
            {
                Gl.glDisable(Gl.GL_TEXTURE_2D);
                float bob = k.Position.Y + 2.45f + (1.15f - k.SavedNoteTimer) * 0.65f;
                Color4 gold = new Color4(1.0f, 0.90f, 0.18f, 1.0f);
                DrawShadedEllipsoid(k.Position.X, bob, k.Position.Z, 0.22f, 0.16f, 0.16f, 4, 6, gold, gold.ScaleRGB(0.8f));
            }

            // 8. Battle Mode 3 Floating SGI-Shaded Balloons!
            if (isBattleMode && k.Balloons > 0)
            {
                Gl.glDisable(Gl.GL_TEXTURE_2D);
                Color4 bTop = k.Character.PrimaryColor;
                Color4 bBot = bTop.ScaleRGB(0.68f);
                for (int b = 0; b < k.Balloons; b++)
                {
                    float ang = globalTime * 2.5f + b * (MathUtil.TWO_PI / Math.Max(1, k.Balloons));
                    float bx = k.Position.X + (float)Math.Cos(ang) * 0.56f;
                    float bz = k.Position.Z + (float)Math.Sin(ang) * 0.56f;
                    float by = k.Position.Y + 2.55f + 0.12f * (float)Math.Sin(globalTime * 5f + b);
                    DrawShadedEllipsoid(bx, by, bz, 0.32f, 0.38f, 0.32f, 5, 8, bTop, bBot);
                }
            }

            // 9. Orbiting SGI Triple Shells or Trailing Banana Bunch!
            if (k.OrbitItemCount > 0 && k.ActiveOrbitType != ItemId.None)
            {
                uint orbTex = SgiSpriteGenerator.ItemTextures[(int)ItemId.GreenShell];
                if (k.ActiveOrbitType == ItemId.TripleRedShells) orbTex = SgiSpriteGenerator.ItemTextures[(int)ItemId.RedShell];
                else if (k.ActiveOrbitType == ItemId.TripleBananas) orbTex = SgiSpriteGenerator.ItemTextures[(int)ItemId.Banana];

                for (int i = 0; i < k.OrbitItemCount; i++)
                {
                    Vec3 itemPos;
                    if (k.ActiveOrbitType == ItemId.TripleBananas)
                    {
                        itemPos = k.Position - k.ForwardDir * (2.0f + i * 1.15f) - new Vec3(0f, 0.15f, 0f);
                    }
                    else
                    {
                        float ang = k.OrbitAngle + i * (MathUtil.TWO_PI / Math.Max(1, k.OrbitItemCount));
                        itemPos = k.Position + new Vec3((float)Math.Cos(ang) * 2.05f, 0.05f, (float)Math.Sin(ang) * 2.05f);
                    }
                    DrawBillboard(itemPos, 1.25f, 1.25f, orbTex, camScreenRight, new Color4(1f, 1f, 1f, 1f));
                }
            }
        }
    }
}
