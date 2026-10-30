using System;
using System.Collections.Generic;
using MarioKart64.Audio;
using MarioKart64.Core;
using MarioKart64.Input;
using MarioKart64.Tracks;

namespace MarioKart64.Entities
{
    public class Kart
    {
        public int SlotIndex;
        public bool IsHuman;
        public int HumanPlayerIndex = -1;
        public CharacterSpec Character;

        // Spatial & Physics State
        public Vec3 Position;
        public Vec3 Velocity;
        public float Yaw;             // Heading angle in radians (0 = +Z, PI/2 = +X)
        public float VisualSteerLean; // Smooth driver lean & front-wheel turn (-1..+1)
        public float WheelSpinPhase;
        public float ForwardSpeed;
        public float VerticalVel;
        public bool IsGrounded = true;
        public SurfaceType CurrentSurface = SurfaceType.Asphalt;
        public int CurrentSegmentIndex;
        public int CurrentBranchIndex = -1;

        // Countdown Rocket Start
        public float StartRevCharge;
        public bool StartOverheated;
        public float BurnoutTimer;

        // Hop, Power-Slide & Mini-Turbo ("White -> Yellow -> Red-Orange E-Smoke")
        public bool IsHopping;
        public bool IsDrifting;
        public int DriftDirection;    // -1 Left, +1 Right
        public float DriftTimer;
        public int MiniTurboStage;    // 0=White, 1=Yellow, 2=OrangeRed (Ready!)
        public int DriftCounterSteerSign;
        public int DriftInflections;

        // Boosts & Slipstream
        public float BoostTimer;
        public float BoostStrength = 1.0f;
        public float GoldenMushroomWindowTimer;
        public float DraftChargeTimer;

        // Status Effects & Reactions
        public float SpinOutTimer;
        public float BananaGraceTimer; // Window for MK64 Banana Braking!
        public float SavedNoteTimer;   // Displays golden '♪' note when Banana Brake succeeds!
        public float TumbleTimer;
        public float TumblePitch;
        public float SquashedTimer;
        public float ShrinkTimer;
        public float StarmanTimer;
        public float BooTimer;
        public float PostHitInvulnTimer;

        // Lakitu Rescue & Wrong Way
        public float LakituRescueTimer;
        public bool RescuedInIceCube;
        public Vec3 SafeRespawnPos;
        public float SafeRespawnYaw;
        public bool IsGoingWrongWay;
        public float WrongWayDuration;

        // Item Roulette & Held Inventory
        public ItemId HeldItem = ItemId.None;
        public float RouletteTimer;
        public ItemId RouletteDisplayItem = ItemId.Banana;
        public int RemainingSubUses;  // Triple Mushrooms (3..1)
        public ItemId ActiveOrbitType = ItemId.None;
        public int OrbitItemCount;    // 1..3 Orbiting Shells or Trailing Bananas
        public float OrbitAngle;

        // Race Progress & Scoring
        public int Lap = 1;
        public int QuarterMask = 1;   // Bits 0,1,2,3 track 4 quarters of the course
        public float RaceProgress;
        public int RaceRank = 1;
        public bool FinishedRace;
        public float FinishTimeSeconds;
        public float CurrentLapStartTime;
        public float BestLapSeconds = 999f;
        public int GrandPrixPoints;

        // Battle Mode State (3 Balloons!)
        public int Balloons = 3;
        public bool IsEliminated;

        // AI Driver internal fields
        public int AiPreferredBranch = -1;
        public float AiItemDelayTimer;
        public float AiLaneOffset;
        public float AiDriftCheckTimer;

        public Vec3 ForwardDir
        {
            get { return new Vec3((float)Math.Sin(Yaw), 0f, (float)Math.Cos(Yaw)); }
        }

        public Vec3 RightDir
        {
            get { return new Vec3(-(float)Math.Cos(Yaw), 0f, (float)Math.Sin(Yaw)); }
        }

        public void ResetForTrack(TrackData track, int gridIndex, bool isTimeTrial)
        {
            Velocity = Vec3.Zero;
            ForwardSpeed = 0f;
            VerticalVel = 0f;
            IsGrounded = true;
            StartRevCharge = 0f;
            StartOverheated = false;
            BurnoutTimer = 0f;
            IsHopping = false;
            IsDrifting = false;
            DriftDirection = 0;
            DriftTimer = 0f;
            MiniTurboStage = 0;
            BoostTimer = 0f;
            GoldenMushroomWindowTimer = 0f;
            DraftChargeTimer = 0f;
            SpinOutTimer = 0f;
            BananaGraceTimer = 0f;
            SavedNoteTimer = 0f;
            TumbleTimer = 0f;
            SquashedTimer = 0f;
            ShrinkTimer = 0f;
            StarmanTimer = 0f;
            BooTimer = 0f;
            PostHitInvulnTimer = 0f;
            LakituRescueTimer = 0f;
            RescuedInIceCube = false;
            IsGoingWrongWay = false;
            WrongWayDuration = 0f;

            HeldItem = ItemId.None;
            RouletteTimer = 0f;
            RemainingSubUses = 0;
            ActiveOrbitType = ItemId.None;
            OrbitItemCount = 0;

            Lap = 1;
            QuarterMask = 1;
            RaceRank = gridIndex + 1;
            FinishedRace = false;
            FinishTimeSeconds = 0f;
            CurrentLapStartTime = 0f;
            BestLapSeconds = 999f;
            Balloons = 3;
            IsEliminated = false;

            if (isTimeTrial && IsHuman)
            {
                // Authentic MK64 Time Trials: start with Triple Mushrooms!
                HeldItem = ItemId.TripleMushrooms;
                RemainingSubUses = 3;
            }

            if (track.IsBattleArena)
            {
                int sp = gridIndex % track.BattleSpawnPositions.Length;
                Position = track.BattleSpawnPositions[sp];
                Yaw = track.BattleSpawnYaws[sp];
                SafeRespawnPos = Position;
                SafeRespawnYaw = Yaw;
            }
            else
            {
                int totalSegs = track.Segments.Length;
                // Staggered 2-column MK64 starting grid behind finish line
                int row = gridIndex / 2;
                int col = gridIndex % 2;
                int segIdx = (totalSegs - 4 - row * 2 + totalSegs) % totalSegs;
                TrackSegment seg = track.Segments[segIdx];
                float lat = (col == 0 ? -3.4f : 3.4f);
                Position = seg.Center + seg.Right * lat + new Vec3(0f, 0.2f, 0f);
                Yaw = (float)Math.Atan2(seg.Forward.X, seg.Forward.Z);
                CurrentSegmentIndex = segIdx;
                SafeRespawnPos = seg.Center + new Vec3(0f, 0.5f, 0f);
                SafeRespawnYaw = Yaw;
            }
        }

        public void UpdateCountdownRev(PlayerInputState input, float countdownTimeRemaining, float dt)
        {
            if (input == null) return;
            if (input.Accelerate)
            {
                // Holding gas way too early (> 1.45s before GO) overheats the engine!
                if (countdownTimeRemaining > 1.45f)
                {
                    StartOverheated = true;
                }
                StartRevCharge = MathUtil.Clamp(StartRevCharge + dt * 1.35f, 0f, 1.5f);
            }
            else
            {
                StartRevCharge = Math.Max(0f, StartRevCharge - dt * 2.2f);
                if (countdownTimeRemaining > 0.65f)
                {
                    // Letting off gas clears early overheat if re-timed properly!
                    StartOverheated = false;
                }
            }
        }

        public void ApplyCountdownLaunch(EasySmxControllerManager padMgr)
        {
            if (StartOverheated && StartRevCharge > 0.85f)
            {
                BurnoutTimer = 1.05f;
                ForwardSpeed = 4.0f;
                if (IsHuman)
                {
                    N64AudioSynth.Instance.PlaySfx(SfxId.BananaSlip, 0.7f);
                    if (padMgr != null) padMgr.TriggerRumble(HumanPlayerIndex, 0.7f, 0.4f, 0.45f);
                }
            }
            else if (StartRevCharge >= 0.42f && StartRevCharge <= 1.25f)
            {
                // Sweet-spot MK64 Rocket Start!
                BoostTimer = 1.15f;
                BoostStrength = 1.28f;
                ForwardSpeed = Character.TopSpeed * 0.95f;
                if (IsHuman)
                {
                    N64AudioSynth.Instance.PlaySfx(SfxId.BoostWhoosh, 1.0f);
                    if (padMgr != null) padMgr.TriggerRumble(HumanPlayerIndex, 0.5f, 0.9f, 0.35f);
                }
            }
        }

        public void TriggerBananaHit()
        {
            if (StarmanTimer > 0f || BooTimer > 0f || PostHitInvulnTimer > 0f || LakituRescueTimer > 0f) return;
            if (SpinOutTimer > 0f || TumbleTimer > 0f) return;

            SpinOutTimer = 1.08f;
            BananaGraceTimer = 0.24f; // 240ms window to tap B for authentic MK64 Banana Braking!
            IsDrifting = false;
            MiniTurboStage = 0;
            if (IsHuman) N64AudioSynth.Instance.PlaySfx(SfxId.BananaSlip, 0.95f);
        }

        public void TriggerHeavyTumble()
        {
            if (StarmanTimer > 0f || PostHitInvulnTimer > 0f || LakituRescueTimer > 0f) return;
            if (TumbleTimer > 0f) return;

            TumbleTimer = 1.35f;
            SpinOutTimer = 0f;
            BananaGraceTimer = 0f;
            IsDrifting = false;
            MiniTurboStage = 0;
            VerticalVel = 15.5f;
            IsGrounded = false;
            ForwardSpeed *= 0.25f;
            PostHitInvulnTimer = 1.85f;

            if (IsHuman) N64AudioSynth.Instance.PlaySfx(SfxId.CrashExplosion, 1.0f);
        }

        public void TriggerSquash()
        {
            if (StarmanTimer > 0f || BooTimer > 0f || LakituRescueTimer > 0f) return;
            SquashedTimer = 2.4f;
            ForwardSpeed *= 0.35f;
            IsDrifting = false;
            if (IsHuman) N64AudioSynth.Instance.PlaySfx(SfxId.Squash, 1.0f);
        }

        public void LoseBattleBalloon()
        {
            if (Balloons <= 0 || IsEliminated) return;
            Balloons--;
            if (Balloons <= 0)
            {
                Balloons = 0;
                IsEliminated = true;
            }
        }

        public void UpdatePhysics(
            PlayerInputState input,
            TrackData track,
            Kart[] allKarts,
            List<WorldItemEntity> worldItems,
            EasySmxControllerManager padMgr,
            EngineClass engineClass,
            float raceElapsedSec,
            Random rng,
            float dt)
        {
            if (IsEliminated) return;

            // Tick status timers
            OrbitAngle += 4.6f * dt;
            if (PostHitInvulnTimer > 0f) PostHitInvulnTimer -= dt;
            if (SavedNoteTimer > 0f) SavedNoteTimer -= dt;
            if (SquashedTimer > 0f) SquashedTimer -= dt;
            if (ShrinkTimer > 0f) ShrinkTimer -= dt;
            if (BooTimer > 0f) BooTimer -= dt;
            if (GoldenMushroomWindowTimer > 0f)
            {
                GoldenMushroomWindowTimer -= dt;
                if (GoldenMushroomWindowTimer <= 0f && HeldItem == ItemId.GoldenMushroom)
                {
                    HeldItem = ItemId.None;
                }
            }
            if (StarmanTimer > 0f)
            {
                StarmanTimer -= dt;
                if (StarmanTimer <= 0f && IsHuman && HumanPlayerIndex == 0)
                {
                    N64AudioSynth.Instance.SetStarmanOverride(false);
                }
            }

            // Item Roulette tick
            if (RouletteTimer > 0f)
            {
                float prev = RouletteTimer;
                RouletteTimer -= dt;
                if (input != null && input.ItemPressed && RouletteTimer > 0.15f)
                {
                    // Fast-stop roulette with Z/LB!
                    RouletteTimer = 0.01f;
                }
                if ((int)(prev * 11f) != (int)(RouletteTimer * 11f))
                {
                    RouletteDisplayItem = (ItemId)(1 + rng.Next(14));
                    if (IsHuman) N64AudioSynth.Instance.PlaySfx(SfxId.ItemRouletteTick, 0.65f);
                }
                if (RouletteTimer <= 0f)
                {
                    RouletteTimer = 0f;
                    HeldItem = ItemSystem.RollItem(RaceRank, allKarts.Length, track.IsBattleArena, rng);
                    if (HeldItem == ItemId.TripleMushrooms) RemainingSubUses = 3;
                    else RemainingSubUses = 1;
                    if (IsHuman) N64AudioSynth.Instance.PlaySfx(SfxId.ItemRouletteLock, 0.9f);
                }
            }
            else if (input != null && input.ItemPressed)
            {
                UseHeldItem(input, allKarts, worldItems, track, rng, padMgr);
            }

            // Lakitu Rescue sequence
            if (LakituRescueTimer > 0f)
            {
                LakituRescueTimer -= dt;
                ForwardSpeed = 0f;
                Velocity = Vec3.Zero;
                // Lift kart smoothly toward SafeRespawnPos
                Position = Vec3.Lerp(Position, SafeRespawnPos + new Vec3(0f, 2.2f, 0f), 5.0f * dt);
                Yaw = MathUtil.LerpAngle(Yaw, SafeRespawnYaw, 6.0f * dt);
                if (LakituRescueTimer <= 0f)
                {
                    Position = SafeRespawnPos;
                    Yaw = SafeRespawnYaw;
                    VerticalVel = 0f;
                    IsGrounded = true;
                    RescuedInIceCube = false;
                    PostHitInvulnTimer = 1.6f;
                }
                return;
            }

            // Speed multiplier by CC class
            float ccScale = 1.0f;
            if (engineClass == EngineClass.CC50) ccScale = 0.84f;
            else if (engineClass == EngineClass.CC100) ccScale = 1.00f;
            else if (engineClass == EngineClass.CC150) ccScale = 1.13f;
            else if (engineClass == EngineClass.ExtraMirror) ccScale = 1.06f;

            float maxSpd = Character.TopSpeed * ccScale;
            if (ShrinkTimer > 0f) maxSpd *= 0.64f;
            if (SquashedTimer > 0f) maxSpd *= 0.56f;
            if (StarmanTimer > 0f) maxSpd *= 1.22f;
            if (BoostTimer > 0f)
            {
                BoostTimer -= dt;
                maxSpd *= BoostStrength;
            }

            // Off-road penalty (ignored during Boost, Starman, or Boo!)
            bool immuneOffRoad = (BoostTimer > 0f || StarmanTimer > 0f || BooTimer > 0f);
            bool onOffRoad =
                CurrentSurface == SurfaceType.OffRoadGrass ||
                CurrentSurface == SurfaceType.OffRoadSand ||
                CurrentSurface == SurfaceType.OffRoadSnow ||
                CurrentSurface == SurfaceType.OffRoadMud;

            if (onOffRoad && !immuneOffRoad)
            {
                maxSpd *= Character.OffRoadRetention;
                if (IsHuman && ForwardSpeed > 18f && padMgr != null)
                {
                    padMgr.TriggerRumble(HumanPlayerIndex, 0.18f, 0.08f, 0.06f);
                }
            }

            // Banana Braking check!
            if (BananaGraceTimer > 0f)
            {
                BananaGraceTimer -= dt;
                if (input != null && input.Brake && Math.Abs(input.Steer) < 0.35f)
                {
                    // Saved from spin-out with MK64 Banana Brake!
                    SpinOutTimer = 0f;
                    BananaGraceTimer = 0f;
                    SavedNoteTimer = 1.15f;
                    ForwardSpeed *= 0.86f;
                    if (IsHuman) N64AudioSynth.Instance.PlaySfx(SfxId.BananaBrakeSaved, 1.0f);
                }
            }

            // Handle Tumble / SpinOut / Burnout vs Normal Driving
            if (TumbleTimer > 0f)
            {
                TumbleTimer -= dt;
                TumblePitch += 11.0f * dt;
                ForwardSpeed = MathUtil.MoveTowards(ForwardSpeed, 0f, 38f * dt);
                if (TumbleTimer <= 0f) TumblePitch = 0f;
            }
            else if (SpinOutTimer > 0f)
            {
                SpinOutTimer -= dt;
                ForwardSpeed = MathUtil.MoveTowards(ForwardSpeed, 0f, 34f * dt);
            }
            else if (BurnoutTimer > 0f)
            {
                BurnoutTimer -= dt;
                ForwardSpeed = MathUtil.MoveTowards(ForwardSpeed, 6f, 20f * dt);
            }
            else if (input != null)
            {
                float steerIn = MathUtil.Clamp(input.Steer, -1f, 1f);
                VisualSteerLean = MathUtil.Lerp(VisualSteerLean, steerIn, 11f * dt);

                // Authentic MK64 AB Spin Turn when stopped or nearly stopped!
                if (input.Accelerate && input.Brake && Math.Abs(ForwardSpeed) < 8.0f && Math.Abs(steerIn) > 0.2f)
                {
                    ForwardSpeed = MathUtil.MoveTowards(ForwardSpeed, 0f, 35f * dt);
                    Yaw -= steerIn * 3.4f * dt;
                }
                else
                {
                    // Acceleration / Braking / Coasting
                    if (BoostTimer > 0f)
                    {
                        ForwardSpeed = MathUtil.MoveTowards(ForwardSpeed, maxSpd, Character.Acceleration * 3.0f * dt);
                    }
                    else if (input.Accelerate)
                    {
                        // Smooth MK64 two-slope acceleration curve
                        float ratio = Math.Abs(ForwardSpeed) / Math.Max(1f, maxSpd);
                        float accelFactor = (ratio < 0.55f) ? 1.25f : 0.75f;
                        ForwardSpeed = MathUtil.MoveTowards(ForwardSpeed, maxSpd, Character.Acceleration * accelFactor * dt);
                    }
                    else if (input.Brake)
                    {
                        if (ForwardSpeed > 1.0f)
                            ForwardSpeed = MathUtil.MoveTowards(ForwardSpeed, 0f, 52f * dt);
                        else
                            ForwardSpeed = MathUtil.MoveTowards(ForwardSpeed, -18f * ccScale, 24f * dt);
                    }
                    else
                    {
                        ForwardSpeed = MathUtil.MoveTowards(ForwardSpeed, 0f, 19f * dt);
                    }

                    // Hop & Power-Slide / Mini-Turbo!
                    if (input.DriftHopPressed && IsGrounded && ForwardSpeed > 18f)
                    {
                        IsHopping = true;
                        IsGrounded = false;
                        VerticalVel = 10.2f;
                        if (IsHuman) N64AudioSynth.Instance.PlaySfx(SfxId.Hop, 0.85f);
                    }

                    if (!input.DriftHopHeld && IsDrifting)
                    {
                        // Release R -> Fire Mini-Turbo if Stage 2 charged!
                        if (MiniTurboStage >= 2)
                        {
                            BoostTimer = 1.25f;
                            BoostStrength = 1.26f;
                            if (IsHuman)
                            {
                                N64AudioSynth.Instance.PlaySfx(SfxId.BoostWhoosh, 0.95f);
                                if (padMgr != null) padMgr.TriggerRumble(HumanPlayerIndex, 0.35f, 0.85f, 0.28f);
                            }
                        }
                        IsDrifting = false;
                        DriftDirection = 0;
                        MiniTurboStage = 0;
                        DriftTimer = 0f;
                    }

                    // Steering & Power-Slide turning
                    float speedTurnScale = MathUtil.Clamp(Math.Abs(ForwardSpeed) / 14f, 0.35f, 1.0f);
                    if (ForwardSpeed < -0.5f) speedTurnScale = -0.75f;

                    if (IsDrifting)
                    {
                        DriftTimer += dt;
                        // Base drift arc + player fine-adjustment (+1 = Right turn decreases Yaw in OpenGL right-handed space!)
                        float driftTurn = (DriftDirection * 0.72f + steerIn * 0.52f) * Character.TurnRate * 1.18f;
                        Yaw -= driftTurn * dt;

                        // Counter-steering charges MK64 Mini-Turbo (White -> Yellow -> Orange/Red)!
                        int curSign = (steerIn < -0.25f) ? -1 : ((steerIn > 0.25f) ? 1 : 0);
                        if (curSign != 0 && curSign != DriftCounterSteerSign)
                        {
                            DriftCounterSteerSign = curSign;
                            DriftInflections++;
                        }

                        int prevStage = MiniTurboStage;
                        if (DriftTimer > 0.42f && DriftInflections >= 1) MiniTurboStage = 1;
                        if (DriftTimer > 0.92f && DriftInflections >= 2) MiniTurboStage = 2;
                        if (MiniTurboStage == 2 && prevStage < 2 && IsHuman)
                        {
                            N64AudioSynth.Instance.PlaySfx(SfxId.MiniTurboReady, 0.9f);
                        }
                    }
                    else
                    {
                        float iceSlip = (CurrentSurface == SurfaceType.Ice) ? 0.76f : 1.0f;
                        Yaw -= steerIn * Character.TurnRate * speedTurnScale * iceSlip * dt;
                    }
                }
            }

            // Slipstream / Drafting check behind karts ahead
            bool draftingNow = false;
            if (ForwardSpeed > 28f && BoostTimer <= 0f)
            {
                Vec3 myFwd = ForwardDir;
                for (int i = 0; i < allKarts.Length; i++)
                {
                    Kart other = allKarts[i];
                    if (other == this || other.IsEliminated) continue;
                    Vec3 diff = other.Position - Position;
                    float dist = diff.LengthXZ;
                    if (dist > 4.0f && dist < 21.0f && Math.Abs(diff.Y) < 3.0f)
                    {
                        float align = Vec3.Dot(diff.NormalizedXZ(), myFwd);
                        if (align > 0.90f)
                        {
                            draftingNow = true;
                            break;
                        }
                    }
                }
            }
            if (draftingNow)
            {
                DraftChargeTimer += dt;
                if (DraftChargeTimer >= 1.35f)
                {
                    DraftChargeTimer = 0f;
                    BoostTimer = 0.95f;
                    BoostStrength = 1.20f;
                    if (IsHuman) N64AudioSynth.Instance.PlaySfx(SfxId.BoostWhoosh, 0.8f);
                }
            }
            else
            {
                DraftChargeTimer = Math.Max(0f, DraftChargeTimer - dt * 1.5f);
            }

            // Integrate horizontal velocity (blend grip so ice & power-slides visibly slide!)
            Vec3 desiredHoriz = ForwardDir * ForwardSpeed;
            float lateralGrip = (CurrentSurface == SurfaceType.Ice) ? 3.4f : (IsDrifting ? 6.8f : 13.5f);
            Velocity.X = MathUtil.Lerp(Velocity.X, desiredHoriz.X, MathUtil.Clamp(lateralGrip * dt, 0f, 1f));
            Velocity.Z = MathUtil.Lerp(Velocity.Z, desiredHoriz.Z, MathUtil.Clamp(lateralGrip * dt, 0f, 1f));

            // Gravity
            if (!IsGrounded)
            {
                VerticalVel -= 38.0f * dt;
            }
            Position.X += Velocity.X * dt;
            Position.Z += Velocity.Z * dt;
            Position.Y += VerticalVel * dt;

            WheelSpinPhase += ForwardSpeed * 0.45f * dt;

            // Sample 3D Track / Battle Arena Surface & Walls
            SurfaceQueryResult sq = track.SampleSurface(Position, CurrentSegmentIndex);
            CurrentSegmentIndex = sq.SegmentIndex;
            CurrentBranchIndex = sq.BranchIndex;
            CurrentSurface = sq.Surface;

            if (sq.FellInLiquidOrVoid)
            {
                TriggerLakituRescue(track, sq.LiquidIsIceWater, padMgr);
                return;
            }

            // Ground contact & Ramp / Boost Pad handling
            if (Position.Y <= sq.GroundY + 0.08f && VerticalVel <= 0.5f)
            {
                bool justLanded = !IsGrounded;
                Position.Y = sq.GroundY;
                VerticalVel = 0f;
                IsGrounded = true;

                if (justLanded && IsHopping)
                {
                    IsHopping = false;
                    // Initiate Power-Slide if holding R + Steering on landing!
                    if (input != null && input.DriftHopHeld && Math.Abs(input.Steer) > 0.22f && ForwardSpeed > 20f)
                    {
                        IsDrifting = true;
                        DriftDirection = (input.Steer < 0f) ? -1 : 1;
                        DriftTimer = 0f;
                        MiniTurboStage = 0;
                        DriftInflections = 0;
                        DriftCounterSteerSign = DriftDirection;
                    }
                }

                // Update safe Lakitu respawn anchor when cleanly on road
                if (!onOffRoad && (sq.Flags & SegmentFlags.JumpRamp) == 0)
                {
                    if (track.IsBattleArena)
                    {
                        SafeRespawnPos = Position + new Vec3(0f, 0.4f, 0f);
                        SafeRespawnYaw = Yaw;
                    }
                    else if (track.Segments != null)
                    {
                        TrackSegment seg = track.Segments[sq.SegmentIndex];
                        SafeRespawnPos = seg.Center + new Vec3(0f, 0.5f, 0f);
                        SafeRespawnYaw = (float)Math.Atan2(seg.Forward.X, seg.Forward.Z);
                    }
                }

                // Boost Pad!
                if ((sq.Flags & SegmentFlags.BoostPad) != 0)
                {
                    if (BoostTimer < 0.6f)
                    {
                        BoostTimer = 1.15f;
                        BoostStrength = 1.32f;
                        ForwardSpeed = Math.Max(ForwardSpeed, Character.TopSpeed * 1.25f);
                        if (IsHuman) N64AudioSynth.Instance.PlaySfx(SfxId.BoostWhoosh, 0.9f);
                    }
                }

                // Jump Ramp launch! (Royal Raceway, DK River Jump, Wario Stadium, Koopa Cave!)
                if ((sq.Flags & SegmentFlags.JumpRamp) != 0 && ForwardSpeed > 26f)
                {
                    IsGrounded = false;
                    VerticalVel = 18.5f + ForwardSpeed * 0.14f;
                    Position.Y += 0.35f;
                }
            }
            else if (Position.Y > sq.GroundY + 0.35f)
            {
                IsGrounded = false;
            }

            // Solid Wall / Guardrail Collision
            if (sq.HitSolidWall)
            {
                Vec3 n = sq.WallPushNormal.NormalizedXZ();
                Position += n * (sq.WallPenetration + 0.12f);
                float intoWall = Vec3.Dot(Velocity, n);
                if (intoWall < 0f)
                {
                    Velocity -= n * (intoWall * 1.35f);
                    ForwardSpeed *= 0.82f;
                    if (Math.Abs(intoWall) > 12f && IsHuman)
                    {
                        N64AudioSynth.Instance.PlaySfx(SfxId.WallBump, 0.7f);
                        if (padMgr != null) padMgr.TriggerRumble(HumanPlayerIndex, 0.55f, 0.35f, 0.14f);
                    }
                }
            }

            // Item Box Pickup Check
            for (int b = 0; b < track.ItemBoxes.Count; b++)
            {
                ItemBoxSpawn box = track.ItemBoxes[b];
                if (!box.Active) continue;
                float dXZ = Vec3.DistanceXZ(Position, box.Position);
                float dY = Math.Abs((Position.Y + 1.0f) - box.Position.Y);
                if (dXZ < 2.55f && dY < 2.8f)
                {
                    box.Active = false;
                    box.RespawnTimer = 4.5f;
                    track.ItemBoxes[b] = box;

                    if (HeldItem == ItemId.None && RouletteTimer <= 0f && OrbitItemCount == 0)
                    {
                        RouletteTimer = 2.15f;
                    }
                    if (IsHuman) N64AudioSynth.Instance.PlaySfx(SfxId.ItemRouletteTick, 0.9f);
                }
            }

            // Lap & Race Progress Tracking (for non-Battle tracks)
            if (!track.IsBattleArena && track.Segments != null)
            {
                UpdateLapAndProgress(track, raceElapsedSec, sq);
            }
        }

        private void TriggerLakituRescue(TrackData track, bool iceWater, EasySmxControllerManager padMgr)
        {
            LakituRescueTimer = 1.65f;
            RescuedInIceCube = iceWater;
            IsDrifting = false;
            MiniTurboStage = 0;
            BoostTimer = 0f;
            if (track.IsBattleArena)
            {
                // Falling into Lava on Big Donut or off Skyscraper costs a Balloon in MK64!
                LoseBattleBalloon();
            }
            if (IsHuman)
            {
                N64AudioSynth.Instance.PlaySfx(SfxId.LakituWarning, 1.0f);
                if (padMgr != null) padMgr.TriggerRumble(HumanPlayerIndex, 0.75f, 0.75f, 0.4f);
            }
        }

        private void UpdateLapAndProgress(TrackData track, float raceElapsedSec, SurfaceQueryResult sq)
        {
            int totalSegs = track.Segments.Length;
            int seg = sq.SegmentIndex;
            int quarter = (seg * 4) / totalSegs; // 0, 1, 2, 3

            // Mark sequential course quarters so shortcuts work fairly while reverse-cheating is blocked
            if (quarter == 0) QuarterMask |= 1;
            else if (quarter == 1 && (QuarterMask & 1) != 0) QuarterMask |= 2;
            else if (quarter == 2 && (QuarterMask & 2) != 0) QuarterMask |= 4;
            else if (quarter == 3 && (QuarterMask & 4) != 0) QuarterMask |= 8;

            // Detect finish-line crossing (transition from quarter 3 -> quarter 0 with quarters 0,1,2,3 visited)
            if (quarter == 0 && seg < 10 && QuarterMask == 15)
            {
                QuarterMask = 1;
                float lapTime = raceElapsedSec - CurrentLapStartTime;
                if (lapTime > 3.0f && lapTime < BestLapSeconds)
                {
                    BestLapSeconds = lapTime;
                }
                CurrentLapStartTime = raceElapsedSec;

                if (!FinishedRace)
                {
                    Lap++;
                    if (Lap == track.LapCount)
                    {
                        if (IsHuman)
                        {
                            N64AudioSynth.Instance.PlaySfx(SfxId.FinalLapFanfare, 1.0f);
                            N64AudioSynth.Instance.SetTempoMultiplier(1.20f);
                        }
                    }
                    else if (Lap > track.LapCount)
                    {
                        Lap = track.LapCount;
                        FinishedRace = true;
                        FinishTimeSeconds = raceElapsedSec;
                        if (IsHuman) N64AudioSynth.Instance.PlaySfx(SfxId.LapComplete, 1.0f);
                    }
                    else
                    {
                        if (IsHuman) N64AudioSynth.Instance.PlaySfx(SfxId.LapComplete, 0.9f);
                    }
                }
            }

            // Wrong-way detection
            float align = Vec3.Dot(ForwardDir, sq.RoadForward);
            if (align < -0.38f && ForwardSpeed > 5.0f)
            {
                WrongWayDuration += 1.0f / 60.0f;
                IsGoingWrongWay = WrongWayDuration > 0.65f;
            }
            else
            {
                WrongWayDuration = 0f;
                IsGoingWrongWay = false;
            }

            float segFrac = track.Segments[seg].CumulativeDist;
            if (FinishedRace)
            {
                // Keep finished karts ordered strictly by finish time!
                RaceProgress = 1000000f - FinishTimeSeconds * 100f;
            }
            else
            {
                // Adjust for starting grid karts slightly behind segment 0 before crossing start line
                int effectiveLap = (QuarterMask == 1 && seg > totalSegs - 24) ? (Lap - 1) : Lap;
                RaceProgress = effectiveLap * track.TotalLength + segFrac;
            }
        }

        public void UseHeldItem(
            PlayerInputState input,
            Kart[] allKarts,
            List<WorldItemEntity> worldItems,
            TrackData track,
            Random rng,
            EasySmxControllerManager padMgr)
        {
            // First: if kart already has orbiting shells or trailing bananas, launch one!
            if (OrbitItemCount > 0 && ActiveOrbitType != ItemId.None)
            {
                OrbitItemCount--;
                if (ActiveOrbitType == ItemId.TripleBananas || ActiveOrbitType == ItemId.Banana)
                {
                    SpawnBananaOrFakeBox(WorldItemKind.Banana, input, worldItems);
                }
                else if (ActiveOrbitType == ItemId.TripleGreenShells || ActiveOrbitType == ItemId.GreenShell)
                {
                    SpawnShell(WorldItemKind.GreenShell, input, allKarts, worldItems);
                }
                else if (ActiveOrbitType == ItemId.TripleRedShells || ActiveOrbitType == ItemId.RedShell)
                {
                    SpawnShell(WorldItemKind.RedShell, input, allKarts, worldItems);
                }
                if (OrbitItemCount <= 0) ActiveOrbitType = ItemId.None;
                return;
            }

            if (HeldItem == ItemId.None) return;

            switch (HeldItem)
            {
                case ItemId.Mushroom:
                    BoostTimer = 1.45f;
                    BoostStrength = 1.34f;
                    ForwardSpeed = Math.Max(ForwardSpeed, Character.TopSpeed * 1.25f);
                    HeldItem = ItemId.None;
                    if (IsHuman)
                    {
                        N64AudioSynth.Instance.PlaySfx(SfxId.BoostWhoosh, 1.0f);
                        if (padMgr != null) padMgr.TriggerRumble(HumanPlayerIndex, 0.4f, 0.9f, 0.3f);
                    }
                    break;

                case ItemId.TripleMushrooms:
                    BoostTimer = 1.40f;
                    BoostStrength = 1.34f;
                    ForwardSpeed = Math.Max(ForwardSpeed, Character.TopSpeed * 1.25f);
                    RemainingSubUses--;
                    if (RemainingSubUses <= 0) HeldItem = ItemId.None;
                    if (IsHuman)
                    {
                        N64AudioSynth.Instance.PlaySfx(SfxId.BoostWhoosh, 1.0f);
                        if (padMgr != null) padMgr.TriggerRumble(HumanPlayerIndex, 0.4f, 0.9f, 0.3f);
                    }
                    break;

                case ItemId.GoldenMushroom:
                    if (GoldenMushroomWindowTimer <= 0f) GoldenMushroomWindowTimer = 8.0f;
                    BoostTimer = 1.25f;
                    BoostStrength = 1.36f;
                    ForwardSpeed = Math.Max(ForwardSpeed, Character.TopSpeed * 1.28f);
                    if (IsHuman)
                    {
                        N64AudioSynth.Instance.PlaySfx(SfxId.BoostWhoosh, 1.0f);
                        if (padMgr != null) padMgr.TriggerRumble(HumanPlayerIndex, 0.5f, 0.95f, 0.25f);
                    }
                    break;

                case ItemId.Banana:
                    SpawnBananaOrFakeBox(WorldItemKind.Banana, input, worldItems);
                    HeldItem = ItemId.None;
                    break;

                case ItemId.TripleBananas:
                    ActiveOrbitType = ItemId.TripleBananas;
                    OrbitItemCount = 3;
                    HeldItem = ItemId.None;
                    break;

                case ItemId.FakeItemBox:
                    SpawnBananaOrFakeBox(WorldItemKind.FakeItemBox, input, worldItems);
                    HeldItem = ItemId.None;
                    break;

                case ItemId.GreenShell:
                    SpawnShell(WorldItemKind.GreenShell, input, allKarts, worldItems);
                    HeldItem = ItemId.None;
                    break;

                case ItemId.TripleGreenShells:
                    ActiveOrbitType = ItemId.TripleGreenShells;
                    OrbitItemCount = 3;
                    HeldItem = ItemId.None;
                    break;

                case ItemId.RedShell:
                    SpawnShell(WorldItemKind.RedShell, input, allKarts, worldItems);
                    HeldItem = ItemId.None;
                    break;

                case ItemId.TripleRedShells:
                    ActiveOrbitType = ItemId.TripleRedShells;
                    OrbitItemCount = 3;
                    HeldItem = ItemId.None;
                    break;

                case ItemId.SpinyBlueShell:
                    SpawnShell(WorldItemKind.SpinyBlueShell, input, allKarts, worldItems);
                    HeldItem = ItemId.None;
                    break;

                case ItemId.SuperStar:
                    StarmanTimer = 9.0f;
                    HeldItem = ItemId.None;
                    if (IsHuman && HumanPlayerIndex == 0)
                    {
                        N64AudioSynth.Instance.SetStarmanOverride(true);
                    }
                    break;

                case ItemId.Boo:
                    BooTimer = 7.5f;
                    HeldItem = ItemId.None;
                    N64AudioSynth.Instance.PlaySfx(SfxId.BooLaugh, 1.0f);
                    // Steal an item from a racer ahead (or give a Mushroom if nobody holds one!)
                    ItemId stolen = ItemId.Mushroom;
                    for (int k = 0; k < allKarts.Length; k++)
                    {
                        Kart victim = allKarts[k];
                        if (victim != this && victim.HeldItem != ItemId.None)
                        {
                            stolen = victim.HeldItem;
                            victim.HeldItem = ItemId.None;
                            break;
                        }
                    }
                    HeldItem = stolen;
                    if (HeldItem == ItemId.TripleMushrooms) RemainingSubUses = 3;
                    break;

                case ItemId.Thunderbolt:
                    HeldItem = ItemId.None;
                    N64AudioSynth.Instance.PlaySfx(SfxId.LightningStrike, 1.0f);
                    for (int k = 0; k < allKarts.Length; k++)
                    {
                        Kart victim = allKarts[k];
                        if (victim == this || victim.IsEliminated) continue;
                        if (victim.StarmanTimer > 0f || victim.BooTimer > 0f) continue;
                        victim.ShrinkTimer = 9.0f;
                        victim.SpinOutTimer = 0.75f;
                        victim.ForwardSpeed *= 0.45f;
                    }
                    break;
            }
        }

        private void SpawnBananaOrFakeBox(WorldItemKind kind, PlayerInputState input, List<WorldItemEntity> worldItems)
        {
            bool throwForward = (input != null && input.AimVertical > 0.55f);
            WorldItemEntity ent = new WorldItemEntity();
            ent.Kind = kind;
            ent.OwnerKartIndex = SlotIndex;
            ent.TrackSegmentHint = CurrentSegmentIndex;
            if (throwForward)
            {
                ent.Position = Position + ForwardDir * 3.2f + new Vec3(0f, 1.4f, 0f);
                ent.Velocity = ForwardDir * (ForwardSpeed + 42f) + new Vec3(0f, 11f, 0f);
            }
            else
            {
                ent.Position = Position - ForwardDir * 2.8f + new Vec3(0f, 0.7f, 0f);
                ent.Velocity = Vec3.Zero;
            }
            worldItems.Add(ent);
            if (IsHuman) N64AudioSynth.Instance.PlaySfx(SfxId.Hop, 0.7f);
        }

        private void SpawnShell(WorldItemKind kind, PlayerInputState input, Kart[] allKarts, List<WorldItemEntity> worldItems)
        {
            bool fireBackward = (input != null && input.AimVertical < -0.55f && kind == WorldItemKind.GreenShell);
            Vec3 dir = fireBackward ? -ForwardDir : ForwardDir;

            WorldItemEntity ent = new WorldItemEntity();
            ent.Kind = kind;
            ent.OwnerKartIndex = SlotIndex;
            ent.Position = Position + dir * 3.1f + new Vec3(0f, 0.7f, 0f);
            ent.Velocity = dir * (kind == WorldItemKind.SpinyBlueShell ? 102f : 86f);
            ent.TrackSegmentHint = CurrentSegmentIndex;
            ent.HomingActive = (kind == WorldItemKind.RedShell || kind == WorldItemKind.SpinyBlueShell);

            if (kind == WorldItemKind.RedShell)
            {
                // Target the racer immediately ahead in race rank (or nearest opponent in Battle Mode)
                int bestIdx = -1;
                float bestScore = float.MaxValue;
                for (int k = 0; k < allKarts.Length; k++)
                {
                    Kart cand = allKarts[k];
                    if (cand == this || cand.IsEliminated) continue;
                    if (RaceRank > 1 && cand.RaceRank == RaceRank - 1)
                    {
                        bestIdx = k;
                        break;
                    }
                    float d = Vec3.DistanceXZ(Position, cand.Position);
                    if (d < bestScore) { bestScore = d; bestIdx = k; }
                }
                ent.TargetKartIndex = bestIdx;
            }

            worldItems.Add(ent);
            if (IsHuman) N64AudioSynth.Instance.PlaySfx(SfxId.ShellShoot, 0.95f);
        }
    }
}
