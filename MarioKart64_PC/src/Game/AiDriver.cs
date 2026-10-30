using System;
using System.Collections.Generic;
using MarioKart64.Core;
using MarioKart64.Entities;
using MarioKart64.Input;
using MarioKart64.Tracks;

namespace MarioKart64.Game
{
    public static class AiDriver
    {
        public static PlayerInputState ComputeInput(
            Kart ai,
            TrackData track,
            Kart[] allKarts,
            List<WorldItemEntity> worldItems,
            List<CourseHazard> hazards,
            EngineClass engineClass,
            bool isDesignatedRival,
            Random rng,
            float dt)
        {
            PlayerInputState inp = new PlayerInputState();
            if (ai.IsEliminated) return inp;

            if (track.IsBattleArena)
            {
                ComputeBattleAi(ai, track, allKarts, inp, rng, dt);
                return inp;
            }

            if (track.Segments == null || track.Segments.Length == 0) return inp;

            int count = track.Segments.Length;
            int lookAhead = (ai.ForwardSpeed > 46f) ? 5 : 4;
            int targetSegIdx = (ai.CurrentSegmentIndex + lookAhead) % count;
            TrackSegment targetSeg = track.Segments[targetSegIdx];

            // Multi-path branch selection (e.g., Yoshi Valley canyon routes!)
            if (track.Branches.Count > 0 && ai.AiPreferredBranch >= 0 && ai.AiPreferredBranch < track.Branches.Count)
            {
                BranchSpline br = track.Branches[ai.AiPreferredBranch];
                int distToStart = (br.StartMainSegment - ai.CurrentSegmentIndex + count) % count;
                if (distToStart < 10 || ai.CurrentBranchIndex == ai.AiPreferredBranch)
                {
                    // Find nearest segment on chosen branch and look ahead
                    int bestB = 0;
                    float bestD = float.MaxValue;
                    for (int b = 0; b < br.Segments.Length; b++)
                    {
                        float d = Vec3.DistanceXZSq(ai.Position, br.Segments[b].Center);
                        if (d < bestD) { bestD = d; bestB = b; }
                    }
                    if (bestB < br.Segments.Length - 3)
                    {
                        targetSeg = br.Segments[Math.Min(br.Segments.Length - 1, bestB + 4)];
                    }
                }
            }

            // Hazard & Banana avoidance lateral shift
            float avoidOffset = ai.AiLaneOffset;
            for (int h = 0; h < hazards.Count; h++)
            {
                CourseHazard hz = hazards[h];
                if (!hz.ActiveCollider) continue;
                Vec3 diff = hz.Position - ai.Position;
                float d = diff.LengthXZ;
                if (d < 26f && Vec3.Dot(diff.NormalizedXZ(), ai.ForwardDir) > 0.6f)
                {
                    float side = Vec3.Dot(diff, targetSeg.Right);
                    avoidOffset = (side >= 0f) ? -targetSeg.HalfWidth * 0.55f : targetSeg.HalfWidth * 0.55f;
                    break;
                }
            }

            float maxSafeLat = targetSeg.HalfWidth * 0.62f;
            float clampedLat = MathUtil.Clamp(avoidOffset, -maxSafeLat, maxSafeLat);
            Vec3 aimPoint = targetSeg.Center + targetSeg.Right * clampedLat;

            Vec3 toAim = (aimPoint - ai.Position).NormalizedXZ();
            float desiredYaw = (float)Math.Atan2(toAim.X, toAim.Z);
            float yawErr = MathUtil.WrapAngle(desiredYaw - ai.Yaw);

            inp.Steer = MathUtil.Clamp(-yawErr * 2.55f, -1f, 1f);
            inp.Accelerate = true;

            // Ease throttle on tight curves without walls so heavyweights (DK/Bowser) stay cleanly on the road!
            if (Math.Abs(yawErr) > 0.40f && ai.ForwardSpeed > 36f &&
                (targetSeg.LeftEdge != EdgeBehavior.SolidWall || targetSeg.RightEdge != EdgeBehavior.SolidWall))
            {
                inp.Accelerate = false;
            }

            // Authentic MK64 Rival Rubber-Banding
            Kart leadHuman = null;
            for (int k = 0; k < allKarts.Length; k++)
            {
                if (allKarts[k].IsHuman)
                {
                    if (leadHuman == null || allKarts[k].RaceProgress > leadHuman.RaceProgress)
                        leadHuman = allKarts[k];
                }
            }
            if (leadHuman != null && !ai.FinishedRace)
            {
                float gap = leadHuman.RaceProgress - ai.RaceProgress;
                float rivalBonus = isDesignatedRival ? 1.05f : 0.99f;
                if (engineClass == EngineClass.CC50) rivalBonus *= 0.95f;
                else if (engineClass == EngineClass.CC150 || engineClass == EngineClass.ExtraMirror) rivalBonus *= 1.04f;

                if (gap > 85f && ai.BoostTimer <= 0f)
                {
                    // Subtle catch-up pace when far behind human leader
                    ai.ForwardSpeed = Math.Min(ai.ForwardSpeed + 6.5f * rivalBonus * dt, ai.Character.TopSpeed * 1.12f * rivalBonus);
                }
                else if (gap < -125f && engineClass != EngineClass.CC150)
                {
                    // Slight ease-off when way ahead in 50cc/100cc
                    if (rng.NextDouble() < 0.18) inp.Accelerate = false;
                }
            }

            // Smart AI Item Usage
            if (ai.HeldItem != ItemId.None || ai.OrbitItemCount > 0)
            {
                ai.AiItemDelayTimer -= dt;
                if (ai.AiItemDelayTimer <= 0f)
                {
                    ai.AiItemDelayTimer = 1.1f + (float)rng.NextDouble() * 1.6f;
                    inp.ItemPressed = true;
                    inp.ItemHeld = true;
                }
            }

            return inp;
        }

        private static void ComputeBattleAi(
            Kart ai,
            TrackData track,
            Kart[] allKarts,
            PlayerInputState inp,
            Random rng,
            float dt)
        {
            Vec3 targetPos = Vec3.Zero;
            bool hasWeapon = (ai.HeldItem != ItemId.None || ai.OrbitItemCount > 0);

            if (!hasWeapon && track.ItemBoxes.Count > 0)
            {
                // Seek nearest active Item Box
                float bestD = float.MaxValue;
                for (int i = 0; i < track.ItemBoxes.Count; i++)
                {
                    if (!track.ItemBoxes[i].Active) continue;
                    float d = Vec3.Distance(ai.Position, track.ItemBoxes[i].Position);
                    if (d < bestD)
                    {
                        bestD = d;
                        targetPos = track.ItemBoxes[i].Position;
                    }
                }
            }
            else
            {
                // Hunt nearest surviving opponent!
                Kart prey = null;
                float bestD = float.MaxValue;
                for (int k = 0; k < allKarts.Length; k++)
                {
                    if (allKarts[k] == ai || allKarts[k].IsEliminated) continue;
                    float d = Vec3.Distance(ai.Position, allKarts[k].Position);
                    if (d < bestD)
                    {
                        bestD = d;
                        prey = allKarts[k];
                    }
                }
                if (prey != null)
                {
                    targetPos = prey.Position;
                    Vec3 toPrey = (prey.Position - ai.Position).NormalizedXZ();
                    if (bestD < 32f && Vec3.Dot(toPrey, ai.ForwardDir) > 0.85f)
                    {
                        ai.AiItemDelayTimer -= dt;
                        if (ai.AiItemDelayTimer <= 0f)
                        {
                            ai.AiItemDelayTimer = 1.0f;
                            inp.ItemPressed = true;
                            inp.ItemHeld = true;
                        }
                    }
                }
            }

            // Avoid central lava pit on Big Donut!
            if (track.Id == CourseId.BigDonut && Math.Abs(ai.Position.X) < 32f && Math.Abs(ai.Position.Z) < 32f)
            {
                targetPos = ai.Position.NormalizedXZ() * 52f;
            }

            Vec3 dir = (targetPos - ai.Position).NormalizedXZ();
            float targetYaw = (float)Math.Atan2(dir.X, dir.Z);
            float err = MathUtil.WrapAngle(targetYaw - ai.Yaw);
            inp.Steer = MathUtil.Clamp(-err * 2.2f, -1f, 1f);
            inp.Accelerate = Math.Abs(err) < 1.25f;
            inp.Brake = Math.Abs(err) > 2.1f;
        }
    }
}
