#include "motion_cache.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static MMDatabase source, loaded;
static void corrupt(const char *path, long pos)
{
    FILE *f = fopen(path, "r+b"); int c;
    assert(f && fseek(f, pos, SEEK_SET) == 0);
    c = fgetc(f); assert(c != EOF);
    assert(fseek(f, pos, SEEK_SET) == 0 && fputc(c ^ 0x40, f) != EOF);
    assert(fclose(f) == 0);
}
int main(int argc, char **argv)
{
    const char *model, *cache, *other, *model_alias; float a[MM_DIMS] = {0}, b[MM_DIMS] = {0};
    FILE *f;
    assert(argc == 5); model = argv[1]; cache = argv[2]; other = argv[3]; model_alias = argv[4];
    f = fopen(model, "wb"); assert(f); assert(fwrite("model", 1, 5, f) == 5); assert(!fclose(f));
    f = fopen(other, "wb"); assert(f); assert(fwrite("other", 1, 5, f) == 5); assert(!fclose(f));
    mm_init(&source); b[1] = 2; b[4] = -1;
    assert(mm_add(&source, 3, .5f, a)); assert(mm_add(&source, 4, 1.25f, b)); assert(mm_finalize(&source));
    assert(!mm_cache_save(model, model, 0x050500, &source));
    assert(!mm_cache_save(model_alias, model, 0x050500, &source));
    assert(mm_cache_save(cache, model, 0x050500, &source));
    assert(mm_cache_load(cache, model, 0x050500, &loaded));
    assert(loaded.count == source.count && loaded.rows[1].clip == 4 && loaded.rows[1].time == 1.25f);
    assert(memcmp(loaded.rows[1].feature, source.rows[1].feature, MM_DIMS * sizeof(float)) == 0);
    assert(mm_search(&loaded, 4, b) == mm_search(&source, 4, b));
    assert(!mm_cache_load(cache, other, 0x050500, &loaded) && loaded.count == 0 && !loaded.ready);
    assert(!mm_cache_load(cache, model, 0x060000, &loaded));
    corrupt(cache, 8); /* unsupported schema */
    assert(!mm_cache_load(cache, model, 0x050500, &loaded));
    assert(mm_cache_save(cache, model, 0x050500, &source));
    corrupt(cache, 40 + 8); /* changed feature, checksum catches it */
    assert(!mm_cache_load(cache, model, 0x050500, &loaded));
    assert(mm_cache_save(cache, model, 0x050500, &source));
    f = fopen(cache, "ab"); assert(f && fputc(0, f) != EOF && !fclose(f));
    assert(!mm_cache_load(cache, model, 0x050500, &loaded));
    f = fopen(cache, "wb"); assert(f && fwrite("bad", 1, 3, f) == 3 && !fclose(f));
    assert(!mm_cache_load(cache, model, 0x050500, &loaded));
    puts("motion cache tests passed"); return 0;
}
