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
    public MatchEngine Engine = null!;
    public InputHub Input = new();
    public Hud Hud = null!;
    public BroadcastCamera Cam = null!;
    public CharacterRig[] Rigs = Array.Empty<CharacterRig>();
    public MeshInstance3D Ball = null!, Cursor = null!, BallRing = null!, OwnerRing = null!,
                          ControlArrow = null!, OwnerArrow = null!;
    /// <summary>When set, the authoritative server drives the sim instead of the local engine.</summary>
    public OnlineMatch? Online;

    private MatchOptions _opts = new();
    private Action? _onExit;
    private float _time;
    private bool _built;
    /// <summary>One-shot button edges survive physics frames that produce no fixed
    /// engine tick, instead of being silently dropped by the accumulator.</summary>
    private PlayerCommand _pending;

    public void Init(MatchOptions opts, List<CharacterSpec>? customHome, Action onExit)
    {
        _opts = opts ?? new MatchOptions();
        if (customHome != null && customHome.Count > 0) _opts.CustomHome = customHome;
        _onExit = onExit;
    }

    public override void _Ready()
    {
        Build();
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
        if (cmd.Charge > _pending.Charge) _pending.Charge = cmd.Charge;
    }

    private void Build()
    {
        if (_built) return;
        _built = true;
        Name = "MatchView";

        var stadium = new Stadium();
        stadium.Build(true);
        AddChild(stadium);

        // Online: the mirror/predictor engine is authoritative for rendering, but
        // it is still a plain MatchEngine so every HUD/camera/rig path is reused.
        Engine = Online != null ? Online.Engine : new MatchEngine(_opts);
        Rigs = new CharacterRig[Engine.State.Players.Length];
        for (int i = 0; i < Rigs.Length; i++)
        {
            Rigs[i] = RigFactory.Create(Engine.State.Players[i].Spec);
            Rigs[i].Name = "Player_" + i;
            AddChild(Rigs[i]);
        }

        Ball = BallFactory.Create();
        AddChild(Ball);

        var green = MarkerMaterial(new Color(.2f, 1f, .55f));
        var amber = MarkerMaterial(new Color(1f, .72f, .18f));
        var yellow = MarkerMaterial(new Color(1f, .95f, .55f));
        Cursor = Marker("ControlledRing",
            new TorusMesh { InnerRadius = .62f, OuterRadius = .82f, RingSegments = 32, Rings = 8 }, green);
        AddChild(Cursor);
        BallRing = Marker("BallRing",
            new TorusMesh { InnerRadius = .30f, OuterRadius = .44f, RingSegments = 24, Rings = 6 }, yellow);
        AddChild(BallRing);
        OwnerRing = Marker("BallOwnerRing",
            new TorusMesh { InnerRadius = .78f, OuterRadius = .94f, RingSegments = 32, Rings = 8 }, amber);
        AddChild(OwnerRing);
        ControlArrow = Marker("ControlledArrow",
            new CylinderMesh { TopRadius = 0f, BottomRadius = .24f, Height = .42f, RadialSegments = 8, Rings = 1 }, green);
        ControlArrow.RotationDegrees = new Vector3(180f, 0f, 0f);
        AddChild(ControlArrow);
        OwnerArrow = Marker("BallOwnerArrow",
            new CylinderMesh { TopRadius = 0f, BottomRadius = .24f, Height = .42f, RadialSegments = 8, Rings = 1 }, amber);
        OwnerArrow.RotationDegrees = new Vector3(180f, 0f, 0f);
        AddChild(OwnerArrow);

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
        Hud.ShowToast("KICK OFF!", 1.8f);
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
            Hud.SetPaused(!Hud.Paused);
            _pending = PlayerCommand.None;
            Input.Reset();
        }
        if (Input.CameraPressed) Cam.Cycle();
        if (Hud.Paused)
        {
            // Keep draining authoritative packets even while the local UI is paused.
            Online?.Client.Poll();
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
            Engine.Step(dt, _pending);
            if (Engine.CurrentTick != before) _pending = PlayerCommand.None;
        }
        PlayEventSounds();
        Sync(dt);
        Hud.Update(Engine, dt, Input.Charge, Cam.ModeName);
    }

    private MatchEvent? _lastSoundEvent;

    /// <summary>Plays the procedural sound for each match event raised since the last tick.
    /// The "Audio" autoload is Scripts/Core/Audio/ProceduralAudio.gd; without it this does nothing.</summary>
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
        _lastSoundEvent = newest;
    }

    private void Sync(float dt)
    {
        for (int i = 0; i < Rigs.Length; i++)
        {
            var p = Engine.State.Players[i];
            var rig = Rigs[i];
            rig.Position = new Vector3(p.Pos.X, 0, p.Pos.Z);
            float yaw = MathF.Atan2(p.Facing.X, p.Facing.Z);
            rig.Rotation = new Vector3(0, yaw, 0);
            RigAnimator.Pose(rig, p, dt, _time, Engine.State.Ball.Pos);
        }
        var b = Engine.State.Ball;
        Ball.Position = G(b.Pos);
        var v = Mx.Flat(b.Vel);
        Ball.RotationDegrees += new Vector3(v.Z, 0, -v.X) * (dt * 190f);

        // Ball, ball owner and controlled player each get a distinct, always-on
        // marker.  The old thin green ring alone did not show WHO had the ball.
        BallRing.Visible = true;
        BallRing.Position = new Vector3(b.Pos.X, .05f, b.Pos.Z);
        BallRing.RotationDegrees = new Vector3(0, _time * -55f, 0);
        int owner = Engine.State.Ball.Owner;
        int ctrl = Engine.State.Controlled;
        bool hasOwner = owner >= 0 && owner < Rigs.Length;
        OwnerRing.Visible = hasOwner && owner != ctrl;
        OwnerArrow.Visible = hasOwner;
        if (hasOwner)
        {
            var o = Engine.State.Players[owner];
            OwnerRing.Position = new Vector3(o.Pos.X, .055f, o.Pos.Z);
            OwnerRing.RotationDegrees = new Vector3(0, _time * 35f, 0);
            OwnerArrow.Position = new Vector3(o.Pos.X, 2.35f + MathF.Sin(_time * 5f) * .08f, o.Pos.Z);
        }
        if (ctrl >= 0 && ctrl < Rigs.Length)
        {
            var c = Engine.State.Players[ctrl];
            Cursor.Visible = true;
            Cursor.Position = new Vector3(c.Pos.X, .045f, c.Pos.Z);
            Cursor.RotationDegrees = new Vector3(0, _time * 40f, 0);
            ControlArrow.Visible = true;
            ControlArrow.Position = new Vector3(c.Pos.X, 2.45f + MathF.Sin(_time * 5f) * .08f, c.Pos.Z);
            Cam.UpdateCamera(G(b.Pos), new Vector3(c.Pos.X, 0, c.Pos.Z), G(c.Facing), dt);
        }
        else
        {
            Cursor.Visible = false;
            ControlArrow.Visible = false;
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
