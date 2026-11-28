"""Meshy API client (v11.41): text / image to 3D, rigging, animation and Text to Motion.

The same calls the Meshy MCP server (`@meshy-ai/meshy-mcp-server`) makes, without needing that server: Sprite Forge
talks to https://api.meshy.ai directly, so it works from the CLI, the Studio and a cloud session alike.

Key: the MESHY_API_KEY environment variable, or the first line of ~/.config/meshy/key (chmod 600). Never put the key
in the repo, a pack or a build folder.

Credits (Meshy's pricing page, Nov 2026): Text to Motion 3 (swift, BVH) or 10 (prime, FBX); rigging 5; animation 3
per action; text / image to 3D 20 mesh-only, 30 textured; refine 10. Status checks, the animation library and the
balance are free. Results are kept by Meshy for 3 days: download them straight away (this module does).

Ownership: paid-plan output belongs to the account holder; free-plan output is CC BY 4.0 (see LIBRARY_LICENSING.md).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

BASE = "https://api.meshy.ai"
DONE = ("SUCCEEDED", "FAILED", "CANCELED")
COST = {"motion_swift": 3, "motion_prime": 10, "rig": 5, "animate": 3, "mesh": 20, "textured": 30, "refine": 10}
KEY_FILE = os.path.join(os.path.expanduser("~"), ".config", "meshy", "key")


class MeshyError(RuntimeError):
    pass


def api_key(required=True):
    k = os.environ.get("MESHY_API_KEY", "").strip()
    if not k and os.path.isfile(KEY_FILE):
        with open(KEY_FILE, encoding="utf-8") as f:
            k = f.readline().strip()
    if not k and required:
        raise MeshyError("no Meshy API key: set MESHY_API_KEY or write it to %s" % KEY_FILE)
    return k


class Client:
    """Thin REST client. `transport(method, url, body, headers) -> (status, bytes)` can be swapped for tests."""

    def __init__(self, key=None, base=BASE, transport=None, poll_s=5.0, sleep=time.sleep):
        self.key = key if key is not None else api_key()
        self.base = base.rstrip("/")
        self.transport = transport or _urllib_transport
        self.poll_s = poll_s
        self.sleep = sleep

    # -- plumbing ---------------------------------------------------------------------------------------
    def call(self, method, path, body=None):
        hdr = {"Authorization": "Bearer " + self.key, "Content-Type": "application/json"}
        status, data = self.transport(method, self.base + path, json.dumps(body).encode() if body is not None else None, hdr)
        if status >= 400:
            msg = data.decode("utf-8", "replace")[:300]
            hint = {401: "the API key is wrong", 402: "not enough credits, or a free plan", 429: "rate limited - try later"}.get(status, "")
            raise MeshyError("Meshy %s %s -> %d %s %s" % (method, path, status, hint, msg))
        return json.loads(data or b"{}")

    def wait(self, kind, task_id, log=None, timeout_s=1800):
        t0 = time.time()
        last = None
        while True:
            t = self.call("GET", "%s/%s" % (kind, task_id))
            if log and (t.get("status"), t.get("progress")) != last:
                last = (t.get("status"), t.get("progress"))
                log("  %s %s %s%%" % (task_id[:8], t.get("status"), t.get("progress")))
            if t.get("status") in DONE:
                if t["status"] != "SUCCEEDED":
                    raise MeshyError("task %s %s: %s" % (task_id, t["status"], t.get("task_error")))
                return t
            if time.time() - t0 > timeout_s:
                raise MeshyError("task %s still %s after %ds" % (task_id, t.get("status"), timeout_s))
            self.sleep(self.poll_s)

    def download(self, url, dst):
        status, data = self.transport("GET", url, None, {})
        if status >= 400:
            raise MeshyError("download %d: %s" % (status, url[:80]))
        os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(data)
        return dst

    # -- free -------------------------------------------------------------------------------------------
    def balance(self):
        return self.call("GET", "/openapi/v1/balance")

    def animation_library(self, search=None, page_size=100):
        out, page = [], 1
        while True:
            q = "?page_size=%d&page_num=%d" % (page_size, page) + ("&search=" + urllib.request.quote(search) if search else "")
            items = self.call("GET", "/openapi/v1/animations/library" + q)
            if isinstance(items, dict):
                items = items.get("result") or items.get("data") or []
            out += items
            if len(items) < page_size:
                return out
            page += 1

    # -- paid -------------------------------------------------------------------------------------------
    def text_to_motion(self, prompt, duration, mode="swift", log=None):
        if not 2 <= duration <= 10 or abs(duration * 2 - round(duration * 2)) > 1e-6:
            raise MeshyError("duration must be 2-10 s in 0.5 s steps, got %s" % duration)
        if len(prompt) > 400:
            raise MeshyError("motion prompt is %d characters; Meshy allows 400" % len(prompt))
        tid = self.call("POST", "/openapi/v1/text-to-motion", {"prompt": prompt, "mode": mode, "duration": duration})["result"]
        return self.wait("/openapi/v1/text-to-motion", tid, log)

    def text_to_3d(self, prompt, texture_prompt=None, pose_mode="t-pose", log=None, **extra):
        p = "/openapi/v2/text-to-3d"
        pre = dict(mode="preview", prompt=prompt, ai_model="latest", pose_mode=pose_mode, target_formats=["glb", "fbx"], **extra)
        pid = self.call("POST", p, pre)["result"]
        self.wait(p, pid, log)
        ref = dict(mode="refine", preview_task_id=pid, enable_pbr=True, target_formats=["glb", "fbx"])
        if texture_prompt:
            ref["texture_prompt"] = texture_prompt
        rid = self.call("POST", p, ref)["result"]
        return self.wait(p, rid, log)

    def image_to_3d(self, image_url, pose_mode="t-pose", log=None, **extra):
        p = "/openapi/v1/image-to-3d"
        body = dict(image_url=image_url, pose_mode=pose_mode, should_texture=True, enable_pbr=True,
                    target_formats=["glb", "fbx"], **extra)
        return self.wait(p, self.call("POST", p, body)["result"], log)

    def rig(self, input_task_id=None, model_url=None, height_m=1.8, skeleton="mixamo", log=None):
        body = dict(height_meters=height_m, skeleton_template=skeleton, animation_type="biped")
        body["input_task_id" if input_task_id else "model_url"] = input_task_id or model_url
        p = "/openapi/v1/rigging"
        return self.wait(p, self.call("POST", p, body)["result"], log)

    def animate(self, rig_task_id, action_id=None, motion_task_id=None, fps=30, log=None):
        body = dict(rig_task_id=rig_task_id, post_process=dict(operation_type="change_fps", fps=fps))
        if motion_task_id:
            body["motion_task_id"] = motion_task_id
        else:
            body["action_id"] = int(action_id)
        p = "/openapi/v1/animations"
        return self.wait(p, self.call("POST", p, body)["result"], log)


def _urllib_transport(method, url, body, headers):
    r = urllib.request.Request(url, method=method, data=body, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=120) as f:
            return f.status, f.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
