// Arena FC - one input layer for keyboard, mouse, gamepad and touch.
// Produces the same PlayerCommand on every platform.
using System;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public sealed class InputHub
{
    // Set by the on-screen touch controls.
    public Vector2 TouchMove;
    public bool TouchSprint, TouchPass, TouchThrough, TouchTackle, TouchSwitch, TouchShoot;
    public bool TouchEnabled;

    private bool _pShoot, _pPass, _pThrough, _pTackle, _pSwitch, _pPause, _pCamera, _pLob;
    private float _charge;
    public float Charge => _charge;
    public bool PausePressed { get; private set; }
    public bool CameraPressed { get; private set; }

    private static bool Edge(bool now, ref bool prev)
    {
        bool r = now && !prev;
        prev = now;
        return r;
    }

    public PlayerCommand Read(float dt)
    {
        var cmd = new PlayerCommand();
        PausePressed = false;
        CameraPressed = false;

        // --- movement: WASD / arrows / left stick / D-pad / virtual stick ---
        Vector2 move = Vector2.Zero;
        if (Input.IsPhysicalKeyPressed(Key.A) || Input.IsPhysicalKeyPressed(Key.Left) || Input.IsJoyButtonPressed(0, JoyButton.DpadLeft)) move.X -= 1;
        if (Input.IsPhysicalKeyPressed(Key.D) || Input.IsPhysicalKeyPressed(Key.Right) || Input.IsJoyButtonPressed(0, JoyButton.DpadRight)) move.X += 1;
        if (Input.IsPhysicalKeyPressed(Key.W) || Input.IsPhysicalKeyPressed(Key.Up) || Input.IsJoyButtonPressed(0, JoyButton.DpadUp)) move.Y -= 1;
        if (Input.IsPhysicalKeyPressed(Key.S) || Input.IsPhysicalKeyPressed(Key.Down) || Input.IsJoyButtonPressed(0, JoyButton.DpadDown)) move.Y += 1;
        float jx = Input.GetJoyAxis(0, JoyAxis.LeftX), jy = Input.GetJoyAxis(0, JoyAxis.LeftY);
        if (MathF.Abs(jx) > .18f || MathF.Abs(jy) > .18f) move += new Vector2(jx, jy);
        if (TouchEnabled) move += TouchMove;
        if (move.LengthSquared() > 1f) move = move.Normalized();
        cmd.Move = new System.Numerics.Vector2(move.X, move.Y);

        bool sprint = Input.IsPhysicalKeyPressed(Key.Shift) || Input.IsJoyButtonPressed(0, JoyButton.RightShoulder)
                      || Input.GetJoyAxis(0, JoyAxis.TriggerRight) > .5f || (TouchEnabled && TouchSprint);
        bool pass = Input.IsPhysicalKeyPressed(Key.E) || Input.IsJoyButtonPressed(0, JoyButton.A) || (TouchEnabled && TouchPass);
        bool through = Input.IsPhysicalKeyPressed(Key.Q) || Input.IsJoyButtonPressed(0, JoyButton.Y) || (TouchEnabled && TouchThrough);
        bool tackle = Input.IsPhysicalKeyPressed(Key.F) || Input.IsJoyButtonPressed(0, JoyButton.B) || (TouchEnabled && TouchTackle);
        bool sw = Input.IsPhysicalKeyPressed(Key.Tab) || Input.IsJoyButtonPressed(0, JoyButton.LeftShoulder) || (TouchEnabled && TouchSwitch);
        bool shoot = Input.IsPhysicalKeyPressed(Key.Space) || Input.IsJoyButtonPressed(0, JoyButton.X) || (TouchEnabled && TouchShoot);
        bool pause = Input.IsPhysicalKeyPressed(Key.Escape) || Input.IsJoyButtonPressed(0, JoyButton.Start);
        bool camera = Input.IsPhysicalKeyPressed(Key.C) || Input.IsJoyButtonPressed(0, JoyButton.RightStick);
        bool lob = Input.IsPhysicalKeyPressed(Key.R);

        cmd.Sprint = sprint;
        cmd.Pass = Edge(pass, ref _pPass);
        cmd.Through = Edge(through, ref _pThrough);
        cmd.Tackle = Edge(tackle, ref _pTackle);
        cmd.Switch = Edge(sw, ref _pSwitch) || Input.IsMouseButtonPressed(MouseButton.Middle);
        cmd.Lob = Edge(lob, ref _pLob);
        PausePressed = Edge(pause, ref _pPause);
        CameraPressed = Edge(camera, ref _pCamera);

        // Hold to charge a shot; release to shoot. Also works on touch & gamepad.
        if (shoot) _charge = MathF.Min(1f, _charge + dt / .95f);
        else if (_charge > 0f) { cmd.Shoot = true; cmd.Charge = MathF.Max(.22f, _charge); _charge = 0f; }
        _pShoot = shoot;
        return cmd;
    }

    public void Reset()
    {
        _charge = 0;
        _pShoot = _pPass = _pThrough = _pTackle = _pSwitch = _pPause = _pCamera = _pLob = false;
    }
}
