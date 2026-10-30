using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;

namespace MarioKart64.Core
{
    public enum GameMode
    {
        MarioGP = 0,
        TimeTrials = 1,
        VsRace = 2,
        Battle = 3
    }

    public enum EngineClass
    {
        CC50 = 0,
        CC100 = 1,
        CC150 = 2,
        ExtraMirror = 3
    }

    public enum CupType
    {
        Mushroom = 0,
        Flower = 1,
        Star = 2,
        Special = 3
    }

    public enum TrophyTier
    {
        None = 0,
        Bronze = 1,
        Silver = 2,
        Gold = 3
    }

    public class GameConfig
    {
        public static readonly GameConfig Instance = new GameConfig();

        // EasySMX Controller & Input Settings
        public float StickDeadzone = 0.16f;
        public float SteeringSensitivity = 1.00f;
        public float TriggerThreshold = 0.28f;
        public bool EnableRumble = true;
        public bool AllowRightTriggerGas = true;

        // XInput customizable action buttons (bitmasks matching XInputGamepadButton)
        // Defaults match EasySMX Xbox/XInput layout with N64 ergonomics:
        // A (0x1000) = Gas, B (0x2000) = Brake, RB (0x0200) = Hop/Drift, LB (0x0100) or X (0x4000) = Item
        public int XInputBtnAccelerate = 0x1000; // A
        public int XInputBtnBrake      = 0x2000; // B
        public int XInputBtnDriftHop   = 0x0200; // RB (R shoulder)
        public int XInputBtnItem       = 0x0100; // LB (Z trigger equivalent, LT also works automatically)
        public int XInputBtnAltBrake   = 0x4000; // X
        public int XInputBtnCameraHud  = 0x8000; // Y

        // DirectInput (EasySMX D-Input / LED 1+3 mode) customizable button indices (0-based)
        // Standard EasySMX D-Input HID descriptors:
        // Btn 0 = Y/X or Cross/A depending on mode; EasySMX PC D-Input:
        // Btn 2 (or 0) = Bottom Face (A), Btn 1 = Right Face (B), Btn 5/7 = R1/R2, Btn 4/6 = L1/L2, Btn 9 = Start, Btn 8 = Back
        public int DInputBtnAccelerate = 0;
        public int DInputBtnAltAccel   = 2;
        public int DInputBtnBrake      = 1;
        public int DInputBtnDriftHop   = 5; // R1
        public int DInputBtnAltDrift   = 7; // R2
        public int DInputBtnItem       = 4; // L1
        public int DInputBtnAltItem    = 6; // L2
        public int DInputBtnStart      = 9;
        public int DInputBtnSelect     = 8;

        // Audio / Video Settings
        public float MusicVolume = 0.65f;
        public float SfxVolume = 0.85f;
        public bool ShowSpeedometer = true;
        public bool ShowMinimap = true;

        // Save Data: 4 Cups x 4 Engine Classes trophies, 16 Track Best Course & Best Lap times (seconds)
        public TrophyTier[,] CupTrophies = new TrophyTier[4, 4];
        public float[] BestCourseSeconds = new float[16];
        public float[] BestLapSeconds = new float[16];

        private string _configPath;
        private string _savePath;

        private GameConfig()
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            _configPath = Path.Combine(baseDir, "easysmx_config.ini");
            _savePath = Path.Combine(baseDir, "mk64_save.ini");

            // Initialize Staff Target Times calibrated to actual 3-lap course lengths
            float[] defaultCourse = new float[16]
            {
                55.50f, 39.20f, 34.50f, 53.80f,
                79.50f, 52.40f, 45.80f, 55.20f,
                68.50f, 50.60f, 41.20f, 49.50f,
                43.80f, 36.50f, 42.20f, 87.50f
            };
            for (int i = 0; i < 16; i++)
            {
                BestCourseSeconds[i] = defaultCourse[i];
                BestLapSeconds[i] = defaultCourse[i] / 3.0f - 1.25f;
            }
        }

        public void Load()
        {
            LoadIni(_configPath, true);
            LoadIni(_savePath, false);
        }

        public void SaveConfig()
        {
            try
            {
                List<string> lines = new List<string>();
                lines.Add("# Mario Kart 64 PC - EasySMX USB Controller & Game Configuration");
                lines.Add("# Supports EasySMX XInput Mode (LED 1+2) and DirectInput Mode (LED 1+3 / 1+4)");
                lines.Add("StickDeadzone=" + StickDeadzone.ToString("F3", CultureInfo.InvariantCulture));
                lines.Add("SteeringSensitivity=" + SteeringSensitivity.ToString("F3", CultureInfo.InvariantCulture));
                lines.Add("TriggerThreshold=" + TriggerThreshold.ToString("F3", CultureInfo.InvariantCulture));
                lines.Add("EnableRumble=" + (EnableRumble ? "1" : "0"));
                lines.Add("AllowRightTriggerGas=" + (AllowRightTriggerGas ? "1" : "0"));
                lines.Add("XInputBtnAccelerate=" + XInputBtnAccelerate);
                lines.Add("XInputBtnBrake=" + XInputBtnBrake);
                lines.Add("XInputBtnDriftHop=" + XInputBtnDriftHop);
                lines.Add("XInputBtnItem=" + XInputBtnItem);
                lines.Add("DInputBtnAccelerate=" + DInputBtnAccelerate);
                lines.Add("DInputBtnAltAccel=" + DInputBtnAltAccel);
                lines.Add("DInputBtnBrake=" + DInputBtnBrake);
                lines.Add("DInputBtnDriftHop=" + DInputBtnDriftHop);
                lines.Add("DInputBtnAltDrift=" + DInputBtnAltDrift);
                lines.Add("DInputBtnItem=" + DInputBtnItem);
                lines.Add("DInputBtnAltItem=" + DInputBtnAltItem);
                lines.Add("DInputBtnStart=" + DInputBtnStart);
                lines.Add("DInputBtnSelect=" + DInputBtnSelect);
                lines.Add("MusicVolume=" + MusicVolume.ToString("F2", CultureInfo.InvariantCulture));
                lines.Add("SfxVolume=" + SfxVolume.ToString("F2", CultureInfo.InvariantCulture));
                lines.Add("ShowSpeedometer=" + (ShowSpeedometer ? "1" : "0"));
                lines.Add("ShowMinimap=" + (ShowMinimap ? "1" : "0"));
                File.WriteAllLines(_configPath, lines.ToArray());
            }
            catch
            {
                // Ignore read-only folder failures gracefully
            }
        }

        public void SaveRecords()
        {
            try
            {
                List<string> lines = new List<string>();
                lines.Add("# Mario Kart 64 PC - Trophies & Time Trial Records");
                for (int cup = 0; cup < 4; cup++)
                {
                    for (int cc = 0; cc < 4; cc++)
                    {
                        lines.Add(string.Format("Trophy_{0}_{1}={2}", cup, cc, (int)CupTrophies[cup, cc]));
                    }
                }
                for (int t = 0; t < 16; t++)
                {
                    lines.Add(string.Format("BestCourse_{0}={1}", t, BestCourseSeconds[t].ToString("F3", CultureInfo.InvariantCulture)));
                    lines.Add(string.Format("BestLap_{0}={1}", t, BestLapSeconds[t].ToString("F3", CultureInfo.InvariantCulture)));
                }
                File.WriteAllLines(_savePath, lines.ToArray());
            }
            catch
            {
            }
        }

        public bool RecordTimeTrial(int trackIndex, float totalSec, float bestLapSec)
        {
            if (trackIndex < 0 || trackIndex >= 16) return false;
            bool newRecord = false;
            if (totalSec > 5f && totalSec < BestCourseSeconds[trackIndex])
            {
                BestCourseSeconds[trackIndex] = totalSec;
                newRecord = true;
            }
            if (bestLapSec > 1.5f && bestLapSec < BestLapSeconds[trackIndex])
            {
                BestLapSeconds[trackIndex] = bestLapSec;
                newRecord = true;
            }
            if (newRecord) SaveRecords();
            return newRecord;
        }

        public void RecordTrophy(CupType cup, EngineClass cc, TrophyTier tier)
        {
            int cIdx = (int)cup;
            int eIdx = (int)cc;
            if ((int)tier > (int)CupTrophies[cIdx, eIdx])
            {
                CupTrophies[cIdx, eIdx] = tier;
                SaveRecords();
            }
        }

        private void LoadIni(string path, bool isConfig)
        {
            try
            {
                if (!File.Exists(path)) return;
                string[] lines = File.ReadAllLines(path);
                for (int i = 0; i < lines.Length; i++)
                {
                    string line = lines[i].Trim();
                    if (line.Length == 0 || line.StartsWith("#") || line.StartsWith(";")) continue;
                    int eq = line.IndexOf('=');
                    if (eq <= 0) continue;
                    string key = line.Substring(0, eq).Trim();
                    string val = line.Substring(eq + 1).Trim();

                    if (isConfig)
                    {
                        float fv;
                        int iv;
                        if (key == "StickDeadzone" && float.TryParse(val, NumberStyles.Float, CultureInfo.InvariantCulture, out fv))
                            StickDeadzone = MathUtil.Clamp(fv, 0.04f, 0.45f);
                        else if (key == "SteeringSensitivity" && float.TryParse(val, NumberStyles.Float, CultureInfo.InvariantCulture, out fv))
                            SteeringSensitivity = MathUtil.Clamp(fv, 0.50f, 1.80f);
                        else if (key == "TriggerThreshold" && float.TryParse(val, NumberStyles.Float, CultureInfo.InvariantCulture, out fv))
                            TriggerThreshold = MathUtil.Clamp(fv, 0.05f, 0.85f);
                        else if (key == "EnableRumble") EnableRumble = (val == "1" || val.Equals("true", StringComparison.OrdinalIgnoreCase));
                        else if (key == "AllowRightTriggerGas") AllowRightTriggerGas = (val == "1" || val.Equals("true", StringComparison.OrdinalIgnoreCase));
                        else if (key == "XInputBtnAccelerate" && int.TryParse(val, out iv)) XInputBtnAccelerate = iv;
                        else if (key == "XInputBtnBrake" && int.TryParse(val, out iv)) XInputBtnBrake = iv;
                        else if (key == "XInputBtnDriftHop" && int.TryParse(val, out iv)) XInputBtnDriftHop = iv;
                        else if (key == "XInputBtnItem" && int.TryParse(val, out iv)) XInputBtnItem = iv;
                        else if (key == "DInputBtnAccelerate" && int.TryParse(val, out iv)) DInputBtnAccelerate = iv;
                        else if (key == "DInputBtnAltAccel" && int.TryParse(val, out iv)) DInputBtnAltAccel = iv;
                        else if (key == "DInputBtnBrake" && int.TryParse(val, out iv)) DInputBtnBrake = iv;
                        else if (key == "DInputBtnDriftHop" && int.TryParse(val, out iv)) DInputBtnDriftHop = iv;
                        else if (key == "DInputBtnAltDrift" && int.TryParse(val, out iv)) DInputBtnAltDrift = iv;
                        else if (key == "DInputBtnItem" && int.TryParse(val, out iv)) DInputBtnItem = iv;
                        else if (key == "DInputBtnAltItem" && int.TryParse(val, out iv)) DInputBtnAltItem = iv;
                        else if (key == "DInputBtnStart" && int.TryParse(val, out iv)) DInputBtnStart = iv;
                        else if (key == "DInputBtnSelect" && int.TryParse(val, out iv)) DInputBtnSelect = iv;
                        else if (key == "MusicVolume" && float.TryParse(val, NumberStyles.Float, CultureInfo.InvariantCulture, out fv))
                            MusicVolume = MathUtil.Clamp(fv, 0f, 1f);
                        else if (key == "SfxVolume" && float.TryParse(val, NumberStyles.Float, CultureInfo.InvariantCulture, out fv))
                            SfxVolume = MathUtil.Clamp(fv, 0f, 1f);
                        else if (key == "ShowSpeedometer") ShowSpeedometer = (val == "1" || val.Equals("true", StringComparison.OrdinalIgnoreCase));
                        else if (key == "ShowMinimap") ShowMinimap = (val == "1" || val.Equals("true", StringComparison.OrdinalIgnoreCase));
                    }
                    else
                    {
                        if (key.StartsWith("Trophy_"))
                        {
                            string[] parts = key.Split('_');
                            int cup, cc, tier;
                            if (parts.Length == 3 && int.TryParse(parts[1], out cup) && int.TryParse(parts[2], out cc) && int.TryParse(val, out tier))
                            {
                                if (cup >= 0 && cup < 4 && cc >= 0 && cc < 4)
                                    CupTrophies[cup, cc] = (TrophyTier)MathUtil.ClampInt(tier, 0, 3);
                            }
                        }
                        else if (key.StartsWith("BestCourse_"))
                        {
                            int t;
                            float fv;
                            if (int.TryParse(key.Substring("BestCourse_".Length), out t) && float.TryParse(val, NumberStyles.Float, CultureInfo.InvariantCulture, out fv))
                            {
                                if (t >= 0 && t < 16 && fv > 1f) BestCourseSeconds[t] = fv;
                            }
                        }
                        else if (key.StartsWith("BestLap_"))
                        {
                            int t;
                            float fv;
                            if (int.TryParse(key.Substring("BestLap_".Length), out t) && float.TryParse(val, NumberStyles.Float, CultureInfo.InvariantCulture, out fv))
                            {
                                if (t >= 0 && t < 16 && fv > 1f) BestLapSeconds[t] = fv;
                            }
                        }
                    }
                }
            }
            catch
            {
            }
        }

        public static string FormatRaceTime(float seconds)
        {
            if (seconds < 0f) seconds = 0f;
            int totalMs = (int)(seconds * 100.0f + 0.5f);
            int mins = totalMs / 6000;
            int secs = (totalMs / 100) % 60;
            int cs = totalMs % 100;
            return string.Format("{0:00}'{1:00}\"{2:00}", mins, secs, cs);
        }
    }
}
