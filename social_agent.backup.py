# ===== BEGIN social_agent.py =====
import os, json, random, time, sys
from pathlib import Path
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---- Config from env
ENV = os.environ
REF_LINK     = ENV.get("REF_LINK", "").strip()
MIN_WAIT     = int(ENV.get("MIN_WAIT", "180"))
MAX_WAIT     = int(ENV.get("MAX_WAIT", "480"))
LINK_RATE    = float(ENV.get("LINK_RATE", "0.12"))
IMAGE_RATE   = float(ENV.get("IMAGE_RATE", "0.08"))
VIDEO_RATE   = float(ENV.get("VIDEO_RATE", "0.10"))
MEDIA_MIN_GAP= int(ENV.get("MEDIA_MIN_GAP_MIN", "45"))

BASE      = Path.home() / "social_agent"
MEDIA_IMG = BASE / "media" / "images"
MEDIA_VID = BASE / "media" / "videos"
LOG_FILE  = BASE / "activity_log.txt"
USED_JSON = BASE / "used_posts.json"
PROFILE   = BASE / "chrome_profile"

for d in [BASE, MEDIA_IMG, MEDIA_VID]:
    d.mkdir(parents=True, exist_ok=True)

# ---- Content bank (edit freely)
POST_TEMPLATES = [
    "🔍 Discovering how AI browsers can save hours every day. Legit next level. {link} #AITools #automation #CometBrowser",
    "Just automated a chunk of my workflow using Perplexity + Comet. Wild how fast this stacks. {link} #automation #AI",
    "Found a clean combo for daily research + tasks: ChatGPT + Perplexity + Comet. Game changer. {link}",
    "Hype is cool, but tools that save time matter more. Browsers + AI agents are underrated. {link}",
]
HASHTAGS = ["#AI","#automation","#Perplexity","#CometBrowser","#Productivity","#AITools"]

def _append_log(msg: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")

def _load_used() -> set:
    if USED_JSON.exists():
        try:
            return set(json.loads(USED_JSON.read_text()))
        except Exception:
            pass
    return set()

def _save_used(s: set):
    USED_JSON.write_text(json.dumps(sorted(list(s)), ensure_ascii=False, indent=0))

def _pick_post(used: set) -> str:
    # simple no-repeat picker
    choices = [p for p in POST_TEMPLATES if p not in used] or POST_TEMPLATES
    return random.choice(choices)

def _human_wait(min_s: int, max_s: int):
    wait = random.randint(min_s, max_s)
    _append_log(f"Waiting {wait//60}m {wait%60}s before next cycle…")
    time.sleep(wait)

def _recent_media_allowed(last_path: Path) -> bool:
    if not last_path.exists(): return True
    try:
        ts = datetime.fromtimestamp(last_path.stat().st_mtime)
        return (datetime.now() - ts) >= timedelta(minutes=MEDIA_MIN_GAP)
    except Exception:
        return True

def _most_recent_file(folder: Path, exts: tuple[str,...]) -> Path | None:
    files = sorted([p for p in folder.glob("*") if p.suffix.lower() in exts], key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def _goto_home(page):
    try:
        page.goto("https://x.com/home", timeout=30000)
        page.wait_for_selector("[data-testid='primaryColumn']", timeout=20000)
    except Exception:
        pass

def _close_center_modals(page):
    # close any center dialog/modal that can steal focus
    try:
        page.keyboard.press("Escape")
        page.wait_for_selector("div[role='dialog']", state="detached", timeout=2000)
    except Exception:
        pass

def _composer_box(page):
    # prefer inline composer in the primary column
    _close_center_modals(page)
    _goto_home(page)
    composer = (
        page.locator("div[role='textbox']")
            .filter(has=page.locator("[data-testid='primaryColumn']"))
            .filter(has_not=page.locator("div[role='dialog']"))
            .first
    )
    composer.wait_for(state="visible", timeout=7000)
    return composer

def _type_text(node, text: str):
    node.click()
    node.press("Control+A") if sys.platform != "darwin" else node.press("Meta+A")
    node.press("Delete")
    node.type(text, delay=random.randint(5,20))  # human-ish

def _click_post(page):
    # try new + old selectors
    for sel in ["[data-testid='tweetButtonInline']", "div[data-testid='tweetButton'] button", "button:has-text('Post')"]:
        try:
            page.locator(sel).click(timeout=4000)
            return True
        except Exception:
            continue
    return False

def _attach_media_if_any(page) -> bool:
    attached = False
    # decide whether to attach
    roll = random.random()
    want_video = roll < VIDEO_RATE
    want_image = not want_video and (roll < (VIDEO_RATE + IMAGE_RATE))

    if want_video:
        vid = _most_recent_file(MEDIA_VID, (".mp4",".mov",".webm"))
        if vid and _recent_media_allowed(vid):
            try:
                page.locator("input[type='file']").set_input_files(str(vid))
                attached = True
            except Exception:
                pass
    elif want_image:
        img = _most_recent_file(MEDIA_IMG, (".png",".jpg",".jpeg",".webp"))
        if img and _recent_media_allowed(img):
            try:
                page.locator("input[type='file']").set_input_files(str(img))
                attached = True
            except Exception:
                pass
    return attached

def _maybe_generate_media():
    """Auto-generate media once in a while IF folders are empty and Replicate is configured."""
    from media_generate import generate_image, generate_video  # lazy import
    try:
        if not any(MEDIA_IMG.iterdir()):
            generate_image("clean tech banner about AI browsers + automation, subtle gradients, sharp typography")
        if not any(MEDIA_VID.iterdir()):
            generate_video("minimal looped tech animation about AI browsers & automation, tasteful, 5-8s")
    except Exception:
        pass

def main_loop():
    used = _load_used()

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=False,
            args=["--disable-notifications"],
        )
        page = ctx.new_page()

        _append_log("Launching Social Agent (persistent Chrome profile)…")
        _goto_home(page)
        _append_log("Logged in via saved session (if you had to log in once, leave this window open).")

        while True:
            try:
                # Generate media if folders are empty and you have Replicate set
                _maybe_generate_media()

                # Build post
                body = _pick_post(used)
                if REF_LINK and random.random() < LINK_RATE:
                    body = body.replace("{link}", REF_LINK)
                else:
                    body = body.replace("{link}", "")

                # Hashtags (light)
                extra_tags = " ".join(random.sample(HASHTAGS, k=min(3, len(HASHTAGS))))
                body = f"{body}\n{extra_tags}".strip()

                # Get composer
                composer = _composer_box(page)
                _append_log("Composing a new post…")
                _type_text(composer, body)

                # Attach media sometimes
                _attach_media_if_any(page)

                # Post
                if not _click_post(page):
                    raise RuntimeError("Post button not found/click failed")

                used.add(body)
                _save_used(used)
                _append_log("Posted. ✅")

                # wait human-like
                _human_wait(MIN_WAIT, MAX_WAIT)

            except PWTimeout:
                _append_log("Composer not found (modal?). If a center pop-up is open, close it once.")
                _close_center_modals(page)
                _human_wait(60, 120)

            except KeyboardInterrupt:
                _append_log("Stopped by user.")
                break

            except Exception as e:
                _append_log(f"Post failed: {type(e).__name__}: {e}; will retry next cycle.")
                _human_wait(90, 180)

        ctx.close()

if __name__ == "__main__":
    main_loop()
# ===== END social_agent.py =====

