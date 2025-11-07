import os, json, argparse, pathlib, sys, base64

def b64_write_png(out_path: str):
    raw = (b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAuMBg3p8r/0A'
           b'AAAASUVORK5CYII=')
    p = pathlib.Path(out_path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(base64.b64decode(raw)); return True

def pillow_fallback(topic: str, out_path: str):
    try:
        from PIL import Image, ImageDraw
        im = Image.new("RGB",(1024,1024),(18,18,18))
        d  = ImageDraw.Draw(im)
        d.text((40,40), "AI Image", fill=(240,240,240))
        d.text((40,100), topic[:120], fill=(200,200,200))
        im.save(out_path); return True
    except Exception:
        return False

def resolve_model_version(model_env: str, version_env: str) -> str | None:
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
        latest = versions[0].id
        return f"{model}:{latest}"
    except Exception as e:
        print(f"[image_gen] resolve version failed: {e}", file=sys.stderr)
        return None

def replicate_image(topic: str, out_path: str) -> bool:
    version = resolve_model_version("REPL_IMAGE_MODEL", "REPL_IMAGE_VERSION")
    if not version:
        return False
    try:
        import replicate, requests
        inputs = {"prompt": topic}
        extra = os.getenv("REPL_IMAGE_INPUT")
        if extra:
            inputs.update(json.loads(extra))
        out = replicate.run(version, input=inputs)
        url = out if isinstance(out, str) else (out[0] if isinstance(out, (list,tuple)) else None)
        if not url:
            try:
                url = out.get("output", [None])[0]
            except Exception:
                pass
        if not url:
            return False
        r = requests.get(url, timeout=600); r.raise_for_status()
        p = pathlib.Path(out_path); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(r.content); return True
    except Exception as e:
        print(f"[image_gen] replicate failed: {e}", file=sys.stderr)
        return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--topic", required=True)
    a = ap.parse_args()

    if replicate_image(a.topic, a.out): return
    if pillow_fallback(a.topic, a.out): return
    if b64_write_png(a.out): return
    raise SystemExit("[image_gen] could not produce image")

if __name__ == "__main__":
    main()

