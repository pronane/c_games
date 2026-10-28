/* Minimal GL 1.1 stencil entry points (exported by opengl32.dll / libGL directly),
 * declared here so no system GL headers (and no windows.h) are needed. */
#ifndef GLMIN_H
#define GLMIN_H
#if defined(_WIN32)
#define GLMIN_API __attribute__((stdcall)) __declspec(dllimport)
#else
#define GLMIN_API
#endif
#define GL_STENCIL_TEST 0x0B90
#define GL_STENCIL_BUFFER_BIT 0x00000400
#define GL_KEEP 0x1E00
#define GL_REPLACE 0x1E01
#define GL_NOTEQUAL 0x0205
GLMIN_API void glEnable(unsigned int cap);
GLMIN_API void glDisable(unsigned int cap);
GLMIN_API void glStencilFunc(unsigned int func, int ref, unsigned int mask);
GLMIN_API void glStencilOp(unsigned int fail, unsigned int zfail, unsigned int zpass);
GLMIN_API void glClearStencil(int s);
GLMIN_API void glClear(unsigned int mask);
#endif
