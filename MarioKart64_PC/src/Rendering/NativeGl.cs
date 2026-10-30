using System;
using System.Runtime.InteropServices;
using MarioKart64.Core;

namespace MarioKart64.Rendering
{
    [StructLayout(LayoutKind.Sequential)]
    public struct PIXELFORMATDESCRIPTOR
    {
        public ushort nSize;
        public ushort nVersion;
        public uint dwFlags;
        public byte iPixelType;
        public byte cColorBits;
        public byte cRedBits;
        public byte cRedShift;
        public byte cGreenBits;
        public byte cGreenShift;
        public byte cBlueBits;
        public byte cBlueShift;
        public byte cAlphaBits;
        public byte cAlphaShift;
        public byte cAccumBits;
        public byte cAccumRedBits;
        public byte cAccumGreenBits;
        public byte cAccumBlueBits;
        public byte cAccumAlphaBits;
        public byte cDepthBits;
        public byte cStencilBits;
        public byte cAuxBuffers;
        public byte iLayerType;
        public byte bReserved;
        public uint dwLayerMask;
        public uint dwVisibleMask;
        public uint dwDamageMask;
    }

    public static class Gl
    {
        // WGL / PFD Constants
        public const uint PFD_DOUBLEBUFFER   = 0x00000001;
        public const uint PFD_DRAW_TO_WINDOW = 0x00000004;
        public const uint PFD_SUPPORT_OPENGL = 0x00000020;
        public const byte PFD_TYPE_RGBA      = 0;
        public const byte PFD_MAIN_PLANE     = 0;

        // Clear masks
        public const uint GL_DEPTH_BUFFER_BIT   = 0x00000100;
        public const uint GL_STENCIL_BUFFER_BIT = 0x00000400;
        public const uint GL_COLOR_BUFFER_BIT   = 0x00004000;

        // Primitives
        public const uint GL_POINTS         = 0x0000;
        public const uint GL_LINES          = 0x0001;
        public const uint GL_LINE_LOOP      = 0x0002;
        public const uint GL_LINE_STRIP     = 0x0003;
        public const uint GL_TRIANGLES      = 0x0004;
        public const uint GL_TRIANGLE_STRIP = 0x0005;
        public const uint GL_TRIANGLE_FAN   = 0x0006;
        public const uint GL_QUADS          = 0x0007;

        // Matrix modes
        public const uint GL_MODELVIEW  = 0x1700;
        public const uint GL_PROJECTION = 0x1701;

        // Capabilities & State
        public const uint GL_ALPHA_TEST     = 0x0BC0;
        public const uint GL_BLEND          = 0x0BE2;
        public const uint GL_CULL_FACE      = 0x0B44;
        public const uint GL_DEPTH_TEST     = 0x0B71;
        public const uint GL_FOG            = 0x0B60;
        public const uint GL_SCISSOR_TEST   = 0x0C11;
        public const uint GL_TEXTURE_2D     = 0x0DE1;

        public const uint GL_NEVER          = 0x0200;
        public const uint GL_LESS           = 0x0201;
        public const uint GL_LEQUAL         = 0x0203;
        public const uint GL_GREATER        = 0x0204;
        public const uint GL_ALWAYS         = 0x0207;

        public const uint GL_SRC_ALPHA           = 0x0302;
        public const uint GL_ONE_MINUS_SRC_ALPHA = 0x0303;
        public const uint GL_ONE                 = 0x0001;

        public const uint GL_SMOOTH = 0x1D01;

        // Fog
        public const uint GL_LINEAR    = 0x2601;
        public const uint GL_FOG_MODE  = 0x0B65;
        public const uint GL_FOG_START = 0x0B63;
        public const uint GL_FOG_END   = 0x0B64;
        public const uint GL_FOG_COLOR = 0x0B66;

        // Textures
        public const uint GL_UNSIGNED_BYTE      = 0x1401;
        public const uint GL_RGBA               = 0x1908;
        public const int  GL_RGBA8              = 0x8058;
        public const uint GL_TEXTURE_MAG_FILTER = 0x2800;
        public const uint GL_TEXTURE_MIN_FILTER = 0x2801;
        public const uint GL_TEXTURE_WRAP_S     = 0x2802;
        public const uint GL_TEXTURE_WRAP_T     = 0x2803;
        public const int  GL_NEAREST            = 0x2600;
        public const int  GL_LINEAR_FILTER      = 0x2601;
        public const int  GL_REPEAT             = 0x2901;
        public const int  GL_CLAMP              = 0x2900;

        // Display Lists
        public const uint GL_COMPILE = 0x1300;

        // Win32 User32 / GDI32 / WGL
        [DllImport("user32.dll")]
        public static extern IntPtr GetDC(IntPtr hWnd);

        [DllImport("user32.dll")]
        public static extern int ReleaseDC(IntPtr hWnd, IntPtr hDC);

        [DllImport("user32.dll")]
        public static extern bool SetProcessDPIAware();

        [DllImport("gdi32.dll")]
        public static extern int ChoosePixelFormat(IntPtr hdc, ref PIXELFORMATDESCRIPTOR ppfd);

        [DllImport("gdi32.dll")]
        public static extern bool SetPixelFormat(IntPtr hdc, int iPixelFormat, ref PIXELFORMATDESCRIPTOR ppfd);

        [DllImport("gdi32.dll")]
        public static extern bool SwapBuffers(IntPtr hdc);

        [DllImport("opengl32.dll")]
        public static extern IntPtr wglCreateContext(IntPtr hdc);

        [DllImport("opengl32.dll")]
        public static extern bool wglMakeCurrent(IntPtr hdc, IntPtr hglrc);

        [DllImport("opengl32.dll")]
        public static extern bool wglDeleteContext(IntPtr hglrc);

        [DllImport("opengl32.dll", CharSet = CharSet.Ansi)]
        public static extern IntPtr wglGetProcAddress(string lpszProc);

        // OpenGL 1.1 Core Exports (guaranteed in C:\Windows\System32\opengl32.dll on all Windows versions)
        [DllImport("opengl32.dll")] public static extern void glViewport(int x, int y, int width, int height);
        [DllImport("opengl32.dll")] public static extern void glScissor(int x, int y, int width, int height);
        [DllImport("opengl32.dll")] public static extern void glClearColor(float red, float green, float blue, float alpha);
        [DllImport("opengl32.dll")] public static extern void glClearDepth(double depth);
        [DllImport("opengl32.dll")] public static extern void glClear(uint mask);
        [DllImport("opengl32.dll")] public static extern void glEnable(uint cap);
        [DllImport("opengl32.dll")] public static extern void glDisable(uint cap);
        [DllImport("opengl32.dll")] public static extern void glDepthFunc(uint func);
        [DllImport("opengl32.dll")] public static extern void glDepthMask(byte flag);
        [DllImport("opengl32.dll")] public static extern void glBlendFunc(uint sfactor, uint dfactor);
        [DllImport("opengl32.dll")] public static extern void glAlphaFunc(uint func, float refVal);
        [DllImport("opengl32.dll")] public static extern void glShadeModel(uint mode);
        [DllImport("opengl32.dll")] public static extern void glMatrixMode(uint mode);
        [DllImport("opengl32.dll")] public static extern void glLoadIdentity();
        [DllImport("opengl32.dll")] public static extern void glPushMatrix();
        [DllImport("opengl32.dll")] public static extern void glPopMatrix();
        [DllImport("opengl32.dll")] public static extern void glOrtho(double left, double right, double bottom, double top, double zNear, double zFar);
        [DllImport("opengl32.dll")] public static extern void glFrustum(double left, double right, double bottom, double top, double zNear, double zFar);
        [DllImport("opengl32.dll")] public static extern void glMultMatrixf(float[] m);
        [DllImport("opengl32.dll")] public static extern void glTranslatef(float x, float y, float z);
        [DllImport("opengl32.dll")] public static extern void glRotatef(float angleDeg, float x, float y, float z);
        [DllImport("opengl32.dll")] public static extern void glScalef(float x, float y, float z);
        [DllImport("opengl32.dll")] public static extern void glBegin(uint mode);
        [DllImport("opengl32.dll")] public static extern void glEnd();
        [DllImport("opengl32.dll")] public static extern void glVertex3f(float x, float y, float z);
        [DllImport("opengl32.dll")] public static extern void glVertex2f(float x, float y);
        [DllImport("opengl32.dll")] public static extern void glColor3f(float r, float g, float b);
        [DllImport("opengl32.dll")] public static extern void glColor4f(float r, float g, float b, float a);
        [DllImport("opengl32.dll")] public static extern void glTexCoord2f(float s, float t);
        [DllImport("opengl32.dll")] public static extern void glNormal3f(float nx, float ny, float nz);
        [DllImport("opengl32.dll")] public static extern void glLineWidth(float width);
        [DllImport("opengl32.dll")] public static extern void glPointSize(float size);
        [DllImport("opengl32.dll")] public static extern void glGenTextures(int n, uint[] textures);
        [DllImport("opengl32.dll")] public static extern void glDeleteTextures(int n, uint[] textures);
        [DllImport("opengl32.dll")] public static extern void glBindTexture(uint target, uint texture);
        [DllImport("opengl32.dll")] public static extern void glTexParameteri(uint target, uint pname, int param);
        [DllImport("opengl32.dll")] public static extern void glTexImage2D(uint target, int level, int internalformat, int width, int height, int border, uint format, uint type, byte[] pixels);
        [DllImport("opengl32.dll")] public static extern void glFogi(uint pname, int param);
        [DllImport("opengl32.dll")] public static extern void glFogf(uint pname, float param);
        [DllImport("opengl32.dll")] public static extern void glFogfv(uint pname, float[] param);
        [DllImport("opengl32.dll")] public static extern uint glGenLists(int range);
        [DllImport("opengl32.dll")] public static extern void glNewList(uint list, uint mode);
        [DllImport("opengl32.dll")] public static extern void glEndList();
        [DllImport("opengl32.dll")] public static extern void glCallList(uint list);
        [DllImport("opengl32.dll")] public static extern void glDeleteLists(uint list, int range);

        [UnmanagedFunctionPointer(CallingConvention.StdCall)]
        private delegate bool WglSwapIntervalEXTDelegate(int interval);

        public static void TrySetSwapInterval(int interval)
        {
            try
            {
                IntPtr ptr = wglGetProcAddress("wglSwapIntervalEXT");
                if (ptr != IntPtr.Zero)
                {
                    WglSwapIntervalEXTDelegate fn = (WglSwapIntervalEXTDelegate)Marshal.GetDelegateForFunctionPointer(ptr, typeof(WglSwapIntervalEXTDelegate));
                    fn(interval);
                }
            }
            catch
            {
            }
        }

        public static void Color(Color4 c)
        {
            glColor4f(c.R, c.G, c.B, c.A);
        }

        public static void Vertex(Vec3 v)
        {
            glVertex3f(v.X, v.Y, v.Z);
        }

        public static void Perspective(float fovYDeg, float aspect, float zNear, float zFar)
        {
            double fH = Math.Tan(fovYDeg * 0.5 * Math.PI / 180.0) * zNear;
            double fW = fH * aspect;
            glFrustum(-fW, fW, -fH, fH, zNear, zFar);
        }

        public static void LookAt(Vec3 eye, Vec3 center, Vec3 up)
        {
            float[] m = MathUtil.BuildLookAtMatrix(eye, center, up);
            glMultMatrixf(m);
        }
    }
}
