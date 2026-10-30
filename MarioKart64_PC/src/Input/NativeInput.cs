using System;
using System.Runtime.InteropServices;

namespace MarioKart64.Input
{
    [StructLayout(LayoutKind.Sequential)]
    public struct XInputGamepad
    {
        public ushort wButtons;
        public byte bLeftTrigger;
        public byte bRightTrigger;
        public short sThumbLX;
        public short sThumbLY;
        public short sThumbRX;
        public short sThumbRY;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct XInputState
    {
        public uint dwPacketNumber;
        public XInputGamepad Gamepad;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct XInputVibration
    {
        public ushort wLeftMotorSpeed;
        public ushort wRightMotorSpeed;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct JOYINFOEX
    {
        public uint dwSize;
        public uint dwFlags;
        public uint dwXpos;
        public uint dwYpos;
        public uint dwZpos;
        public uint dwRpos;
        public uint dwUpos;
        public uint dwVpos;
        public uint dwButtons;
        public uint dwButtonNumber;
        public uint dwPOV;
        public uint dwReserved1;
        public uint dwReserved2;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct JOYCAPSW
    {
        public ushort wMid;
        public ushort wPid;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string szPname;
        public uint wXmin;
        public uint wXmax;
        public uint wYmin;
        public uint wYmax;
        public uint wZmin;
        public uint wZmax;
        public uint wNumButtons;
        public uint wPeriodMin;
        public uint wPeriodMax;
        public uint wRmin;
        public uint wRmax;
        public uint wUmin;
        public uint wUmax;
        public uint wVmin;
        public uint wVmax;
        public uint wCaps;
        public uint wMaxAxes;
        public uint wNumAxes;
        public uint wMaxButtons;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string szRegKey;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
        public string szOEMVxD;
    }

    public static class XInputButtons
    {
        public const ushort DPAD_UP        = 0x0001;
        public const ushort DPAD_DOWN      = 0x0002;
        public const ushort DPAD_LEFT      = 0x0004;
        public const ushort DPAD_RIGHT     = 0x0008;
        public const ushort START          = 0x0010;
        public const ushort BACK           = 0x0020;
        public const ushort LEFT_THUMB     = 0x0040;
        public const ushort RIGHT_THUMB    = 0x0080;
        public const ushort LEFT_SHOULDER  = 0x0100;
        public const ushort RIGHT_SHOULDER = 0x0200;
        public const ushort A              = 0x1000;
        public const ushort B              = 0x2000;
        public const ushort X              = 0x4000;
        public const ushort Y              = 0x8000;

        public static string GetButtonName(int mask)
        {
            switch (mask)
            {
                case A: return "A (Bottom)";
                case B: return "B (Right)";
                case X: return "X (Left)";
                case Y: return "Y (Top)";
                case LEFT_SHOULDER: return "LB (L1)";
                case RIGHT_SHOULDER: return "RB (R1)";
                case LEFT_THUMB: return "L3";
                case RIGHT_THUMB: return "R3";
                case BACK: return "Back/Select";
                case START: return "Start";
                default: return "Btn 0x" + mask.ToString("X4");
            }
        }
    }

    public static class NativeInput
    {
        public const uint JOY_RETURNX       = 0x00000001;
        public const uint JOY_RETURNY       = 0x00000002;
        public const uint JOY_RETURNZ       = 0x00000004;
        public const uint JOY_RETURNR       = 0x00000008;
        public const uint JOY_RETURNU       = 0x00000010;
        public const uint JOY_RETURNV       = 0x00000020;
        public const uint JOY_RETURNPOV     = 0x00000040;
        public const uint JOY_RETURNBUTTONS = 0x00000080;
        public const uint JOY_RETURNALL     = 0x000000FF;
        public const uint JOYCAPS_HASZ      = 0x0001;
        public const uint JOYCAPS_HASR      = 0x0002;
        public const uint JOYCAPS_HASPOV    = 0x0010;

        private static int _xinputDllVariant = 0; // 0=untested, 1=1_4, 2=1_3, 3=9_1_0, -1=unavailable
        private static bool _winmmAvailable = true;

        [DllImport("xinput1_4.dll", EntryPoint = "XInputGetState")]
        private static extern uint XInputGetState_14(uint dwUserIndex, out XInputState pState);

        [DllImport("xinput1_4.dll", EntryPoint = "XInputSetState")]
        private static extern uint XInputSetState_14(uint dwUserIndex, ref XInputVibration pVibration);

        [DllImport("xinput1_3.dll", EntryPoint = "XInputGetState")]
        private static extern uint XInputGetState_13(uint dwUserIndex, out XInputState pState);

        [DllImport("xinput1_3.dll", EntryPoint = "XInputSetState")]
        private static extern uint XInputSetState_13(uint dwUserIndex, ref XInputVibration pVibration);

        [DllImport("xinput9_1_0.dll", EntryPoint = "XInputGetState")]
        private static extern uint XInputGetState_910(uint dwUserIndex, out XInputState pState);

        [DllImport("xinput9_1_0.dll", EntryPoint = "XInputSetState")]
        private static extern uint XInputSetState_910(uint dwUserIndex, ref XInputVibration pVibration);

        [DllImport("winmm.dll")]
        private static extern uint joyGetNumDevs();

        [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
        private static extern uint joyGetDevCapsW(UIntPtr uJoyID, out JOYCAPSW pjc, uint cbjc);

        [DllImport("winmm.dll")]
        private static extern uint joyGetPosEx(uint uJoyID, ref JOYINFOEX pji);

        public static bool IsWindowsPlatform()
        {
            PlatformID p = Environment.OSVersion.Platform;
            return p == PlatformID.Win32NT || p == PlatformID.Win32Windows;
        }

        public static bool TryXInputGetState(uint index, out XInputState state)
        {
            state = new XInputState();
            if (!IsWindowsPlatform() || _xinputDllVariant == -1) return false;

            if (_xinputDllVariant == 0)
            {
                try { uint r = XInputGetState_14(index, out state); _xinputDllVariant = 1; return r == 0; }
                catch (DllNotFoundException) { }
                catch (EntryPointNotFoundException) { }

                try { uint r = XInputGetState_13(index, out state); _xinputDllVariant = 2; return r == 0; }
                catch (DllNotFoundException) { }
                catch (EntryPointNotFoundException) { }

                try { uint r = XInputGetState_910(index, out state); _xinputDllVariant = 3; return r == 0; }
                catch (DllNotFoundException) { _xinputDllVariant = -1; return false; }
                catch (EntryPointNotFoundException) { _xinputDllVariant = -1; return false; }
            }

            try
            {
                if (_xinputDllVariant == 1) return XInputGetState_14(index, out state) == 0;
                if (_xinputDllVariant == 2) return XInputGetState_13(index, out state) == 0;
                if (_xinputDllVariant == 3) return XInputGetState_910(index, out state) == 0;
            }
            catch
            {
                _xinputDllVariant = -1;
            }
            return false;
        }

        public static void TryXInputSetVibration(uint index, ushort leftMotor, ushort rightMotor)
        {
            if (!IsWindowsPlatform() || _xinputDllVariant <= 0) return;
            XInputVibration vib = new XInputVibration();
            vib.wLeftMotorSpeed = leftMotor;
            vib.wRightMotorSpeed = rightMotor;
            try
            {
                if (_xinputDllVariant == 1) XInputSetState_14(index, ref vib);
                else if (_xinputDllVariant == 2) XInputSetState_13(index, ref vib);
                else if (_xinputDllVariant == 3) XInputSetState_910(index, ref vib);
            }
            catch
            {
            }
        }

        public static uint GetWinMmNumDevs()
        {
            if (!IsWindowsPlatform() || !_winmmAvailable) return 0;
            try
            {
                return joyGetNumDevs();
            }
            catch
            {
                _winmmAvailable = false;
                return 0;
            }
        }

        public static bool TryGetJoyCaps(uint joyId, out JOYCAPSW caps)
        {
            caps = new JOYCAPSW();
            if (!IsWindowsPlatform() || !_winmmAvailable) return false;
            try
            {
                uint size = (uint)Marshal.SizeOf(typeof(JOYCAPSW));
                return joyGetDevCapsW(new UIntPtr(joyId), out caps, size) == 0;
            }
            catch
            {
                return false;
            }
        }

        public static bool TryGetJoyPosEx(uint joyId, out JOYINFOEX info)
        {
            info = new JOYINFOEX();
            if (!IsWindowsPlatform() || !_winmmAvailable) return false;
            try
            {
                info.dwSize = (uint)Marshal.SizeOf(typeof(JOYINFOEX));
                info.dwFlags = JOY_RETURNALL;
                return joyGetPosEx(joyId, ref info) == 0;
            }
            catch
            {
                return false;
            }
        }
    }
}
