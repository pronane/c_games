// Arena FC - small in-code UI toolkit (no external fonts/images, works on every export).
using System;
using Godot;

namespace ArenaFC.GodotGame;

public static class Ui
{
    public static readonly Color Bg = new(.045f, .075f, .085f, .94f);
    public static readonly Color Panel = new(.075f, .13f, .14f, .95f);
    public static readonly Color Accent = new(.12f, .85f, .52f);
    public static readonly Color Text = new(.92f, .96f, .95f);
    public static readonly Color Sub = new(.58f, .70f, .68f);

    public static StyleBoxFlat Box(Color bg, Color? border = null, int radius = 8, int borderWidth = 1)
        => Bordered(bg, border, radius, borderWidth);

    private static StyleBoxFlat Bordered(Color bg, Color? border, int radius, int borderWidth)
    {
        var box = new StyleBoxFlat
        {
            BgColor = bg,
            BorderColor = border ?? new Color(1, 1, 1, .06f),
            CornerRadiusTopLeft = radius, CornerRadiusTopRight = radius,
            CornerRadiusBottomLeft = radius, CornerRadiusBottomRight = radius,
            ContentMarginLeft = 10, ContentMarginRight = 10,
            ContentMarginTop = 6, ContentMarginBottom = 6,
        };
        box.SetBorderWidthAll(borderWidth);
        return box;
    }

    public static void Style(Button b, bool primary = false)
    {
        b.AddThemeStyleboxOverride("normal", Box(primary ? new Color(.10f, .55f, .36f, .96f) : Panel));
        b.AddThemeStyleboxOverride("hover", Box(primary ? new Color(.13f, .72f, .46f) : new Color(.13f, .22f, .23f)));
        b.AddThemeStyleboxOverride("pressed", Box(new Color(.09f, .38f, .27f)));
        b.AddThemeStyleboxOverride("disabled", Box(new Color(.10f, .12f, .13f)));
        b.AddThemeColorOverride("font_color", Text);
        b.AddThemeColorOverride("font_hover_color", Color.FromHsv(.41f, .1f, 1f));
        b.AddThemeFontSizeOverride("font_size", 17);
        b.CustomMinimumSize = new Vector2(0, 40);
        b.FocusMode = Control.FocusModeEnum.None;
    }

    public static Button Btn(string text, Action onClick, bool primary = false)
    {
        var b = new Button { Text = text };
        Style(b, primary);
        b.Pressed += onClick;
        return b;
    }

    public static Label Lbl(string text, int size = 16, Color? color = null)
    {
        var l = new Label { Text = text };
        l.AddThemeFontSizeOverride("font_size", size);
        l.AddThemeColorOverride("font_color", color ?? Text);
        l.AutowrapMode = TextServer.AutowrapMode.WordSmart;
        return l;
    }

    public static PanelContainer PanelC(Control child, Color? bg = null)
    {
        var p = new PanelContainer();
        p.AddThemeStyleboxOverride("panel", Box(bg ?? Bg));
        p.AddChild(child);
        return p;
    }

    public static HSlider Slider(float min, float max, float step, float value, Action<double> changed)
    {
        var s = new HSlider { MinValue = min, MaxValue = max, Step = step, Value = value, CustomMinimumSize = new Vector2(170, 22) };
        s.ValueChanged += (v) => changed(v);
        return s;
    }

    public static HBoxContainer SliderRow(string label, float min, float max, float step, float value,
                                          Action<double> changed, out HSlider slider, out Label valueLabel, string fmt = "0.00")
    {
        var row = new HBoxContainer();
        var l = Lbl(label, 14, Sub); l.CustomMinimumSize = new Vector2(126, 0);
        valueLabel = Lbl(value.ToString(fmt), 13, Accent); valueLabel.CustomMinimumSize = new Vector2(52, 0);
        var vl = valueLabel;
        slider = Slider(min, max, step, value, (v) => { vl.Text = v.ToString(fmt); changed(v); });
        slider.SizeFlagsHorizontal = Control.SizeFlags.ExpandFill;
        row.AddChild(l); row.AddChild(slider); row.AddChild(valueLabel);
        return row;
    }

    public static ColorPickerButton ColorBtn(string hex, Action<Color> changed)
    {
        var c = new ColorPickerButton { Color = CharacterRig.C(hex), CustomMinimumSize = new Vector2(120, 36), Text = "Colour" };
        c.ColorChanged += (col) => changed(col);
        return c;
    }

    public static HBoxContainer ColorRow(string label, string hex, Action<Color> changed)
    {
        var row = new HBoxContainer();
        var l = Lbl(label, 14, Sub); l.CustomMinimumSize = new Vector2(126, 0);
        row.AddChild(l);
        row.AddChild(ColorBtn(hex, changed));
        return row;
    }

    public static OptionButton Combo(string[] items, int selected, Action<int> changed)
    {
        var o = new OptionButton { CustomMinimumSize = new Vector2(0, 36) };
        foreach (var i in items) o.AddItem(i);
        o.Selected = selected;
        o.ItemSelected += (long idx) => changed((int)idx);
        return o;
    }

    public static CheckBox Check(string text, bool value, Action<bool> changed)
    {
        var c = new CheckBox { Text = text, ButtonPressed = value };
        c.Toggled += (on) => changed(on);
        return c;
    }

    public static VBoxContainer VBox(int separation = 6)
    {
        var b = new VBoxContainer();
        b.AddThemeConstantOverride("separation", separation);
        return b;
    }

    public static string ColorToHex(Color c) => c.ToHtml(false);
}
