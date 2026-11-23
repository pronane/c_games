#include "motion_cache.h"
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <float.h>
#include <math.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <stdlib.h>
#endif

#define CACHE_VERSION 1u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)
static const unsigned char magic[8] = {'G','F','M','O','T','I','O','N'};

static uint64_t hash_bytes(uint64_t h, const unsigned char *p, size_t n)
{ while (n--) { h ^= *p++; h *= FNV_PRIME; } return h; }
static int model_hash(const char *path, uint64_t *hash)
{
    unsigned char b[8192]; size_t n; FILE *f;
    if (!path || !hash || !(f = fopen(path, "rb"))) return 0;
    *hash = FNV_OFFSET;
    while ((n = fread(b, 1, sizeof b, f)) > 0) *hash = hash_bytes(*hash, b, n);
    if (ferror(f)) { fclose(f); return 0; }
    return fclose(f) == 0;
}
static void put32(unsigned char *p, uint32_t x)
{ int i; for (i = 0; i < 4; ++i) p[i] = (unsigned char)(x >> (8*i)); }
static void put64(unsigned char *p, uint64_t x)
{ int i; for (i = 0; i < 8; ++i) p[i] = (unsigned char)(x >> (8*i)); }
static uint32_t get32(const unsigned char *p)
{ return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24; }
static uint64_t get64(const unsigned char *p)
{ int i; uint64_t x = 0; for (i = 0; i < 8; ++i) x |= (uint64_t)p[i] << (8*i); return x; }
static void put_float(unsigned char *p, float f)
{ uint32_t u; memcpy(&u, &f, 4); put32(p, u); }
static float get_float(const unsigned char *p)
{ uint32_t u = get32(p); float f; memcpy(&f, &u, 4); return f; }
static int same_file(const char *a, const char *b)
{
    struct stat sa, sb;
    if (!strcmp(a, b)) return 1;
#ifdef _WIN32
    {
        char aa[4096], bb[4096];
        if (_fullpath(aa, a, sizeof aa) && _fullpath(bb, b, sizeof bb) && !_stricmp(aa, bb)) return 1;
    }
#endif
    return stat(a, &sa) == 0 && stat(b, &sb) == 0 && sa.st_ino != 0 &&
           sa.st_dev == sb.st_dev && sa.st_ino == sb.st_ino;
}
static int supported(void) { return sizeof(float) == 4 && FLT_RADIX == 2 && FLT_MANT_DIG == 24; }

#define HEADER_SIZE 40
#define ROW_SIZE (8 + 4*MM_DIMS)
static int encode_row(const AMRow *r, unsigned char out[ROW_SIZE])
{
    int i;
    if (r->clip < 0 || !isfinite(r->time) || r->time < 0 || r->category || r->ball || r->action) return 0;
    put32(out, (uint32_t)r->clip); put_float(out+4, r->time);
    for (i = 0; i < MM_DIMS; ++i) {
        if (!isfinite(r->feature[i])) return 0;
        put_float(out+8+4*i, r->feature[i]);
    }
    for (i = MM_DIMS; i < AM_DIMENSIONS; ++i) if (r->feature[i] != 0) return 0;
    return 1;
}

int mm_cache_save(const char *path, const char *model_path, unsigned version, const MMDatabase *db)
{
    unsigned char header[HEADER_SIZE] = {0}, row[ROW_SIZE]; uint64_t model, payload = FNV_OFFSET;
    FILE *f; int i, ok = 1;
    if (!supported() || !path || !model_path || same_file(path, model_path) || !db || !db->ready ||
        db->count <= 0 || db->count > MM_MAX_ROWS || !model_hash(model_path, &model)) return 0;
    for (i = 0; i < db->count; ++i) {
        if (!encode_row(&db->rows[i], row)) return 0;
        payload = hash_bytes(payload, row, sizeof row);
    }
    memcpy(header, magic, 8); put32(header+8, CACHE_VERSION); put32(header+12, version);
    put64(header+16, model); put32(header+24, (uint32_t)db->count); put32(header+28, MM_DIMS);
    put64(header+32, payload);
    if (!(f = fopen(path, "wb"))) return 0;
    if (fwrite(header, 1, sizeof header, f) != sizeof header) ok = 0;
    for (i = 0; ok && i < db->count; ++i) {
        if (!encode_row(&db->rows[i], row) || fwrite(row, 1, sizeof row, f) != sizeof row) ok = 0;
    }
    if (fclose(f) != 0) ok = 0;
    return ok;
}

int mm_cache_load(const char *path, const char *model_path, unsigned version, MMDatabase *db)
{
    unsigned char header[HEADER_SIZE], row[ROW_SIZE]; uint64_t model, payload = FNV_OFFSET;
    uint32_t count; int i, j, ok = 0; FILE *f;
    if (!db) return 0;
    mm_init(db);
    if (!supported() || !path || !model_hash(model_path, &model) || !(f = fopen(path, "rb"))) return 0;
    if (fread(header, 1, sizeof header, f) != sizeof header || memcmp(header, magic, 8) ||
        get32(header+8) != CACHE_VERSION || get32(header+12) != version || get64(header+16) != model ||
        get32(header+28) != MM_DIMS) goto done;
    count = get32(header+24);
    if (!count || count > MM_MAX_ROWS) goto done;
    for (i = 0; i < (int)count; ++i) {
        float feature[MM_DIMS], time; uint32_t clip;
        if (fread(row, 1, sizeof row, f) != sizeof row) goto done;
        payload = hash_bytes(payload, row, sizeof row); clip = get32(row); time = get_float(row+4);
        if (clip > INT32_MAX) goto done;
        for (j = 0; j < MM_DIMS; ++j) feature[j] = get_float(row+8+4*j);
        if (!mm_add(db, (int)clip, time, feature)) goto done;
    }
    if (payload != get64(header+32) || fgetc(f) != EOF || ferror(f) || !mm_finalize(db)) goto done;
    ok = 1;
done:
    if (fclose(f) != 0) ok = 0;
    if (!ok) mm_init(db);
    return ok;
}
