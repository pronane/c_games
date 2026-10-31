// Arena FC - ties the pure-C# match simulation to the 3D stadium, rigged players,
// ball, broadcast cameras and HUD. Runs at the physics tick on every platform.
using System;
using System.Collections.Generic;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public partial class MatchView : Node3D
{
    public MatchEngine Engine = null!;
    public InputHub Input = new();
    public Hud Hud = null!;
    public BroadcastCamera Cam = null!;
    public CharacterRig[] Rigs = Array.Empty<CharacterRig>();
    public MeshInstance3D Ball = null!, Cursor = null!;

    private MatchOptions _opts = new();
    private Action? _onExit;
    private float _time;
    private bool _built;

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

    private void Build()
    {
        if (_built) return;
        _built = true;
        Name = "MatchView";

        var stadium = new Stadium();
        stadium.Build(true);
        AddChild(stadium);

        Engine = new MatchEngine(_opts);
        Rigs = new CharacterRig[Engine.State.Players.Length];
        for (int i = 0; i < Rigs.Length; i++)
        {
            Rigs[i] = RigFactory.Create(Engine.State.Players[i].Spec);
            Rigs[i].Name = "Player_" + i;
            AddChild(Rigs[i]);
        }

        Ball = BallFactory.Create();
        AddChild(Ball);

        var cursorMat = new StandardMaterial3D
        {
            AlbedoColor = new Color(.2f, 1f, .55f),
            EmissionEnabled = true,
            Emission = new Color(.2f, 1f, .55f),
            ShadingMode = BaseMaterial3D.ShadingModeEnum.Unshaded,
        };
        Cursor = new MeshInstance3D
        {
            Name = "ControlledRing",
            Mesh = new TorusMesh { InnerRadius = .52f, OuterRadius = .68f, RingSegments = 24, Rings = 6 },
            MaterialOverride = cursorMat,
        };
        AddChild(Cursor);

        Cam = new BroadcastCamera { Name = "BroadcastCamera", Fov = 55, Far = 600f };
        AddChild(Cam);
        Cam.MakeCurrent();

        Hud = new Hud();
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
        if (Input.PausePressed) Hud.SetPaused(!Hud.Paused);
        if (Input.CameraPressed) Cam.Cycle();
        if (Hud.Paused) { Hud.Update(Engine, dt, Input.Charge, Cam.ModeName); return; }
        Engine.Step(dt, cmd);
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
        if (Engine.State.Controlled >= 0 && Engine.State.Controlled < Rigs.Length)
        {
            var c = Engine.State.Players[Engine.State.Controlled];
            Cursor.Visible = true;
            Cursor.Position = new Vector3(c.Pos.X, .045f, c.Pos.Z);
            Cursor.RotationDegrees = new Vector3(0, _time * 40f, 0);
            Cam.UpdateCamera(G(b.Pos), new Vector3(c.Pos.X, 0, c.Pos.Z), G(c.Facing), dt);
        }
        else { Cursor.Visible = false; Cam.UpdateCamera(G(b.Pos), G(b.Pos), new Vector3(1, 0, 0), dt); }
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
