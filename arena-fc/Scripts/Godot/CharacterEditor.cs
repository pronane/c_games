// Arena FC - IN-GAME CHARACTER EDITOR.
// Edit the rig proportions, skinned mesh, kit, face, attributes and individual
// bone poses of every squad member, preview skeletal animation, save/load JSON,
// export a real .glb (skeleton + skin + mesh) or import your own glTF character.
using System;
using System.Collections.Generic;
using System.Linq;
using ArenaFC.Core;
using Godot;

namespace ArenaFC.GodotGame;

public partial class CharacterEditor : Node3D
{
    public Action? OnExit;
    public Action<List<CharacterSpec>>? OnPlay;
    public Action<List<CharacterSpec>>? OnApplyRoster;

    private List<CharacterSpec> _roster = new();
    private int _index;
    private CharacterSpec _spec = new();
    private CharacterRig _rig = null!;
    private Node3D _pivot = null!;
    private Camera3D _cam = null!;
    private Label _status = null!;
    private ItemList _players = null!, _files = null!;
    private OptionButton _boneCombo = null!, _clipCombo = null!;
    private HSlider _rx = null!, _ry = null!, _rz = null!;
    private LineEdit _nameEdit = null!, _shortEdit = null!;
    private SpinBox _number = null!;
    private OptionButton _skinCombo = null!, _hairCombo = null!, _roleCombo = null!;
    private CheckBox _longSleeves = null!;
    private FileDialog _fd = null!;
    private Node? _imported;
    private readonly List<Action> _refreshers = new();
    private string _clip = "idle";
    private bool _showBones;
    private float _time;
    private string _selectedBone = "LThigh";
    private static readonly string[] Clips = { "Idle", "Run", "Kick", "Celebrate", "Keeper dive" };

    public void Init(List<CharacterSpec> roster)
    {
        _roster = roster.Select(x => x.Clone()).ToList();
        if (_roster.Count == 0) _roster.Add(new CharacterSpec());
        _spec = _roster[0].Clone();
    }

    public override void _Ready()
    {
        if (_roster.Count == 0) Init(Clubs.CreateRoster(0, 11));
        Build3D();
        BuildUI();
        RebuildRig();
        RefreshLists();
        SyncControls();
        Status("Ready. Select a player, then edit anything — the skinned mesh updates live.");
    }

    public override void _Process(double delta)
    {
        _time += (float)delta;
        _pivot.Rotation = new Vector3(0, MathF.Sin(_time * .25f) * .28f, 0);
        if (_rig != null && _rig.Visible)
        {
            if (_clip == "Keeper dive")
            {
                var d = new PlayerState { Action = "dive", ActionTimer = .65f - (_time % .65f), AnimPhase = 0 };
                RigAnimator.Pose(_rig, d, (float)delta, _time, System.Numerics.Vector3.Zero);
                _rig.Skeleton.Position = Vector3.Zero;
            }
            else RigAnimator.Preview(_rig, _clip.ToLowerInvariant(), _time);
        }
    }

    private void Build3D()
    {
        var env = new Godot.Environment
        {
            BackgroundMode = Godot.Environment.BGMode.Color,
            BackgroundColor = new Color(.035f, .06f, .075f),
            AmbientLightSource = Godot.Environment.AmbientSource.Color,
            AmbientLightColor = new Color(.55f, .66f, .72f),
            AmbientLightEnergy = .9f,
            TonemapMode = Godot.Environment.ToneMapper.Filmic,
        };
        AddChild(new WorldEnvironment { Environment = env });
        var key = new DirectionalLight3D { LightEnergy = 1.7f, RotationDegrees = new Vector3(-38, -40, 0), ShadowEnabled = true };
        AddChild(key);
        var rim = new DirectionalLight3D { LightEnergy = .8f, LightColor = new Color(.35f, .8f, 1f), RotationDegrees = new Vector3(-15, 140, 0) };
        AddChild(rim);
        AddChild(Stadium.Mesh(new CylinderMesh { TopRadius = 1.45f, BottomRadius = 1.45f, Height = .06f, RadialSegments = 48 },
            Stadium.Mat(new Color(.075f, .16f, .14f)), new Vector3(0, -.035f, 0), "PreviewPodium"));
        _pivot = new Node3D { Name = "Turntable" };
        AddChild(_pivot);
        _cam = new Camera3D { Name = "EditorCamera", Position = new Vector3(0, 1.52f, 3.65f), Fov = 38 };
        _cam.LookAtFromPosition(_cam.Position, new Vector3(0, 1.0f, 0), Vector3.Up);
        AddChild(_cam);
        _cam.MakeCurrent();
    }

    private static void Place(Control c, float ax, float ay, float x, float y, float w, float h)
    {
        c.AnchorLeft = c.AnchorRight = ax; c.AnchorTop = c.AnchorBottom = ay;
        c.OffsetLeft = x; c.OffsetTop = y; c.OffsetRight = x + w; c.OffsetBottom = y + h;
    }

    private void BuildUI()
    {
        var layer = new CanvasLayer { Layer = 20 };
        AddChild(layer);
        var root = new Control { MouseFilter = Control.MouseFilterEnum.Ignore };
        root.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
        layer.AddChild(root);

        // ---------------- left column ----------------
        var left = Ui.VBox(8);
        left.AddChild(Ui.Lbl("CHARACTER EDITOR", 22, Ui.Accent));
        left.AddChild(Ui.Lbl("Squad — click a player to edit", 13, Ui.Sub));
        _players = new ItemList { CustomMinimumSize = new Vector2(270, 262) };
        _players.ItemSelected += (long i) => { Select((int)i); };
        left.AddChild(_players);
        var squadBtns = new HBoxContainer();
        squadBtns.AddChild(Ui.Btn("Add", AddPlayer));
        squadBtns.AddChild(Ui.Btn("Copy", DuplicatePlayer));
        squadBtns.AddChild(Ui.Btn("Remove", RemovePlayer));
        left.AddChild(squadBtns);
        left.AddChild(Ui.Lbl("Animation preview", 13, Ui.Sub));
        _clipCombo = Ui.Combo(Clips, 0, i => _clip = Clips[i].ToLowerInvariant());
        left.AddChild(_clipCombo);
        left.AddChild(Ui.Check("Show skeleton / bones", false, v => { _showBones = v; _rig?.ShowBones(v); }));
        left.AddChild(Ui.Lbl("Saved characters (user://characters)", 12, Ui.Sub));
        _files = new ItemList { CustomMinimumSize = new Vector2(270, 96) };
        left.AddChild(_files);
        left.AddChild(Ui.Btn("Refresh file list", RefreshFiles));
        left.AddChild(Ui.Btn("Open user data folder", () => OS.ShellOpen(ProjectSettings.GlobalizePath("user://"))));
        var leftScroll = new ScrollContainer { CustomMinimumSize = new Vector2(292, 608) };
        left.SizeFlagsHorizontal = Control.SizeFlags.ExpandFill;
        leftScroll.AddChild(left);
        var leftPanel = Ui.PanelC(leftScroll, Ui.Panel);
        Place(leftPanel, 0, 0, 16, 16, 324, 640);
        root.AddChild(leftPanel);

        // ---------------- right column (custom tab strip, no TabContainer quirks) ----------------
        _tabPanels = new[]
        {
            BuildBodyTab(), BuildKitTab(), BuildFaceTab(),
            BuildSkeletonTab(), BuildAttributesTab(), BuildFilesTab(),
        };
        string[] tabNames = { "Body", "Kit", "Face", "Skeleton", "Attributes", "Files" };
        var tabBar = new HBoxContainer();
        tabBar.AddThemeConstantOverride("separation", 4);
        _tabButtons = new Button[tabNames.Length];
        for (int i = 0; i < tabNames.Length; i++)
        {
            int capture = i;
            _tabButtons[i] = Ui.Btn(tabNames[i], () => SelectTab(capture));
            _tabButtons[i].CustomMinimumSize = new Vector2(0, 38);
            _tabButtons[i].SizeFlagsHorizontal = Control.SizeFlags.ExpandFill;
            _tabButtons[i].AddThemeFontSizeOverride("font_size", 14);
            tabBar.AddChild(_tabButtons[i]);
        }
        Place(tabBar, 1, 0, -552, 16, 536, 40);
        root.AddChild(tabBar);

        _tabHost = new ScrollContainer();
        _tabHost.SizeFlagsHorizontal = Control.SizeFlags.ExpandFill;
        _tabHost.SizeFlagsVertical = Control.SizeFlags.ExpandFill;
        var tabPanel = Ui.PanelC(_tabHost, new Color(.055f, .085f, .095f, .96f));
        Place(tabPanel, 1, 0, -552, 62, 536, 592);
        root.AddChild(tabPanel);
        SelectTab(0);

        // ---------------- bottom bar ----------------
        var bottom = new HBoxContainer();
        _status = Ui.Lbl("", 13, Ui.Accent);
        _status.AutowrapMode = TextServer.AutowrapMode.Off;
        _status.SizeFlagsHorizontal = Control.SizeFlags.ExpandFill;
        _status.CustomMinimumSize = new Vector2(0, 26);
        bottom.CustomMinimumSize = new Vector2(0, 36);
        bottom.AddChild(_status);
        bottom.AddChild(Ui.Btn("Back", () => OnExit?.Invoke()));
        bottom.AddChild(Ui.Btn("Use this squad & play", () => OnPlay?.Invoke(_roster.Select(x => x.Clone()).ToList()), true));
        var bottomPanel = Ui.PanelC(bottom, Ui.Panel);
        bottomPanel.CustomMinimumSize = new Vector2(860, 48);
        Place(bottomPanel, .5f, 1f, -430, -62, 860, 48);
        root.AddChild(bottomPanel);

        _fd = new FileDialog
        {
            Name = "ImportGlbDialog",
            FileMode = FileDialog.FileModeEnum.OpenFile,
            Access = FileDialog.AccessEnum.Filesystem,
            Title = "Import a rigged glTF character",
            Size = new Vector2I(760, 520),
        };
        _fd.AddFilter("*.glb,*.gltf", "glTF 3D models");
        _fd.FileSelected += (string path) => ImportGlb(path);
        _importLayer = layer;
    }

    private CanvasLayer _importLayer = null!;

    private void ShowImportDialog()
    {
        // A FileDialog is a Window; keep it out of the tree until needed so it
        // never paints an embedded window backdrop over the editor.
        if (_fd.GetParent() == null) _importLayer.AddChild(_fd);
        _fd.PopupCentered();
    }

    private Button[] _tabButtons = Array.Empty<Button>();
    private VBoxContainer[] _tabPanels = Array.Empty<VBoxContainer>();
    private ScrollContainer _tabHost = null!;

    private void SelectTab(int i)
    {
        if (_tabHost == null) return;
        foreach (Node c in _tabHost.GetChildren()) _tabHost.RemoveChild(c);
        var panel = _tabPanels[i];
        panel.SizeFlagsHorizontal = Control.SizeFlags.ExpandFill;
        _tabHost.AddChild(panel);
        for (int b = 0; b < _tabButtons.Length; b++) Ui.Style(_tabButtons[b], b == i);
    }

    private VBoxContainer BuildBodyTab()
    {
        var v = Ui.VBox(6);
        v.AddChild(Ui.Lbl("RIG PROPORTIONS — rebuilds the skeleton + skinned mesh live", 13, Ui.Sub));
        BodySlider(v, "Height (m)", 1.50f, 2.10f, .01f, s => s.Height, (s, x) => s.Height = x, "0.00");
        BodySlider(v, "Bulk", .70f, 1.40f, .01f, s => s.Bulk, (s, x) => s.Bulk = x);
        BodySlider(v, "Leg length", .82f, 1.20f, .01f, s => s.LegLength, (s, x) => s.LegLength = x);
        BodySlider(v, "Arm length", .82f, 1.20f, .01f, s => s.ArmLength, (s, x) => s.ArmLength = x);
        BodySlider(v, "Head scale", .80f, 1.25f, .01f, s => s.HeadScale, (s, x) => s.HeadScale = x);
        BodySlider(v, "Shoulder width", .80f, 1.25f, .01f, s => s.ShoulderWidth, (s, x) => s.ShoulderWidth = x);
        var row = new HBoxContainer();
        row.AddChild(Ui.Lbl("Skin tone", 14, Ui.Sub));
        _skinCombo = Ui.Combo(Enumerable.Range(1, CharacterSpec.SkinPalette.Length).Select(i => "Tone " + i).ToArray(),
            _spec.SkinTone, i => { _spec.SkinTone = i; _rig.Rebuild(_spec); });
        row.AddChild(_skinCombo);
        _refreshers.Add(() => _skinCombo.Selected = _spec.SkinTone);
        v.AddChild(row);
        return v;
    }

    private void BodySlider(VBoxContainer v, string label, float min, float max, float step,
                            Func<CharacterSpec, float> get, Action<CharacterSpec, float> set, string fmt = "0.00")
    {
        var row = Ui.SliderRow(label, min, max, step, get(_spec), value =>
        {
            set(_spec, (float)value);
            _rig.Rebuild(_spec);
            _rig.ShowBones(_showBones);
            _rig.Visible = _imported == null;
        }, out var sl, out var vl, fmt);
        _refreshers.Add(() => { sl.Value = get(_spec); vl.Text = ((float)sl.Value).ToString(fmt); });
        v.AddChild(row);
    }

    private VBoxContainer BuildKitTab()
    {
        var v = Ui.VBox(6);
        var r1 = new HBoxContainer();
        r1.AddChild(Ui.Lbl("Full name", 14, Ui.Sub));
        _nameEdit = new LineEdit { Text = _spec.Name, CustomMinimumSize = new Vector2(240, 34) };
        _nameEdit.TextChanged += (string t) => { _spec.Name = t; _spec.DisplayName = t.Length > 2 ? t.Split(' ').Last().ToUpperInvariant() : t.ToUpperInvariant(); _shortEdit.Text = _spec.DisplayName; _rig.ApplyAppearance(); };
        r1.AddChild(_nameEdit);
        _refreshers.Add(() => _nameEdit.Text = _spec.Name);
        v.AddChild(r1);
        var r2 = new HBoxContainer();
        r2.AddChild(Ui.Lbl("Shirt name", 14, Ui.Sub));
        _shortEdit = new LineEdit { Text = _spec.DisplayName, CustomMinimumSize = new Vector2(180, 34) };
        _shortEdit.TextChanged += (string t) => { _spec.DisplayName = t.ToUpperInvariant(); _rig.ApplyAppearance(); };
        r2.AddChild(_shortEdit);
        _refreshers.Add(() => _shortEdit.Text = _spec.DisplayName);
        v.AddChild(r2);
        var r3 = new HBoxContainer();
        r3.AddChild(Ui.Lbl("Number", 14, Ui.Sub));
        _number = new SpinBox { MinValue = 1, MaxValue = 99, Value = _spec.Number, CustomMinimumSize = new Vector2(100, 34) };
        _number.ValueChanged += (double n) => { _spec.Number = (int)n; _rig.ApplyAppearance(); };
        _refreshers.Add(() => _number.Value = _spec.Number);
        r3.AddChild(_number);
        r3.AddChild(Ui.Lbl("Role", 14, Ui.Sub));
        _roleCombo = Ui.Combo(Enum.GetNames<Role>(), (int)_spec.Role, i => { _spec.Role = (Role)i; _rig.Rebuild(_spec); });
        _refreshers.Add(() => _roleCombo.Selected = (int)_spec.Role);
        r3.AddChild(_roleCombo);
        v.AddChild(r3);
        ColorPick(v, "Kit primary", s => s.KitPrimary, (s, x) => s.KitPrimary = x);
        ColorPick(v, "Kit secondary", s => s.KitSecondary, (s, x) => s.KitSecondary = x);
        ColorPick(v, "Shorts", s => s.ShortsColor, (s, x) => s.ShortsColor = x);
        ColorPick(v, "Socks", s => s.SocksColor, (s, x) => s.SocksColor = x);
        ColorPick(v, "Boots", s => s.BootsColor, (s, x) => s.BootsColor = x);
        ColorPick(v, "Gloves", s => s.GlovesColor, (s, x) => s.GlovesColor = x);
        _longSleeves = Ui.Check("Long sleeves", _spec.LongSleeves, on => { _spec.LongSleeves = on; _rig.Rebuild(_spec); });
        _refreshers.Add(() => _longSleeves.ButtonPressed = _spec.LongSleeves);
        v.AddChild(_longSleeves);
        return v;
    }

    private void ColorPick(VBoxContainer v, string label, Func<CharacterSpec, string> get, Action<CharacterSpec, string> set)
    {
        var row = new HBoxContainer();
        var l = Ui.Lbl(label, 14, Ui.Sub); l.CustomMinimumSize = new Vector2(126, 0);
        var btn = Ui.ColorBtn(get(_spec), c => { set(_spec, "#" + Ui.ColorToHex(c)); _rig.ApplyAppearance(); });
        row.AddChild(l); row.AddChild(btn);
        _refreshers.Add(() => btn.Color = CharacterRig.C(get(_spec)));
        v.AddChild(row);
    }

    private VBoxContainer BuildFaceTab()
    {
        var v = Ui.VBox(8);
        var row = new HBoxContainer();
        row.AddChild(Ui.Lbl("Hair style", 14, Ui.Sub));
        _hairCombo = Ui.Combo(new[] { "Crop", "Short", "Curly", "Bald", "Long" }, _spec.HairStyle,
            i => { _spec.HairStyle = i; _rig.Rebuild(_spec); });
        _refreshers.Add(() => _hairCombo.Selected = _spec.HairStyle);
        row.AddChild(_hairCombo);
        v.AddChild(row);
        ColorPick(v, "Hair colour", s => s.HairColor, (s, x) => s.HairColor = x);
        v.AddChild(Ui.Lbl("Face geometry is skinned to the Head / Face bones, so head scale and bone rotations carry through to glTF export.", 13, Ui.Sub));
        return v;
    }

    private VBoxContainer BuildSkeletonTab()
    {
        var v = Ui.VBox(8);
        v.AddChild(Ui.Lbl("SKELETON POSE EDITOR (18 bones)", 14, Ui.Accent));
        var row = new HBoxContainer();
        row.AddChild(Ui.Lbl("Bone", 14, Ui.Sub));
        _boneCombo = Ui.Combo(RigBuilder.BoneNames, Array.IndexOf(RigBuilder.BoneNames, _selectedBone),
            i => { _selectedBone = RigBuilder.BoneNames[i]; ShowBoneValues(); });
        row.AddChild(_boneCombo);
        v.AddChild(row);
        _rx = PoseSlider(v, "Rotate X", 0);
        _ry = PoseSlider(v, "Rotate Y", 1);
        _rz = PoseSlider(v, "Rotate Z", 2);
        v.AddChild(Ui.Btn("Reset selected bone", () =>
        {
            _spec.SetBoneRotation(_selectedBone, 0, 0, 0);
            ShowBoneValues(); _rig.ApplyPoseOverrides();
        }));
        v.AddChild(Ui.Btn("Reset whole pose", () =>
        {
            _spec.BoneRotations.Clear();
            ShowBoneValues(); _rig.ApplyPoseOverrides();
        }));
        v.AddChild(Ui.Check("Show bone overlay in preview", false, on => { _showBones = on; _rig.ShowBones(on); }));
        v.AddChild(Ui.Lbl("Pose offsets are saved in the character JSON and written into the glTF skin's rest pose.", 13, Ui.Sub));
        return v;
    }

    private HSlider PoseSlider(VBoxContainer v, string label, int axis)
    {
        var row = Ui.SliderRow(label, -170f, 170f, 1f, 0f, value =>
        {
            var e = _spec.GetBoneRotation(_selectedBone);
            e[axis] = (float)value;
            _spec.SetBoneRotation(_selectedBone, e[0], e[1], e[2]);
            _clip = "idle";
            _rig.ApplyPoseOverrides();
        }, out var sl, out var vl, "0");
        v.AddChild(row);
        _refreshers.Add(() => { var e = _spec.GetBoneRotation(_selectedBone); sl.Value = e[axis]; vl.Text = e[axis].ToString("0"); });
        return sl;
    }

    private void ShowBoneValues()
    {
        var e = _spec.GetBoneRotation(_selectedBone);
        _rx.Value = e[0]; _ry.Value = e[1]; _rz.Value = e[2];
    }

    private VBoxContainer BuildAttributesTab()
    {
        var v = Ui.VBox(6);
        v.AddChild(Ui.Lbl("PLAYER ATTRIBUTES (0..1)", 13, Ui.Sub));
        AttrSlider(v, "Pace", s => s.Pace, (s, x) => s.Pace = x);
        AttrSlider(v, "Shooting", s => s.Shooting, (s, x) => s.Shooting = x);
        AttrSlider(v, "Passing", s => s.Passing, (s, x) => s.Passing = x);
        AttrSlider(v, "Defending", s => s.Defending, (s, x) => s.Defending = x);
        AttrSlider(v, "Goalkeeping", s => s.Goalkeeping, (s, x) => s.Goalkeeping = x);
        AttrSlider(v, "Stamina", s => s.StaminaMax, (s, x) => s.StaminaMax = x);
        return v;
    }

    private void AttrSlider(VBoxContainer v, string label, Func<CharacterSpec, float> get, Action<CharacterSpec, float> set)
    {
        var row = Ui.SliderRow(label, .1f, 1f, .01f, get(_spec), value => set(_spec, (float)value), out var sl, out var vl);
        _refreshers.Add(() => { sl.Value = get(_spec); vl.Text = ((float)sl.Value).ToString("0.00"); });
        v.AddChild(row);
    }

    private VBoxContainer BuildFilesTab()
    {
        var v = Ui.VBox(8);
        v.AddChild(Ui.Lbl("SAVE / LOAD / EXPORT", 14, Ui.Accent));
        v.AddChild(Ui.Btn("Save character JSON", SaveCharacter, true));
        v.AddChild(Ui.Btn("Load selected character JSON", LoadSelectedCharacter));
        v.AddChild(Ui.Btn("Save whole squad JSON", SaveRoster));
        v.AddChild(Ui.Btn("Load whole squad JSON", LoadRoster));
        v.AddChild(Ui.Btn("Export rigged character as .glb", ExportGlb, true));
        v.AddChild(Ui.Btn("Import external .glb / .gltf for preview", ShowImportDialog));
        v.AddChild(Ui.Btn("Remove imported model", RemoveImported));
        v.AddChild(Ui.Btn("Apply edited squad to home team", () => OnApplyRoster?.Invoke(_roster.Select(x => x.Clone()).ToList())));
        v.AddChild(Ui.Lbl("Exported .glb files contain the Skeleton3D joint hierarchy, inverse bind matrices, 4-weight skinning, all 9 PBR material surfaces and the current bone pose. Open them in Blender, Maya or Godot.", 13, Ui.Sub));
        return v;
    }

    // ---------------- data plumbing ----------------
    private void Select(int i)
    {
        _roster[_index] = _spec.Clone();
        _index = Math.Clamp(i, 0, _roster.Count - 1);
        _spec = _roster[_index].Clone();
        RemoveImported();
        RebuildRig();
        SyncControls();
        Status("Editing " + _spec.Name);
    }

    private void AddPlayer()
    {
        var p = _spec.Clone();
        p.Id = Guid.NewGuid().ToString("N")[..10];
        p.Name = "New Player"; p.DisplayName = "NEW"; p.Number = _roster.Count + 1;
        _roster.Add(p);
        RefreshLists();
        Select(_roster.Count - 1);
    }
    private void DuplicatePlayer() { var p = _spec.Clone(); p.Id = Guid.NewGuid().ToString("N")[..10]; p.Number += 1; _roster.Add(p); RefreshLists(); Select(_roster.Count - 1); }
    private void RemovePlayer()
    {
        if (_roster.Count <= 1) { Status("A squad needs at least one player."); return; }
        _roster.RemoveAt(_index); _index = Math.Clamp(_index, 0, _roster.Count - 1); _spec = _roster[_index].Clone();
        RefreshLists(); RebuildRig(); SyncControls();
    }

    private void RebuildRig()
    {
        _spec.Sanitize();
        if (_rig == null)
        {
            _rig = RigFactory.Create(_spec, true);
            _pivot.AddChild(_rig);
        }
        else _rig.Rebuild(_spec);
        _rig.ShowBones(_showBones);
        _rig.Visible = _imported == null;
    }

    private void SyncControls()
    {
        foreach (var a in _refreshers) { try { a(); } catch { } }
        ShowBoneValues();
    }

    private void RefreshLists()
    {
        _players.Clear();
        foreach (var p in _roster) _players.AddItem($"{p.Number:00}  {p.DisplayName}  ·  {p.Role}");
        if (_index < _players.ItemCount) _players.Select(_index);
        RefreshFiles();
    }

    private void RefreshFiles()
    {
        _files.Clear();
        Godot.DirAccess.MakeDirRecursiveAbsolute("user://characters");
        using var dir = Godot.DirAccess.Open("user://characters");
        if (dir == null) return;
        foreach (string f in dir.GetFiles())
            if (f.EndsWith(".json", StringComparison.OrdinalIgnoreCase)) _files.AddItem(f);
    }

    private void SaveCharacter()
    {
        Godot.DirAccess.MakeDirRecursiveAbsolute("user://characters");
        string path = $"user://characters/{GlbExporter.Sanitize(_spec.DisplayName)}_{_spec.Number:00}.json";
        using var f = Godot.FileAccess.Open(path, Godot.FileAccess.ModeFlags.Write);
        if (f == null) { Status("Save failed: " + Godot.FileAccess.GetOpenError()); return; }
        f.StoreString(_spec.ToJson());
        RefreshFiles();
        Status("Saved " + ProjectSettings.GlobalizePath(path));
    }

    private void LoadSelectedCharacter()
    {
        var sel = _files.GetSelectedItems();
        if (sel.Length == 0) { Status("Select a JSON file in the left panel first."); return; }
        string path = "user://characters/" + _files.GetItemText(sel[0]);
        _spec = CharacterSpec.FromJson(Godot.FileAccess.GetFileAsString(path));
        _spec.Sanitize();
        _roster[_index] = _spec.Clone();
        RemoveImported(); RebuildRig(); SyncControls(); RefreshLists();
        Status("Loaded " + _spec.Name);
    }

    private void SaveRoster()
    {
        Godot.DirAccess.MakeDirRecursiveAbsolute("user://characters");
        string path = "user://characters/custom_roster.json";
        using var f = Godot.FileAccess.Open(path, Godot.FileAccess.ModeFlags.Write);
        if (f == null) { Status("Save failed"); return; }
        _roster[_index] = _spec.Clone();
        f.StoreString(CharacterIo.SerializeRoster(_roster, "CUSTOM FC"));
        RefreshFiles();
        Status("Saved squad: " + ProjectSettings.GlobalizePath(path));
    }

    private void LoadRoster()
    {
        string path = "user://characters/custom_roster.json";
        if (!Godot.FileAccess.FileExists(path)) { Status("No custom_roster.json saved yet."); return; }
        var list = CharacterIo.DeserializeRoster(Godot.FileAccess.GetFileAsString(path), out _);
        if (list.Count == 0) { Status("Roster file was empty or invalid."); return; }
        _roster = list; _index = 0; _spec = _roster[0].Clone();
        RemoveImported(); RebuildRig(); SyncControls(); RefreshLists();
        Status($"Loaded squad with {_roster.Count} players.");
    }

    private void ExportGlb()
    {
        _roster[_index] = _spec.Clone();
        var result = GlbExporter.Export(_rig, $"{_spec.DisplayName}_{_spec.Number:00}");
        Status(result.ok ? "GLB exported → " + result.path + "  (" + result.info + ")" : "Export failed: " + result.info);
        if (result.ok) OS.ShellOpen(ProjectSettings.GlobalizePath("user://exports"));
    }

    private void ImportGlb(string path)
    {
        try
        {
            var doc = new GltfDocument();
            var state = new GltfState();
            Error err = doc.AppendFromFile(path, state);
            if (err != Error.Ok) { Status("glTF import failed: " + err); return; }
            Node node = doc.GenerateScene(state);
            RemoveImported();
            _imported = node;
            _pivot.AddChild(_imported);
            _rig.Visible = false;
            int bones = 0;
            CountBones(node, ref bones);
            Status($"Imported {System.IO.Path.GetFileName(path)} — {bones} bones. Procedural rig hidden; click 'Remove imported model' to edit again.");
        }
        catch (Exception ex) { Status("glTF import error: " + ex.Message); }
    }

    private static void CountBones(Node n, ref int count)
    {
        if (n is Skeleton3D sk) count += sk.GetBoneCount();
        foreach (Node c in n.GetChildren()) CountBones(c, ref count);
    }

    private void RemoveImported()
    {
        if (_imported == null) return;
        _pivot.RemoveChild(_imported);
        _imported.QueueFree();
        _imported = null;
        if (_rig != null) _rig.Visible = true;
    }

    private void Status(string s)
    {
        if (_status != null) _status.Text = s;
        GD.Print("[CharacterEditor] " + s);
    }
}
