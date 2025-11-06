# ===== media_generate.py (Replicate helper) =====
from __future__ import annotations
from pathlib import Path
import os, time, json, shutil, requests

API = "https://api.replicate.com/v1/predictions"
TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
IMG_MODEL = os.getenv("REPLICATE_IMAGE_MODEL", "")   # e.g. black-forest-labs/FLUX.1-schnell
VID_MODEL = os.getenv("REPLICATE_VIDEO_MODEL", "")   # e.g. pika-labs/pika-1-5

BASE = Path(__file__).resolve().parent
IMG_DIR = BASE / "media" / "images"
VID_DIR = BASE / "media" / "videos"
for p in (IMG_DIR, VID_DIR): p.mkdir(parents=True, exist_ok=True)

HDRS = {"Authorization": f"Token {TOKEN}", "Content-Type": "application/json"}

def _slug(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in "-_ ").strip().replace(" ", "_")[:80] or "media"

def _start(model: str, payload: dict) -> str | None:
    r = requests.post(API, headers=HDRS, data=json.dumps({"model": model, "input": payload}))
    if r.status_code >= 400: return None
    return r.json().get("id")

def _poll(pid: str, timeout = 900) -> str | None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = requests.get(f"{API}/{pid}", headers=HDRS)
        if r.status_code >= 400: return None
        j = r.json()
        st = j.get("status","")
        if st in ("succeeded", "failed", "canceled"):
            out = j.get("output","")
            # normalize: some models return a list
            if isinstance(out, list) and out: out = out[0]
            return out if st=="succeeded" and isinstance(out, str) else None
        time.sleep(3)
    return None

def _download(url: str, outpath: Path) -> Path | None:
    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(outpath, "wb") as f:
                shutil.copyfileobj(r.raw, f)
        return outpath
    except Exception:
        return None

def generate_image(prompt: str) -> Path | None:
    if not (TOKEN and IMG_MODEL): return None
    pid = _start(IMG_MODEL, {"prompt": prompt})
    if not pid: return None
    url = _poll(pid)
    if not url: return None
    return _download(url, IMG_DIR / f"{_slug(prompt)}.png")

def generate_video(prompt: str) -> Path | None:
    if not (TOKEN and VID_MODEL): return None
    pid = _start(VID_MODEL, {"prompt": prompt})
    if not pid: return None
    url = _poll(pid, timeout=1200)
    if not url: return None
    return _download(url, VID_DIR / f"{_slug(prompt)}.mp4")
# ===== END media_generate.py =====

