import os, json, argparse, pathlib, sys

def moviepy_fallback(topic: str, out_path: str) -> bool:
    try:
        from moviepy.editor import TextClip, ColorClip, CompositeVideoClip
        bg  = ColorClip(size=(1280,720), color=(18,18,18), duration=5)
        txt = TextClip(f"{topic}", fontsize=48, color="white").set_duration(5).set_position("center")
        CompositeVideoClip([bg, txt]).write_videofile(out_path, fps=24, codec="libx264",
                                                      audio=False, verbose=False, logger=None)
        return True
    except Exception as e:
        print(f"[video_gen] moviepy fallback failed: {e}", file=sys.stderr)
        return False

def resolve_model_version(model_env: str, version_env: str) -> str | None:
    """
    If VERSION is provided -> return it.
    Else if MODEL is provided -> look up latest version via Replicate SDK and return 'model:version_id'.
    Else -> None.
    """
    ver = os.getenv(version_env)
    if ver:
        return ver
    model = os.getenv(model_env)
    if not model:
        return None
    try:
        import replicate
        client = replicate.Client(api_token=os.getenv("REPLICATE_API_TOKEN"))
        m = client.models.get(model)
        versions = list(m.versions.list())
        if not versions:
            return None
        latest = versions[0].id  # latest first
        return f"{model}:{latest}"
    except Exception as e:
        print(f"[video_gen] resolve version failed: {e}", file=sys.stderr)
        return None

def replicate_veo(topic: str, out_path: str) -> bool:
    version = resolve_model_version("REPL_VEO_MODEL", "REPL_VEO_VERSION")
    if not version:
        return False
    try:
        import replicate, requests
        inputs = {"prompt": topic, "duration": 5, "fps": 24, "width": 1280, "height": 720}
        extra = os.getenv("REPL_VEO_INPUT")
        if extra:
            inputs.update(json.loads(extra))
        out = replicate.run(version, input=inputs)
        url = out if isinstance(out, str) else (out[0] if isinstance(out, (list, tuple)) else None)
        if not url:
            # some APIs return dict-like; try digging
            try:
                url = out.get("output", [None])[0]
            except Exception:
                pass
        if not url:
            return False
        import requests
        r = requests.get(url, timeout=1200); r.raise_for_status()
        p = pathlib.Path(out_path); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(r.content); return True
    except Exception as e:
        print(f"[video_gen] replicate Veo failed: {e}", file=sys.stderr)
        return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--topic", required=True)
    a = ap.parse_args()

    if replicate_veo(a.topic, a.out): return
    if moviepy_fallback(a.topic, a.out): return
    raise SystemExit("[video_gen] could not produce video")

if __name__ == "__main__":
    main()

