/* File and math support for the vendored raylib 5.5 animation loader only.
 * This is not a renderer or a substitute for raylib in the game. The build
 * discards all unrelated rmodels.c sections; no graphics context is created. */
#include "raylib.h"
#define RAYMATH_IMPLEMENTATION
#include "raymath.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <limits.h>

void TraceLog(int level, const char *fmt, ...)
{
    va_list args;
    if (level < LOG_WARNING) return;
    va_start(args, fmt); vfprintf(stderr, fmt, args); va_end(args); fputc('\n', stderr);
}
void *MemAlloc(unsigned int size) { return malloc(size); }
void MemFree(void *p) { free(p); }
unsigned char *LoadFileData(const char *name, int *size)
{
    FILE *f; long n; unsigned char *p;
    if (!name || !size) return NULL;
    *size = 0; f = fopen(name, "rb"); if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) || (n = ftell(f)) < 0 || n > INT_MAX || fseek(f, 0, SEEK_SET)) { fclose(f); return NULL; }
    p = malloc((size_t)n + 1);
    if (!p) { fclose(f); return NULL; }
    if (fread(p, 1, (size_t)n, f) != (size_t)n) { free(p); fclose(f); return NULL; }
    fclose(f); *size = (int)n; return p;
}
void UnloadFileData(unsigned char *p) { free(p); }
bool IsFileExtension(const char *name, const char *ext)
{
    const char *p = strrchr(name, '.'); size_t n;
    if (!p) return false;
    n = strlen(p);
    while (*ext) {
        const char *end = strchr(ext, ';'); size_t len = end ? (size_t)(end - ext) : strlen(ext);
        if (len == n && !strncmp(ext, p, n)) return true;
        if (!end) break;
        ext = end + 1;
    }
    return false;
}
const char *GetDirectoryPath(const char *path)
{
    static char b[4096]; const char *p = strrchr(path, '/'); size_t n;
    if (!p) return ".";
    n = (size_t)(p - path); if (!n) return "/"; if (n >= sizeof b) n = sizeof b - 1;
    memcpy(b, path, n); b[n] = 0; return b;
}
const char *TextFormat(const char *fmt, ...)
{
    static char b[4096]; va_list args;
    va_start(args, fmt); vsnprintf(b, sizeof b, fmt, args); va_end(args); return b;
}
