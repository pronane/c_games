"""Repack already-captured frames for bounded annotation transport; never advances a game."""
from io import BytesIO
from pathlib import Path
import sys
from PIL import Image

root = Path(sys.argv[1])
for index in (0, 6, 12, 18, 24, 30):
    source = root / f"frame-{index:03d}.png"
    with Image.open(source) as original:
        data = b""
        for width, quality in ((480, 35), (400, 25), (320, 15)):
            frame = original.convert("RGB")
            frame.thumbnail((width, width))
            output = BytesIO()
            frame.save(output, format="JPEG", quality=quality)
            data = output.getvalue()
            if len(data) <= 10000:
                break
        if len(data) > 10000:
            raise RuntimeError(f"Preview size budget exceeded: {source}")
        (root / f"preview-{index:03d}.jpg").write_bytes(data)
        print(f"{source.name}: {len(data)} preview bytes")
