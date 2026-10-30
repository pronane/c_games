using System;
using System.IO;
using System.Windows.Forms;
using MarioKart64.Core;
using MarioKart64.Game;
using MarioKart64.Input;
using MarioKart64.Rendering;

namespace MarioKart64
{
    public static class Program
    {
        [STAThread]
        public static int Main(string[] args)
        {
            GameConfig.Instance.Load();

            if (args != null)
            {
                for (int i = 0; i < args.Length; i++)
                {
                    string a = (args[i] ?? "").Trim().ToLowerInvariant();
                    if (a == "--self-test")
                    {
                        return SelfTest.Run(true);
                    }
                    if (a == "--verify")
                    {
                        return SelfTest.Run(false);
                    }
                }
            }

            try
            {
                if (NativeInput.IsWindowsPlatform())
                {
                    try { Gl.SetProcessDPIAware(); } catch { }
                }

                if (!File.Exists(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "easysmx_config.ini")))
                {
                    GameConfig.Instance.SaveConfig();
                }

                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                using (GameWindow win = new GameWindow())
                {
                    Application.Run(win);
                }
                return 0;
            }
            catch (Exception ex)
            {
                try
                {
                    File.WriteAllText(
                        Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "mk64_error.log"),
                        ex.ToString());
                }
                catch { }

                MessageBox.Show(
                    "Mario Kart 64 PC encountered an initialization error:\n\n" + ex.Message,
                    "Mario Kart 64 PC",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return 1;
            }
        }
    }
}
