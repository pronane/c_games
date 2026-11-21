// Arena FC - ties the pure-C# match simulation to the 3D stadium, rigged players,
// ball, broadcast cameras and HUD. Runs at the physics tick on every platform.
using System;
using System.Collections.Generic;
using ArenaFC.Core;
using ArenaFC.Core.Net;
using Godot;

namespace ArenaFC.GodotGame;

public partial class MatchView : Node3D
{
    // CrowdDensity (P2) drives the noise of the ground: attendance follows the
    // competition, and goals push the excitement up so the stadium reacts.
    private readonly CrowdDensitySystem _crowd = new();
    private int _lastGoals = -1;
    // AmbientBehaviour / FacialExpression: off-ball players gesture and react,
    // and both now show on the nameplates instead of being simulated nowhere.
    private AmbientBehaviour[] _ambient = Array.Empty<AmbientBehaviour>();
    private FacialExpression[] _face = Array.Empty<FacialExpression>();
    // BlendLearner: which movement clip each player is actually using.
    private readonly BlendLearner _blend = new();
    private readonly MotionDriver _motion = new();
    private int _blendFrame;
    private AmbientAction[] _ambientTag = Array.Empty<AmbientAction>();
    private Emotion[] _faceTag = Array.Empty<Emotion>();
    private bool _photoKeyHeld;
    public MatchEngine Engine = null!;
    public InputHub Input = new();
    public Hud Hud = null!;
    public BroadcastCamera Cam = null!;
    public CharacterRig[] Rigs = Array.Empty<CharacterRig>();
    public MeshInstance3D Ball = null!, BallShadow = null!, Cursor = null!, BallRing = null!, OwnerRing = null!,
                          ControlArrow = null!, OwnerArrow = null!, PressureRing = null!;
    /// <summary>Billboarded, always-visible nameplates for the controlled player,
    /// the ball carrier, a loose ball and the nearest opponent.</summary>
    public Label3D ControlName = null!, OwnerName = null!, BallName = null!, PressureName = null!;
    /// <summary>When set, the authoritative server drives the sim instead of the local engine.</summary>
    public OnlineMatch? Online;

    private MatchOptions _opts = new();
    private Action? _onExit;
    public Action<MatchState>? OnMatchEnd;
    private float _time;
    private bool _built;
    /// <summary>One-shot button edges survive physics frames that produce no fixed
    /// engine tick, instead of being silently dropped by the accumulator.</summary>
    private PlayerCommand _pending;
    /// <summary>Training coach and the coach / shootout overlay (Modes 2 and 3).</summary>
    private TrainingCoach? _coach;
    private ModeOverlay? _modeOverlay;

    public void Init(MatchOptions opts, List<CharacterSpec>? customHome, Action onExit)
    {
        _opts = opts ?? new MatchOptions();
        if (customHome != null && customHome.Count > 0) _opts.CustomHome = customHome;
        _onExit = onExit;
    }

    public override void _Ready()
    {
        SetProcessInput(true);
        Build();
    }

    public override void _Input(InputEvent @event)
    {
        // Direct --match boots have no PadMenuNavigator on the Window, so latch
        // quick controller taps here as well.  Duplicate events are deduplicated
        // by InputHub's pending-press set.
        if (@event is InputEventJoypadButton jb)
            InputHub.PushJoyButton(jb.Device, (int)jb.ButtonIndex, jb.Pressed);
    }

    private static Vector3 G(System.Numerics.Vector3 v) => new(v.X, v.Y, v.Z);

    private static StandardMaterial3D MarkerMaterial(Color c) => new()
    {
        AlbedoColor = c,
        EmissionEnabled = true,
        Emission = c,
        ShadingMode = BaseMaterial3D.ShadingModeEnum.Unshaded,
    };

    private static MeshInstance3D Marker(string name, Mesh mesh, StandardMaterial3D mat) => new()
    {
        Name = name, Mesh = mesh, MaterialOverride = mat,
    };

    private static Label3D TrackerLabel(string name, Color color, string text) 
    {
        var l = new Label3D
        {
            Name = name,
            Text = text,
            FontSize = 16,
            PixelSize = .004f,
            OutlineSize = 4,
            Modulate = color,
            DoubleSided = true,
        };
        // Billboard so labels face the camera. No fixed_size/no_depth_test —
        // those made labels render huge and on top of everything.
        l.Set("billboard", 1);
        l.Set("outline_modulate", new Color(0f, 0f, 0f, .92f));
        return l;
    }

    private static void SetText(Label3D label, string text)
    {
        if (label.Text != text) label.Text = text;
    }

    /// <summary>The home club's ground. Clubs.All and Clubs.Stadiums are
    /// index-aligned, which the pure-C# core suite asserts.</summary>
    public static int StadiumIndexFor(int club) =>
        Clubs.Stadiums.Length == 0 ? 0 : ((club % Clubs.Stadiums.Length) + Clubs.Stadiums.Length) % Clubs.Stadiums.Length;

    private void MergePending(PlayerCommand cmd)
    {
        _pending.Move = cmd.Move;
        _pending.Sprint = cmd.Sprint;
        _pending.Shield = cmd.Shield;
        _pending.Dribble = cmd.Dribble;
        _pending.Pass |= cmd.Pass;
        _pending.Shoot |= cmd.Shoot;
        _pending.Through |= cmd.Through;
        _pending.Tackle |= cmd.Tackle;
        _pending.Slide |= cmd.Slide;
        _pending.Switch |= cmd.Switch;
        _pending.Lob |= cmd.Lob;
        _pending.CallForBall |= cmd.CallForBall;
        _pending.Punch |= cmd.Punch;
        _pending.Headbutt |= cmd.Headbutt;
        if (cmd.Skill != SkillMove.None) _pending.Skill = cmd.Skill;
        if (cmd.Charge > _pending.Charge) _pending.Charge = cmd.Charge;
    }

    private void Build()
    {
        if (_built) return;
        _built = true;
        Name = "MatchView";

        // The home club's own ground: World3D used to be built with the default
        // index, so every fixture in the game was played at "Lions Den".
        var stadium = new Stadium();
        _crowd.SetFromMatchType(_opts.Mode == 0 ? "Kickoff" : "Tournament");
        // Empty grounds still get the stadium, just not the crowd.
        stadium.Build(_crowd.GetCrowdCount() > 0, _opts.Quality, StadiumIndexFor(_opts.HomeClub));
        AddChild(stadium);

        // Online: the mirror/predictor engine is authoritative for rendering, but
        // it is still a plain MatchEngine so every HUD/camera/rig path is reused.
        Engine = Online != null ? Online.Engine : new MatchEngine(_opts);
        // Substitutions are not in the wire protocol yet: refuse them online
        // instead of desyncing the room.
        Engine.OnlineLocked = Online != null;
        Rigs = new CharacterRig[Engine.State.Players.Length];
        _motion.EnsureCapacity(Rigs.Length);
        if (Godot.FileAccess.FileExists("res://Data/clips/clip_manifest.json"))
            _motion.LoadManifest(Godot.FileAccess.GetFileAsString("res://Data/clips/clip_manifest.json"));
        _ambient = new AmbientBehaviour[Rigs.Length];
        _face = new FacialExpression[Rigs.Length];
        _ambientTag = new AmbientAction[Rigs.Length];
        _faceTag = new Emotion[Rigs.Length];
        for (int i = 0; i < Rigs.Length; i++)
        {
            _ambient[i] = new AmbientBehaviour();
            _face[i] = new FacialExpression();
        }
        for (int i = 0; i < Rigs.Length; i++)
        {
            Rigs[i] = RigFactory.Create(Engine.State.Players[i].Spec);
            Rigs[i].Name = "Player_" + i;
            AddChild(Rigs[i]);
        }

        Ball = BallFactory.Create();
        AddChild(Ball);
        var shadowMat = new StandardMaterial3D
        {
            AlbedoColor = new Color(.015f, .025f, .018f, .36f),
            Transparency = BaseMaterial3D.TransparencyEnum.Alpha,
            ShadingMode = BaseMaterial3D.ShadingModeEnum.Unshaded,
            CullMode = BaseMaterial3D.CullModeEnum.Disabled,
        };
        BallShadow = Marker("BallGroundShadow",
            new CylinderMesh { TopRadius = 1f, BottomRadius = 1f, Height = .02f, RadialSegments = 32 }, shadowMat);
        BallShadow.CastShadow = GeometryInstance3D.ShadowCastingSetting.Off;
        AddChild(BallShadow);

        var green = MarkerMaterial(new Color(.2f, 1f, .55f));
        var amber = MarkerMaterial(new Color(1f, .72f, .18f));
        var yellow = MarkerMaterial(new Color(1f, .95f, .55f));
        var blue = MarkerMaterial(new Color(.35f, .65f, 1f));
        Cursor = Marker("ControlledRing",
            new TorusMesh { InnerRadius = .72f, OuterRadius = .95f, RingSegments = 32, Rings = 8 }, green);
        AddChild(Cursor);
        BallRing = Marker("BallRing",
            new TorusMesh { InnerRadius = .28f, OuterRadius = .38f, RingSegments = 24, Rings = 6 }, yellow);
        AddChild(BallRing);
        OwnerRing = Marker("BallOwnerRing",
            new TorusMesh { InnerRadius = .90f, OuterRadius = 1.08f, RingSegments = 32, Rings = 8 }, amber);
        AddChild(OwnerRing);
        PressureRing = Marker("PressureRing",
            new TorusMesh { InnerRadius = .90f, OuterRadius = 1.06f, RingSegments = 32, Rings = 8 }, blue);
        AddChild(PressureRing);
        ControlArrow = Marker("ControlledArrow",
            new CylinderMesh { TopRadius = 0f, BottomRadius = .24f, Height = .42f, RadialSegments = 8, Rings = 1 }, green);
        ControlArrow.RotationDegrees = new Vector3(180f, 0f, 0f);
        ControlArrow.Scale = new Vector3(1.25f, 1.25f, 1.25f);
        AddChild(ControlArrow);
        OwnerArrow = Marker("BallOwnerArrow",
            new CylinderMesh { TopRadius = 0f, BottomRadius = .24f, Height = .42f, RadialSegments = 8, Rings = 1 }, amber);
        OwnerArrow.RotationDegrees = new Vector3(180f, 0f, 0f);
        OwnerArrow.Scale = new Vector3(1.25f, 1.25f, 1.25f);
        AddChild(OwnerArrow);

        ControlName = TrackerLabel("ControlledName", new Color(.2f, 1f, .55f), "YOU");
        OwnerName = TrackerLabel("BallOwnerName", new Color(1f, .72f, .18f), "BALL");
        BallName = TrackerLabel("BallName", new Color(1f, .95f, .55f), "LOOSE BALL");
        PressureName = TrackerLabel("PressureName", new Color(.55f, .8f, 1f), "OPP");
        AddChild(ControlName); AddChild(OwnerName); AddChild(BallName); AddChild(PressureName);

        Cam = new BroadcastCamera { Name = "BroadcastCamera", Fov = 55, Far = 600f };
        AddChild(Cam);
        Cam.MakeCurrent();

        // One shared InputHub: the HUD touch buttons used to drive a different
        // instance from the one MatchView.Read() polls, so touch/pad edges died.
        Hud = new Hud { Input = Input };
        AddChild(Hud);
        Hud.OnQuit = () => _onExit?.Invoke();
        Hud.OnResume = () => Hud.SetPaused(false);
        Hud.OnCamera = () => Cam.Cycle();
        bool touch = DisplayServer.IsTouchscreenAvailable() || OS.HasFeature("mobile") || OS.HasFeature("web");
        Hud.SetTouch(touch);
        if (_opts.Mode == MatchEngine.ModeTraining || _opts.Mode == MatchEngine.ModeShootout)
        {
            if (_opts.Mode == MatchEngine.ModeTraining)
            {
                _coach = new TrainingCoach();
                bool practiceArena = GameApp.Instance?.Mode == GameMode.PracticeArena
                                     || System.Array.IndexOf(OS.GetCmdlineUserArgs(), "--practice") >= 0;
                if (practiceArena) _coach.StartIndex = _coach.Lessons.Count - 1; // straight to free practice
            }
            _modeOverlay = new ModeOverlay();
            _modeOverlay.Setup(_opts.Mode);
            AddChild(_modeOverlay);
            Hud.ShowToast(_opts.Mode == MatchEngine.ModeTraining ? "TRAINING GROUND" : "PENALTY SHOOTOUT", 1.8f);
        }
        else Hud.ShowToast("KICK OFF!", 1.8f);
        Sync(0f);
    }

    public override void _PhysicsProcess(double delta)
    {
        if (!_built) return;
        float dt = (float)delta;
        _time += dt;
        var cmd = Input.Read(dt);
        // WASD is camera-relative: W always means "towards the top of the screen",
        // including the behind-the-player and top-down angles.  The pure-C# engine
        // works in world X/Z, so rotate the stick here where the camera basis lives.
        if (cmd.Move.LengthSquared() > 0.0001f)
        {
            var basis = Cam.GlobalTransform.Basis;
            var right = new System.Numerics.Vector2(basis.X.X, basis.X.Z);
            var up = new System.Numerics.Vector2(basis.Y.X, basis.Y.Z);
            if (right.LengthSquared() < 1e-4f || up.LengthSquared() < 1e-4f)
            {
                right = new System.Numerics.Vector2(1f, 0f);
                up = new System.Numerics.Vector2(0f, -1f);
            }
            right = System.Numerics.Vector2.Normalize(right);
            up = System.Numerics.Vector2.Normalize(up);
            var worldMove = right * cmd.Move.X + up * (-cmd.Move.Y);
            cmd.Move = worldMove.LengthSquared() > 1f
                ? System.Numerics.Vector2.Normalize(worldMove) : worldMove;
        }
        if (Input.PausePressed)
        {
            // Esc leaves photo mode before it opens the pause menu.
            if (Hud.PhotoModeActive) { Hud.TogglePhotoMode(); Input.Reset(); return; }
            Hud.SetPaused(!Hud.Paused);
            _pending = PlayerCommand.None;
            Input.Reset();
        }
        if (Input.CameraPressed) Cam.Cycle();
        if (Godot.Input.IsPhysicalKeyPressed(Key.P))
        {
            if (!_photoKeyHeld) { _photoKeyHeld = true; Hud.TogglePhotoMode(); }
        }
        else _photoKeyHeld = false;
        if (Hud.Paused)
        {
            // Keep draining authoritative packets even while the local UI is paused.
            Online?.Client.Poll();
            // Sync with dt=0 freezes player animations (prevents running on the spot).
            Sync(0f);
            Hud.Update(Engine, dt, Input.Charge, Cam.ModeName);
            return;
        }
        if (Online != null) Online.Step(dt, cmd);   // send input + predict/reconcile
        else
        {
            // Engine.Step() uses a fixed-tick accumulator.  When a physics frame
            // produces no tick, buffer the one-shot edges until one does.
            MergePending(cmd);
            int before = Engine.CurrentTick;
            var stepped = _pending;
            Engine.Step(dt, _pending);
            bool ticked = Engine.CurrentTick != before;
            if (ticked) _pending = PlayerCommand.None;
            if (_coach != null)
            {
                if (Input.TrainingNextPressed) _coach.Next(Engine);
                else if (Input.TrainingPrevPressed) _coach.Previous(Engine);
                else _coach.Update(Engine, ticked ? stepped : cmd, dt);
            }
        }
        PlayEventSounds();
        Sync(dt);
        // Crowd reacts to goals and settles back down between them.
        int goals = Engine.State.Score[0] + Engine.State.Score[1];
        if (_lastGoals >= 0 && goals > _lastGoals)
        {
            _crowd.OnGoal();
            for (int i = 0; i < _face.Length && i < Engine.State.Players.Length; i++)
            {
                bool home = Engine.State.Players[i].Team == 0;
                _face[i].ReactToEvent(home ? "goal_scored" : "goal_conceded");
                _ambient[i].OnGoal(home);
            }
        }
        _lastGoals = goals;
        _crowd.Update(dt);
        RecordBlendClips();
        var stadium = GetNodeOrNull<Stadium>("../Stadium");
        stadium?.UpdateCrowd(dt);
        stadium?.UpdateWeather();
        Hud.Update(Engine, dt, Input.Charge, Cam.ModeName);
        _modeOverlay?.UpdateOverlay(Engine, _coach);
        AutoplayReport();
        // Phase 4: Trigger post-match screen on FullTime
        if (Engine.State.Phase == Phase.FullTime && OnMatchEnd != null)
        {
            GameApp.Instance?.RememberHeat(Engine.Heat);
            GameApp.Instance?.RememberBlend(_blend);
            GameApp.Instance?.RememberEvents(Engine.Events);
            OnMatchEnd(Engine.State);
            OnMatchEnd = null; // only once
        }
    }

    // ---- QA: --autoplay plays a whole match/shootout/drill unattended, logging
    // progress every 5 game-minutes and a summary at the end, then quits.
    private readonly bool _autoplay = System.Array.IndexOf(OS.GetCmdlineUserArgs(), "--autoplay") >= 0;
    private int _autoplayBucket = -1;
    private bool _autoplayDone;
    private double _autoplayStart = -1;
    private void AutoplayReport()
    {
        if (!_autoplay || _autoplayDone || Engine == null) return;
        var S = Engine.State;
        double now = Time.GetTicksMsec() / 1000.0;
        if (_autoplayStart < 0) _autoplayStart = now;
        int bucket = S.Clock > 0 ? (int)(S.Clock / 300f) : (int)((now - _autoplayStart) / 30.0);
        if (bucket != _autoplayBucket)
        {
            _autoplayBucket = bucket;
            GD.Print($"[AUTOPLAY] {S.Clock / 60f:0}' half {S.Half} {S.Phase} score {S.Score[0]}-{S.Score[1]} "
                   + $"shots {S.Shots[0]}-{S.Shots[1]} fps {Godot.Engine.GetFramesPerSecond():0} real {now - _autoplayStart:0}s");
        }
        bool trainingDone = _opts.Mode == MatchEngine.ModeTraining && now - _autoplayStart > 90;
        if (S.Phase == Phase.FullTime || trainingDone)
        {
            _autoplayDone = true;
            int K(EventKind k) { int n = 0; foreach (var e in Engine.Events) if (e.Kind == k) n++; return n; }
            int T(string t) { int n = 0; foreach (var e in Engine.Events) if (e.Text.StartsWith(t)) n++; return n; }
            GD.Print($"[AUTOPLAY] END mode {_opts.Mode} score {S.Score[0]}-{S.Score[1]} shots {S.Shots[0]}-{S.Shots[1]} "
                   + $"on target {S.ShotsOnTarget[0]}-{S.ShotsOnTarget[1]} passes {S.Passes[0]}-{S.Passes[1]} "
                   + $"fouls {S.Fouls[0]}-{S.Fouls[1]} corners {S.Corners[0]}-{S.Corners[1]} "
                   + $"(last {Engine.Events.Count} events: throw-ins {T("Throw-in")} goal kicks {T("Goal kick")} saves {K(EventKind.Save)}) "
                   + $"shootout {S.ShootoutKicksHome}/{S.ShootoutKicksAway} real {now - _autoplayStart:0}s");
            int from = Math.Max(0, Engine.Events.Count - 60);
            for (int i = from; i < Engine.Events.Count; i++)
                GD.Print($"[AUTOPLAY]   {Engine.Events[i].Clock:0}' {Engine.Events[i].Kind}: {Engine.Events[i].Text}");
                        GetTree().CreateTimer(3.0).Timeout += () => GetTree().Quit();
        }
    }

    private MatchEvent? _lastSoundEvent;
    private readonly CommentaryAudio _commentary = new();
    private CommentaryContext _commentaryCtx = new();
    public ReplaySystem Replay = new();

    /// <summary>Plays the procedural sound for each match event raised since the last tick.
    /// The "Audio" autoload is Scripts/Core/Audio/ProceduralAudio.gd; without it this does nothing.</summary>
    /// <summary>Sample which movement clip each player is using (BlendLearner).</summary>
    private void RecordBlendClips()
    {
        if (++_blendFrame % 6 != 0 || Engine == null) return;
        int owner = Engine.State.Ball.Owner;
        foreach (var p in Engine.State.Players)
        {
            float speed = Mx.Flat(p.Vel).Length();
            int band = speed < .5f ? 0 : speed < 1.8f ? 1 : speed < 3.2f ? 2 : speed < 5f ? 3 : 4;
            string clip = band switch { 0 => "idle", 1 => "walk", 2 => "jog", 3 => "run", _ => "sprint" };
            int ball = p.Index == owner ? (p.Dribbling ? 2 : 1) : 0;
            _blend.Weights.Record(new BlendCell { SpeedBand = band, TurnBand = 0, BallState = ball }, clip);
        }
        _blend.Weights.Normalise();
    }

    /// <summary>Off-ball gesture / emotion tag for a nameplate.</summary>
    private string MoodTag(int index)
    {
        if (index < 0 || index >= _ambientTag.Length) return "";
        string ambient = _ambientTag[index] switch
        {
            AmbientAction.Point => " · POINTING",
            AmbientAction.Gesture => " · CALLING",
            AmbientAction.Direct => " · DIRECTING",
            AmbientAction.LookAround => " · SCANNING",
            AmbientAction.Stretch => " · STRETCHING",
            AmbientAction.WalkBack => " · WALKING BACK",
            _ => "",
        };
        string mood = _faceTag[index] switch
        {
            Emotion.Happy => " · HAPPY",
            Emotion.Sad => " · DOWN",
            Emotion.Angry => " · ANGRY",
            Emotion.Tired => " · TIRED",
            Emotion.Focused => " · FOCUSED",
            Emotion.Surprised => " · SURPRISED",
            Emotion.Injured => " · HURT",
            _ => "",
        };
        return ambient + mood;
    }

    private void PlayEventSounds()
    {
        var events = Engine.Events;
        if (events.Count == 0) return;
        var newest = events[events.Count - 1];
        if (ReferenceEquals(newest, _lastSoundEvent)) return;
        int start = events.Count - 1;                       // first call: only the latest event
        if (_lastSoundEvent != null)
        {
            int seen = events.LastIndexOf(_lastSoundEvent);
            start = seen >= 0 ? seen + 1 : Math.Max(0, events.Count - 8);   // trimmed out of the list: catch up a little
        }
        var audio = GetNodeOrNull("/root/Audio");
        if (audio != null)
            for (int i = start; i < events.Count; i++)
                audio.Call("play_for_event", events[i].Kind.ToString());
        // Crowd celebration on goal + commentary + replay.
        for (int i = start; i < events.Count; i++)
        {
            var evt = events[i];
            Replay.RecordEvent(evt, Engine.CurrentTick);
            if (evt.Kind == EventKind.Goal)
            {
                var stadium = GetNodeOrNull<Stadium>("../Stadium");
                stadium?.CelebrateCrowd(5f);
                // Update commentary context with score.
                _commentaryCtx.HomeScore = Engine.State.Score[0];
                _commentaryCtx.AwayScore = Engine.State.Score[1];
                _commentaryCtx.Minute = (int)(Engine.State.Clock / 60f);
                _commentaryCtx.LastScorer = evt.Text;
                _commentaryCtx.LastScorerTeam = evt.Side == 0 ? "Home" : "Away";
                string line = _commentary.Generate(CommentaryEvent.Goal, _commentaryCtx);
                Hud?.AddCommentary(line);
                audio?.Call("play_voice_cue", "goal");
                audio?.Call("play_chant");
            }
            else if (evt.Kind == EventKind.Shot)
            {
                _commentaryCtx.LastScorer = evt.Text;
                string line = _commentary.Generate(CommentaryEvent.Shot, _commentaryCtx);
                Hud?.AddCommentary(line);
                audio?.Call("play_voice_cue", "excited");
            }
            else if (evt.Kind == EventKind.Save)
            {
                string line = _commentary.Generate(CommentaryEvent.Save, _commentaryCtx);
                Hud?.AddCommentary(line);
                audio?.Call("play_voice_cue", "excited");
            }
            else if (evt.Kind == EventKind.Foul)
            {
                string line = _commentary.Generate(CommentaryEvent.Foul, _commentaryCtx);
                Hud?.AddCommentary(line);
                audio?.Call("play_voice_cue", "calm");
            }
            else if (evt.Kind == EventKind.Corner)
            {
                string line = _commentary.Generate(CommentaryEvent.Corner, _commentaryCtx);
                Hud?.AddCommentary(line);
            }
            else if (evt.Kind == EventKind.Offside)
            {
                string line = _commentary.Generate(CommentaryEvent.Offside, _commentaryCtx);
                Hud?.AddCommentary(line);
            }
        }
        _lastSoundEvent = newest;
    }

    private void Sync(float dt)
    {
        var b = Engine.State.Ball;
        int owner = b.Owner;
        int ctrl = Engine.State.Controlled;
        bool hasOwner = owner >= 0 && owner < Rigs.Length;
        for (int i = 0; i < Rigs.Length; i++)
        {
            var p = Engine.State.Players[i];
            var rig = Rigs[i];
            rig.Position = new Vector3(p.Pos.X, 0, p.Pos.Z);
            float yaw = MathF.Atan2(p.Facing.X, p.Facing.Z);
            rig.Rotation = new Vector3(0, yaw, 0);
            // MotionDriver owns only render-phase state; simulation PlayerState and BallState
            // remain read-only inputs. Keep the mature procedural selector if metadata is absent.
            var motion = _motion.UpdatePlayer(i, p, b, owner == i, Engine.CurrentTick);
            if (rig.Soccer != null && motion != null)
                rig.Soccer.ApplyMotion(motion);
            RigAnimator.Pose(rig, p, dt, _time, b.Pos);
            var ambient = _ambient[i].Update(dt, _time, i == owner, i != owner, p.Stamina);
            var (faceYaw, facePitch, faceRoll) = _face[i].Update(dt);
            if (rig.BoneIndex.TryGetValue("Head", out int headBone) && rig.Skeleton != null
                && (MathF.Abs(facePitch) > .001f || MathF.Abs(faceRoll) > .001f))
            {
                // Small readable head reaction without fighting the gait pose.
                var q = rig.Skeleton.GetBonePoseRotation(headBone);
                rig.Skeleton.SetBonePoseRotation(headBone,
                    q * new Quaternion(new Vector3(1f, 0f, 0f), facePitch * .6f)
                      * new Quaternion(new Vector3(0f, 0f, 1f), faceRoll * .6f));
            }
            _ambientTag[i] = ambient;
            _faceTag[i] = _face[i].Current;
            // The world-space role trackers below carry the useful names; hide
            // the rig's own duplicate label to avoid stacked text over key players.
            rig.NameLabel.Visible = false;
        }
        Ball.Position = G(b.Pos);
        float shadowHeight = Math.Clamp(b.Pos.Y, 0f, 8f);
        float shadowRadius = .62f + shadowHeight * .045f;
        BallShadow.Position = new Vector3(b.Pos.X, .022f, b.Pos.Z);
        BallShadow.Scale = new Vector3(shadowRadius, shadowRadius, shadowRadius);
        if (BallShadow.MaterialOverride is StandardMaterial3D shadowMaterial)
            shadowMaterial.AlbedoColor = new Color(.015f, .025f, .018f, Math.Clamp(.38f - shadowHeight * .035f, .08f, .38f));
        var v = Mx.Flat(b.Vel);
        Ball.RotationDegrees += new Vector3(v.Z, 0, -v.X) * (dt * 190f);

        // Ball, ball owner, controlled player and nearest opponent each get a
        // distinct, always-on marker.  The thin single ring was unreadable in
        // the recording; billboarded nameplates make possession obvious.
        BallRing.Visible = true;
        BallRing.Position = new Vector3(b.Pos.X, .05f, b.Pos.Z);
        BallRing.RotationDegrees = Vector3.Zero;
        OwnerRing.Visible = hasOwner && owner != ctrl;
        OwnerArrow.Visible = hasOwner && owner != ctrl;
        if (hasOwner)
        {
            var o = Engine.State.Players[owner];
            OwnerRing.Position = new Vector3(o.Pos.X, .055f, o.Pos.Z);
            OwnerRing.RotationDegrees = new Vector3(0, _time * 35f, 0);
            OwnerArrow.Position = new Vector3(o.Pos.X, 2.35f + MathF.Sin(_time * 5f) * .08f, o.Pos.Z);
            SetText(OwnerName, (owner == ctrl
                ? $"YOU · BALL · {o.Spec.DisplayName}"
                : $"BALL · {o.Spec.DisplayName}") + MoodTag(owner));
            OwnerName.Modulate = owner == ctrl ? new Color(.2f, 1f, .55f) : new Color(1f, .72f, .18f);
            OwnerName.Position = new Vector3(o.Pos.X, 2.2f + MathF.Sin(_time * 5f) * .08f, o.Pos.Z);
        }
        OwnerName.Visible = hasOwner;
        BallName.Visible = !hasOwner;
        if (BallName.Visible)
        {
            SetText(BallName, "LOOSE BALL");
            BallName.Position = new Vector3(b.Pos.X, 1.05f, b.Pos.Z);
        }
        if (ctrl >= 0 && ctrl < Rigs.Length)
        {
            var c = Engine.State.Players[ctrl];
            Cursor.Visible = true;
            Cursor.Position = new Vector3(c.Pos.X, .045f, c.Pos.Z);
            Cursor.RotationDegrees = new Vector3(0, _time * 40f, 0);
            ControlArrow.Visible = true;
            ControlArrow.Position = new Vector3(c.Pos.X, 2.45f + MathF.Sin(_time * 5f) * .08f, c.Pos.Z);
            ControlName.Visible = !hasOwner || owner != ctrl;
            if (ControlName.Visible)
            {
                SetText(ControlName, $"YOU · {c.Spec.DisplayName}" + MoodTag(ctrl));
                ControlName.Position = new Vector3(c.Pos.X, 2.2f + MathF.Sin(_time * 5f) * .08f, c.Pos.Z);
            }

            // Mark the nearest pressing opponent only while the controlled
            // side has possession; otherwise the ball-carrier marker already
            // identifies the opponent nearest to the ball.
            bool teamHasBall = hasOwner && Engine.State.Players[owner].Team == c.Team;
            int pressure = -1;
            float bd = float.MaxValue;
            if (teamHasBall)
            {
                foreach (var q in Engine.State.Players)
                {
                    if (q.Team == c.Team || q.IsKeeper) continue;
                    float d = Mx.FlatDist(q.Pos, b.Pos);
                    if (d < bd) { bd = d; pressure = q.Index; }
                }
            }
            bool showPressure = teamHasBall && pressure >= 0 && pressure < Rigs.Length && bd < 7f;
            PressureRing.Visible = showPressure;
            PressureName.Visible = false; // the ring alone is enough for secondary pressure
            if (showPressure)
            {
                var q = Engine.State.Players[pressure];
                PressureRing.Position = new Vector3(q.Pos.X, .05f, q.Pos.Z);
                PressureRing.RotationDegrees = new Vector3(0, _time * -30f, 0);
                SetText(PressureName, "OPP");
                PressureName.Position = new Vector3(q.Pos.X, 2.85f, q.Pos.Z);
            }
            Cam.UpdateCamera(G(b.Pos), new Vector3(c.Pos.X, 0, c.Pos.Z), G(c.Facing), dt);
        }
        else
        {
            Cursor.Visible = false;
            ControlArrow.Visible = false;
            ControlName.Visible = false;
            PressureRing.Visible = false;
            PressureName.Visible = false;
            Cam.UpdateCamera(G(b.Pos), G(b.Pos), new Vector3(1, 0, 0), dt);
        }
    }

    /// <summary>Used by the headless self-test to drive the whole 3D match pipeline without a render loop.</summary>
    public void SimulateForTest(float seconds)
    {
        if (!_built) Build();
        int steps = (int)(seconds * 60f);
        for (int i = 0; i < steps; i++)
        {
            Engine.Step(1f / 60f, PlayerCommand.None);
            Sync(1f / 60f);
        }
        Hud.Update(Engine, 1f / 60f, 0f, Cam.ModeName);
    }
}
