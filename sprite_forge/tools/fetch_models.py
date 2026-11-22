#!/usr/bin/env python3
"""Download the models in sforge/models/registry.json into a folder (default sforge/models).

    python tools/fetch_models.py [--dir DIR] [ids ...]
"""
import argparse, io, json, os, sys, urllib.request, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(HERE, "..", "sforge", "models", "registry.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(HERE, "..", "sforge", "models"))
    ap.add_argument("ids", nargs="*")
    a = ap.parse_args()
    reg = json.load(open(REG))["models"]
    for rid, m in reg.items():
        if a.ids and rid not in a.ids:
            continue
        dst = os.path.join(a.dir, m["file"])
        if os.path.isfile(dst):
            print("  have", rid); continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if "zip" in m:
            data = urllib.request.urlopen(m["zip"]).read()
            zipfile.ZipFile(io.BytesIO(data)).extractall(a.dir)
        else:
            urllib.request.urlretrieve(m["url"], dst)
        print("  got ", rid, "(%s)" % m["licence"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
