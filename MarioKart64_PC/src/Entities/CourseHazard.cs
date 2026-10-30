using System;
using System.Collections.Generic;
using MarioKart64.Audio;
using MarioKart64.Core;
using MarioKart64.Input;
using MarioKart64.Tracks;

namespace MarioKart64.Entities
{
    public class CourseHazard
    {
        public HazardSpawnSpec Spec;
        public Vec3 Position;
        public float Yaw;
        public float AnimTime;
        public float DistAlongTrack;
        public float HitRadius = 2.4f;
        public bool ActiveCollider = true;

        public CourseHazard(HazardSpawnSpec spec, TrackData track)
        {
            Spec = spec;
            Position = spec.BasePos;
            AnimTime = spec.PhaseOffset * 3.0f;

            if (track.Segments != null && track.Segments.Length > 0)
            {
                int idx = MathUtil.ClampInt(spec.SegmentIndex, 0, track.Segments.Length - 1);
                DistAlongTrack = track.Segments[idx].CumulativeDist;
            }

            switch (spec.Kind)
            {
                case HazardKind.KalimariTrain:   HitRadius = 3.8f; break;
                case HazardKind.HighwayTruck:    HitRadius = 3.4f; break;
                case HazardKind.HighwayBus:      HitRadius = 3.4f; break;
                case HazardKind.HighwayCar:      HitRadius = 2.6f; break;
                case HazardKind.MontyMole:       HitRadius = 1.7f; break;
                case HazardKind.SnowmanMine:     HitRadius = 2.1f; break;
                case HazardKind.FallingBoulder:  HitRadius = 2.5f; break;
                case HazardKind.SlidingPenguin:  HitRadius = 1.9f; break;
                case HazardKind.StompingThwomp:  HitRadius = 2.8f; break;
                case HazardKind.GiantYoshiEgg:   HitRadius = 3.6f; break;
                case HazardKind.SwoopingBat:     HitRadius = 1.9f; break;
                case HazardKind.ChainChomp:      HitRadius = 2.9f; break;
                case HazardKind.LeapingCheepCheep: HitRadius = 2.8f; break;
            }
        }

        public void Update(TrackData track, Kart[] karts, EasySmxControllerManager padMgr, float dt)
        {
            AnimTime += dt;
            ActiveCollider = true;

            switch (Spec.Kind)
            {
                case HazardKind.KalimariTrain:
                    if (Spec.CustomLoop != null && Spec.CustomLoop.Length >= 4)
                    {
                        int n = Spec.CustomLoop.Length;
                        float loopProgress = (AnimTime * 0.055f - Spec.PhaseOffset);
                        while (loopProgress < 0f) loopProgress += 1.0f;
                        loopProgress = loopProgress - (float)Math.Floor(loopProgress);
                        float exact = loopProgress * n;
                        int i1 = ((int)exact) % n;
                        int i0 = (i1 - 1 + n) % n;
                        int i2 = (i1 + 1) % n;
                        int i3 = (i1 + 2) % n;
                        float f = exact - (int)exact;
                        Vec3 nextP = Vec3.CatmullRom(Spec.CustomLoop[i0], Spec.CustomLoop[i1], Spec.CustomLoop[i2], Spec.CustomLoop[i3], Math.Min(1f, f + 0.05f));
                        Position = Vec3.CatmullRom(Spec.CustomLoop[i0], Spec.CustomLoop[i1], Spec.CustomLoop[i2], Spec.CustomLoop[i3], f);
                        Vec3 fwd = (nextP - Position).NormalizedXZ();
                        Yaw = (float)Math.Atan2(fwd.X, fwd.Z);
                    }
                    break;

                case HazardKind.HighwayTruck:
                case HazardKind.HighwayBus:
                case HazardKind.HighwayCar:
                case HazardKind.ChainChomp:
                    if (track.Segments != null && track.Segments.Length > 0)
                    {
                        DistAlongTrack += Spec.Speed * dt;
                        while (DistAlongTrack >= track.TotalLength) DistAlongTrack -= track.TotalLength;
                        while (DistAlongTrack < 0f) DistAlongTrack += track.TotalLength;

                        // Binary/linear lookup of segment
                        int segIdx = (int)((DistAlongTrack / track.TotalLength) * track.Segments.Length) % track.Segments.Length;
                        TrackSegment seg = track.Segments[segIdx];
                        float lat = track.IsMirrored ? -Spec.PatrolRadius : Spec.PatrolRadius;
                        float hopY = (Spec.Kind == HazardKind.ChainChomp) ? Math.Abs((float)Math.Sin(AnimTime * 7.5f)) * 1.15f : 0f;
                        Position = seg.Center + seg.Right * lat + new Vec3(0f, hopY, 0f);
                        Vec3 dir = (Spec.Speed >= 0f) ? seg.Forward : -seg.Forward;
                        Yaw = (float)Math.Atan2(dir.X, dir.Z);
                    }
                    break;

                case HazardKind.MontyMole:
                    {
                        // Pops up out of dirt hole periodically!
                        float wave = (float)Math.Sin(AnimTime * Spec.Speed);
                        if (wave > 0.15f)
                        {
                            Position = Spec.BasePos + new Vec3(0f, (wave - 0.15f) * 2.2f, 0f);
                            ActiveCollider = true;
                        }
                        else
                        {
                            Position = Spec.BasePos + new Vec3(0f, -1.2f, 0f);
                            ActiveCollider = false;
                        }
                    }
                    break;

                case HazardKind.SnowmanMine:
                    Position = Spec.BasePos;
                    break;

                case HazardKind.FallingBoulder:
                    if (track.Segments != null)
                    {
                        TrackSegment seg = track.Segments[Spec.SegmentIndex % track.Segments.Length];
                        float sweep = (float)Math.Sin(AnimTime * 1.65f) * Spec.PatrolRadius;
                        float bounce = Math.Abs((float)Math.Sin(AnimTime * 5.8f)) * 3.2f;
                        Position = seg.Center + seg.Right * sweep + new Vec3(0f, bounce + 1.4f, 0f);
                        Yaw = AnimTime * 4.0f;
                    }
                    break;

                case HazardKind.SlidingPenguin:
                    if (track.Segments != null)
                    {
                        TrackSegment seg = track.Segments[Spec.SegmentIndex % track.Segments.Length];
                        float sweep = (float)Math.Sin(AnimTime * 1.4f) * Spec.PatrolRadius;
                        Position = seg.Center + seg.Right * sweep;
                        float dirSign = (float)Math.Cos(AnimTime * 1.4f) >= 0f ? 1f : -1f;
                        Vec3 dir = seg.Right * dirSign;
                        Yaw = (float)Math.Atan2(dir.X, dir.Z);
                    }
                    break;

                case HazardKind.StompingThwomp:
                    {
                        // Hover high -> pause -> SLAM down -> pause -> rise!
                        float cycle = (AnimTime * 0.65f) % 1.0f;
                        float h = 7.5f;
                        if (cycle < 0.45f) h = 7.5f;
                        else if (cycle < 0.55f) h = MathUtil.Lerp(7.5f, 0.0f, (cycle - 0.45f) / 0.10f);
                        else if (cycle < 0.72f) h = 0.0f;
                        else h = MathUtil.Lerp(0.0f, 7.5f, (cycle - 0.72f) / 0.28f);

                        Position = Spec.BasePos + new Vec3(0f, h, 0f);
                        ActiveCollider = (h < 2.6f);
                    }
                    break;

                case HazardKind.GiantYoshiEgg:
                    {
                        float ang = AnimTime * Spec.Speed * 0.65f;
                        Position = Spec.BasePos + new Vec3((float)Math.Cos(ang) * Spec.PatrolRadius, 0f, (float)Math.Sin(ang) * Spec.PatrolRadius);
                        Yaw = AnimTime * 6.0f;
                    }
                    break;

                case HazardKind.SwoopingBat:
                    if (track.Segments != null)
                    {
                        TrackSegment seg = track.Segments[Spec.SegmentIndex % track.Segments.Length];
                        float sweep = (float)Math.Sin(AnimTime * 2.4f) * Spec.PatrolRadius;
                        float swoopY = 1.4f + (1.0f + (float)Math.Cos(AnimTime * 3.1f)) * 1.8f;
                        Position = seg.Center + seg.Right * sweep + new Vec3(0f, swoopY, 0f);
                        Yaw = AnimTime * 2.0f;
                    }
                    break;

                case HazardKind.LeapingCheepCheep:
                    if (track.Segments != null)
                    {
                        TrackSegment seg = track.Segments[Spec.SegmentIndex % track.Segments.Length];
                        float phase = (AnimTime * 0.45f) % 1.0f;
                        float sweep = MathUtil.Lerp(-Spec.PatrolRadius, Spec.PatrolRadius, phase);
                        float arcY = (float)Math.Sin(phase * MathUtil.PI) * 11.5f - 2.5f;
                        Position = seg.Center + seg.Right * sweep + new Vec3(0f, arcY, 0f);
                        ActiveCollider = (arcY > -0.5f && arcY < 3.5f);
                    }
                    break;
            }

            if (!ActiveCollider) return;

            // Collide against Karts
            for (int k = 0; k < karts.Length; k++)
            {
                Kart kart = karts[k];
                if (kart.IsEliminated || kart.LakituRescueTimer > 0f) continue;
                if (kart.BooTimer > 0f) continue;

                float dXZ = Vec3.DistanceXZ(Position, kart.Position);
                float dY = Math.Abs(Position.Y - kart.Position.Y);
                if (dXZ < HitRadius + 1.15f && dY < 3.2f)
                {
                    if (kart.StarmanTimer > 0f)
                    {
                        // Starman shrugs off hazards (except Train/Truck push aside)
                        if (Spec.Kind == HazardKind.KalimariTrain || Spec.Kind == HazardKind.HighwayTruck)
                        {
                            Vec3 push = (kart.Position - Position).NormalizedXZ();
                            kart.Position += push * 2.2f;
                        }
                        continue;
                    }

                    if (Spec.Kind == HazardKind.StompingThwomp)
                    {
                        kart.TriggerSquash();
                    }
                    else if (Spec.Kind == HazardKind.MontyMole || Spec.Kind == HazardKind.SlidingPenguin || Spec.Kind == HazardKind.SwoopingBat)
                    {
                        kart.TriggerBananaHit();
                    }
                    else
                    {
                        kart.TriggerHeavyTumble();
                    }

                    if (kart.IsHuman && padMgr != null)
                    {
                        padMgr.TriggerRumble(kart.HumanPlayerIndex, 0.85f, 0.75f, 0.35f);
                    }
                }
            }
        }

        public static void ResolveKartToKartCollisions(Kart[] karts, bool isBattleMode, EasySmxControllerManager padMgr)
        {
            for (int i = 0; i < karts.Length; i++)
            {
                Kart a = karts[i];
                if (a.IsEliminated || a.LakituRescueTimer > 0f) continue;

                for (int j = i + 1; j < karts.Length; j++)
                {
                    Kart b = karts[j];
                    if (b.IsEliminated || b.LakituRescueTimer > 0f) continue;
                    if (a.BooTimer > 0f || b.BooTimer > 0f) continue;

                    float distXZ = Vec3.DistanceXZ(a.Position, b.Position);
                    float distY = Math.Abs(a.Position.Y - b.Position.Y);
                    if (distXZ < 2.25f && distY < 2.2f)
                    {
                        // Starman collision!
                        if (a.StarmanTimer > 0f && b.StarmanTimer <= 0f)
                        {
                            b.TriggerHeavyTumble();
                            if (isBattleMode) b.LoseBattleBalloon();
                            continue;
                        }
                        if (b.StarmanTimer > 0f && a.StarmanTimer <= 0f)
                        {
                            a.TriggerHeavyTumble();
                            if (isBattleMode) a.LoseBattleBalloon();
                            continue;
                        }

                        // Authentic MK64: Full-size kart driving over a Lightning-shrunken kart squashes them flat!
                        if (a.ShrinkTimer <= 0f && b.ShrinkTimer > 0f && b.SquashedTimer <= 0f)
                        {
                            b.TriggerSquash();
                            continue;
                        }
                        if (b.ShrinkTimer <= 0f && a.ShrinkTimer > 0f && a.SquashedTimer <= 0f)
                        {
                            a.TriggerSquash();
                            continue;
                        }

                        // Weight-class physics bump! (Bowser/Wario/DK knock Toad/Peach/Yoshi sideways!)
                        Vec3 normal = (b.Position - a.Position).NormalizedXZ();
                        if (normal.LengthSq < 1e-4f) normal = Vec3.Right;
                        float overlap = 2.25f - distXZ;

                        float totalMass = a.Character.Mass + b.Character.Mass;
                        float ratioA = b.Character.Mass / totalMass;
                        float ratioB = a.Character.Mass / totalMass;

                        a.Position -= normal * (overlap * ratioA);
                        b.Position += normal * (overlap * ratioB);

                        Vec3 relVel = b.Velocity - a.Velocity;
                        float sepVel = Vec3.Dot(relVel, normal);
                        if (sepVel < 0f)
                        {
                            float impulse = -sepVel * 1.25f;
                            a.Velocity -= normal * (impulse * ratioA);
                            b.Velocity += normal * (impulse * ratioB);

                            if (impulse > 10f)
                            {
                                if (a.IsHuman)
                                {
                                    N64AudioSynth.Instance.PlaySfx(SfxId.WallBump, 0.55f);
                                    if (padMgr != null) padMgr.TriggerRumble(a.HumanPlayerIndex, 0.4f * ratioA, 0.3f, 0.12f);
                                }
                                if (b.IsHuman)
                                {
                                    N64AudioSynth.Instance.PlaySfx(SfxId.WallBump, 0.55f);
                                    if (padMgr != null) padMgr.TriggerRumble(b.HumanPlayerIndex, 0.4f * ratioB, 0.3f, 0.12f);
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
