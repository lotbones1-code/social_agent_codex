# ===== BEGIN media_generate.py =====
"""
Optional helper for Replicate image/video generation.

Env vars:
  REPLICATE_API_TOKEN
  REPLICATE_IMAGE_MODEL
  REPLICATE_VIDEO_MODEL

Outputs:
  media/images/*.png
  media/videos/*.mp4

If not configured, functions just return None.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

import requests

BASE = Path(__file__).resolve().parent
MEDIA = BASE / "media"
IMG_DIR = MEDIA / "images"
VID_DIR = MEDIA / "videos"
for d in (MEDIA, IMG_DIR, VID_DIR):
    d.mkdir(parents=True, exist_ok=True)

API = "https://api.replicate.com/v1/predictions"
TOKEN = os.getenv("REPLICATE_API_TOKEN", "").strip()
IMG_MODEL = os.getenv("REPLICATE_IMAGE_MODEL", "").strip()
VID_MODEL = os.getenv("REPLICATE_VIDEO_MODEL", "").strip()

HDRS = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json",
}


def _slug(s: str) -> str:
    s = "".join(c for c in s if c.isalnum() or c in " _-")[:60]
    return s.strip().replace(" ", "_").lower() or "media"


def _start(model: str, payload: dict) -> Optional[str]:
    if not TOKEN or not model:
        return None
    r = requests.post(API, headers=HDRS, data=json.dumps({"model": model, "input": payload}), timeout=30)
    r.raise_for_status()
    return r.json().get("id")


def _poll(pred_id: str, timeout: int = 900) -> Optional[str]:
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = requests.get(f"{API}/{pred_id}", headers=HDRS, timeout=15)
        r.raise_for_status()
        js = r.json()
        status = js.get("status")
        if status in ("failed", "canceled"):
            return None
        if status == "succeeded":
            out = js.get("output")
            if isinstance(out, list) and out:
                return out[-1]
            if isinstance(out, str):
                return out
            return None
        time.sleep(5)
    return None


def _download(url: str, out_path: Path) -> Optional[Path]:
    if not url:
        return None
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with out_path.open("wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
    return out_path


def generate_image(prompt: str) -> Optional[Path]:
    if not (TOKEN and IMG_MODEL and prompt):
        return None
    pred_id = _start(IMG_MODEL, {"prompt": prompt})
    if not pred_id:
        return None
    url = _poll(pred_id)
    if not url:
        return None
    out = IMG_DIR / f"{_slug(prompt)}.png"
    return _download(url, out)


def generate_video(prompt: str) -> Optional[Path]:
    if not (TOKEN and VID_MODEL and prompt):
        return None
    pred_id = _start(VID_MODEL, {"prompt": prompt})
    if not pred_id:
        return None
    url = _poll(pred_id, timeout=1800)
    if not url:
        return None
    out = VID_DIR / f"{_slug(prompt)}.mp4"
    return _download(url, out)


# ===== END media_generate.py =====

