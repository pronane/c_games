#!/usr/bin/env python3
"""Download a textured, animated GLB character into the game's model folder.

The source model is Khronos glTF Sample Asset "Fox". Its Run animation is
included, and its embedded texture uses TEXCOORD_0 UV coordinates. The model
is a stylized fox rather than a human footballer.

The model is CC0. Rigging/animation and the glTF conversion are CC BY 4.0;
the script writes the required attribution beside the downloaded model.
"""

import json
import os
import struct
import sys
import urllib.error
import urllib.request
from pathlib import Path


REPOSITORY_COMMIT = "15cd02d304e54cb42a4db4eefe719f76190f4b68"
ASSET_URL = (
    "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/"
    + REPOSITORY_COMMIT
    + "/Models/Fox/glTF-Binary/Fox.glb"
)
MAX_ASSET_BYTES = 32 * 1024 * 1024
JSON_CHUNK_TYPE = 0x4E4F534A
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = PROJECT_ROOT / "assets" / "models" / "player_model.glb"
LICENSE_PATH = OUTPUT_PATH.with_name("player_model.LICENSE.txt")

ATTRIBUTION = """\
Asset: Fox, Khronos glTF Sample Asset
Source: https://github.com/KhronosGroup/glTF-Sample-Assets/tree/15cd02d304e54cb42a4db4eefe719f76190f4b68/Models/Fox
Model: PixelMannen, CC0 1.0 Universal
Rigging and animation: tomkranis, CC BY 4.0
glTF conversion: AsoboStudio and scurest, CC BY 4.0
CC BY 4.0 license: https://creativecommons.org/licenses/by/4.0/

Downloaded by download_assets.py. The animation clips are ordered with Run
first so the game's current first-clip animation playback uses the run cycle.
Mesh, skin, and texture data are unchanged.
"""


def read_glb_json(data):
    if len(data) < 20:
        raise ValueError("Downloaded file is too short to be a GLB.")

    magic, version, declared_size = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2:
        raise ValueError("Downloaded asset is not a glTF 2.0 binary (.glb).")
    if declared_size != len(data):
        raise ValueError("GLB file size does not match its header.")

    offset = 12
    while offset + 8 <= len(data):
        chunk_size, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk_end = offset + chunk_size
        if chunk_end > len(data):
            raise ValueError("GLB contains a truncated data chunk.")
        if chunk_type == JSON_CHUNK_TYPE:
            try:
                return json.loads(data[offset:chunk_end].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("GLB contains invalid JSON metadata.") from error
        offset = chunk_end

    raise ValueError("GLB does not contain a JSON metadata chunk.")


def validate_character(data):
    document = read_glb_json(data)

    animations = document.get("animations", [])
    if not any(animation.get("name", "").lower() == "run"
               for animation in animations):
        raise ValueError("GLB has no animation track named 'Run'.")
    if not document.get("skins"):
        raise ValueError("GLB does not contain a skinned character.")
    if not document.get("textures") or not document.get("images"):
        raise ValueError("GLB does not contain a texture image.")
    if not any(
        image.get("bufferView") is not None or image.get("uri", "").startswith("data:")
        for image in document["images"]
    ):
        raise ValueError("GLB texture image is not embedded in the file.")

    has_uvs = any(
        "TEXCOORD_0" in primitive.get("attributes", {})
        for mesh in document.get("meshes", [])
        for primitive in mesh.get("primitives", [])
    )
    if not has_uvs:
        raise ValueError("GLB has no TEXCOORD_0 UV mapping.")

    has_base_color_texture = any(
        material.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        for material in document.get("materials", [])
    )
    if not has_base_color_texture:
        raise ValueError("GLB has no PBR base-color texture material.")


def put_run_animation_first(data):
    document = read_glb_json(data)
    animations = document.get("animations", [])
    run_index = next(
        index for index, animation in enumerate(animations)
        if animation.get("name", "").lower() == "run"
    )
    if run_index == 0:
        return data

    json_chunk_size, json_chunk_type = struct.unpack_from("<II", data, 12)
    if json_chunk_type != JSON_CHUNK_TYPE:
        raise ValueError("GLB JSON metadata is not the first data chunk.")
    old_json_end = 20 + json_chunk_size
    document["animations"] = (
        [animations[run_index]]
        + animations[:run_index]
        + animations[run_index + 1:]
    )
    json_chunk = json.dumps(
        document, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    json_chunk += b" " * (-len(json_chunk) % 4)
    chunks = struct.pack("<II", len(json_chunk), JSON_CHUNK_TYPE)
    chunks += json_chunk + data[old_json_end:]
    return struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks


def download_asset():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = OUTPUT_PATH.with_name(OUTPUT_PATH.name + ".download")
    request = urllib.request.Request(
        ASSET_URL,
        headers={"User-Agent": "GaelicFootballAssetSetup/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_ASSET_BYTES:
                raise ValueError("Asset exceeds the 32 MiB download limit.")
            total_size = 0
            with temporary_path.open("wb") as output:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    total_size += len(block)
                    if total_size > MAX_ASSET_BYTES:
                        raise ValueError("Asset exceeds the 32 MiB download limit.")
                    output.write(block)

        data = temporary_path.read_bytes()
        validate_character(data)
        data = put_run_animation_first(data)
        validate_character(data)
        if read_glb_json(data)["animations"][0].get("name", "").lower() != "run":
            raise ValueError("Could not make the Run animation the default clip.")
        temporary_path.write_bytes(data)
        os.replace(temporary_path, OUTPUT_PATH)
        LICENSE_PATH.write_text(ATTRIBUTION, encoding="utf-8")
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    print("Downloaded and verified the animated character:")
    print("  {}".format(OUTPUT_PATH))
    print("Attribution saved to:")
    print("  {}".format(LICENSE_PATH))
    print("Note: the selected character is a stylized fox, not a human footballer.")


if __name__ == "__main__":
    try:
        download_asset()
    except (OSError, ValueError, urllib.error.URLError) as error:
        print("Asset download failed: {}".format(error), file=sys.stderr)
        sys.exit(1)
