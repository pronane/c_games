using System;
using System.Collections.Generic;
using MarioKart64.Audio;
using MarioKart64.Core;
using MarioKart64.Entities;
using MarioKart64.Input;
using MarioKart64.Rendering;
using MarioKart64.Tracks;

namespace MarioKart64.Game
{
    public enum SessionPhase
    {
        CourseIntro = 0,
        Countdown = 1,
        ActivePlay = 2,
        Paused = 3,
        RaceResults = 4,
        CupTrophyPodium = 5
    }

    public class GameSession
    {
        public GameMode Mode;
        public EngineClass ClassCC;
        public CupType SelectedCup;
        public int CupRaceIndex; // 0..3
        public CourseId CurrentCourseId;
        public TrackData Track;

        public int HumanCount = 1;
        public Kart[] Karts;
        public List<WorldItemEntity> WorldItems = new List<WorldItemEntity>();
        public List<CourseHazard> Hazards = new List<CourseHazard>();

        public SessionPhase Phase = SessionPhase.CourseIntro;
        public float PhaseTimer;
        public float CountdownRemaining;
        public int LastCountdownBeepSecond = 4;
        public float RaceElapsed;
        public float GlobalTime;
        public float LightningFlashTimer;
        public bool NewTimeTrialRecord;

        // Per-human camera state
        private readonly Vec3[] _camPos = new Vec3[4];
        private readonly Vec3[] _camLook = new Vec3[4];
        private readonly int[] _camDistanceMode = new int[4]; // 0=Normal, 1=Far, 2=Close
        private readonly bool[] _camInitialized = new bool[4];

        // Pause / Results menu cursor
        public int PauseCursor = 0;
        public int ResultsCursor = 0;

        private readonly Random _rng = new Random(641996);

        public void StartNewMatch(
            GameMode mode,
            EngineClass cc,
            int humanCount,
            CharacterId[] chosenChars,
            CupType cup,
            CourseId directCourse)
        {
            Mode = mode;
            ClassCC = cc;
            HumanCount = MathUtil.ClampInt(humanCount, 1, 4);
            SelectedCup = cup;
            CupRaceIndex = 0;

            int totalRacers = 8;
            if (mode == GameMode.TimeTrials) totalRacers = 1;
            else if (mode == GameMode.Battle) totalRacers = 4;

            Karts = new Kart[totalRacers];

            // Assign Human characters first, then fill remaining slots with distinct MK64 characters
            List<CharacterId> pool = new List<CharacterId>();
            for (int c = 0; c < 8; c++) pool.Add((CharacterId)c);

            for (int i = 0; i < Math.Min(HumanCount, totalRacers); i++)
            {
                CharacterId cid = (chosenChars != null && i < chosenChars.Length) ? chosenChars[i] : (CharacterId)i;
                pool.Remove(cid);

                Kart k = new Kart();
                k.SlotIndex = i;
                k.IsHuman = true;
                k.HumanPlayerIndex = i;
                k.Character = CharacterRoster.Get(cid);
                Karts[i] = k;
            }

            for (int i = HumanCount; i < totalRacers; i++)
            {
                CharacterId cid = pool.Count > 0 ? pool[0] : (CharacterId)(i % 8);
                if (pool.Count > 0) pool.RemoveAt(0);

                Kart k = new Kart();
                k.SlotIndex = i;
                k.IsHuman = false;
                k.HumanPlayerIndex = -1;
                k.Character = CharacterRoster.Get(cid);
                k.AiLaneOffset = ((i % 3) - 1) * 2.2f;
                k.AiPreferredBranch = (i % 3) - 1;
                Karts[i] = k;
            }

            CourseId firstCourse = (mode == GameMode.MarioGP)
                ? TrackRegistry.GetCupCourse(SelectedCup, 0)
                : directCourse;

            LoadCourseForSession(firstCourse);
        }

        public void LoadCourseForSession(CourseId courseId)
        {
            CurrentCourseId = courseId;
            bool mirror = (ClassCC == EngineClass.ExtraMirror) && (Mode != GameMode.Battle);
            Track = TrackRegistry.Create(courseId, mirror);

            WorldItems.Clear();
            Hazards.Clear();
            for (int i = 0; i < Track.HazardSpecs.Count; i++)
            {
                Hazards.Add(new CourseHazard(Track.HazardSpecs[i], Track));
            }

            for (int i = 0; i < Karts.Length; i++)
            {
                // Reverse/grid order or standing order
                Karts[i].ResetForTrack(Track, Karts.Length - 1 - i, Mode == GameMode.TimeTrials);
            }

            for (int i = 0; i < 4; i++) _camInitialized[i] = false;

            Phase = SessionPhase.CourseIntro;
            PhaseTimer = 2.1f;
            CountdownRemaining = 3.2f;
            LastCountdownBeepSecond = 4;
            RaceElapsed = 0f;
            LightningFlashTimer = 0f;
            NewTimeTrialRecord = false;
            PauseCursor = 0;
            ResultsCursor = 0;

            N64AudioSynth.Instance.SetStarmanOverride(false);
            N64AudioSynth.Instance.SetMusic(Track.Music, 1.0f);
        }

        // Returns true if user chose "QUIT TO MENU"
        public bool Update(EasySmxControllerManager padMgr, SceneRenderer sceneRenderer, float dt)
        {
            GlobalTime += dt;
            if (LightningFlashTimer > 0f) LightningFlashTimer = Math.Max(0f, LightningFlashTimer - dt * 2.5f);

            PlayerInputState p1 = padMgr.GetPlayer(0);

            // Camera distance toggle per player via Select / Back / Y / C
            for (int p = 0; p < HumanCount; p++)
            {
                if (padMgr.GetPlayer(p).SelectPressed)
                {
                    _camDistanceMode[p] = (_camDistanceMode[p] + 1) % 3;
                }
            }

            if (Phase == SessionPhase.Paused)
            {
                N64AudioSynth.Instance.SetEngineState(false, 0f, false, false);
                padMgr.StopAllRumble();

                if (p1.MenuUpPressed)   { PauseCursor = (PauseCursor + 2) % 3; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                if (p1.MenuDownPressed) { PauseCursor = (PauseCursor + 1) % 3; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }

                if (p1.StartPressed)
                {
                    Phase = SessionPhase.ActivePlay;
                    N64AudioSynth.Instance.PlaySfx(SfxId.MenuConfirm);
                    return false;
                }
                if (p1.ConfirmPressed)
                {
                    N64AudioSynth.Instance.PlaySfx(SfxId.MenuConfirm);
                    if (PauseCursor == 0)
                    {
                        Phase = SessionPhase.ActivePlay;
                    }
                    else if (PauseCursor == 1)
                    {
                        sceneRenderer.InvalidateDisplayList();
                        LoadCourseForSession(CurrentCourseId);
                    }
                    else
                    {
                        sceneRenderer.InvalidateDisplayList();
                        return true;
                    }
                }
                return false;
            }

            if (Phase == SessionPhase.CourseIntro)
            {
                PhaseTimer -= dt;
                if (p1.ConfirmPressed || p1.StartPressed || PhaseTimer <= 0f)
                {
                    Phase = SessionPhase.Countdown;
                }
                UpdateCameras(dt, true);
                return false;
            }

            if (Phase == SessionPhase.Countdown)
            {
                CountdownRemaining -= dt;
                int sec = (int)Math.Ceiling(CountdownRemaining);
                if (sec >= 1 && sec <= 3 && sec < LastCountdownBeepSecond)
                {
                    LastCountdownBeepSecond = sec;
                    N64AudioSynth.Instance.PlaySfx(SfxId.CountdownTick);
                }

                for (int i = 0; i < Karts.Length; i++)
                {
                    if (Karts[i].IsHuman)
                    {
                        Karts[i].UpdateCountdownRev(padMgr.GetPlayer(Karts[i].HumanPlayerIndex), CountdownRemaining, dt);
                    }
                }

                N64AudioSynth.Instance.SetEngineState(true, Karts[0].StartRevCharge * 0.7f, false, false);

                if (CountdownRemaining <= 0f)
                {
                    N64AudioSynth.Instance.PlaySfx(SfxId.CountdownGo);
                    for (int i = 0; i < Karts.Length; i++)
                    {
                        Karts[i].ApplyCountdownLaunch(padMgr);
                    }
                    Phase = SessionPhase.ActivePlay;
                }
                UpdateCameras(dt, false);
                return false;
            }

            if (Phase == SessionPhase.RaceResults)
            {
                N64AudioSynth.Instance.SetEngineState(false, 0f, false, false);
                padMgr.StopAllRumble();
                UpdateCameras(dt, true);

                if (p1.MenuUpPressed || p1.MenuDownPressed)
                {
                    ResultsCursor = 1 - ResultsCursor;
                    N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove);
                }
                if (p1.ConfirmPressed || p1.StartPressed)
                {
                    N64AudioSynth.Instance.PlaySfx(SfxId.MenuConfirm);
                    if (ResultsCursor == 1)
                    {
                        // Retry current course
                        sceneRenderer.InvalidateDisplayList();
                        LoadCourseForSession(CurrentCourseId);
                        return false;
                    }

                    if (Mode == GameMode.MarioGP)
                    {
                        CupRaceIndex++;
                        if (CupRaceIndex < 4)
                        {
                            sceneRenderer.InvalidateDisplayList();
                            LoadCourseForSession(TrackRegistry.GetCupCourse(SelectedCup, CupRaceIndex));
                        }
                        else
                        {
                            // Award Cup Trophy!
                            AwardCupTrophy();
                            Phase = SessionPhase.CupTrophyPodium;
                            N64AudioSynth.Instance.SetMusic(MusicTrackId.VictoryPodium, 1.0f);
                        }
                    }
                    else
                    {
                        sceneRenderer.InvalidateDisplayList();
                        return true;
                    }
                }
                return false;
            }

            if (Phase == SessionPhase.CupTrophyPodium)
            {
                UpdateCameras(dt, true);
                if (p1.ConfirmPressed || p1.StartPressed)
                {
                    N64AudioSynth.Instance.PlaySfx(SfxId.MenuConfirm);
                    sceneRenderer.InvalidateDisplayList();
                    return true;
                }
                return false;
            }

            // === ActivePlay ===
            if (p1.StartPressed)
            {
                Phase = SessionPhase.Paused;
                PauseCursor = 0;
                N64AudioSynth.Instance.PlaySfx(SfxId.MenuConfirm);
                return false;
            }

            RaceElapsed += dt;

            // Respawn picked-up Item Boxes
            for (int b = 0; b < Track.ItemBoxes.Count; b++)
            {
                ItemBoxSpawn box = Track.ItemBoxes[b];
                if (!box.Active)
                {
                    box.RespawnTimer -= dt;
                    if (box.RespawnTimer <= 0f) box.Active = true;
                    Track.ItemBoxes[b] = box;
                }
            }

            CharacterId primaryRival = CharacterRoster.GetPrimaryRival(Karts[0].Character.Id);

            // Step every Kart (Humans use EasySMX/Keyboard, finished humans & CPUs use AI)
            for (int i = 0; i < Karts.Length; i++)
            {
                Kart k = Karts[i];
                PlayerInputState inp;
                bool hadThunderbolt = (k.HeldItem == ItemId.Thunderbolt);

                if (k.IsHuman && !k.FinishedRace)
                {
                    inp = padMgr.GetPlayer(k.HumanPlayerIndex);
                }
                else
                {
                    bool isRival = (k.Character.Id == primaryRival);
                    inp = AiDriver.ComputeInput(k, Track, Karts, WorldItems, Hazards, ClassCC, isRival, _rng, dt);
                }

                k.UpdatePhysics(inp, Track, Karts, WorldItems, padMgr, ClassCC, RaceElapsed, _rng, dt);

                if (hadThunderbolt && k.HeldItem == ItemId.None)
                {
                    LightningFlashTimer = 1.0f;
                }
            }

            // Kart-to-Kart collisions, Course Hazards, & Active Shells/Bananas
            int[] prevHits = new int[Karts.Length];
            for (int i = 0; i < Karts.Length; i++) prevHits[i] = (Karts[i].TumbleTimer > 0f || Karts[i].SpinOutTimer > 0f) ? 1 : 0;

            CourseHazard.ResolveKartToKartCollisions(Karts, Track.IsBattleArena, padMgr);
            for (int h = 0; h < Hazards.Count; h++)
            {
                Hazards[h].Update(Track, Karts, padMgr, dt);
            }
            ItemSystem.UpdateWorldItems(WorldItems, Karts, Track, dt);

            // Deduct Battle Mode balloons on newly triggered hits
            if (Track.IsBattleArena)
            {
                for (int i = 0; i < Karts.Length; i++)
                {
                    bool nowHit = (Karts[i].TumbleTimer > 1.25f || Karts[i].SpinOutTimer > 0.98f);
                    if (prevHits[i] == 0 && nowHit)
                    {
                        Karts[i].LoseBattleBalloon();
                    }
                }
            }

            // Compute Live Race Ranks (1st .. 8th)
            UpdateRaceRankings();

            // Update P1 Engine Audio
            Kart p1Kart = Karts[0];
            N64AudioSynth.Instance.SetEngineState(
                !p1Kart.FinishedRace && !p1Kart.IsEliminated,
                Math.Abs(p1Kart.ForwardSpeed) / Math.Max(1f, p1Kart.Character.TopSpeed),
                p1Kart.IsDrifting,
                p1Kart.ShrinkTimer > 0f);

            UpdateCameras(dt, false);

            // Check Race / Battle Completion!
            CheckMatchCompletion();

            return false;
        }

        private void UpdateRaceRankings()
        {
            if (Track.IsBattleArena) return;
            for (int i = 0; i < Karts.Length; i++)
            {
                int rank = 1;
                for (int j = 0; j < Karts.Length; j++)
                {
                    if (i == j) continue;
                    if (Karts[j].RaceProgress > Karts[i].RaceProgress ||
                        (Karts[j].RaceProgress == Karts[i].RaceProgress && j < i))
                    {
                        rank++;
                    }
                }
                Karts[i].RaceRank = rank;
            }
        }

        private void CheckMatchCompletion()
        {
            if (Mode == GameMode.Battle)
            {
                int aliveCount = 0;
                int aliveHumans = 0;
                for (int i = 0; i < Karts.Length; i++)
                {
                    if (!Karts[i].IsEliminated)
                    {
                        aliveCount++;
                        if (Karts[i].IsHuman) aliveHumans++;
                    }
                }
                if (aliveCount <= 1 || aliveHumans == 0)
                {
                    Phase = SessionPhase.RaceResults;
                    ResultsCursor = 0;
                    N64AudioSynth.Instance.SetMusic(MusicTrackId.VictoryPodium, 1.0f);
                }
                return;
            }

            bool anyHuman = false;
            bool allHumansDone = true;
            for (int i = 0; i < Karts.Length; i++)
            {
                if (Karts[i].IsHuman)
                {
                    anyHuman = true;
                    if (!Karts[i].FinishedRace)
                    {
                        allHumansDone = false;
                        break;
                    }
                }
            }
            if (!anyHuman) allHumansDone = false;

            if (allHumansDone)
            {
                // Auto-score remaining AI positions cleanly and award MK64 GP points (9, 6, 3, 1)!
                int[] mk64Points = { 9, 6, 3, 1, 0, 0, 0, 0 };
                for (int i = 0; i < Karts.Length; i++)
                {
                    int r = MathUtil.ClampInt(Karts[i].RaceRank - 1, 0, 7);
                    if (Mode == GameMode.MarioGP)
                    {
                        Karts[i].GrandPrixPoints += mk64Points[r];
                    }
                }

                if (Mode == GameMode.TimeTrials && (int)CurrentCourseId < 16)
                {
                    NewTimeTrialRecord = GameConfig.Instance.RecordTimeTrial(
                        (int)CurrentCourseId,
                        Karts[0].FinishTimeSeconds,
                        Karts[0].BestLapSeconds);
                }

                Phase = SessionPhase.RaceResults;
                ResultsCursor = 0;
                N64AudioSynth.Instance.SetMusic(MusicTrackId.VictoryPodium, 1.0f);
            }
        }

        private void AwardCupTrophy()
        {
            // Rank all 8 drivers by cumulative GrandPrixPoints
            int p1Standing = 1;
            for (int i = 1; i < Karts.Length; i++)
            {
                if (Karts[i].GrandPrixPoints > Karts[0].GrandPrixPoints) p1Standing++;
            }
            TrophyTier tier = TrophyTier.None;
            if (p1Standing == 1) tier = TrophyTier.Gold;
            else if (p1Standing == 2) tier = TrophyTier.Silver;
            else if (p1Standing == 3) tier = TrophyTier.Bronze;

            if (tier != TrophyTier.None)
            {
                GameConfig.Instance.RecordTrophy(SelectedCup, ClassCC, tier);
            }
        }

        private void UpdateCameras(float dt, bool orbitOverview)
        {
            for (int p = 0; p < HumanCount; p++)
            {
                Kart k = Karts[Math.Min(p, Karts.Length - 1)];
                if (orbitOverview)
                {
                    float ang = GlobalTime * 0.65f + p;
                    Vec3 desiredEye = k.Position + new Vec3((float)Math.Cos(ang) * 14f, 6.2f, (float)Math.Sin(ang) * 14f);
                    Vec3 desiredLook = k.Position + new Vec3(0f, 1.6f, 0f);
                    _camPos[p] = _camInitialized[p] ? Vec3.Lerp(_camPos[p], desiredEye, 5f * dt) : desiredEye;
                    _camLook[p] = _camInitialized[p] ? Vec3.Lerp(_camLook[p], desiredLook, 8f * dt) : desiredLook;
                    _camInitialized[p] = true;
                }
                else
                {
                    float dist = 6.3f;
                    float height = 2.38f;
                    if (_camDistanceMode[p] == 1) { dist = 9.8f; height = 3.65f; }
                    else if (_camDistanceMode[p] == 2) { dist = 5.1f; height = 2.02f; }

                    Vec3 fwd = k.ForwardDir;
                    Vec3 desiredEye = k.Position - fwd * dist + new Vec3(0f, height, 0f);
                    Vec3 desiredLook = k.Position + fwd * 6.8f + new Vec3(0f, 1.22f, 0f);

                    if (!_camInitialized[p])
                    {
                        _camPos[p] = desiredEye;
                        _camLook[p] = desiredLook;
                        _camInitialized[p] = true;
                    }
                    else
                    {
                        _camPos[p] = Vec3.Lerp(_camPos[p], desiredEye, MathUtil.Clamp(11.5f * dt, 0f, 1f));
                        _camLook[p] = Vec3.Lerp(_camLook[p], desiredLook, MathUtil.Clamp(16.0f * dt, 0f, 1f));
                    }
                }
            }
        }

        public void Render(int clientW, int clientH, SceneRenderer sceneRenderer)
        {
            // Render 1P, 2P, 3P, or 4P Split-Screen Viewports!
            if (HumanCount == 1)
            {
                RenderSinglePlayerView(0, 0, clientW, clientH, 0, false, sceneRenderer);
            }
            else if (HumanCount == 2)
            {
                int halfH = clientH / 2;
                // P1 Top Half (Note: OpenGL viewport Y=0 is bottom of window!)
                RenderSinglePlayerView(0, halfH + 2, clientW, clientH - halfH - 2, 0, true, sceneRenderer);
                // P2 Bottom Half
                RenderSinglePlayerView(0, 0, clientW, halfH - 2, 1, true, sceneRenderer);
            }
            else
            {
                int halfW = clientW / 2;
                int halfH = clientH / 2;
                RenderSinglePlayerView(0,         halfH + 2, halfW - 2, clientH - halfH - 2, 0, true, sceneRenderer);
                RenderSinglePlayerView(halfW + 2, halfH + 2, clientW - halfW - 2, clientH - halfH - 2, 1, true, sceneRenderer);
                RenderSinglePlayerView(0,         0,         halfW - 2, halfH - 2, 2, true, sceneRenderer);
                if (HumanCount >= 4)
                {
                    RenderSinglePlayerView(halfW + 2, 0, clientW - halfW - 2, halfH - 2, 3, true, sceneRenderer);
                }
            }

            // Full-window Overlay for Course Intro, Pause, Race Standings, & Cup Trophy Podium
            if (Phase == SessionPhase.CourseIntro ||
                Phase == SessionPhase.Paused ||
                Phase == SessionPhase.RaceResults ||
                Phase == SessionPhase.CupTrophyPodium)
            {
                RenderFullWindowOverlay(clientW, clientH);
            }
        }

        private void RenderSinglePlayerView(int vx, int vy, int vw, int vh, int pIdx, bool compact, SceneRenderer sceneRenderer)
        {
            Kart pk = Karts[Math.Min(pIdx, Karts.Length - 1)];
            sceneRenderer.RenderViewport(
                vx, vy, vw, vh,
                _camPos[pIdx], _camLook[pIdx],
                Track, Karts, WorldItems, Hazards,
                GlobalTime, LightningFlashTimer);

            if (Phase == SessionPhase.Countdown || Phase == SessionPhase.ActivePlay)
            {
                HudRenderer.RenderPlayerHud(
                    vx, vy, vw, vh,
                    pk, Karts, Track, Mode,
                    RaceElapsed, CountdownRemaining,
                    Phase == SessionPhase.ActivePlay,
                    GlobalTime, compact);
            }
        }

        private void RenderFullWindowOverlay(int clientW, int clientH)
        {
            Gl.glViewport(0, 0, clientW, clientH);
            Gl.glDisable(Gl.GL_DEPTH_TEST);
            Gl.glDisable(Gl.GL_FOG);

            Gl.glMatrixMode(Gl.GL_PROJECTION);
            Gl.glLoadIdentity();
            Gl.glOrtho(0, 960, 540, 0, -1, 1);
            Gl.glMatrixMode(Gl.GL_MODELVIEW);
            Gl.glLoadIdentity();

            Color4 goldTop = Color4.FromBytes(255, 245, 90);
            Color4 goldBot = Color4.FromBytes(245, 148, 22);
            Color4 white = new Color4(1f, 1f, 1f, 1f);

            if (Phase == SessionPhase.CourseIntro)
            {
                ProceduralTextures.DrawSolidRect2D(180f, 195f, 600f, 135f, new Color4(0.04f, 0.07f, 0.18f, 0.84f));
                ProceduralTextures.DrawRectOutline2D(180f, 195f, 600f, 135f, 3f, goldTop);
                ProceduralTextures.DrawText2D(Track.CupName, 480f, 215f, 24f, white, Color4.FromBytes(165, 205, 255), true);
                ProceduralTextures.DrawText2D("WELCOME TO " + Track.Name + "!", 480f, 258f, 32f, goldTop, goldBot, true);
                if (Track.IsMirrored)
                    ProceduralTextures.DrawText2D("EXTRA MODE (MIRRORED COURSE)", 480f, 298f, 18f, Color4.FromBytes(255, 125, 215), white, true);
            }
            else if (Phase == SessionPhase.Paused)
            {
                ProceduralTextures.DrawSolidRect2D(290f, 155f, 380f, 225f, new Color4(0.03f, 0.05f, 0.14f, 0.90f));
                ProceduralTextures.DrawRectOutline2D(290f, 155f, 380f, 225f, 3f, goldTop);
                ProceduralTextures.DrawText2D("- PAUSE -", 480f, 175f, 32f, goldTop, goldBot, true);

                string[] opts = { "CONTINUE", "RETRY COURSE", "QUIT TO MENU" };
                for (int i = 0; i < opts.Length; i++)
                {
                    bool sel = (PauseCursor == i);
                    Color4 cTop = sel ? goldTop : white;
                    Color4 cBot = sel ? goldBot : Color4.FromBytes(170, 185, 210);
                    ProceduralTextures.DrawText2D((sel ? "> " : "  ") + opts[i], 480f, 232f + i * 42f, 24f, cTop, cBot, true);
                }
            }
            else if (Phase == SessionPhase.RaceResults)
            {
                ProceduralTextures.DrawSolidRect2D(150f, 52f, 660f, 435f, new Color4(0.03f, 0.06f, 0.16f, 0.90f));
                ProceduralTextures.DrawRectOutline2D(150f, 52f, 660f, 435f, 3f, goldTop);

                ProceduralTextures.DrawText2D(Track.Name + " - RESULTS", 480f, 68f, 28f, goldTop, goldBot, true);

                if (Mode == GameMode.TimeTrials)
                {
                    ProceduralTextures.DrawText2D("TOTAL TIME: " + GameConfig.FormatRaceTime(Karts[0].FinishTimeSeconds), 480f, 145f, 28f, white, goldTop, true);
                    ProceduralTextures.DrawText2D("BEST LAP:   " + GameConfig.FormatRaceTime(Karts[0].BestLapSeconds), 480f, 195f, 26f, white, goldTop, true);
                    if (NewTimeTrialRecord)
                    {
                        ProceduralTextures.DrawText2D("** NEW COURSE RECORD SAVED! **", 480f, 255f, 26f, Color4.FromBytes(95, 255, 130), goldTop, true);
                    }
                }
                else if (Mode == GameMode.Battle)
                {
                    for (int i = 0; i < Karts.Length; i++)
                    {
                        Kart kt = Karts[i];
                        string line = string.Format("{0,-10}  BALLOONS LEFT: {1}  {2}",
                            kt.Character.Name, kt.Balloons, kt.IsEliminated ? "(OUT)" : "** WINNER! **");
                        ProceduralTextures.DrawText2D(line, 480f, 140f + i * 42f, 23f, kt.Character.PrimaryColor, white, true);
                    }
                }
                else
                {
                    // Sort karts by RaceRank for Standings Table
                    List<Kart> ordered = new List<Kart>(Karts);
                    ordered.Sort(delegate(Kart a, Kart b) { return a.RaceRank.CompareTo(b.RaceRank); });

                    for (int i = 0; i < ordered.Count; i++)
                    {
                        Kart kt = ordered[i];
                        string pts = (Mode == GameMode.MarioGP) ? (kt.GrandPrixPoints + " PTS") : "";
                        string tag = kt.IsHuman ? (" [P" + (kt.HumanPlayerIndex + 1) + "]") : "";
                        string row = string.Format("{0}  {1,-8}{2,-6}   {3}",
                            HudRenderer.FormatOrdinal(kt.RaceRank), kt.Character.Name, tag, pts);
                        Color4 rowCol = kt.IsHuman ? goldTop : white;
                        ProceduralTextures.DrawText2D(row, 480f, 118f + i * 33f, 21f, rowCol, rowCol.ScaleRGB(0.8f), true);
                    }
                }

                string nextLabel = (Mode == GameMode.MarioGP)
                    ? ((CupRaceIndex < 3) ? "NEXT COURSE" : "TROPHY CEREMONY")
                    : "RETURN TO MENU";
                string[] acts = { nextLabel, "RETRY COURSE" };
                for (int i = 0; i < 2; i++)
                {
                    bool sel = (ResultsCursor == i);
                    ProceduralTextures.DrawText2D((sel ? "> " : "  ") + acts[i], 480f, 405f + i * 34f, 23f, sel ? goldTop : white, sel ? goldBot : white, true);
                }
            }
            else if (Phase == SessionPhase.CupTrophyPodium)
            {
                ProceduralTextures.DrawSolidRect2D(165f, 85f, 630f, 370f, new Color4(0.04f, 0.06f, 0.18f, 0.92f));
                ProceduralTextures.DrawRectOutline2D(165f, 85f, 630f, 370f, 3.5f, goldTop);

                ProceduralTextures.DrawText2D("CONGRATULATIONS!", 480f, 108f, 36f, goldTop, goldBot, true);
                ProceduralTextures.DrawText2D(TrackRegistry.CupNames[(int)SelectedCup] + " COMPLETE!", 480f, 158f, 26f, white, goldTop, true);

                List<Kart> standings = new List<Kart>(Karts);
                standings.Sort(delegate(Kart a, Kart b) { return b.GrandPrixPoints.CompareTo(a.GrandPrixPoints); });

                int p1Place = 1;
                for (int i = 0; i < standings.Count; i++)
                {
                    if (standings[i] == Karts[0]) { p1Place = i + 1; break; }
                }

                string trophyStr = (p1Place == 1) ? "GOLD TROPHY WON!!" :
                                   (p1Place == 2) ? "SILVER TROPHY WON!" :
                                   (p1Place == 3) ? "BRONZE TROPHY WON!" : ("FINISHED " + HudRenderer.FormatOrdinal(p1Place) + " OVERALL");
                Color4 trCol = (p1Place == 1) ? Color4.FromBytes(255, 222, 40) :
                               (p1Place == 2) ? Color4.FromBytes(215, 225, 240) :
                               Color4.FromBytes(225, 145, 75);

                ProceduralTextures.DrawText2D(trophyStr, 480f, 215f, 32f, trCol, trCol.ScaleRGB(0.7f), true);

                for (int i = 0; i < Math.Min(4, standings.Count); i++)
                {
                    Kart sk = standings[i];
                    ProceduralTextures.DrawText2D(
                        string.Format("{0}. {1} - {2} PTS", i + 1, sk.Character.Name, sk.GrandPrixPoints),
                        480f, 272f + i * 30f, 22f, sk.Character.PrimaryColor, white, true);
                }

                ProceduralTextures.DrawText2D("PRESS A / START TO RETURN TO TITLE", 480f, 412f, 20f, goldTop, goldBot, true);
            }
        }
    }
}
