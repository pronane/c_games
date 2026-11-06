#!/usr/bin/env bash
# Build stub shared libraries so Blender (bpy) can run on headless Linux
# machines that lack an X11/Mesa stack. The stubs only satisfy the dynamic
# linker: a background-mode Blender never calls into X/GL.
#
# Usage: ./headless_stubs.sh [stubs_dir]
set -eu
cd "$(dirname "$0")"
STUBS="${1:-$PWD/stubs}"
mkdir -p "$STUBS"

SITE=$(ls -d .venv/lib/python*/site-packages/bpy 2>/dev/null | head -1)
if [ -z "${SITE:-}" ]; then
  SITE=$(python3 -c "import bpy,os;print(os.path.dirname(bpy.__file__))")
fi

python3 - "$SITE" "$STUBS" <<'PY'
import subprocess, sys, os, glob, collections, re

site, stubs = sys.argv[1], sys.argv[2]

# symbols provided by every real library we can see (plus Blender's own
# bundled libraries, which are loaded into the same address space)
provided = set()
search = ["/lib/x86_64-linux-gnu", "/usr/lib/x86_64-linux-gnu", "/usr/lib", "/lib"]
libs = []
for d in search:
    libs += glob.glob(os.path.join(d, "lib*.so*"))

bundled = [p for p in glob.glob(os.path.join(site, "lib", "*")) + glob.glob(os.path.join(site, "*"))
           if os.path.isfile(p) and ".so" in os.path.basename(p)]
seen = set()
for lib in libs + bundled:
    real = os.path.realpath(lib)
    if real in seen or not os.path.isfile(real):
        continue
    seen.add(real)
    try:
        out = subprocess.run(["readelf", "-W", "--dyn-syms", real],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        continue
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[3] in ("FUNC","IFUNC") and parts[6] != "UND":
            provided.add(parts[7].split("@")[0])

# undefined symbols in Blender's own libraries
missing = set()
all_undef = set()
for so in bundled:
    out = subprocess.run(["readelf", "-W", "--dyn-syms", so],
                         capture_output=True, text=True, timeout=60).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[3] in ("FUNC","IFUNC") and parts[6] == "UND":
            missing.add(parts[7].split("@")[0])
            all_undef.add(parts[7].split("@")[0])

missing -= provided
missing -= {"__ard_stub"}

def bucket_of(name):
    n = name
    if n.startswith(("egl", "EGL")):
        return "libEGL.so.1"
    if n.startswith(("XRender",)):
        return "libXrender.so.1"
    if n.startswith(("XFixes",)):
        return "libXfixes.so.3"
    if n.startswith(("XI", "_Xi", "XListInputDevices", "XSelectExtensionEvent",
                     "XGetDeviceDontPropagateList", "XChangeFeedbackControl",
                     "XGetExtensionVersion", "XOpenDevice", "XCloseDevice")):
        return "libXi.so.6"
    if n.startswith(("xkb_", "_xkb")):
        return "libxkbcommon.so.0"
    if n.startswith(("Ice", "_Ice")):
        return "libICE.so.6"
    if n.startswith(("Smc", "Sms", "_Smc", "_Sms")):
        return "libSM.so.6"
    return "libGL.so.1"   # GL/GLX & friends

buckets = collections.defaultdict(list)
for name in sorted(missing):
    buckets[bucket_of(name)].append(name)

# EGL is dlopen()'d by soname and looked up via dlsym, so its symbols never
# appear in any ELF table. Hard-code the standard EGL 1.x entry points.
EGL_API = """
eglGetDisplay eglGetPlatformDisplay eglInitialize eglTerminate eglQueryString
eglGetConfigs eglChooseConfig eglGetConfigAttrib eglCreateContext
eglDestroyContext eglMakeCurrent eglGetCurrentContext eglGetCurrentDisplay
eglGetCurrentSurface eglCreateWindowSurface eglCreatePbufferSurface
eglCreatePbufferFromClientBuffer eglDestroySurface eglQuerySurface eglSwapBuffers
eglSwapInterval eglWaitGL eglWaitClient eglBindAPI eglQueryAPI eglQueryContext
eglGetError eglGetProcAddress eglReleaseThread eglSurfaceAttrib eglBindTexImage
eglReleaseTexImage eglCopyBuffers
""".split()
buckets["libEGL.so.1"] = sorted(set(EGL_API) | {n for n in all_undef if n.startswith(("egl", "EGL"))})

# libEGL must behave minimally: epoxy parses eglQueryString(EGL_VERSION) and
# asserts on the result, so provide a tiny working implementation.
EGL_C = r'''
/* hand-written headless stub for libEGL.so.1 (background Blender only) */
#include <string.h>
static const char *kVersion = "1.5";
static const char *kEmpty = "";
typedef int EGLint;
typedef unsigned int EGLenum;
typedef void *EGLDisplay;
typedef void *EGLContext;
typedef void *EGLSurface;
typedef void *EGLConfig;
typedef void *EGLNativeDisplayType;
typedef void *EGLNativeWindowType;
typedef void *EGLNativePixmapType;
typedef int EGLBoolean;
typedef void (*__eglMustCastToProperFunctionPointerType)(void);

EGLDisplay eglGetDisplay(EGLNativeDisplayType d){ (void)d; return (void*)1; }
EGLDisplay eglGetPlatformDisplay(EGLenum p, void *n, const EGLint *a){ (void)p;(void)n;(void)a; return (void*)1; }
EGLBoolean eglInitialize(EGLDisplay d, EGLint *maj, EGLint *min){ (void)d; if(maj)*maj=1; if(min)*min=5; return 1; }
EGLBoolean eglTerminate(EGLDisplay d){ (void)d; return 1; }
const char *eglQueryString(EGLDisplay d, EGLenum name){ (void)d; return name == 0x3054u ? kVersion : kEmpty; }
EGLBoolean eglGetConfigs(EGLDisplay d, EGLConfig *c, EGLint n, EGLint *got){ (void)d;(void)c;(void)n; if(got)*got=1; return 1; }
EGLBoolean eglChooseConfig(EGLDisplay d, const EGLint *a, EGLConfig *c, EGLint n, EGLint *got){ (void)d;(void)a;(void)c;(void)n; if(got)*got=1; return 1; }
EGLBoolean eglGetConfigAttrib(EGLDisplay d, EGLConfig c, EGLint a, EGLint *v){ (void)d;(void)c;(void)a; if(v)*v=1; return 1; }
EGLContext eglCreateContext(EGLDisplay d, EGLConfig c, EGLContext s, const EGLint *a){ (void)d;(void)c;(void)s;(void)a; return (void*)2; }
EGLBoolean eglDestroyContext(EGLDisplay d, EGLContext c){ (void)d;(void)c; return 1; }
EGLBoolean eglMakeCurrent(EGLDisplay d, EGLSurface dr, EGLSurface wr, EGLContext c){ (void)d;(void)dr;(void)wr;(void)c; return 1; }
EGLContext eglGetCurrentContext(void){ return (void*)2; }
EGLDisplay eglGetCurrentDisplay(void){ return (void*)1; }
EGLSurface eglGetCurrentSurface(EGLint r){ (void)r; return (void*)3; }
EGLSurface eglCreateWindowSurface(EGLDisplay d, EGLConfig c, EGLNativeWindowType w, const EGLint *a){ (void)d;(void)c;(void)w;(void)a; return (void*)3; }
EGLSurface eglCreatePbufferSurface(EGLDisplay d, EGLConfig c, const EGLint *a){ (void)d;(void)c;(void)a; return (void*)3; }
EGLSurface eglCreatePbufferFromClientBuffer(EGLDisplay d, EGLenum t, void *b, EGLConfig c, const EGLint *a){ (void)d;(void)t;(void)b;(void)c;(void)a; return (void*)3; }
EGLBoolean eglDestroySurface(EGLDisplay d, EGLSurface s){ (void)d;(void)s; return 1; }
EGLBoolean eglQuerySurface(EGLDisplay d, EGLSurface s, EGLint a, EGLint *v){ (void)d;(void)s;(void)a; if(v)*v=16; return 1; }
EGLBoolean eglSwapBuffers(EGLDisplay d, EGLSurface s){ (void)d;(void)s; return 1; }
EGLBoolean eglSwapInterval(EGLDisplay d, EGLint i){ (void)d;(void)i; return 1; }
EGLBoolean eglWaitGL(void){ return 1; }
EGLBoolean eglWaitClient(void){ return 1; }
EGLBoolean eglBindAPI(EGLenum a){ (void)a; return 1; }
EGLenum eglQueryAPI(void){ return 0x30A0u; }
EGLBoolean eglQueryContext(EGLDisplay d, EGLContext c, EGLint a, EGLint *v){ (void)d;(void)c;(void)a; if(v)*v=1; return 1; }
EGLint eglGetError(void){ return 0x3000; }
__eglMustCastToProperFunctionPointerType eglGetProcAddress(const char *n){ (void)n; return 0; }
EGLBoolean eglReleaseThread(void){ return 1; }
EGLBoolean eglSurfaceAttrib(EGLDisplay d, EGLSurface s, EGLint a, EGLint v){ (void)d;(void)s;(void)a;(void)v; return 1; }
EGLBoolean eglBindTexImage(EGLDisplay d, EGLSurface s, EGLint b){ (void)d;(void)s;(void)b; return 1; }
EGLBoolean eglReleaseTexImage(EGLDisplay d, EGLSurface s, EGLint b){ (void)d;(void)s;(void)b; return 1; }
EGLBoolean eglCopyBuffers(EGLDisplay d, EGLSurface s, EGLNativePixmapType p){ (void)d;(void)s;(void)p; return 1; }
'''

GL_C = r'''
/* hand-written headless stub core for libGL.so.1 */
typedef unsigned int GLenum;
typedef unsigned int GLuint;
typedef int GLint;
typedef int GLsizei;
typedef unsigned char GLubyte;
typedef unsigned char GLboolean;
typedef float GLfloat;
typedef double GLdouble;
typedef long long GLint64;
typedef void (*__GLXextFuncPtr)(void);
static const GLubyte *kVersion = (const GLubyte *)"4.6 (Core Profile) Mesa Stub";
static const GLubyte *kRenderer = (const GLubyte *)"headless-stub";
static const GLubyte *kEmpty = (const GLubyte *)"";
const GLubyte *glGetString(GLenum n){ return n == 0x1F02u ? kVersion : (n == 0x1F01u ? kRenderer : kEmpty); }
const GLubyte *glGetStringi(GLenum n, GLuint i){ (void)n;(void)i; return kEmpty; }
void glGetIntegerv(GLenum n, GLint *v){ if(!v) return; switch(n){ case 0x821Bu: *v=4; break; case 0x821Cu: *v=6; break; case 0x1F00u: *v=0; break; default: *v=0; } }
void glGetInteger64v(GLenum n, GLint64 *v){ (void)n; if(v) *v=0; }
void glGetBooleanv(GLenum n, GLboolean *v){ (void)n; if(v) *v=0; }
void glGetFloatv(GLenum n, GLfloat *v){ (void)n; if(v) *v=0; }
void glGetDoublev(GLenum n, GLdouble *v){ (void)n; if(v) *v=0; }
GLenum glGetError(void){ return 0; }
__GLXextFuncPtr glXGetProcAddress(const GLubyte *n){ (void)n; return 0; }
__GLXextFuncPtr glXGetProcAddressARB(const GLubyte *n){ (void)n; return 0; }

/* GLX entry points (dlsym'd one by one by Blender's GHOST layer) */
typedef struct _XDisplay Display;
typedef unsigned long GLXDrawable;
typedef unsigned long XID;
typedef void *GLXContext;
typedef void *GLXFBConfig;
typedef void *GLXWindow;
typedef void *GLXPbuffer;
typedef void *GLXPixmap;
typedef struct { int dummy; } XVisualInfo;
static const char *kStr14 = "1.4";
static const char *kStrEmpty = "";
static const char *kGlxExts = "GLX_ARB_get_proc_address GLX_ARB_create_context GLX_ARB_create_context_profile GLX_EXT_swap_control GLX_SGI_swap_control GLX_ARB_multisample GLX_ARB_framebuffer_sRGB GLX_EXT_framebuffer_sRGB GLX_ARB_create_context_robustness";
const char *glXQueryExtensionsString(Display *d, int s){ (void)d;(void)s; return kGlxExts; }
const char *glXGetClientString(Display *d, int n){ (void)d; return n == 3 ? kGlxExts : kStr14; }
const char *glXQueryServerString(Display *d, int s, int n){ (void)d;(void)s;(void)n; return kStr14; }
int glXQueryVersion(Display *d, int *maj, int *min){ (void)d; if(maj)*maj=1; if(min)*min=4; return 1; }
GLXContext glXCreateContext(Display *d, XVisualInfo *v, GLXContext s, int direct){ (void)d;(void)v;(void)s;(void)direct; return (void*)2; }
GLXContext glXCreateNewContext(Display *d, GLXFBConfig c, int t, GLXContext s, int direct){ (void)d;(void)c;(void)t;(void)s;(void)direct; return (void*)2; }
GLXContext glXCreateContextAttribsARB(Display *d, GLXFBConfig c, GLXContext s, int direct, const int *a){ (void)d;(void)c;(void)s;(void)direct;(void)a; return (void*)2; }
void glXDestroyContext(Display *d, GLXContext c){ (void)d;(void)c; }
int glXMakeCurrent(Display *d, GLXDrawable dr, GLXContext c){ (void)d;(void)dr;(void)c; return 1; }
GLXContext glXGetCurrentContext(void){ return (void*)2; }
Display *glXGetCurrentDisplay(void){ return (void*)1; }
GLXDrawable glXGetCurrentDrawable(void){ return 3; }
GLXDrawable glXGetCurrentReadDrawable(void){ return 3; }
void glXSwapBuffers(Display *d, GLXDrawable dr){ (void)d;(void)dr; }
int glXIsDirect(Display *d, GLXContext c){ (void)d;(void)c; return 0; }
void glXWaitGL(void){ }
void glXWaitX(void){ }
void glXUseXFont(XID f, int first, int count, int list){ (void)f;(void)first;(void)count;(void)list; }
void glXCopyContext(Display *d, GLXContext s, GLXContext t, unsigned long m){ (void)d;(void)s;(void)t;(void)m; }
int glXQueryContext(Display *d, GLXContext c, int a, int *v){ (void)d;(void)c;(void)a; if(v)*v=1; return 1; }
void glXSelectEvent(Display *d, GLXDrawable dr, unsigned long m){ (void)d;(void)dr;(void)m; }
void glXGetSelectedEvent(Display *d, GLXDrawable dr, unsigned long *m){ (void)d;(void)dr; if(m)*m=0; }
XVisualInfo *glXChooseVisual(Display *d, int s, int *a){ (void)d;(void)s;(void)a; return 0; }
XVisualInfo *glXGetVisualFromFBConfig(Display *d, GLXFBConfig c){ (void)d;(void)c; return 0; }
GLXFBConfig *glXChooseFBConfig(Display *d, int s, const int *a, int *n){ (void)d;(void)s;(void)a; if(n)*n=0; return 0; }
GLXFBConfig *glXGetFBConfigs(Display *d, int s, int *n){ (void)d;(void)s; if(n)*n=0; return 0; }
int glXGetFBConfigAttrib(Display *d, GLXFBConfig c, int a, int *v){ (void)d;(void)c;(void)a; if(v)*v=0; return 0; }
GLXWindow glXCreateWindow(Display *d, GLXFBConfig c, XID w, const int *a){ (void)d;(void)c;(void)w;(void)a; return (void*)3; }
void glXDestroyWindow(Display *d, GLXWindow w){ (void)d;(void)w; }
GLXPbuffer glXCreatePbuffer(Display *d, GLXFBConfig c, const int *a){ (void)d;(void)c;(void)a; return (void*)3; }
void glXDestroyPbuffer(Display *d, GLXPbuffer p){ (void)d;(void)p; }
GLXPixmap glXCreatePixmap(Display *d, GLXFBConfig c, XID p, const int *a){ (void)d;(void)c;(void)p;(void)a; return (void*)3; }
void glXDestroyPixmap(Display *d, GLXPixmap p){ (void)d;(void)p; }
int glXQueryDrawable(Display *d, GLXDrawable dr, int a, unsigned int *v){ (void)d;(void)dr;(void)a; if(v)*v=16; return 1; }
GLXPixmap glXCreateGLXPixmap(Display *d, XVisualInfo *v, XID p){ (void)d;(void)v;(void)p; return (void*)3; }
void glXDestroyGLXPixmap(Display *d, GLXPixmap p){ (void)d;(void)p; }
int glXSwapIntervalEXT(Display *d, GLXDrawable dr, int i){ (void)d;(void)dr;(void)i; return 1; }
int glXSwapIntervalMESA(unsigned int i){ (void)i; return 1; }
int glXSwapIntervalSGI(int i){ (void)i; return 1; }
'''

specs = ["libXrender.so.1", "libXfixes.so.3", "libXi.so.6", "libxkbcommon.so.0",
         "libICE.so.6", "libSM.so.6", "libGL.so.1", "libEGL.so.1"]
for spec in specs:
    syms = buckets.get(spec, [])
    src = os.path.join(stubs, spec + ".c")
    with open(src, "w") as f:
        if spec == "libEGL.so.1":
            f.write(EGL_C)
        elif spec == "libGL.so.1":
            f.write(GL_C)
            f.write("/* auto-generated empty stubs */\n")
            done = set(re.findall(r"^[\w\* ]+\b(\w+)\s*\([^;]*\)\s*\{", GL_C, re.M))
            for s in syms:
                if s in done:
                    continue
                f.write("void %s(void){}\n" % s)
        else:
            f.write("/* auto-generated headless stub for %s */\n" % spec)
            for s in syms:
                f.write("void %s(void){}\n" % s)
    out = os.path.join(stubs, spec)
    cmd = ["gcc", "-shared", "-fPIC", "-Wl,-soname," + spec]
    if spec == "libxkbcommon.so.0":
        # glibc asserts when a versioned lookup (V_0.5.0) hits an unversioned
        # definition from the map named in the VERNEED entry, so version it.
        ver = os.path.join(stubs, spec + ".ver")
        with open(ver, "w") as f:
            f.write("V_0.5.0 { global: *; };\n")
        cmd += ["-Wl,--version-script=" + ver]
    cmd += ["-o", out, src]
    subprocess.run(cmd, check=True)
    print(f"stub {spec}: {len(syms)} symbols")
print("total stubbed symbols:", len(missing))
PY
