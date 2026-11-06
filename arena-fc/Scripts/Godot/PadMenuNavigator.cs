// Gamepad navigation for every menu in the desktop build.
//
// Ui.Style() used to force FocusMode.None on every Button, so the main menu, pause
// menu, settings, controls, controller setup and character editor could only be
// driven with a mouse.  This node lives on the Window (outside GameApp.Clear()),
// watches whichever Control currently owns GUI focus and drives it from any pad —
// including unmapped EasySMX D-input pads, via the same PadLayout tables gameplay uses.
using System;
using System.Collections.Generic;
using Godot;

namespace ArenaFC.GodotGame;

public partial class PadMenuNavigator : Node
{
    /// <summary>Only enabled while a menu is on screen (so A during play still shoots).</summary>
    public static bool Active = true;

    private bool _up, _down, _left, _right, _accept, _back;

    public override void _Ready()
    {
        Name = "PadMenuNavigator";
        ProcessMode = Node.ProcessModeEnum.Always;
        InputHub.EnsureMenuPadActions();
    }

    public override void _Process(double delta)
    {
        InputHub.ReadMenuPad(out bool up, out bool down, out bool left, out bool right,
                             out bool accept, out bool back);
        bool eUp = up && !_up, eDown = down && !_down, eLeft = left && !_left,
             eRight = right && !_right, eAccept = accept && !_accept, eBack = back && !_back;
        _up = up; _down = down; _left = left; _right = right; _accept = accept; _back = back;
        if (!Active || !(eUp || eDown || eLeft || eRight || eAccept || eBack)) return;

        var root = GetTree().Root;
        var focus = GetViewport().GuiGetFocusOwner();
        if (focus == null)
        {
            // Seed focus AND activate on the same press.  Requiring a second press
            // made A / START look dead whenever a freshly opened overlay had no
            // GUI focus owner yet.
            Ui.FocusFirst(root);
            var seeded = GetViewport().GuiGetFocusOwner();
            if (eAccept && seeded != null) Activate(seeded);
            return;
        }

        var list = Ui.Focusables(root);
        int idx = list.IndexOf(focus);
        if (idx < 0) { Ui.FocusFirst(root); return; }

        int dir = eRight ? 1 : eLeft ? -1 : 0;
        if (focus is OptionButton combo && (dir != 0 || eAccept || eBack))
        {
            int step = eBack ? -1 : dir != 0 ? dir : 1;
            StepCombo(combo, step);
            return;
        }
        if (focus is Slider slider && (dir != 0 || eAccept || eBack))
        {
            float step = slider.Step > 0f ? (float)slider.Step
                                          : (float)(slider.MaxValue - slider.MinValue) / 20f;
            slider.Value = Math.Clamp(slider.Value + (eBack ? -step : dir != 0 ? dir * step : step),
                                      slider.MinValue, slider.MaxValue);
            return;
        }
        if (eDown || eUp || (dir != 0))
        {
            int step = eDown || eRight ? 1 : -1;
            Control next = list[(idx + step + list.Count) % list.Count];
            if (next != focus) next.GrabFocus();
            return;
        }
        if (eAccept) Activate(focus);
        if (eBack) GoBack(root);
    }

    private static void StepCombo(OptionButton combo, int step)
    {
        int count = combo.ItemCount;
        if (count <= 0) return;
        int next = (combo.Selected + step + count) % count;
        combo.Selected = next;               // does not emit ItemSelected
        if (Ui.ComboChanged.TryGetValue(combo, out var changed)) changed(next);
    }

    private void Activate(Control focus)
    {
        if (focus is CheckBox check)
        {
            bool on = !check.ButtonPressed;
            check.ButtonPressed = on;                    // visual state
            if (Ui.CheckChanged.TryGetValue(check, out var toggled)) toggled(on);
            else check.EmitSignal(BaseButton.SignalName.Toggled, on);
        }
        else if (focus is Button btn)
        {
            // Call the same Action that a mouse click uses.  EmitSignal("pressed")
            // alone proved unreliable for C# event subscriptions from another node.
            if (Ui.ButtonClicked.TryGetValue(btn, out var click)) click();
            else btn.EmitSignal(BaseButton.SignalName.Pressed);
        }
        else if (focus is BaseButton other) other.EmitSignal(BaseButton.SignalName.Pressed);
        else
        {
            // A non-button Control somehow owns focus: fall back to the first
            // actionable Button instead of silently swallowing START.
            foreach (Control c in Ui.Focusables(GetTree().Root))
                if (c is Button b) { Activate(b); return; }
        }
    }

    private static void GoBack(Node root)
    {
        // Overlays always have a "Back" button; the pause menu has "Resume".
        foreach (Control c in Ui.Focusables(root))
            if (c is Button b && (b.Text == "Back" || b.Text == "Resume"))
            {
                b.GrabFocus();
                if (Ui.ButtonClicked.TryGetValue(b, out var click)) click();
                else b.EmitSignal(BaseButton.SignalName.Pressed);
                return;
            }
    }
}
