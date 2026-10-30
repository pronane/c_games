using System;
using System.Collections.Generic;
using MarioKart64.Audio;
using MarioKart64.Core;
using MarioKart64.Tracks;

namespace MarioKart64.Entities
{
    public enum ItemId
    {
        None = 0,
        Banana = 1,
        TripleBananas = 2,
        GreenShell = 3,
        TripleGreenShells = 4,
        RedShell = 5,
        TripleRedShells = 6,
        SpinyBlueShell = 7,
        FakeItemBox = 8,
        Mushroom = 9,
        TripleMushrooms = 10,
        GoldenMushroom = 11,
        Thunderbolt = 12,
        Boo = 13,
        SuperStar = 14
    }

    public enum WorldItemKind
    {
        Banana = 0,
        FakeItemBox = 1,
        GreenShell = 2,
        RedShell = 3,
        SpinyBlueShell = 4
    }

    public class WorldItemEntity
    {
        public WorldItemKind Kind;
        public int OwnerKartIndex;
        public Vec3 Position;
        public Vec3 Velocity;
        public float Yaw;
        public float Age;
        public float MaxLifetime = 22.0f;
        public int WallBounces;
        public int TrackSegmentHint;
        public int TargetKartIndex = -1;
        public bool HomingActive;
        public bool Alive = true;
    }

    public static class ItemSystem
    {
        public static string GetItemName(ItemId id)
        {
            switch (id)
            {
                case ItemId.Banana:            return "BANANA";
                case ItemId.TripleBananas:     return "BANANA BUNCH";
                case ItemId.GreenShell:        return "GREEN SHELL";
                case ItemId.TripleGreenShells: return "3 GREEN SHELLS";
                case ItemId.RedShell:          return "RED SHELL";
                case ItemId.TripleRedShells:   return "3 RED SHELLS";
                case ItemId.SpinyBlueShell:    return "SPINY SHELL";
                case ItemId.FakeItemBox:       return "FAKE ITEM BOX";
                case ItemId.Mushroom:          return "MUSHROOM";
                case ItemId.TripleMushrooms:   return "3 MUSHROOMS";
                case ItemId.GoldenMushroom:    return "SUPER MUSHROOM";
                case ItemId.Thunderbolt:       return "LIGHTNING";
                case ItemId.Boo:               return "BOO";
                case ItemId.SuperStar:         return "SUPER STAR";
                default:                       return "";
            }
        }

        public static Color4 GetItemColor(ItemId id)
        {
            switch (id)
            {
                case ItemId.Banana:
                case ItemId.TripleBananas:     return Color4.FromBytes(252, 226, 38);
                case ItemId.GreenShell:
                case ItemId.TripleGreenShells: return Color4.FromBytes(42, 205, 62);
                case ItemId.RedShell:
                case ItemId.TripleRedShells:   return Color4.FromBytes(235, 38, 38);
                case ItemId.SpinyBlueShell:    return Color4.FromBytes(45, 115, 252);
                case ItemId.FakeItemBox:       return Color4.FromBytes(245, 75, 165);
                case ItemId.Mushroom:
                case ItemId.TripleMushrooms:   return Color4.FromBytes(238, 52, 42);
                case ItemId.GoldenMushroom:    return Color4.FromBytes(255, 205, 28);
                case ItemId.Thunderbolt:       return Color4.FromBytes(255, 242, 48);
                case ItemId.Boo:               return Color4.FromBytes(232, 238, 255);
                case ItemId.SuperStar:         return Color4.FromBytes(255, 222, 45);
                default:                       return new Color4(1f, 1f, 1f, 0.3f);
            }
        }

        // Authentic MK64 Position-Weighted Item Roulette
        public static ItemId RollItem(int rank1Based, int totalRacers, bool isBattleMode, Random rng)
        {
            int r = rng.Next(100);
            if (isBattleMode)
            {
                if (r < 22) return ItemId.GreenShell;
                if (r < 42) return ItemId.TripleGreenShells;
                if (r < 62) return ItemId.RedShell;
                if (r < 74) return ItemId.Banana;
                if (r < 82) return ItemId.FakeItemBox;
                if (r < 92) return ItemId.SuperStar;
                return ItemId.Boo;
            }

            if (rank1Based <= 1)
            {
                // 1st Place: Defensive traps & skill items
                if (r < 36) return ItemId.Banana;
                if (r < 64) return ItemId.GreenShell;
                if (r < 82) return ItemId.FakeItemBox;
                if (r < 94) return ItemId.Mushroom;
                return ItemId.Boo;
            }
            else if (rank1Based <= 3)
            {
                if (r < 16) return ItemId.Banana;
                if (r < 30) return ItemId.TripleBananas;
                if (r < 46) return ItemId.GreenShell;
                if (r < 66) return ItemId.RedShell;
                if (r < 80) return ItemId.Mushroom;
                if (r < 90) return ItemId.TripleGreenShells;
                if (r < 96) return ItemId.Boo;
                return ItemId.SuperStar;
            }
            else if (rank1Based <= 5)
            {
                if (r < 18) return ItemId.RedShell;
                if (r < 34) return ItemId.TripleRedShells;
                if (r < 48) return ItemId.TripleGreenShells;
                if (r < 64) return ItemId.TripleMushrooms;
                if (r < 76) return ItemId.SuperStar;
                if (r < 86) return ItemId.Boo;
                if (r < 94) return ItemId.GoldenMushroom;
                return ItemId.SpinyBlueShell;
            }
            else
            {
                // 6th - 8th Place: Powerhouse comeback items!
                if (r < 20) return ItemId.TripleRedShells;
                if (r < 38) return ItemId.TripleMushrooms;
                if (r < 56) return ItemId.GoldenMushroom;
                if (r < 74) return ItemId.SuperStar;
                if (r < 88) return ItemId.Thunderbolt;
                return ItemId.SpinyBlueShell;
            }
        }

        public static void UpdateWorldItems(
            List<WorldItemEntity> items,
            Kart[] karts,
            TrackData track,
            float dt)
        {
            for (int i = items.Count - 1; i >= 0; i--)
            {
                WorldItemEntity it = items[i];
                if (!it.Alive)
                {
                    items.RemoveAt(i);
                    continue;
                }

                it.Age += dt;
                if (it.Age > it.MaxLifetime)
                {
                    items.RemoveAt(i);
                    continue;
                }

                // Stationary traps (Bananas & Fake Item Boxes) settle onto ground
                if (it.Kind == WorldItemKind.Banana || it.Kind == WorldItemKind.FakeItemBox)
                {
                    it.Position += it.Velocity * dt;
                    it.Velocity.X *= 0.90f;
                    it.Velocity.Z *= 0.90f;
                    it.Velocity.Y -= 36f * dt;

                    SurfaceQueryResult sq = track.SampleSurface(it.Position, it.TrackSegmentHint);
                    it.TrackSegmentHint = sq.SegmentIndex;
                    if (sq.FellInLiquidOrVoid)
                    {
                        items.RemoveAt(i);
                        continue;
                    }
                    if (it.Position.Y <= sq.GroundY + 0.55f)
                    {
                        it.Position.Y = sq.GroundY + 0.55f;
                        it.Velocity = Vec3.Zero;
                    }
                }
                else
                {
                    // Moving Shells (Green, Red, Spiny Blue)
                    UpdateMovingShell(it, karts, track, dt);
                    if (!it.Alive)
                    {
                        items.RemoveAt(i);
                        continue;
                    }
                }

                // Check collision with Karts
                float hitRadius = (it.Kind == WorldItemKind.FakeItemBox) ? 2.1f : 1.85f;
                for (int k = 0; k < karts.Length; k++)
                {
                    Kart victim = karts[k];
                    if (victim.IsEliminated || victim.LakituRescueTimer > 0f) continue;
                    // Brief self-hit immunity right after launch
                    if (k == it.OwnerKartIndex && it.Age < 0.45f) continue;

                    float distXZ = Vec3.DistanceXZ(it.Position, victim.Position);
                    float distY = Math.Abs(it.Position.Y - (victim.Position.Y + 0.8f));
                    if (distXZ < hitRadius && distY < 2.6f)
                    {
                        // Check orbiting shells or trailed item shield!
                        if (victim.OrbitItemCount > 0 && it.Kind != WorldItemKind.SpinyBlueShell)
                        {
                            victim.OrbitItemCount--;
                            if (victim.OrbitItemCount <= 0) victim.ActiveOrbitType = ItemId.None;
                            N64AudioSynth.Instance.PlaySfx(SfxId.WallBump, 0.8f);
                            it.Alive = false;
                            break;
                        }

                        if (victim.BooTimer > 0f && it.Kind != WorldItemKind.FakeItemBox)
                        {
                            // Ghostly Boo phases right through shells & bananas!
                            continue;
                        }

                        if (victim.StarmanTimer > 0f)
                        {
                            // Starman destroys the obstacle cleanly!
                            N64AudioSynth.Instance.PlaySfx(SfxId.WallBump, 0.8f);
                            it.Alive = false;
                            break;
                        }

                        if (it.Kind == WorldItemKind.Banana)
                        {
                            victim.TriggerBananaHit();
                            it.Alive = false;
                            break;
                        }
                        else if (it.Kind == WorldItemKind.FakeItemBox)
                        {
                            victim.TriggerHeavyTumble();
                            it.Alive = false;
                            break;
                        }
                        else if (it.Kind == WorldItemKind.SpinyBlueShell)
                        {
                            // Authentic MK64 Ground-Skimming Spiny Shell:
                            // Knocks aside ANY kart in its path AND keeps going until it hits 1st Place!
                            victim.TriggerHeavyTumble();
                            if (victim.RaceRank == 1 || k == it.TargetKartIndex)
                            {
                                it.Alive = false;
                                break;
                            }
                        }
                        else
                        {
                            victim.TriggerHeavyTumble();
                            it.Alive = false;
                            break;
                        }
                    }
                }
            }
        }

        private static void UpdateMovingShell(WorldItemEntity it, Kart[] karts, TrackData track, float dt)
        {
            float targetSpeed = (it.Kind == WorldItemKind.SpinyBlueShell) ? 102.0f : 84.0f;

            if (it.Kind == WorldItemKind.SpinyBlueShell && !track.IsBattleArena && track.Segments != null)
            {
                // Ground-skimming MK64 Spiny Shell: tracks centerline until close to 1st place kart!
                int leaderIdx = 0;
                for (int k = 0; k < karts.Length; k++)
                {
                    if (karts[k].RaceRank == 1) { leaderIdx = k; break; }
                }
                it.TargetKartIndex = leaderIdx;
                Kart leader = karts[leaderIdx];

                float distToLeader = Vec3.Distance(it.Position, leader.Position);
                if (distToLeader < 28.0f)
                {
                    Vec3 toLeader = (leader.Position - it.Position).NormalizedXZ();
                    it.Velocity = toLeader * targetSpeed;
                }
                else
                {
                    int lookSeg = (it.TrackSegmentHint + 4) % track.Segments.Length;
                    Vec3 wp = track.Segments[lookSeg].Center;
                    Vec3 dir = (wp - it.Position).NormalizedXZ();
                    it.Velocity = Vec3.Lerp(it.Velocity.NormalizedXZ(), dir, 12f * dt).NormalizedXZ() * targetSpeed;
                }
            }
            else if (it.Kind == WorldItemKind.RedShell && it.HomingActive)
            {
                // Red Shell: guides along track spline until within 32m of target kart, then homes directly!
                Kart target = (it.TargetKartIndex >= 0 && it.TargetKartIndex < karts.Length) ? karts[it.TargetKartIndex] : null;
                if (target != null && !target.IsEliminated)
                {
                    float dist = Vec3.Distance(it.Position, target.Position);
                    if (dist < 34f || track.IsBattleArena)
                    {
                        Vec3 toTarget = (target.Position - it.Position).NormalizedXZ();
                        Vec3 steered = Vec3.Lerp(it.Velocity.NormalizedXZ(), toTarget, 8.5f * dt).NormalizedXZ();
                        it.Velocity = steered * targetSpeed;
                    }
                    else if (track.Segments != null)
                    {
                        int lookSeg = (it.TrackSegmentHint + 3) % track.Segments.Length;
                        Vec3 toRoad = (track.Segments[lookSeg].Center - it.Position).NormalizedXZ();
                        Vec3 steered = Vec3.Lerp(it.Velocity.NormalizedXZ(), toRoad, 9.0f * dt).NormalizedXZ();
                        it.Velocity = steered * targetSpeed;
                    }
                }
            }

            it.Position += it.Velocity * dt;
            it.Yaw += 12.0f * dt;

            SurfaceQueryResult sq = track.SampleSurface(it.Position, it.TrackSegmentHint);
            it.TrackSegmentHint = sq.SegmentIndex;

            if (sq.FellInLiquidOrVoid)
            {
                it.Alive = false;
                return;
            }

            it.Position.Y = sq.GroundY + 0.65f;

            if (sq.HitSolidWall)
            {
                if (it.Kind == WorldItemKind.RedShell)
                {
                    // Authentic MK64: Red Shells shatter if they slam straight into a solid wall!
                    it.Alive = false;
                    return;
                }
                else if (it.Kind == WorldItemKind.GreenShell)
                {
                    // Green Shells ricochet up to 6 times!
                    Vec3 n = sq.WallPushNormal.NormalizedXZ();
                    it.Position += n * (sq.WallPenetration + 0.3f);
                    float dot = Vec3.Dot(it.Velocity, n);
                    if (dot < 0f)
                    {
                        it.Velocity = (it.Velocity - n * (2.0f * dot)).NormalizedXZ() * targetSpeed;
                        it.WallBounces++;
                        if (it.WallBounces > 6) it.Alive = false;
                    }
                }
            }
        }
    }
}
