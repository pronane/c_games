#include "motion_cache.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static MMDatabase source, loaded;
static AMDatabase actions, loadedActions;
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
    { GAActionMeta m = {5, 8, GA_LIMB_HAND_L, .1f, 1.f, .6f, 1.f};
      ga_action_db_init(&actions); assert(ga_action_add(&actions, &m, .2f, b)); assert(am_finalize(&actions)); }
    assert(!mm_cache_save(model, model, 0x050500, &source, &actions));
    assert(!mm_cache_save(model_alias, model, 0x050500, &source, &actions));
    assert(mm_cache_save(cache, model, 0x050500, &source, &actions));
    assert(mm_cache_load(cache, model, 0x050500, &loaded, &loadedActions));
    assert(loadedActions.count == 1 && loadedActions.rows[0].action == 5 &&
           loadedActions.rows[0].category == GA_LIMB_HAND_L && loadedActions.rows[0].feature[23] > .39f);
    assert(loaded.count == source.count && loaded.rows[1].clip == 4 && loaded.rows[1].time == 1.25f);
    assert(memcmp(loaded.rows[1].feature, source.rows[1].feature, MM_DIMS * sizeof(float)) == 0);
    assert(mm_search(&loaded, 4, b) == mm_search(&source, 4, b));
    assert(!mm_cache_load(cache, other, 0x050500, &loaded, &loadedActions) && loaded.count == 0 && !loaded.ready);
    assert(!mm_cache_load(cache, model, 0x060000, &loaded, &loadedActions));
    corrupt(cache, 8); /* unsupported schema */
    assert(!mm_cache_load(cache, model, 0x050500, &loaded, &loadedActions));
    assert(mm_cache_save(cache, model, 0x050500, &source, &actions));
    corrupt(cache, 40 + 8); /* changed feature, checksum catches it */
    assert(!mm_cache_load(cache, model, 0x050500, &loaded, &loadedActions));
    assert(mm_cache_save(cache, model, 0x050500, &source, &actions));
    corrupt(cache, 40 + 2*40 + 20); /* action pose corruption */
    assert(!mm_cache_load(cache, model, 0x050500, &loaded, &loadedActions));
    assert(mm_cache_save(cache, model, 0x050500, &source, &actions));
    f = fopen(cache, "ab"); assert(f && fputc(0, f) != EOF && !fclose(f));
    assert(!mm_cache_load(cache, model, 0x050500, &loaded, &loadedActions));
    f = fopen(cache, "wb"); assert(f && fwrite("bad", 1, 3, f) == 3 && !fclose(f));
    assert(!mm_cache_load(cache, model, 0x050500, &loaded, &loadedActions));
    puts("motion cache tests passed"); return 0;
}
