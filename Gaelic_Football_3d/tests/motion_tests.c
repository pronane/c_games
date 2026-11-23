#include "motion_match.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

static MMDatabase db;
int main(void)
{
    float a[MM_DIMS] = {0}, b[MM_DIMS] = {0}, bad[MM_DIMS] = {0};
    int i;
    mm_init(&db);
    assert(!mm_finalize(&db));
    assert(mm_search(&db, 1, a) == -1);
    bad[0] = NAN;
    assert(!mm_add(&db, 0, 0, bad));
    assert(!mm_add(&db, 0, -1, a));
    b[0] = 2; b[4] = 1;
    assert(mm_add(&db, 0, 0, a));
    assert(mm_add(&db, 1, .5f, b));
    assert(mm_add(&db, 1, .6f, b));
    assert(mm_finalize(&db));
    assert(mm_search(&db, 1, b) == 1); /* stable tie */
    assert(mm_search(&db, 0, b) == 0); /* hard clip filter */
    assert(mm_search(&db, 2, b) == -1);
    assert(mm_search(&db, 1, bad) == -1);
    for (i = db.count; i < MM_MAX_ROWS; ++i) assert(mm_add(&db, 0, 0, a));
    assert(!mm_add(&db, 0, 0, a));
    puts("motion matcher tests passed");
    return 0;
}
