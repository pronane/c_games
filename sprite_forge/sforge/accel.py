"""Compute backend for the heavy per-frame maths (v9.3): GPU when there is one, NumPy otherwise.

    from sforge import accel
    be = accel.backend()          # SFS_DEVICE = auto (default) | cpu | cuda | cuda:1 | mps
    be.name                       # 'numpy' | 'torch:cuda' | 'torch:mps' | 'torch:cpu'

auto picks PyTorch on CUDA (NVIDIA) or MPS (Apple silicon) when torch is installed and a device is present, and
falls back to NumPy everywhere else, so the same build runs on a laptop, a gaming PC or a cloud GPU.  PyTorch is
optional (requirements-gpu.txt); nothing else changes when it is missing.

Only three kernels live here - they are what photo3d spends its time on:
  skin(P, ia, ib, w, M)          linear-blend skinning of N points by two bones each (M: (B,3,4) bone matrices)
  splat(x, y, z, rgb, a, W, H)   z-buffered point splat: the nearest point wins each pixel -> (H,W,4) uint8
  rotate(P, R)                   P @ R.T
Inputs and outputs are NumPy arrays; a torch backend moves the static point data to the device once (cache_key)
and keeps it there between frames."""
from __future__ import annotations
import os
import numpy as np


class NumpyBackend:
    name = "numpy"
    gpu = False

    def put(self, a, key=None):
        return np.asarray(a)

    def get(self, a):
        return np.asarray(a)

    def skin(self, P, ia, ib, w, M):
        """P (N,3); ia, ib (N,) bone indices; w (N,) weight of bone b; M (B,3,4) -> (N,3)"""
        Ma, Mb = M[ia], M[ib]
        pa = np.einsum("nij,nj->ni", Ma[:, :, :3], P) + Ma[:, :, 3]
        pb = np.einsum("nij,nj->ni", Mb[:, :, :3], P) + Mb[:, :, 3]
        return pa + (pb - pa) * w[:, None]

    def rotate(self, P, R):
        return P @ np.asarray(R).T

    def splat(self, x, y, z, rgb, W, H):
        """nearest point (largest z) per pixel; returns (H,W,4) uint8 with alpha 255 where covered"""
        xi = np.round(x).astype(np.int64); yi = np.round(y).astype(np.int64)
        ok = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
        xi, yi, z, rgb = xi[ok], yi[ok], z[ok], rgb[ok]
        key = yi * W + xi
        order = np.lexsort((z, key))                  # by pixel, then depth ascending
        ks = key[order]
        last = np.r_[ks[1:] != ks[:-1], True]         # the nearest point of each pixel
        sel = order[last]
        out = np.zeros((H * W, 4), np.uint8)
        out[key[sel], :3] = np.clip(rgb[sel], 0, 255).astype(np.uint8)
        out[key[sel], 3] = 255
        return out.reshape(H, W, 4)


class TorchBackend:
    gpu = True

    def __init__(self, torch, device):
        self.t = torch
        self.dev = torch.device(device)
        self.name = "torch:%s" % device
        self.gpu = self.dev.type != "cpu"
        self._cache = {}
        # MPS has no float64; float32 is plenty for screen-space maths
        self.f = torch.float32

    def put(self, a, key=None):
        if key is not None and key in self._cache:
            return self._cache[key]
        a = np.asarray(a)
        dt = self.f if a.dtype.kind == "f" else (self.t.int64 if a.dtype.kind in "iu" else None)
        v = self.t.as_tensor(a, dtype=dt, device=self.dev) if dt is not None else self.t.as_tensor(a, device=self.dev)
        if key is not None:
            self._cache[key] = v
        return v

    def get(self, a):
        return a.detach().cpu().numpy() if hasattr(a, "detach") else np.asarray(a)

    def skin(self, P, ia, ib, w, M):
        t = self.t
        P, ia, ib, w = (x if t.is_tensor(x) else self.put(x) for x in (P, ia, ib, w))
        M = self.put(np.asarray(M, np.float32))
        Ma, Mb = M[ia], M[ib]
        pa = t.einsum("nij,nj->ni", Ma[:, :, :3], P) + Ma[:, :, 3]
        pb = t.einsum("nij,nj->ni", Mb[:, :, :3], P) + Mb[:, :, 3]
        return pa + (pb - pa) * w[:, None]

    def rotate(self, P, R):
        t = self.t
        P = P if t.is_tensor(P) else self.put(P)
        return P @ self.put(np.asarray(R, np.float32)).T

    def splat(self, x, y, z, rgb, W, H):
        t = self.t
        x, y, z, rgb = (v if t.is_tensor(v) else self.put(v) for v in (x, y, z, rgb))
        xi = t.round(x).long(); yi = t.round(y).long()
        ok = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
        xi, yi, z, rgb = xi[ok], yi[ok], z[ok], rgb[ok]
        key = yi * W + xi
        # z-buffer: max depth per pixel, then the point(s) that reach it write their colour
        zbuf = t.full((H * W,), -1e30, dtype=z.dtype, device=self.dev)
        zbuf = zbuf.scatter_reduce(0, key, z, reduce="amax", include_self=True)
        win = z >= zbuf[key]
        out = t.zeros((H * W, 4), dtype=t.uint8, device=self.dev)
        out[key[win], :3] = t.clamp(rgb[win], 0, 255).to(t.uint8)
        out[key[win], 3] = 255
        return self.get(out.reshape(H, W, 4))


_BACKEND = {}


def backend(pref=None, log=None):
    """the best available backend for `pref` (default env SFS_DEVICE or 'auto'); cached per preference"""
    pref = (pref or os.environ.get("SFS_DEVICE", "auto")).strip().lower()
    if pref in _BACKEND:
        return _BACKEND[pref]
    be = None
    if pref != "cpu" and pref != "numpy":
        try:
            import torch
            dev = None
            if pref.startswith("cuda") and torch.cuda.is_available():
                dev = pref
            elif pref == "mps" and getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                dev = "mps"
            elif pref == "auto":
                if torch.cuda.is_available():
                    dev = "cuda"
                elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                    dev = "mps"
            elif pref == "torch":
                dev = "cpu"
            if dev:
                be = TorchBackend(torch, dev)
        except Exception as e:                      # torch missing / broken driver: CPU is always fine
            if log:
                log("accel: GPU backend unavailable (%s) - using NumPy" % e)
    if be is None:
        be = NumpyBackend()
    _BACKEND[pref] = be
    return be


def describe():
    """one line for `forge.py doctor`"""
    try:
        import torch
        bits = ["torch %s" % torch.__version__]
        if torch.cuda.is_available():
            bits.append("CUDA %s (%s)" % (torch.version.cuda, torch.cuda.get_device_name(0)))
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            bits.append("Apple MPS")
        if len(bits) == 1:
            bits.append("no GPU visible")
        return ", ".join(bits)
    except Exception:
        return "PyTorch not installed - NumPy CPU backend (pip install -r requirements-gpu.txt for CUDA / MPS)"
