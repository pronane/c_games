using System;
using System.Collections.Generic;
using System.Windows.Forms;
using MarioKart64.Core;

namespace MarioKart64.Input
{
    public enum ControllerBackendType
    {
        KeyboardOnly = 0,
        EasySmxXInput = 1,
        EasySmxDirectInput = 2
    }

    public class PlayerInputState
    {
        public int PlayerIndex;
        public ControllerBackendType Backend = ControllerBackendType.KeyboardOnly;
        public string DeviceLabel = "Keyboard";
        public bool IsGamepadConnected;

        // Continuous driving axes (-1..+1)
        public float Steer;
        public float AimVertical; // +1 forward throw, -1 backward throw
        public float RawStickX;
        public float RawStickY;
        public float LeftTrigger;
        public float RightTrigger;
        public uint RawButtonMask;

        // Held states
        public bool Accelerate;
        public bool Brake;
        public bool DriftHopHeld;
        public bool ItemHeld;
        public bool StartHeld;
        public bool SelectHeld;
        public bool DpadUp;
        public bool DpadDown;
        public bool DpadLeft;
        public bool DpadRight;

        // Edge-triggered states (true for 1 tick)
        public bool DriftHopPressed;
        public bool DriftHopReleased;
        public bool ItemPressed;
        public bool ItemReleased;
        public bool BrakePressed;
        public bool StartPressed;
        public bool SelectPressed;
        public bool ConfirmPressed;
        public bool CancelPressed;
        public bool MenuUpPressed;
        public bool MenuDownPressed;
        public bool MenuLeftPressed;
        public bool MenuRightPressed;

        // Previous tick state for edge detection
        internal bool PrevDriftHop;
        internal bool PrevItem;
        internal bool PrevBrake;
        internal bool PrevStart;
        internal bool PrevSelect;
        internal bool PrevConfirm;
        internal bool PrevCancel;
        internal bool PrevMenuUp;
        internal bool PrevMenuDown;
        internal bool PrevMenuLeft;
        internal bool PrevMenuRight;
        internal float MenuRepeatTimer;
    }

    public class EasySmxControllerManager
    {
        public const int MaxPlayers = 4;

        private readonly PlayerInputState[] _players = new PlayerInputState[MaxPlayers];
        private readonly HashSet<Keys> _keysDown = new HashSet<Keys>();

        // XInput tracking
        private readonly bool[] _xinputConnected = new bool[4];
        private int _rescanCounter = 0;

        // Rumble timers per XInput slot
        private readonly float[] _rumbleTimer = new float[4];
        private readonly ushort[] _rumbleLeft = new ushort[4];
        private readonly ushort[] _rumbleRight = new ushort[4];
        private readonly bool[] _rumbleActive = new bool[4];

        // DirectInput (WinMM) discovered non-XInput devices
        private struct DInputSlotInfo
        {
            public uint JoyId;
            public string ProductName;
            public uint XMin, XMax, YMin, YMax, ZMin, ZMax, RMin, RMax;
            public bool HasPov;
        }
        private readonly List<DInputSlotInfo> _dinputDevices = new List<DInputSlotInfo>();

        // Live button capture for remapping screen
        public bool IsCapturingBinding = false;
        public int CapturedXInputMask = 0;
        public int CapturedDInputButton = -1;

        public EasySmxControllerManager()
        {
            for (int i = 0; i < MaxPlayers; i++)
            {
                _players[i] = new PlayerInputState();
                _players[i].PlayerIndex = i;
            }
            RescanDevices();
        }

        public PlayerInputState GetPlayer(int index)
        {
            return _players[MathUtil.ClampInt(index, 0, MaxPlayers - 1)];
        }

        public int ConnectedGamepadCount
        {
            get
            {
                int count = 0;
                for (int i = 0; i < MaxPlayers; i++)
                {
                    if (_players[i].IsGamepadConnected) count++;
                }
                return count;
            }
        }

        public void OnKeyDown(Keys key)
        {
            _keysDown.Add(key);
        }

        public void OnKeyUp(Keys key)
        {
            _keysDown.Remove(key);
        }

        public void ClearKeys()
        {
            _keysDown.Clear();
        }

        public bool IsKeyDown(Keys key)
        {
            return _keysDown.Contains(key);
        }

        public void TriggerRumble(int playerIndex, float lowFreq, float highFreq, float durationSeconds)
        {
            if (!GameConfig.Instance.EnableRumble) return;
            if (playerIndex < 0 || playerIndex >= 4) return;
            if (_players[playerIndex].Backend != ControllerBackendType.EasySmxXInput) return;

            ushort l = (ushort)(MathUtil.Clamp(lowFreq, 0f, 1f) * 65535f);
            ushort r = (ushort)(MathUtil.Clamp(highFreq, 0f, 1f) * 65535f);
            if (_rumbleTimer[playerIndex] <= 0f || l >= _rumbleLeft[playerIndex] || r >= _rumbleRight[playerIndex])
            {
                _rumbleLeft[playerIndex] = l;
                _rumbleRight[playerIndex] = r;
                _rumbleTimer[playerIndex] = Math.Max(_rumbleTimer[playerIndex], durationSeconds);
                _rumbleActive[playerIndex] = true;
                NativeInput.TryXInputSetVibration((uint)playerIndex, l, r);
            }
        }

        public void StopAllRumble()
        {
            for (int i = 0; i < 4; i++)
            {
                if (_rumbleActive[i])
                {
                    _rumbleActive[i] = false;
                    _rumbleTimer[i] = 0f;
                    _rumbleLeft[i] = 0;
                    _rumbleRight[i] = 0;
                    NativeInput.TryXInputSetVibration((uint)i, 0, 0);
                }
            }
        }

        public void RescanDevices()
        {
            int activeXInputCount = 0;
            for (uint i = 0; i < 4; i++)
            {
                XInputState st;
                _xinputConnected[i] = NativeInput.TryXInputGetState(i, out st);
                if (_xinputConnected[i]) activeXInputCount++;
            }

            _dinputDevices.Clear();
            uint numJoy = NativeInput.GetWinMmNumDevs();
            if (numJoy > 16) numJoy = 16;

            int skippedXInputShadows = 0;
            for (uint j = 0; j < numJoy; j++)
            {
                JOYINFOEX pos;
                if (!NativeInput.TryGetJoyPosEx(j, out pos)) continue;

                JOYCAPSW caps;
                if (!NativeInput.TryGetJoyCaps(j, out caps)) continue;

                string pname = (caps.szPname != null) ? caps.szPname.Trim() : "USB Gamepad";
                string upper = pname.ToUpperInvariant();

                // Deduplicate Windows XInput wrapper devices so one EasySMX pad in XInput mode
                // is not counted twice via WinMM DirectInput.
                bool looksLikeXInputWrapper =
                    upper.Contains("XBOX") ||
                    upper.Contains("XINPUT") ||
                    (caps.wMid == 0x045E && (caps.wPid == 0x028E || caps.wPid == 0x02A1 || caps.wPid == 0x02FF));

                if (looksLikeXInputWrapper && skippedXInputShadows < activeXInputCount)
                {
                    skippedXInputShadows++;
                    continue;
                }

                DInputSlotInfo info = new DInputSlotInfo();
                info.JoyId = j;
                info.ProductName = pname.Length > 0 ? pname : "EasySMX USB D-Input";
                info.XMin = caps.wXmin; info.XMax = caps.wXmax > caps.wXmin ? caps.wXmax : 65535;
                info.YMin = caps.wYmin; info.YMax = caps.wYmax > caps.wYmin ? caps.wYmax : 65535;
                info.ZMin = caps.wZmin; info.ZMax = caps.wZmax > caps.wZmin ? caps.wZmax : 65535;
                info.RMin = caps.wRmin; info.RMax = caps.wRmax > caps.wRmin ? caps.wRmax : 65535;
                info.HasPov = (caps.wCaps & NativeInput.JOYCAPS_HASPOV) != 0;
                _dinputDevices.Add(info);
                if (_dinputDevices.Count >= 4) break;
            }
        }

        public void Update(float dt)
        {
            _rescanCounter++;
            if (_rescanCounter >= 45)
            {
                _rescanCounter = 0;
                RescanDevices();
            }

            // Update rumble decay
            for (int i = 0; i < 4; i++)
            {
                if (_rumbleActive[i])
                {
                    _rumbleTimer[i] -= dt;
                    if (_rumbleTimer[i] <= 0f || !GameConfig.Instance.EnableRumble)
                    {
                        _rumbleActive[i] = false;
                        _rumbleTimer[i] = 0f;
                        _rumbleLeft[i] = 0;
                        _rumbleRight[i] = 0;
                        NativeInput.TryXInputSetVibration((uint)i, 0, 0);
                    }
                }
            }

            int nextDInputIdx = 0;
            for (int p = 0; p < MaxPlayers; p++)
            {
                PlayerInputState st = _players[p];

                // Reset continuous/held fields before merging active backends
                st.Steer = 0f;
                st.AimVertical = 0f;
                st.RawStickX = 0f;
                st.RawStickY = 0f;
                st.LeftTrigger = 0f;
                st.RightTrigger = 0f;
                st.RawButtonMask = 0;
                st.Accelerate = false;
                st.Brake = false;
                st.DriftHopHeld = false;
                st.ItemHeld = false;
                st.StartHeld = false;
                st.SelectHeld = false;
                st.DpadUp = false;
                st.DpadDown = false;
                st.DpadLeft = false;
                st.DpadRight = false;
                st.IsGamepadConnected = false;
                st.Backend = ControllerBackendType.KeyboardOnly;
                st.DeviceLabel = (p == 0) ? "Keyboard (P1)" : ((p == 1) ? "Keyboard (P2)" : "Unassigned");

                bool readXInput = false;
                if (_xinputConnected[p])
                {
                    XInputState xst;
                    if (NativeInput.TryXInputGetState((uint)p, out xst))
                    {
                        readXInput = true;
                        ApplyXInputToPlayer(st, xst, p);
                    }
                    else
                    {
                        _xinputConnected[p] = false;
                    }
                }

                if (!readXInput && nextDInputIdx < _dinputDevices.Count)
                {
                    DInputSlotInfo dinfo = _dinputDevices[nextDInputIdx];
                    nextDInputIdx++;
                    JOYINFOEX jpos;
                    if (NativeInput.TryGetJoyPosEx(dinfo.JoyId, out jpos))
                    {
                        ApplyDInputToPlayer(st, dinfo, jpos);
                    }
                }

                // Merge Keyboard for Player 1 (and Player 2 secondary keys in multiplayer if desired)
                if (p == 0)
                {
                    ApplyKeyboardP1(st);
                }
                else if (p == 1 && !st.IsGamepadConnected)
                {
                    ApplyKeyboardP2(st);
                }

                FinalizeEdges(st, dt);
            }
        }

        private void ApplyXInputToPlayer(PlayerInputState st, XInputState xst, int slot)
        {
            GameConfig cfg = GameConfig.Instance;
            st.IsGamepadConnected = true;
            st.Backend = ControllerBackendType.EasySmxXInput;
            st.DeviceLabel = "EasySMX USB [XInput #" + (slot + 1) + "]";

            ushort btns = xst.Gamepad.wButtons;
            st.RawButtonMask = btns;

            if (IsCapturingBinding && btns != 0)
            {
                ushort maskOnlyButtons = (ushort)(btns & 0xF3F0);
                if (maskOnlyButtons != 0)
                {
                    // Extract lowest set bit
                    int lowestBit = maskOnlyButtons & (-maskOnlyButtons);
                    CapturedXInputMask = lowestBit;
                }
            }

            float lx = xst.Gamepad.sThumbLX / 32767.0f;
            float ly = xst.Gamepad.sThumbLY / 32767.0f;
            st.RawStickX = MathUtil.Clamp(lx, -1f, 1f);
            st.RawStickY = MathUtil.Clamp(ly, -1f, 1f);

            Vec2 stick = ApplyRadialDeadzone(st.RawStickX, st.RawStickY, cfg.StickDeadzone);
            float curvedX = ApplyN64SteerCurve(stick.X * cfg.SteeringSensitivity);

            st.LeftTrigger = xst.Gamepad.bLeftTrigger / 255.0f;
            st.RightTrigger = xst.Gamepad.bRightTrigger / 255.0f;

            st.DpadUp    = (btns & XInputButtons.DPAD_UP) != 0;
            st.DpadDown  = (btns & XInputButtons.DPAD_DOWN) != 0;
            st.DpadLeft  = (btns & XInputButtons.DPAD_LEFT) != 0;
            st.DpadRight = (btns & XInputButtons.DPAD_RIGHT) != 0;

            float dpadSteer = 0f;
            if (st.DpadLeft) dpadSteer -= 1f;
            if (st.DpadRight) dpadSteer += 1f;

            st.Steer = Math.Abs(curvedX) > 0.01f ? curvedX : dpadSteer;
            st.AimVertical = Math.Abs(stick.Y) > 0.25f ? stick.Y : (st.DpadUp ? 1f : (st.DpadDown ? -1f : 0f));

            bool rtGas = cfg.AllowRightTriggerGas && (st.RightTrigger >= cfg.TriggerThreshold);
            bool ltItem = st.LeftTrigger >= cfg.TriggerThreshold;

            st.Accelerate   = ((btns & cfg.XInputBtnAccelerate) != 0) || rtGas;
            st.Brake        = ((btns & cfg.XInputBtnBrake) != 0) || ((btns & cfg.XInputBtnAltBrake) != 0);
            st.DriftHopHeld = ((btns & cfg.XInputBtnDriftHop) != 0) || (!cfg.AllowRightTriggerGas && st.RightTrigger >= cfg.TriggerThreshold);
            st.ItemHeld     = ((btns & cfg.XInputBtnItem) != 0) || ltItem;
            st.StartHeld    = (btns & XInputButtons.START) != 0;
            st.SelectHeld   = ((btns & XInputButtons.BACK) != 0) || ((btns & cfg.XInputBtnCameraHud) != 0);
        }

        private void ApplyDInputToPlayer(PlayerInputState st, DInputSlotInfo info, JOYINFOEX jpos)
        {
            GameConfig cfg = GameConfig.Instance;
            st.IsGamepadConnected = true;
            st.Backend = ControllerBackendType.EasySmxDirectInput;
            st.DeviceLabel = info.ProductName + " [D-Input]";

            uint btns = jpos.dwButtons;
            st.RawButtonMask = btns;

            if (IsCapturingBinding && btns != 0)
            {
                for (int b = 0; b < 16; b++)
                {
                    if ((btns & (1u << b)) != 0)
                    {
                        CapturedDInputButton = b;
                        break;
                    }
                }
            }

            float lx = NormalizeAxis(jpos.dwXpos, info.XMin, info.XMax);
            // DirectInput Y axis: 0 = Up, 65535 = Down -> invert to match +1 = Up
            float ly = -NormalizeAxis(jpos.dwYpos, info.YMin, info.YMax);
            st.RawStickX = lx;
            st.RawStickY = ly;

            Vec2 stick = ApplyRadialDeadzone(lx, ly, cfg.StickDeadzone);
            float curvedX = ApplyN64SteerCurve(stick.X * cfg.SteeringSensitivity);

            // Decode POV Hat (hundredths of degrees, 0=Up, 9000=Right, 18000=Down, 27000=Left, >=36000=Centered)
            if (info.HasPov && jpos.dwPOV < 36000)
            {
                uint pov = jpos.dwPOV;
                st.DpadUp    = (pov >= 31500 || pov <= 4500);
                st.DpadRight = (pov >= 4500 && pov <= 13500);
                st.DpadDown  = (pov >= 13500 && pov <= 22500);
                st.DpadLeft  = (pov >= 22500 && pov <= 31500);
            }

            float dpadSteer = 0f;
            if (st.DpadLeft) dpadSteer -= 1f;
            if (st.DpadRight) dpadSteer += 1f;

            st.Steer = Math.Abs(curvedX) > 0.01f ? curvedX : dpadSteer;
            st.AimVertical = Math.Abs(stick.Y) > 0.25f ? stick.Y : (st.DpadUp ? 1f : (st.DpadDown ? -1f : 0f));

            st.Accelerate   = HasDInputBtn(btns, cfg.DInputBtnAccelerate) || HasDInputBtn(btns, cfg.DInputBtnAltAccel);
            st.Brake        = HasDInputBtn(btns, cfg.DInputBtnBrake) || HasDInputBtn(btns, 3);
            st.DriftHopHeld = HasDInputBtn(btns, cfg.DInputBtnDriftHop) || HasDInputBtn(btns, cfg.DInputBtnAltDrift);
            st.ItemHeld     = HasDInputBtn(btns, cfg.DInputBtnItem) || HasDInputBtn(btns, cfg.DInputBtnAltItem);
            st.StartHeld    = HasDInputBtn(btns, cfg.DInputBtnStart);
            st.SelectHeld   = HasDInputBtn(btns, cfg.DInputBtnSelect);
        }

        private static bool HasDInputBtn(uint mask, int index)
        {
            if (index < 0 || index >= 31) return false;
            return (mask & (1u << index)) != 0;
        }

        private static float NormalizeAxis(uint val, uint min, uint max)
        {
            if (max <= min) return 0f;
            float mid = (min + max) * 0.5f;
            float half = (max - min) * 0.5f;
            return MathUtil.Clamp((val - mid) / half, -1f, 1f);
        }

        private static Vec2 ApplyRadialDeadzone(float x, float y, float deadzone)
        {
            float mag = (float)Math.Sqrt(x * x + y * y);
            if (mag < deadzone) return new Vec2(0f, 0f);
            float scaled = (mag - deadzone) / (1.0f - deadzone);
            if (scaled > 1.0f) scaled = 1.0f;
            return new Vec2((x / mag) * scaled, (y / mag) * scaled);
        }

        private static float ApplyN64SteerCurve(float v)
        {
            float sign = v < 0f ? -1f : 1f;
            float a = Math.Abs(v);
            if (a > 1f) a = 1f;
            // Subtle N64-style precision curve near center while reaching full lock cleanly
            float curved = 0.65f * a + 0.35f * a * a;
            return sign * MathUtil.Clamp(curved, 0f, 1f);
        }

        private void ApplyKeyboardP1(PlayerInputState st)
        {
            bool kLeft  = IsKeyDown(Keys.Left) || IsKeyDown(Keys.A);
            bool kRight = IsKeyDown(Keys.Right) || IsKeyDown(Keys.D);
            bool kUp    = IsKeyDown(Keys.Up) || IsKeyDown(Keys.W);
            bool kDown  = IsKeyDown(Keys.Down) || IsKeyDown(Keys.S);

            float kSteer = 0f;
            if (kLeft) kSteer -= 1f;
            if (kRight) kSteer += 1f;

            if (Math.Abs(kSteer) > Math.Abs(st.Steer)) st.Steer = kSteer;
            if (kUp) { st.DpadUp = true; st.AimVertical = 1f; }
            if (kDown) { st.DpadDown = true; st.AimVertical = -1f; }
            if (kLeft) st.DpadLeft = true;
            if (kRight) st.DpadRight = true;

            bool kGas   = IsKeyDown(Keys.Up) || IsKeyDown(Keys.W) || IsKeyDown(Keys.Z) || IsKeyDown(Keys.K);
            bool kBrake = IsKeyDown(Keys.Down) || IsKeyDown(Keys.S) || IsKeyDown(Keys.X) || IsKeyDown(Keys.L);
            bool kHop   = IsKeyDown(Keys.Space) || IsKeyDown(Keys.RShiftKey) || IsKeyDown(Keys.ShiftKey) && IsKeyDown(Keys.Right) == false && false;
            // Explicit Hop/Drift keys: Space, J, or Right Shift
            kHop = IsKeyDown(Keys.Space) || IsKeyDown(Keys.J) || IsKeyDown(Keys.RShiftKey);
            // Explicit Item keys: E, Q, Left Shift, ControlKey, Return/F
            bool kItem  = IsKeyDown(Keys.E) || IsKeyDown(Keys.Q) || IsKeyDown(Keys.LShiftKey) || IsKeyDown(Keys.ControlKey) || IsKeyDown(Keys.F);

            st.Accelerate   = st.Accelerate || kGas;
            st.Brake        = st.Brake || kBrake;
            st.DriftHopHeld = st.DriftHopHeld || kHop;
            st.ItemHeld     = st.ItemHeld || kItem;
            st.StartHeld    = st.StartHeld || IsKeyDown(Keys.Enter) || IsKeyDown(Keys.Escape) || IsKeyDown(Keys.P);
            st.SelectHeld   = st.SelectHeld || IsKeyDown(Keys.Tab) || IsKeyDown(Keys.C);
        }

        private void ApplyKeyboardP2(PlayerInputState st)
        {
            bool kLeft  = IsKeyDown(Keys.NumPad4);
            bool kRight = IsKeyDown(Keys.NumPad6);
            bool kUp    = IsKeyDown(Keys.NumPad8);
            bool kDown  = IsKeyDown(Keys.NumPad5) || IsKeyDown(Keys.NumPad2);

            if (kLeft) { st.Steer = -1f; st.DpadLeft = true; }
            if (kRight) { st.Steer = 1f; st.DpadRight = true; }
            if (kUp) { st.DpadUp = true; st.AimVertical = 1f; }
            if (kDown) { st.DpadDown = true; st.AimVertical = -1f; }

            st.Accelerate   = st.Accelerate || kUp || IsKeyDown(Keys.NumPad0);
            st.Brake        = st.Brake || kDown;
            st.DriftHopHeld = st.DriftHopHeld || IsKeyDown(Keys.NumPad7) || IsKeyDown(Keys.Add);
            st.ItemHeld     = st.ItemHeld || IsKeyDown(Keys.NumPad9) || IsKeyDown(Keys.Decimal);
        }

        private void FinalizeEdges(PlayerInputState st, float dt)
        {
            st.DriftHopPressed  = st.DriftHopHeld && !st.PrevDriftHop;
            st.DriftHopReleased = !st.DriftHopHeld && st.PrevDriftHop;
            st.ItemPressed      = st.ItemHeld && !st.PrevItem;
            st.ItemReleased     = !st.ItemHeld && st.PrevItem;
            st.BrakePressed     = st.Brake && !st.PrevBrake;
            st.StartPressed     = st.StartHeld && !st.PrevStart;
            st.SelectPressed    = st.SelectHeld && !st.PrevSelect;

            bool confirmNow = st.Accelerate || st.StartHeld || (st.PlayerIndex == 0 && IsKeyDown(Keys.Enter));
            bool cancelNow  = st.Brake || (st.PlayerIndex == 0 && (IsKeyDown(Keys.Escape) || IsKeyDown(Keys.Back)));
            st.ConfirmPressed = confirmNow && !st.PrevConfirm;
            st.CancelPressed  = cancelNow && !st.PrevCancel;

            bool upNow    = st.DpadUp || st.RawStickY > 0.52f;
            bool downNow  = st.DpadDown || st.RawStickY < -0.52f;
            bool leftNow  = st.DpadLeft || st.Steer < -0.52f;
            bool rightNow = st.DpadRight || st.Steer > 0.52f;

            bool anyDir = upNow || downNow || leftNow || rightNow;
            bool repeatPulse = false;
            if (anyDir)
            {
                st.MenuRepeatTimer += dt;
                if (st.MenuRepeatTimer >= 0.28f)
                {
                    st.MenuRepeatTimer -= 0.12f;
                    repeatPulse = true;
                }
            }
            else
            {
                st.MenuRepeatTimer = 0f;
            }

            st.MenuUpPressed    = (upNow && !st.PrevMenuUp) || (upNow && repeatPulse);
            st.MenuDownPressed  = (downNow && !st.PrevMenuDown) || (downNow && repeatPulse);
            st.MenuLeftPressed  = (leftNow && !st.PrevMenuLeft) || (leftNow && repeatPulse);
            st.MenuRightPressed = (rightNow && !st.PrevMenuRight) || (rightNow && repeatPulse);

            st.PrevDriftHop  = st.DriftHopHeld;
            st.PrevItem      = st.ItemHeld;
            st.PrevBrake     = st.Brake;
            st.PrevStart     = st.StartHeld;
            st.PrevSelect    = st.SelectHeld;
            st.PrevConfirm   = confirmNow;
            st.PrevCancel    = cancelNow;
            st.PrevMenuUp    = upNow;
            st.PrevMenuDown  = downNow;
            st.PrevMenuLeft  = leftNow;
            st.PrevMenuRight = rightNow;
        }
    }
}
