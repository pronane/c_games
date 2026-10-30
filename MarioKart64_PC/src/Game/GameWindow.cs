using System;
using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;
using MarioKart64.Audio;
using MarioKart64.Core;
using MarioKart64.Entities;
using MarioKart64.Input;
using MarioKart64.Rendering;
using MarioKart64.Tracks;

namespace MarioKart64.Game
{
    public enum MenuScreen
    {
        Title = 0,
        ModeAndClass = 1,
        CharacterSelect = 2,
        CupOrTrackSelect = 3,
        EasySmxStudio = 4,
        InSession = 5
    }

    public sealed class GameWindow : Form
    {
        private IntPtr _hdc = IntPtr.Zero;
        private IntPtr _hglrc = IntPtr.Zero;
        private bool _glReady = false;

        private readonly EasySmxControllerManager _controllers = new EasySmxControllerManager();
        private readonly SceneRenderer _sceneRenderer = new SceneRenderer();
        private readonly GameSession _session = new GameSession();

        // Background attract-mode demo session on Title Screen!
        private readonly GameSession _attractDemo = new GameSession();

        // Menu Navigation State
        private MenuScreen _screen = MenuScreen.Title;
        private int _titleCursor = 0;
        private GameMode _chosenMode = GameMode.MarioGP;
        private EngineClass _chosenCC = EngineClass.CC100;
        private int _chosenPlayers = 1;
        private int _setupRow = 0;

        // Character Selection (P1..P4)
        private readonly CharacterId[] _chosenChars = new CharacterId[4]
        {
            CharacterId.Mario, CharacterId.Luigi, CharacterId.Yoshi, CharacterId.Toad
        };
        private int _selectingPlayerIdx = 0;

        // Cup / Track Selection
        private CupType _chosenCup = CupType.Mushroom;
        private int _chosenTrackInCup = 0; // 0..3
        private int _chosenBattleIdx = 0;  // 0..3

        // EasySMX Controller Studio state
        private int _studioRow = 0;
        private int _rebindingAction = -1; // -1=none, 0=Accelerate, 1=Brake, 2=Hop/Drift, 3=Item

        // Fullscreen state
        private bool _isFullscreen = false;
        private FormBorderStyle _savedBorder;
        private Rectangle _savedBounds;

        // High-precision 60Hz fixed-timestep loop
        private readonly Stopwatch _clock = new Stopwatch();
        private double _lastTimeSec = 0.0;
        private double _accumulator = 0.0;
        private float _uiTime = 0f;

        public GameWindow()
        {
            Text = "Mario Kart 64 PC - N64 Edition (EasySMX USB Controller Ready)";
            ClientSize = new Size(1280, 720);
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.Black;
            KeyPreview = true;

            SetStyle(ControlStyles.Opaque | ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint, true);

            try
            {
                string icoPath = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "mk64.ico");
                if (!System.IO.File.Exists(icoPath))
                    icoPath = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, @"..\assets\mk64.ico");
                if (System.IO.File.Exists(icoPath))
                    Icon = new Icon(icoPath);
            }
            catch { }
        }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams cp = base.CreateParams;
                // CS_OWNDC (0x0020): Dedicated Win32 OpenGL Device Context
                cp.ClassStyle |= 0x0020;
                return cp;
            }
        }

        protected override void OnPaintBackground(PaintEventArgs e)
        {
            // Suppressed so GDI never flickers over OpenGL SwapBuffers
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            InitOpenGL();
        }

        private void InitOpenGL()
        {
            if (_glReady) return;
            _hdc = Gl.GetDC(Handle);
            PIXELFORMATDESCRIPTOR pfd = new PIXELFORMATDESCRIPTOR();
            pfd.nSize = (ushort)System.Runtime.InteropServices.Marshal.SizeOf(typeof(PIXELFORMATDESCRIPTOR));
            pfd.nVersion = 1;
            pfd.dwFlags = Gl.PFD_DRAW_TO_WINDOW | Gl.PFD_SUPPORT_OPENGL | Gl.PFD_DOUBLEBUFFER;
            pfd.iPixelType = Gl.PFD_TYPE_RGBA;
            pfd.cColorBits = 32;
            pfd.cDepthBits = 24;
            pfd.cStencilBits = 8;
            pfd.iLayerType = Gl.PFD_MAIN_PLANE;

            int pf = Gl.ChoosePixelFormat(_hdc, ref pfd);
            Gl.SetPixelFormat(_hdc, pf, ref pfd);

            _hglrc = Gl.wglCreateContext(_hdc);
            Gl.wglMakeCurrent(_hdc, _hglrc);
            Gl.TrySetSwapInterval(1);
            Gl.glShadeModel(Gl.GL_SMOOTH);

            ProceduralTextures.InitializeAll();
            _glReady = true;

            // Start live 3D attract-mode background race on Luigi Raceway!
            _attractDemo.StartNewMatch(GameMode.VsRace, EngineClass.CC100, 1, _chosenChars, CupType.Mushroom, CourseId.LuigiRaceway);
            _attractDemo.Karts[0].IsHuman = false;
            _attractDemo.Phase = SessionPhase.ActivePlay;

            N64AudioSynth.Instance.Initialize();
            N64AudioSynth.Instance.SetMusic(MusicTrackId.TitleGroove, 1.0f);

            _clock.Start();
            _lastTimeSec = _clock.Elapsed.TotalSeconds;
            Application.Idle += OnApplicationIdle;
        }

        private void OnApplicationIdle(object sender, EventArgs e)
        {
            NativeMsg msg;
            while (!PeekMessage(out msg, IntPtr.Zero, 0, 0, 0))
            {
                if (!Created || IsDisposed) return;
                StepAndRenderFrame();
            }
        }

        [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
        private struct NativeMsg
        {
            public IntPtr hWnd;
            public uint message;
            public IntPtr wParam;
            public IntPtr lParam;
            public uint time;
            public Point pt;
        }

        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern bool PeekMessage(out NativeMsg lpMsg, IntPtr hWnd, uint wMsgFilterMin, uint wMsgFilterMax, uint wRemoveMsg);

        protected override void OnKeyDown(KeyEventArgs e)
        {
            base.OnKeyDown(e);
            if (e.KeyCode == Keys.F11 || (e.Alt && e.KeyCode == Keys.Enter))
            {
                ToggleFullscreen();
                e.Handled = true;
                return;
            }
            if (e.KeyCode == Keys.F1 && _screen != MenuScreen.InSession)
            {
                _screen = MenuScreen.EasySmxStudio;
                N64AudioSynth.Instance.PlaySfx(SfxId.MenuConfirm);
                return;
            }
            _controllers.OnKeyDown(e.KeyCode);
        }

        protected override void OnKeyUp(KeyEventArgs e)
        {
            base.OnKeyUp(e);
            _controllers.OnKeyUp(e.KeyCode);
        }

        protected override void OnDeactivate(EventArgs e)
        {
            base.OnDeactivate(e);
            _controllers.ClearKeys();
            _controllers.StopAllRumble();
        }

        private void ToggleFullscreen()
        {
            if (!_isFullscreen)
            {
                _savedBorder = FormBorderStyle;
                _savedBounds = Bounds;
                FormBorderStyle = FormBorderStyle.None;
                Bounds = Screen.FromControl(this).Bounds;
                _isFullscreen = true;
            }
            else
            {
                FormBorderStyle = _savedBorder;
                Bounds = _savedBounds;
                _isFullscreen = false;
            }
        }

        private void StepAndRenderFrame()
        {
            if (!_glReady || WindowState == FormWindowState.Minimized)
            {
                System.Threading.Thread.Sleep(10);
                return;
            }

            double now = _clock.Elapsed.TotalSeconds;
            double frameDelta = now - _lastTimeSec;
            _lastTimeSec = now;
            if (frameDelta > 0.10) frameDelta = 0.10;

            _accumulator += frameDelta;
            const double FixedDt = 1.0 / 60.0;

            bool stepped = false;
            while (_accumulator >= FixedDt)
            {
                _accumulator -= FixedDt;
                FixedUpdate((float)FixedDt);
                stepped = true;
            }

            if (stepped)
            {
                RenderFrame();
                Gl.SwapBuffers(_hdc);
            }
            else
            {
                System.Threading.Thread.Sleep(1);
            }
        }

        private void FixedUpdate(float dt)
        {
            _uiTime += dt;
            _controllers.Update(dt);

            if (_screen == MenuScreen.InSession)
            {
                bool quitToMenu = _session.Update(_controllers, _sceneRenderer, dt);
                if (quitToMenu)
                {
                    _screen = MenuScreen.Title;
                    _controllers.StopAllRumble();
                    N64AudioSynth.Instance.SetEngineState(false, 0f, false, false);
                    N64AudioSynth.Instance.SetStarmanOverride(false);
                    N64AudioSynth.Instance.SetMusic(MusicTrackId.TitleGroove, 1.0f);
                }
                return;
            }

            // Advance live 3D attract-mode race behind menus!
            N64AudioSynth.Instance.SetEngineState(false, 0f, false, false);
            _attractDemo.Update(_controllers, _sceneRenderer, dt);
            // Keep attract demo permanently in ActivePlay
            if (_attractDemo.Phase != SessionPhase.ActivePlay)
                _attractDemo.Phase = SessionPhase.ActivePlay;

            UpdateMenuNavigation(dt);
        }

        private void UpdateMenuNavigation(float dt)
        {
            PlayerInputState p1 = _controllers.GetPlayer(0);

            if (_screen == MenuScreen.Title)
            {
                // 0=Mario GP, 1=Time Trials, 2=VS Mode, 3=Battle Mode, 4=EasySMX Controller Studio, 5=Quit
                if (p1.MenuUpPressed)   { _titleCursor = (_titleCursor + 5) % 6; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                if (p1.MenuDownPressed) { _titleCursor = (_titleCursor + 1) % 6; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }

                if (p1.ConfirmPressed)
                {
                    N64AudioSynth.Instance.PlaySfx(SfxId.MenuConfirm);
                    if (_titleCursor == 5)
                    {
                        Close();
                        return;
                    }
                    if (_titleCursor == 4)
                    {
                        _screen = MenuScreen.EasySmxStudio;
                        _studioRow = 0;
                        _rebindingAction = -1;
                        return;
                    }

                    _chosenMode = (GameMode)_titleCursor;
                    if (_chosenMode == GameMode.TimeTrials) _chosenPlayers = 1;
                    _setupRow = 0;
                    _screen = MenuScreen.ModeAndClass;
                    N64AudioSynth.Instance.SetMusic(MusicTrackId.MenuSetup, 1.0f);
                }
            }
            else if (_screen == MenuScreen.ModeAndClass)
            {
                int rowCount = (_chosenMode == GameMode.TimeTrials) ? 1 : 2;
                if (p1.MenuUpPressed)   { _setupRow = (_setupRow + rowCount) % (rowCount + 1); N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                if (p1.MenuDownPressed) { _setupRow = (_setupRow + 1) % (rowCount + 1); N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }

                if (_setupRow == 0 && _chosenMode != GameMode.TimeTrials)
                {
                    if (p1.MenuLeftPressed)  { _chosenPlayers = MathUtil.ClampInt(_chosenPlayers - 1, 1, 4); N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                    if (p1.MenuRightPressed) { _chosenPlayers = MathUtil.ClampInt(_chosenPlayers + 1, 1, 4); N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                }
                else if ((_setupRow == 1 && _chosenMode != GameMode.TimeTrials) || (_setupRow == 0 && _chosenMode == GameMode.TimeTrials))
                {
                    if (_chosenMode != GameMode.Battle)
                    {
                        int cc = (int)_chosenCC;
                        if (p1.MenuLeftPressed)  { cc = (cc + 3) % 4; _chosenCC = (EngineClass)cc; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                        if (p1.MenuRightPressed) { cc = (cc + 1) % 4; _chosenCC = (EngineClass)cc; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                    }
                }

                if (p1.ConfirmPressed)
                {
                    N64AudioSynth.Instance.PlaySfx(SfxId.MenuConfirm);
                    _selectingPlayerIdx = 0;
                    _screen = MenuScreen.CharacterSelect;
                }
                else if (p1.CancelPressed)
                {
                    N64AudioSynth.Instance.PlaySfx(SfxId.MenuBack);
                    _screen = MenuScreen.Title;
                    N64AudioSynth.Instance.SetMusic(MusicTrackId.TitleGroove, 1.0f);
                }
            }
            else if (_screen == MenuScreen.CharacterSelect)
            {
                // Active player's controller (or P1 fallback so solo user can set all slots easily!)
                PlayerInputState activeIn = _controllers.GetPlayer(_selectingPlayerIdx);
                if (!activeIn.IsGamepadConnected && _selectingPlayerIdx > 0) activeIn = p1;

                int cur = (int)_chosenChars[_selectingPlayerIdx];
                int row = cur / 4;
                int col = cur % 4;

                if (activeIn.MenuLeftPressed)  { col = (col + 3) % 4; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                if (activeIn.MenuRightPressed) { col = (col + 1) % 4; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                if (activeIn.MenuUpPressed || activeIn.MenuDownPressed) { row = 1 - row; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                _chosenChars[_selectingPlayerIdx] = (CharacterId)(row * 4 + col);

                if (activeIn.ConfirmPressed)
                {
                    N64AudioSynth.Instance.PlaySfx(SfxId.MenuConfirm);
                    _selectingPlayerIdx++;
                    if (_selectingPlayerIdx >= _chosenPlayers)
                    {
                        _selectingPlayerIdx = _chosenPlayers - 1;
                        _screen = MenuScreen.CupOrTrackSelect;
                    }
                }
                else if (activeIn.CancelPressed)
                {
                    N64AudioSynth.Instance.PlaySfx(SfxId.MenuBack);
                    if (_selectingPlayerIdx > 0) _selectingPlayerIdx--;
                    else _screen = MenuScreen.ModeAndClass;
                }
            }
            else if (_screen == MenuScreen.CupOrTrackSelect)
            {
                if (_chosenMode == GameMode.Battle)
                {
                    if (p1.MenuLeftPressed || p1.MenuUpPressed)    { _chosenBattleIdx = (_chosenBattleIdx + 3) % 4; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                    if (p1.MenuRightPressed || p1.MenuDownPressed) { _chosenBattleIdx = (_chosenBattleIdx + 1) % 4; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                }
                else if (_chosenMode == GameMode.MarioGP)
                {
                    int cup = (int)_chosenCup;
                    if (p1.MenuLeftPressed || p1.MenuUpPressed)    { cup = (cup + 3) % 4; _chosenCup = (CupType)cup; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                    if (p1.MenuRightPressed || p1.MenuDownPressed) { cup = (cup + 1) % 4; _chosenCup = (CupType)cup; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                }
                else
                {
                    // Time Trials & VS Mode: Select ANY of the 4 Cups (Left/Right) AND ANY of the 4 Tracks in Cup (Up/Down)!
                    int cup = (int)_chosenCup;
                    if (p1.MenuLeftPressed)  { cup = (cup + 3) % 4; _chosenCup = (CupType)cup; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                    if (p1.MenuRightPressed) { cup = (cup + 1) % 4; _chosenCup = (CupType)cup; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                    if (p1.MenuUpPressed)    { _chosenTrackInCup = (_chosenTrackInCup + 3) % 4; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                    if (p1.MenuDownPressed)  { _chosenTrackInCup = (_chosenTrackInCup + 1) % 4; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
                }

                if (p1.ConfirmPressed)
                {
                    N64AudioSynth.Instance.PlaySfx(SfxId.MenuConfirm);
                    CourseId startCourse;
                    if (_chosenMode == GameMode.Battle)
                        startCourse = (CourseId)(16 + _chosenBattleIdx);
                    else if (_chosenMode == GameMode.MarioGP)
                        startCourse = TrackRegistry.GetCupCourse(_chosenCup, 0);
                    else
                        startCourse = TrackRegistry.GetCupCourse(_chosenCup, _chosenTrackInCup);

                    _sceneRenderer.InvalidateDisplayList();
                    _session.StartNewMatch(_chosenMode, _chosenCC, _chosenPlayers, _chosenChars, _chosenCup, startCourse);
                    _screen = MenuScreen.InSession;
                }
                else if (p1.CancelPressed)
                {
                    N64AudioSynth.Instance.PlaySfx(SfxId.MenuBack);
                    _screen = MenuScreen.CharacterSelect;
                }
            }
            else if (_screen == MenuScreen.EasySmxStudio)
            {
                UpdateEasySmxStudio(p1);
            }
        }

        private void UpdateEasySmxStudio(PlayerInputState p1)
        {
            GameConfig cfg = GameConfig.Instance;

            if (_rebindingAction >= 0)
            {
                if (_controllers.IsKeyDown(Keys.Escape))
                {
                    _rebindingAction = -1;
                    _controllers.IsCapturingBinding = false;
                    N64AudioSynth.Instance.PlaySfx(SfxId.MenuBack);
                    return;
                }

                if (_controllers.CapturedXInputMask != 0)
                {
                    int m = _controllers.CapturedXInputMask;
                    if (_rebindingAction == 0) cfg.XInputBtnAccelerate = m;
                    else if (_rebindingAction == 1) cfg.XInputBtnBrake = m;
                    else if (_rebindingAction == 2) cfg.XInputBtnDriftHop = m;
                    else if (_rebindingAction == 3) cfg.XInputBtnItem = m;
                    cfg.SaveConfig();
                    _rebindingAction = -1;
                    _controllers.IsCapturingBinding = false;
                    N64AudioSynth.Instance.PlaySfx(SfxId.MenuConfirm);
                }
                else if (_controllers.CapturedDInputButton >= 0)
                {
                    int b = _controllers.CapturedDInputButton;
                    if (_rebindingAction == 0) cfg.DInputBtnAccelerate = b;
                    else if (_rebindingAction == 1) cfg.DInputBtnBrake = b;
                    else if (_rebindingAction == 2) cfg.DInputBtnDriftHop = b;
                    else if (_rebindingAction == 3) cfg.DInputBtnItem = b;
                    cfg.SaveConfig();
                    _rebindingAction = -1;
                    _controllers.IsCapturingBinding = false;
                    N64AudioSynth.Instance.PlaySfx(SfxId.MenuConfirm);
                }
                return;
            }

            // Rows:
            // 0: Deadzone
            // 1: Steering Sensitivity
            // 2: Rumble Vibration Toggle + Test Pulse
            // 3: Right Trigger (RT) Accelerate Toggle
            // 4: Rebind Accelerate (A)
            // 5: Rebind Brake/Reverse (B)
            // 6: Rebind Hop/Drift (R / RB)
            // 7: Rebind Use Item (Z / LB)
            // 8: Save & Back to Title
            const int RowCount = 9;
            if (p1.MenuUpPressed)   { _studioRow = (_studioRow + RowCount - 1) % RowCount; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }
            if (p1.MenuDownPressed) { _studioRow = (_studioRow + 1) % RowCount; N64AudioSynth.Instance.PlaySfx(SfxId.MenuMove); }

            if (_studioRow == 0)
            {
                if (p1.MenuLeftPressed)  { cfg.StickDeadzone = MathUtil.Clamp(cfg.StickDeadzone - 0.02f, 0.04f, 0.40f); cfg.SaveConfig(); }
                if (p1.MenuRightPressed) { cfg.StickDeadzone = MathUtil.Clamp(cfg.StickDeadzone + 0.02f, 0.04f, 0.40f); cfg.SaveConfig(); }
            }
            else if (_studioRow == 1)
            {
                if (p1.MenuLeftPressed)  { cfg.SteeringSensitivity = MathUtil.Clamp(cfg.SteeringSensitivity - 0.05f, 0.60f, 1.60f); cfg.SaveConfig(); }
                if (p1.MenuRightPressed) { cfg.SteeringSensitivity = MathUtil.Clamp(cfg.SteeringSensitivity + 0.05f, 0.60f, 1.60f); cfg.SaveConfig(); }
            }
            else if (_studioRow == 2 && (p1.MenuLeftPressed || p1.MenuRightPressed || p1.ConfirmPressed))
            {
                if (p1.MenuLeftPressed || p1.MenuRightPressed) cfg.EnableRumble = !cfg.EnableRumble;
                cfg.SaveConfig();
                if (cfg.EnableRumble) _controllers.TriggerRumble(0, 0.8f, 0.8f, 0.35f);
                N64AudioSynth.Instance.PlaySfx(SfxId.BoostWhoosh, 0.7f);
            }
            else if (_studioRow == 3 && (p1.MenuLeftPressed || p1.MenuRightPressed || p1.ConfirmPressed))
            {
                cfg.AllowRightTriggerGas = !cfg.AllowRightTriggerGas;
                cfg.SaveConfig();
                N64AudioSynth.Instance.PlaySfx(SfxId.MenuConfirm);
            }
            else if (_studioRow >= 4 && _studioRow <= 7 && p1.ConfirmPressed)
            {
                _rebindingAction = _studioRow - 4;
                _controllers.CapturedXInputMask = 0;
                _controllers.CapturedDInputButton = -1;
                _controllers.IsCapturingBinding = true;
                N64AudioSynth.Instance.PlaySfx(SfxId.MenuConfirm);
            }
            else if (_studioRow == 8 && p1.ConfirmPressed)
            {
                cfg.SaveConfig();
                _screen = MenuScreen.Title;
                N64AudioSynth.Instance.PlaySfx(SfxId.MenuBack);
            }

            if (p1.CancelPressed)
            {
                cfg.SaveConfig();
                _screen = MenuScreen.Title;
                N64AudioSynth.Instance.PlaySfx(SfxId.MenuBack);
            }
        }

        private void RenderFrame()
        {
            int w = Math.Max(16, ClientSize.Width);
            int h = Math.Max(16, ClientSize.Height);

            if (_screen == MenuScreen.InSession)
            {
                _session.Render(w, h, _sceneRenderer);
                return;
            }

            // Render live 3D attract-mode race behind the menus!
            Kart demoKart = _attractDemo.Karts[0];
            Vec3 eye = demoKart.Position - demoKart.ForwardDir * 11f + new Vec3(0f, 4.8f, 0f);
            Vec3 look = demoKart.Position + demoKart.ForwardDir * 6f + new Vec3(0f, 1.5f, 0f);
            _sceneRenderer.RenderViewport(0, 0, w, h, eye, look, _attractDemo.Track, _attractDemo.Karts, _attractDemo.WorldItems, _attractDemo.Hazards, _uiTime, 0f);

            // Overlay 2D Menu UI in virtual 960 x 540 resolution
            Gl.glViewport(0, 0, w, h);
            Gl.glDisable(Gl.GL_DEPTH_TEST);
            Gl.glDisable(Gl.GL_FOG);
            Gl.glMatrixMode(Gl.GL_PROJECTION);
            Gl.glLoadIdentity();
            Gl.glOrtho(0, 960, 540, 0, -1, 1);
            Gl.glMatrixMode(Gl.GL_MODELVIEW);
            Gl.glLoadIdentity();

            switch (_screen)
            {
                case MenuScreen.Title:            RenderTitleMenu(); break;
                case MenuScreen.ModeAndClass:     RenderModeClassMenu(); break;
                case MenuScreen.CharacterSelect:  RenderCharacterSelectMenu(); break;
                case MenuScreen.CupOrTrackSelect: RenderCupTrackSelectMenu(); break;
                case MenuScreen.EasySmxStudio:    RenderEasySmxStudioMenu(); break;
            }
        }

        private void RenderTitleMenu()
        {
            Color4 goldTop = Color4.FromBytes(255, 246, 92);
            Color4 goldBot = Color4.FromBytes(245, 142, 20);
            Color4 redTop  = Color4.FromBytes(255, 72, 68);
            Color4 white   = new Color4(1f, 1f, 1f, 1f);

            // Iconic N64 Title Plaque with SGI Mario & Bowser Portraits!
            ProceduralTextures.DrawSolidRect2D(145f, 24f, 670f, 128f, new Color4(0.03f, 0.06f, 0.18f, 0.80f));
            ProceduralTextures.DrawRectOutline2D(145f, 24f, 670f, 128f, 3.5f, goldTop);
            if (SgiSpriteGenerator.FullBodySelectTextures[0] != 0)
                ProceduralTextures.DrawSprite2D(SgiSpriteGenerator.FullBodySelectTextures[0], 158f, 36f, 102f, 102f, new Color4(1f, 1f, 1f, 1f));
            if (SgiSpriteGenerator.FullBodySelectTextures[7] != 0)
                ProceduralTextures.DrawSprite2D(SgiSpriteGenerator.FullBodySelectTextures[7], 700f, 36f, 102f, 102f, new Color4(1f, 1f, 1f, 1f));
            ProceduralTextures.DrawText2D("MARIO KART 64", 480f, 40f, 48f, redTop, goldTop, true);
            ProceduralTextures.DrawText2D("N64 PC EDITION  *  16 TRACKS + 4 BATTLE ARENAS", 480f, 108f, 17.5f, white, Color4.FromBytes(175, 218, 255), true);

            // Main Menu Box
            ProceduralTextures.DrawSolidRect2D(255f, 172f, 450f, 282f, new Color4(0.03f, 0.05f, 0.15f, 0.86f));
            ProceduralTextures.DrawRectOutline2D(255f, 172f, 450f, 282f, 2.5f, Color4.FromBytes(95, 165, 255));

            string[] items =
            {
                "MARIO GP (4 CUPS - 16 TRACKS)",
                "TIME TRIALS",
                "VS RACE (1-4 PLAYERS)",
                "BATTLE MODE (4 ARENAS)",
                "EASYSMX USB CONTROLLER SETUP",
                "QUIT GAME"
            };

            for (int i = 0; i < items.Length; i++)
            {
                bool sel = (_titleCursor == i);
                if (sel)
                {
                    ProceduralTextures.DrawSolidRect2D(272f, 186f + i * 42f, 416f, 34f, new Color4(0.95f, 0.65f, 0.12f, 0.28f));
                }
                Color4 tCol = sel ? goldTop : white;
                Color4 bCol = sel ? goldBot : Color4.FromBytes(185, 202, 225);
                ProceduralTextures.DrawText2D((sel ? "> " : "  ") + items[i], 480f, 191f + i * 42f, 21f, tCol, bCol, true);
            }

            // Live EasySMX USB Controller Detection Status Bar at bottom!
            PlayerInputState p1 = _controllers.GetPlayer(0);
            ProceduralTextures.DrawSolidRect2D(90f, 474f, 780f, 48f, new Color4(0.02f, 0.05f, 0.12f, 0.88f));
            string padStatus = p1.IsGamepadConnected
                ? ("CONNECTED: " + p1.DeviceLabel + "  |  A: Confirm  RB: Drift  LB/LT: Item  F11: Fullscreen")
                : "NO USB PAD DETECTED (PLUG IN EASYSMX USB PAD ANYTIME!) | KEYBOARD: Arrows/WASD, Space=Drift, E=Item, F1=Setup";
            Color4 stCol = p1.IsGamepadConnected ? Color4.FromBytes(95, 255, 138) : Color4.FromBytes(255, 225, 115);
            ProceduralTextures.DrawText2D(padStatus, 480f, 488f, 16.5f, stCol, white, true);
        }

        private void RenderModeClassMenu()
        {
            Color4 goldTop = Color4.FromBytes(255, 245, 92);
            Color4 goldBot = Color4.FromBytes(245, 145, 22);
            Color4 white = new Color4(1f, 1f, 1f, 1f);

            ProceduralTextures.DrawSolidRect2D(180f, 95f, 600f, 345f, new Color4(0.03f, 0.06f, 0.16f, 0.90f));
            ProceduralTextures.DrawRectOutline2D(180f, 95f, 600f, 345f, 3f, goldTop);

            ProceduralTextures.DrawText2D("SELECT PLAYERS & ENGINE CLASS", 480f, 118f, 28f, goldTop, goldBot, true);

            if (_chosenMode != GameMode.TimeTrials)
            {
                bool selP = (_setupRow == 0);
                ProceduralTextures.DrawText2D(
                    string.Format("{0}PLAYERS:  <  {1} PLAYER{2}  >", selP ? "> " : "  ", _chosenPlayers, _chosenPlayers > 1 ? "S (SPLIT-SCREEN)" : ""),
                    480f, 195f, 25f, selP ? goldTop : white, selP ? goldBot : white, true);
            }

            if (_chosenMode != GameMode.Battle)
            {
                string[] ccNames = { "50cc (NORMAL)", "100cc (FAST)", "150cc (EXPERT)", "EXTRA (MIRROR MODE!)" };
                bool selC = (_chosenMode == GameMode.TimeTrials) ? (_setupRow == 0) : (_setupRow == 1);
                ProceduralTextures.DrawText2D(
                    string.Format("{0}CLASS:  <  {1}  >", selC ? "> " : "  ", ccNames[(int)_chosenCC]),
                    480f, 265f, 25f, selC ? goldTop : white, selC ? goldBot : white, true);
            }
            else
            {
                ProceduralTextures.DrawText2D("3-BALLOON BATTLE ARENA RULES", 480f, 265f, 23f, Color4.FromBytes(120, 225, 255), white, true);
            }

            ProceduralTextures.DrawText2D("PRESS A / ENTER TO CONTINUE   |   B / ESC TO GO BACK", 480f, 382f, 19f, goldTop, white, true);
        }

        private void RenderCharacterSelectMenu()
        {
            Color4 goldTop = Color4.FromBytes(255, 245, 92);
            Color4 goldBot = Color4.FromBytes(245, 145, 22);
            Color4 white = new Color4(1f, 1f, 1f, 1f);

            ProceduralTextures.DrawSolidRect2D(90f, 42f, 780f, 456f, new Color4(0.03f, 0.06f, 0.16f, 0.90f));
            ProceduralTextures.DrawRectOutline2D(90f, 42f, 780f, 456f, 3f, goldTop);

            ProceduralTextures.DrawText2D(
                string.Format("SELECT DRIVER - PLAYER {0} OF {1}", _selectingPlayerIdx + 1, _chosenPlayers),
                480f, 58f, 28f, goldTop, goldBot, true);

            // 2 Rows x 4 Columns Authentic MK64 Character Grid!
            for (int i = 0; i < 8; i++)
            {
                CharacterSpec ch = CharacterRoster.Get(i);
                int r = i / 4;
                int c = i % 4;
                float gx = 135f + c * 176f;
                float gy = 112f + r * 132f;

                bool selectedByCurrent = ((int)_chosenChars[_selectingPlayerIdx] == i);
                Color4 bg = selectedByCurrent ? ch.PrimaryColor.WithAlpha(0.45f) : new Color4(0.08f, 0.12f, 0.24f, 0.85f);
                ProceduralTextures.DrawSolidRect2D(gx, gy, 156f, 122f, bg);
                ProceduralTextures.DrawRectOutline2D(gx, gy, 156f, 122f, selectedByCurrent ? 3.5f : 1.5f, selectedByCurrent ? goldTop : ch.PrimaryColor);

                // Authentic SGI 3D Character Portrait (rotates 360 degrees when highlighted!)
                int spinFrame = ((int)(_uiTime * 6.5f)) % SgiSpriteGenerator.YawSteps;
                uint portTex = selectedByCurrent ? SgiSpriteGenerator.KartTextures[i, spinFrame] : SgiSpriteGenerator.FullBodySelectTextures[i];
                if (portTex != 0)
                {
                    ProceduralTextures.DrawSprite2D(portTex, gx + 40f, gy + 2f, 76f, 76f, new Color4(1f, 1f, 1f, 1f));
                }
                ProceduralTextures.DrawText2D(ch.Name, gx + 78f, gy + 76f, 19f, white, silverBot(), true);

                string wt = (ch.WeightClass == WeightClass.Light) ? "LIGHT" :
                            (ch.WeightClass == WeightClass.Medium) ? "MEDIUM" : "HEAVY";
                ProceduralTextures.DrawText2D(wt, gx + 78f, gy + 98f, 14f, goldTop, white, true);
            }

            // Selected Character Stats Bar at bottom
            CharacterSpec curSpec = CharacterRoster.Get(_chosenChars[_selectingPlayerIdx]);
            string stats = string.Format("{0}:  TOP SPEED {1:F0}   ACCEL {2:F0}   HANDLING {3:F1}   WEIGHT {4:F2}",
                curSpec.Name, curSpec.TopSpeed * 2.0f, curSpec.Acceleration * 2.2f, curSpec.TurnRate * 4.0f, curSpec.Mass);
            ProceduralTextures.DrawText2D(stats, 480f, 396f, 20f, curSpec.PrimaryColor, white, true);
            ProceduralTextures.DrawText2D("PRESS A / ENTER TO CONFIRM DRIVER   |   B / ESC BACK", 480f, 452f, 18f, goldTop, white, true);
        }

        private void RenderCupTrackSelectMenu()
        {
            Color4 goldTop = Color4.FromBytes(255, 245, 92);
            Color4 goldBot = Color4.FromBytes(245, 145, 22);
            Color4 white = new Color4(1f, 1f, 1f, 1f);

            ProceduralTextures.DrawSolidRect2D(85f, 45f, 790f, 450f, new Color4(0.03f, 0.06f, 0.16f, 0.90f));
            ProceduralTextures.DrawRectOutline2D(85f, 45f, 790f, 450f, 3f, goldTop);

            if (_chosenMode == GameMode.Battle)
            {
                ProceduralTextures.DrawText2D("SELECT BATTLE COURSE", 480f, 65f, 30f, goldTop, goldBot, true);
                for (int i = 0; i < 4; i++)
                {
                    bool sel = (_chosenBattleIdx == i);
                    float bx = 135f + i * 176f;
                    ProceduralTextures.DrawSolidRect2D(bx, 165f, 158f, 165f, sel ? new Color4(0.9f, 0.5f, 0.1f, 0.35f) : new Color4(0.08f, 0.12f, 0.22f, 0.85f));
                    ProceduralTextures.DrawRectOutline2D(bx, 165f, 158f, 165f, sel ? 3.5f : 1.5f, sel ? goldTop : white);
                    ProceduralTextures.DrawText2D(TrackRegistry.CourseNames[16 + i], bx + 79f, 232f, 19f, sel ? goldTop : white, white, true);
                }
            }
            else
            {
                ProceduralTextures.DrawText2D(
                    (_chosenMode == GameMode.MarioGP) ? "SELECT GRAND PRIX CUP" : "SELECT CUP & COURSE",
                    480f, 62f, 29f, goldTop, goldBot, true);

                // 4 Cup Columns
                for (int c = 0; c < 4; c++)
                {
                    bool selCup = ((int)_chosenCup == c);
                    float cx = 108f + c * 188f;
                    ProceduralTextures.DrawSolidRect2D(cx, 112f, 174f, 62f, selCup ? new Color4(0.95f, 0.65f, 0.1f, 0.35f) : new Color4(0.07f, 0.11f, 0.22f, 0.85f));
                    ProceduralTextures.DrawRectOutline2D(cx, 112f, 174f, 62f, selCup ? 3f : 1.5f, selCup ? goldTop : white);
                    ProceduralTextures.DrawText2D(TrackRegistry.CupNames[c], cx + 87f, 122f, 18f, selCup ? goldTop : white, white, true);

                    TrophyTier tr = GameConfig.Instance.CupTrophies[c, (int)_chosenCC];
                    string trStr = (tr == TrophyTier.Gold) ? "TROPHY: GOLD" :
                                   (tr == TrophyTier.Silver) ? "TROPHY: SILVER" :
                                   (tr == TrophyTier.Bronze) ? "TROPHY: BRONZE" : "NO TROPHY YET";
                    ProceduralTextures.DrawText2D(trStr, cx + 87f, 148f, 14f, goldTop, silverBot(), true);
                }

                // 4 Tracks inside Selected Cup!
                for (int t = 0; t < 4; t++)
                {
                    int globalTrackIdx = ((int)_chosenCup) * 4 + t;
                    bool selTrack = (_chosenMode != GameMode.MarioGP) && (_chosenTrackInCup == t);
                    float ty = 200f + t * 54f;

                    if (selTrack)
                        ProceduralTextures.DrawSolidRect2D(165f, ty - 4f, 630f, 44f, new Color4(0.25f, 0.55f, 0.95f, 0.35f));

                    string line = string.Format("ROUND {0}:  {1}", t + 1, TrackRegistry.CourseNames[globalTrackIdx]);
                    if (_chosenMode == GameMode.TimeTrials)
                    {
                        line += "   |  BEST: " + GameConfig.FormatRaceTime(GameConfig.Instance.BestCourseSeconds[globalTrackIdx]);
                    }
                    ProceduralTextures.DrawText2D((selTrack ? "> " : "  ") + line, 480f, ty + 4f, 22f, selTrack ? goldTop : white, white, true);
                }
            }

            ProceduralTextures.DrawText2D("PRESS A / START TO LAUNCH RACE!   |   B / ESC BACK", 480f, 448f, 20f, goldTop, goldBot, true);
        }

        private void RenderEasySmxStudioMenu()
        {
            GameConfig cfg = GameConfig.Instance;
            PlayerInputState p1 = _controllers.GetPlayer(0);
            Color4 goldTop = Color4.FromBytes(255, 245, 92);
            Color4 goldBot = Color4.FromBytes(245, 145, 22);
            Color4 white = new Color4(1f, 1f, 1f, 1f);
            Color4 green = Color4.FromBytes(90, 255, 135);

            ProceduralTextures.DrawSolidRect2D(55f, 28f, 850f, 484f, new Color4(0.02f, 0.05f, 0.14f, 0.94f));
            ProceduralTextures.DrawRectOutline2D(55f, 28f, 850f, 484f, 3f, goldTop);

            ProceduralTextures.DrawText2D("EASYSMX USB CONTROLLER STUDIO (XINPUT + DIRECTINPUT)", 480f, 42f, 25f, goldTop, goldBot, true);

            // Live P1..P4 Slot Diagnostic Panel on Right
            ProceduralTextures.DrawSolidRect2D(555f, 88f, 325f, 245f, new Color4(0.06f, 0.10f, 0.22f, 0.90f));
            ProceduralTextures.DrawRectOutline2D(555f, 88f, 325f, 245f, 2f, Color4.FromBytes(90, 175, 255));
            ProceduralTextures.DrawText2D("LIVE USB SLOTS & STICK TEST", 717f, 98f, 17f, green, white, true);

            for (int i = 0; i < 4; i++)
            {
                PlayerInputState ps = _controllers.GetPlayer(i);
                string slotTxt = string.Format("P{0}: {1}", i + 1, ps.DeviceLabel);
                ProceduralTextures.DrawText2D(slotTxt, 568f, 126f + i * 24f, 15f, ps.IsGamepadConnected ? green : silverBot(), white, false);
            }

            // Analog Stick 2D Crosshair Visualizer for P1!
            float cx = 635f, cy = 275f, rad = 42f;
            ProceduralTextures.DrawSolidRect2D(cx - rad, cy - rad, rad * 2f, rad * 2f, new Color4(0f, 0f, 0f, 0.65f));
            ProceduralTextures.DrawRectOutline2D(cx - rad, cy - rad, rad * 2f, rad * 2f, 1.5f, white);
            float dotX = cx + p1.RawStickX * (rad - 5f);
            float dotY = cy - p1.RawStickY * (rad - 5f);
            ProceduralTextures.DrawSolidRect2D(dotX - 5f, dotY - 5f, 10f, 10f, goldTop);

            // Trigger & Button readout
            ProceduralTextures.DrawText2D(string.Format("STEER: {0:F2}", p1.Steer), 705f, 236f, 16f, white, white, false);
            ProceduralTextures.DrawText2D(string.Format("LT:{0:F2} RT:{1:F2}", p1.LeftTrigger, p1.RightTrigger), 705f, 260f, 16f, white, white, false);
            ProceduralTextures.DrawText2D("MASK: 0x" + p1.RawButtonMask.ToString("X4"), 705f, 284f, 16f, goldTop, white, false);

            // Configurable Options & Button Bindings on Left
            string[] rows = new string[9];
            rows[0] = string.Format("STICK DEADZONE:       < {0:P0} >", cfg.StickDeadzone);
            rows[1] = string.Format("STEER SENSITIVITY:    < {0:P0} >", cfg.SteeringSensitivity);
            rows[2] = string.Format("FORCE RUMBLE (TEST):  < {0} >", cfg.EnableRumble ? "ON" : "OFF");
            rows[3] = string.Format("RT TRIGGER GAS:       < {0} >", cfg.AllowRightTriggerGas ? "ENABLED" : "OFF");
            rows[4] = string.Format("ACCELERATE (N64 A):   XIn [{0}] / DIn [Btn {1}]", XInputButtons.GetButtonName(cfg.XInputBtnAccelerate), cfg.DInputBtnAccelerate + 1);
            rows[5] = string.Format("BRAKE/REV  (N64 B):   XIn [{0}] / DIn [Btn {1}]", XInputButtons.GetButtonName(cfg.XInputBtnBrake), cfg.DInputBtnBrake + 1);
            rows[6] = string.Format("HOP/DRIFT  (N64 R):   XIn [{0}] / DIn [Btn {1}]", XInputButtons.GetButtonName(cfg.XInputBtnDriftHop), cfg.DInputBtnDriftHop + 1);
            rows[7] = string.Format("USE ITEM   (N64 Z):   XIn [{0}] / DIn [Btn {1}]", XInputButtons.GetButtonName(cfg.XInputBtnItem), cfg.DInputBtnItem + 1);
            rows[8] = "SAVE & RETURN TO TITLE SCREEN";

            for (int r = 0; r < rows.Length; r++)
            {
                bool sel = (_studioRow == r);
                Color4 c = sel ? goldTop : white;
                ProceduralTextures.DrawText2D((sel ? "> " : "  ") + rows[r], 75f, 96f + r * 38f, 17.5f, c, c.ScaleRGB(0.85f), false);
            }

            if (_rebindingAction >= 0)
            {
                ProceduralTextures.DrawSolidRect2D(200f, 210f, 560f, 110f, new Color4(0.08f, 0.02f, 0.02f, 0.96f));
                ProceduralTextures.DrawRectOutline2D(200f, 210f, 560f, 110f, 3f, goldTop);
                ProceduralTextures.DrawText2D("PRESS ANY BUTTON ON YOUR EASYSMX CONTROLLER...", 480f, 236f, 21f, goldTop, white, true);
                ProceduralTextures.DrawText2D("(PRESS ESC ON KEYBOARD TO CANCEL)", 480f, 276f, 17f, silverBot(), white, true);
            }
            else
            {
                ProceduralTextures.DrawText2D("TIP: EASYSMX HOME BUTTON SWITCHES XINPUT (LED 1+2) / D-INPUT (LED 1+3) - BOTH WORK AUTOMATICALLY!", 480f, 468f, 15.5f, green, white, true);
            }
        }

        private static Color4 silverBot()
        {
            return Color4.FromBytes(185, 202, 228);
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            Application.Idle -= OnApplicationIdle;
            _controllers.StopAllRumble();
            N64AudioSynth.Instance.Dispose();
            _sceneRenderer.Dispose();

            if (_hglrc != IntPtr.Zero)
            {
                Gl.wglMakeCurrent(IntPtr.Zero, IntPtr.Zero);
                Gl.wglDeleteContext(_hglrc);
                _hglrc = IntPtr.Zero;
            }
            if (_hdc != IntPtr.Zero)
            {
                Gl.ReleaseDC(Handle, _hdc);
                _hdc = IntPtr.Zero;
            }
            base.OnFormClosed(e);
        }
    }
}
