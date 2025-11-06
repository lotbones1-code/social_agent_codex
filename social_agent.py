# ===== social_agent.py (fully integrated) =====
from __future__ import annotations
from pathlib import Path
import os, sys, json, time, random, datetime as dt
from typing import Optional
from playwright.sync_api import sync_playwright, TimeoutError as PTimeoutError

# --- paths & env ---
BASE = Path(__file__).resolve().parent
MEDIA = BASE / "media"
IMG_DIR = MEDIA / "images"
VID_DIR = MEDIA / "videos"
USED_POSTS = BASE / "used_posts.json"
COPY_BANK = BASE / "copy_bank.json"
ACTIVITY_LOG = BASE / "activity_log.txt"
PROFILE_DIR = BASE / ".chrome_profile"  # persistent profile to stay logged-in
for p in (IMG_DIR, VID_DIR): p.mkdir(parents=True, exist_ok=True)

# cadence / options (can override with .env)
REF_LINK = os.getenv("REF_LINK", "").strip()
MIN_WAIT = int(os.getenv("MIN_WAIT", "180"))      # seconds
MAX_WAIT = int(os.getenv("MAX_WAIT", "480"))      # seconds
LINK_RATE = float(os.getenv("LINK_RATE", "0.12")) # probability to include your link
IMAGE_RATE = float(os.getenv("IMAGE_RATE", "0.08"))
VIDEO_RATE = float(os.getenv("VIDEO_RATE", "0.10"))
MEDIA_MIN_GAP_MIN = int(os.getenv("MEDIA_MIN_GAP_MIN", "45"))

# media gen (Replicate) – only used if folders are empty
try:
    from media_generate import generate_image, generate_video
except Exception:
    def generate_image(_): return None
    def generate_video(_): return None

# --- content (you can edit later) ---
POST_TEMPLATES = [
    "🔍 Discovering how AI browsers can save hours every day. Legit next level.",
    "💡 Automating my routine with Comet + Perplexity. Wild productivity gains.",
    "🧩 Found a hidden gem for automation lovers — pairing AI browser + agents.",
    "⚡️ 10x output with Perplexity + Comet combo. Not hype — actual time saved.",
]
REPLY_TEMPLATES = [
    "If you're exploring AI browsers/automation, try this — free to start.",
    "I did exactly this with Perplexity Browser + Comet — halved my routine work.",
    "If Zapier/Make are your vibe, pairing them with an AI browser is wild.",
]
HASHTAGS = ["#AI", "#automation", "#Perplexity", "#CometBrowser", "#Productivity", "#AITools"]

# --- utils ---
def _now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def _save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _log(msg: str):
    line = f"[{_now()}] {msg}\n"
    ACTIVITY_LOG.write_text(ACTIVITY_LOG.read_text(encoding="utf-8") + line if ACTIVITY_LOG.exists() else line, encoding="utf-8")
    print(line, end="")

def _pick_post() -> str:
    bank = _load_json(COPY_BANK, {})
    base = random.choice(POST_TEMPLATES)
    if random.random() < 0.5 and bank.get("extra"):
        base += " " + random.choice(bank["extra"])
    if REF_LINK and random.random() < LINK_RATE:
        base += f"\n{REF_LINK}"
    # tastefully add 1–3 hashtags
    tags = " ".join(random.sample(HASHTAGS, k=random.randint(1,3)))
    return f"{base}\n{tags}".strip()

def _choose_file(dir: Path, accepts: tuple[str,...]) -> Optional[Path]:
    files = [p for p in dir.glob("*") if p.suffix.lower() in accepts]
    return random.choice(files) if files else None

def _minutes_since(path: Path) -> float:
    if not path.exists(): return 9999.0
    return (time.time() - path.stat().st_mtime) / 60.0

def _maybe_autogen_assets() -> None:
    """Generate a quick image/video once if folders are empty."""
    if not any(IMG_DIR.iterdir()):
        try:
            p = generate_image("clean tech banner about AI browsers + automation")
            if p: _log(f"Auto-generated image: {p.name}")
        except Exception as e:
            _log(f"Image gen skipped: {e}")
    if not any(VID_DIR.iterdir()):
        try:
            p = generate_video("minimal looped tech animation about AI browsers + automation")
            if p: _log(f"Auto-generated video: {p.name}")
        except Exception as e:
            _log(f"Video gen skipped: {e}")

# --- X helpers ---
def _goto_home(page):
    try:
        page.goto("https://x.com/home", timeout=30000)
    except Exception:
        try:
            page.goto("https://x.com/compose/post", timeout=30000)
        except Exception:
            pass

def _close_center_modals(page):
    # dismiss any pop-up dialog that can steal the composer focus
    try:
        if page.locator("div[role='dialog']").count() > 0:
            # try an obvious close button
            for sel in ['div[aria-label="Close"]', 'div[data-testid="app-bar-close"]', 'div[role="button"][aria-label*="Close"]']:
                loc = page.locator(sel)
                if loc.count() > 0:
                    loc.first.click(timeout=1000)
                    time.sleep(0.5)
    except Exception:
        pass

def _composer_inline(page):
    """
    Prefer the inline composer in the primary column, not the pop-up dialog.
    """
    # newest UI: a single contenteditable div
    c = (page.locator("div[role='textbox']")
            .filter(has=page.locator('[data-testid="primaryColumn"]'))
            .filter(has_not=page.locator('div[role="dialog"]'))
            .first)
    return c

def _attach_media(page) -> bool:
    """
    Attach image or video occasionally (respecting MEDIA_MIN_GAP_MIN).
    Returns True if something was attached.
    """
    stamp = BASE / ".last_media_stamp"
    if _minutes_since(stamp) < MEDIA_MIN_GAP_MIN:
        return False

    attach_type = None
    pick_video = random.random() < VIDEO_RATE
    if pick_video:
        _maybe_autogen_assets()
        f = _choose_file(VID_DIR, (".mp4", ".mov"))
        attach_type = "video"
    else:
        _maybe_autogen_assets()
        f = _choose_file(IMG_DIR, (".png", ".jpg", ".jpeg", ".webp"))
        attach_type = "image"

    if not f: 
        return False

    ok = False
    try:
        # Twitter/X usually keeps a hidden file input for media:
        selector_candidates = [
            'input[type="file"][data-testid="fileInput"]',
            'input[type="file"][accept*="image"], input[type="file"][accept*="video"]'
        ]
        for sel in selector_candidates:
            if page.locator(sel).count() > 0:
                page.locator(sel).first.set_input_files(str(f))
                ok = True
                break
        if ok:
            stamp.write_text(_now(), encoding="utf-8")
            _log(f"Attached {attach_type}: {f.name}")
    except Exception as e:
        _log(f"Attach failed: {e}")
        ok = False
    return ok

def _click_post(page) -> bool:
    # common selectors for the inline "Post" button
    for sel in ['div[data-testid="tweetButtonInline"]', 'div[data-testid="tweetButton"]', 'button[data-testid="tweetButtonInline"]']:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_enabled():
                loc.first.click(timeout=3000)
                return True
        except Exception:
            continue
    return False

def main_loop():
    used = _load_json(USED_POSTS, [])
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page()
        _goto_home(page)
        time.sleep(2)

        # First-run login helper
        if page.url.startswith("https://x.com/i/flow/login") or "login" in page.url:
            _log("Login required: please log in ONCE in this Chromium window, then leave it open.")
            # give user a minute to complete login
            try:
                page.wait_for_url("**/home", timeout=120000)
            except TimeoutError:
                pass

        while True:
            try:
                _close_center_modals(page)
                _goto_home(page)

                comp = _composer_inline(page)
                if comp.count() == 0:
                    _log("Composer not found (modal?). If a center pop-up is open, close it once.")
                    time.sleep(10)
                    continue

                text = _pick_post()
                if text in used:
                    # simple anti-repeat; repick
                    tries = 0
                    while text in used and tries < 5:
                        text = _pick_post(); tries += 1

                comp.click(timeout=5000)
                page.keyboard.type(text, delay=random.randint(1,20))  # human-ish typing

                # media (occasionally)
                _attach_media(page)

                posted = _click_post(page)
                if posted:
                    _log(f"Posted: {text[:90].replace('\n',' ')}{'...' if len(text)>90 else ''}")
                    used.append(text)
                    used = used[-400:]  # keep last N
                    _save_json(USED_POSTS, used)
                else:
                    _log("Post failed; will retry next cycle.")

                wait_s = random.randint(MIN_WAIT, MAX_WAIT)
                _log(f"Waiting {wait_s//60}m {wait_s%60:02d}s before next cycle…")
                time.sleep(wait_s)
            except KeyboardInterrupt:
                _log("Stopped by user.")
                break
            except PTimeoutError:
                _log("Timeout; retry next cycle.")
                time.sleep(30)
            except Exception as e:
                _log(f"Error: {e}")
                time.sleep(30)

if __name__ == "__main__":
    _log("Launching Social Agent (persistent Chrome profile)…")
    main_loop()
# ===== END social_agent.py =====

