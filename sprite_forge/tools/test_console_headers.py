"""Compile + run a tiny C program against every generated console header: checks every tile-map entry points
inside its bank, every rect inside its page, and anim ranges inside the frame table."""
import glob, json, os, subprocess, sys
O = sys.argv[1]; bad = 0; n = 0
for cj in sorted(glob.glob(O + "/*/*/console/console.json")):
    st = json.load(open(cj)); cd = os.path.dirname(cj); hdr = st["header"]; sym = hdr[:-2]
    if st["console"] == "atari2600":
        body = 'int n=0; for (int i=0;i<(int)(sizeof %s_frame_offset/2);i++) if (%s_frame_offset[i] >= sizeof %s_gfx) return 1; n += sizeof %s_colours; printf("%%d rows ok\\n", n);' % ((sym,) * 4)
    elif "banks" in st:
        nf = sum(a["count"] for a in st["anims"])
        body = '''int sprites = 0;
  for (int i = 0; i < %d; i++) { const SFTFrame *f = &%s_frames[i];
    for (int c = 0; c < f->tw * f->th; c++) { uint16_t e = %s_maps[f->map + c]; if (e == SFT_EMPTY) continue;
      if (SFT_TILE(e) >= %s_banks[f->bank].count) { printf("bad tile %%d frame %%d\\n", SFT_TILE(e), i); return 1; } sprites++; } }
  for (int a = 0; a < %d; a++) if (%s_anims[a].first + %s_anims[a].count > %d) return 2;
  printf("%%d frames, %%d hardware sprites total, palette[1]=0x%%X ok\\n", %d, sprites, (unsigned)%s_palette[1]);''' % (
            nf, sym, sym, sym, len(st["anims"]), sym, sym, nf, nf, sym)
    else:
        nf = len(st["rects"])
        body = '''for (int i = 0; i < %d; i++) { const SFTRect *r = &%s_rects[i]; if (r->w == 0 || r->page >= %d) return 1; }
  for (int a = 0; a < %d; a++) if (%s_anims[a].first + %s_anims[a].count > %d) return 2;
  printf("%%d rects ok\\n", %d);''' % (nf, sym, st["pages"], len(st["anims"]), sym, sym, nf, nf)
    src = '#include <stdio.h>\n#include "%s"\nint main(void) {\n  %s\n  return 0; }\n' % (hdr, body)
    c = "/tmp/sft_test.c"; open(c, "w").write(src)
    r = subprocess.run(["gcc", "-std=c99", "-Wall", "-Wno-unused-const-variable", "-Wno-unused-variable", "-I", cd, c, "-o", "/tmp/sft_test"], capture_output=True, text=True)
    ok = r.returncode == 0
    out = subprocess.run(["/tmp/sft_test"], capture_output=True, text=True) if ok else None
    ok = ok and out.returncode == 0
    n += 1; bad += not ok
    print("%s %-60s %s" % ("PASS" if ok else "FAIL", os.path.relpath(cd, O), (out.stdout.strip() if out else r.stderr[:300])))
print("RESULT: %s (%d headers, %d failed)" % ("PASS" if not bad else "FAIL", n, bad))
