#!/usr/bin/env python3
# social_agent.py — Chrome persistent login + anti-duplicate posting + image/video generator hooks

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Error as PWError
from pathlib import Path
import time, sys, json, random, re, subprocess, hashlib, os
from datetime import datetime

from x_login import ensure_x_logged_in, XLoginError

# ====================== CONFIG ======================

REFERRAL_LINK = "https://pplx.ai/ssj4shamil93949"

SEARCH_TERMS = [
    "perplexity comet",
    "research workflow browser",
]

REPLY_TEMPLATES = [
    (
        "When I’m digging into {topic}, I lean on this browser workspace to keep tabs and notes synced. "
        "If you want the same setup, I saved my invite here: {link}"
    ),
    (
        "Been using this tool for research loops around {topic}; it keeps the context tidy without feeling like an ad. "
        "Sharing the link I use in case it helps: {link}"
    ),
    (
        "Little productivity boost that’s helped me with {topic} threads—one-click summaries, gentle automations, nothing spammy. "
        "My sign-up link if you’re curious: {link}"
    ),
    (
        "If you ever need to switch between research and quick automations on {topic}, this has been the smoothest option I found. "
        "I tucked my referral here (totally optional): {link}"
    ),
    (
        "This isn’t a promo, just the workflow that’s kept my {topic} work from getting messy. "
        "Here’s the same access link I use: {link}"
    ),
]

# pacing (anti-spam)
REPLIES_PER_TERM      = (1, 2)
DELAY_BETWEEN_REPLIES = (45, 90)
DELAY_BETWEEN_TERMS   = (20, 45)
MAX_ARTICLES_SCAN     = 20
MAX_RUN_HOURS         = 0  # 0 = run until Ctrl+C

# media toggles
ENABLE_IMAGES       = True
ENABLE_VIDEOS       = False   # turn True after your video wrapper test passes
MEDIA_ATTACH_RATE   = 0.30
IMAGES_DIR          = Path("media/images")
VIDEOS_DIR          = Path("media/videos")

# generator hooks (we call these wrappers; they load your old funcs from social_agent.backup.py)
IMAGE_WRAPPER = Path("generators/image_gen.py")
VIDEO_WRAPPER = Path("generators/video_gen.py")
GENERATE_IMAGE_EVERY_N_REPLIES = 4
GENERATE_VIDEO_EVERY_N_REPLIES = 10

# ====================================================

BASE_DIR = Path(__file__).resolve().parent
_env_profile = os.getenv("PW_PROFILE_DIR")
if _env_profile:
    PROFILE_DIR = Path(_env_profile).expanduser()
    if not PROFILE_DIR.is_absolute():
        PROFILE_DIR = (BASE_DIR / PROFILE_DIR).resolve()
    else:
        PROFILE_DIR = PROFILE_DIR.resolve()
else:
    PROFILE_DIR = (BASE_DIR / ".pwprofile").resolve()
STORAGE_PATH = Path("storage/x.json")
DEDUP_TWEETS = Path("storage/replied.json")
DEDUP_TEXTS  = Path("storage/text_hashes.json")   # avoid posting the exact same sentence back to back
LOG_PATH     = Path("logs/run.log")

MOCK_LOGIN = os.getenv("SOCIAL_AGENT_MOCK_LOGIN", "").lower() in {"1", "true", "yes", "on"}

HOME_URL   = "https://x.com/home"
LOGIN_URL  = "https://x.com/login"
SEARCH_URL = "https://x.com/search?q={q}&src=typed_query&f=live"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.open("a", encoding="utf-8").write(line + "\n")
    except Exception:
        pass

def load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def save_json(path: Path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"Could not write {path}: {e}")

def human_pause(a: float, b: float):
    time.sleep(random.uniform(a, b))

def sanitize(text: str) -> str:
    text = re.sub(r"[^\S\r\n]+", " ", text).strip()
    return text.replace("\u200b", "").replace("\u2060", "")

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def launch_ctx(p):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        channel="chrome",
        headless=False,
        viewport=None,
        user_agent=USER_AGENT,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
    page.add_init_script("window.chrome = window.chrome || {};")
    return ctx, page

def stable_goto(page, url, timeout=120_000):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except (PWTimeout, PWError):
        pass

def on_home(page):
    try:
        if page.url.startswith(HOME_URL):
            return True
        for s in ('[data-testid="SideNav_NewTweet_Button"]','[aria-label="Post"]','a[href="/home"][aria-current="page"]'):
            if page.locator(s).first.is_visible(timeout=0):
                return True
    except Exception:
        return False
    return False

def wait_until_home(page, max_seconds=600):
    start = time.time()
    while time.time() - start < max_seconds:
        if on_home(page):
            return True
        time.sleep(1.5)
    return False

def ensure_login(page, ctx):
    stable_goto(page, HOME_URL)
    if on_home(page):
        return True
    stable_goto(page, LOGIN_URL)
    log("👉 Login required. Sign in in the Chrome window; I’ll auto-detect Home.")
    if not wait_until_home(page, max_seconds=600):
        log(f"⚠️ Still not on Home. Try removing the profile at {PROFILE_DIR} and run again.")
        return False
    try:
        STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        ctx.storage_state(path=str(STORAGE_PATH))
        log(f"✅ Saved cookies to {STORAGE_PATH}")
    except Exception as e:
        log(f"⚠️ Could not save storage: {e}")
    return True

def search_live(page, query: str):
    url = SEARCH_URL.format(q=query.replace(" ", "%20"))
    stable_goto(page, url)
    human_pause(1.0, 2.0)
    for _ in range(30):
        if page.locator('article[data-testid="tweet"]').count() > 0:
            break
        human_pause(0.3, 0.6)

def collect_articles(page, limit=20):
    cards = page.locator('article[data-testid="tweet"]')
    n = min(cards.count(), limit)
    return [cards.nth(i) for i in range(n)]

def extract_tweet_id(card):
    try:
        a = card.locator('a[href*="/status/"]').first
        href = a.get_attribute("href") or ""
        m = re.search(r"/status/(\d+)", href)
        return m.group(1) if m else None
    except Exception:
        return None

def compose_reply_text(topic: str) -> str:
    return sanitize(
        random.choice(REPLY_TEMPLATES).format(
            link=REFERRAL_LINK,
            topic=topic,
        )
    )

def find_file_input(page):
    for sel in ("input[data-testid='fileInput']", "input[type='file']"):
        try:
            el = page.locator(sel).first
            if el.count():
                return el
        except Exception:
            continue
    return None

def run_wrapper(wrapper: Path, out_path: Path, topic: str, timeout_sec=300) -> bool:
    """Run generator wrapper with the venv python."""
    if not wrapper.exists():
        return False
    cmd = [sys.executable, str(wrapper), "--out", str(out_path), "--topic", topic]
    try:
        log(f"🎨 Running generator: {' '.join(cmd)}")
        subprocess.run(cmd, timeout=timeout_sec, check=True)
        ok = out_path.exists() and out_path.stat().st_size > 0
        log("✅ Generator output ready" if ok else "⚠️ Generator ran but no output")
        return ok
    except Exception as e:
        log(f"⚠️ Generator failed: {e}")
        return False

def maybe_generate_media(topic: str, reply_idx: int):
    generated = False
    if ENABLE_IMAGES and reply_idx % max(1, GENERATE_IMAGE_EVERY_N_REPLIES) == 0:
        out = IMAGES_DIR / f"auto_{int(time.time())}.png"
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        generated |= run_wrapper(IMAGE_WRAPPER, out, topic)
    if ENABLE_VIDEOS and reply_idx % max(1, GENERATE_VIDEO_EVERY_N_REPLIES) == 0:
        out = VIDEOS_DIR / f"auto_{int(time.time())}.mp4"
        VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        generated |= run_wrapper(VIDEO_WRAPPER, out, topic)
    return generated

def maybe_attach_media(page, topic: str, reply_idx: int):
    if random.random() > MEDIA_ATTACH_RATE:
        return
    # optional fresh generation
    maybe_generate_media(topic, reply_idx)

    try:
        if ENABLE_IMAGES:
            imgs = [p for p in IMAGES_DIR.glob("*") if p.suffix.lower() in {".png",".jpg",".jpeg"}]
            if imgs:
                file_input = find_file_input(page)
                if file_input:
                    file_input.set_input_files(str(random.choice(imgs)))
                    human_pause(0.9, 1.6)
                    return
        if ENABLE_VIDEOS:
            vids = [p for p in VIDEOS_DIR.glob("*") if p.suffix.lower() in {".mp4",".mov"}]
            if vids:
                file_input = find_file_input(page)
                if file_input:
                    file_input.set_input_files(str(random.choice(vids)))
                    human_pause(1.5, 3.0)
                    return
    except Exception as e:
        log(f"Media attach skipped: {e}")

def click_post_once(page) -> bool:
    """Click a single button if present; only use keyboard if no button is clickable."""
    selectors = [
        "button[data-testid='tweetButtonInline']",
        "div[data-testid='tweetButtonInline']",
        "button[data-testid='tweetButton']",
        "div[data-testid='tweetButton']",
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.count() and btn.is_enabled():
                btn.click()
                try:
                    btn.wait_for(state="detached", timeout=4000)
                except Exception:
                    pass
                return True
        except Exception:
            continue
    # fallback: keyboard only if no clickable button
    try:
        page.keyboard.press("Meta+Enter")  # macOS
        return True
    except Exception:
        try:
            page.keyboard.press("Control+Enter")
            return True
        except Exception:
            return False

def reply_to_card(page, card, topic: str, recent_text_hashes: set, reply_idx: int) -> bool:
    # open composer
    try:
        card.locator('[data-testid="reply"]').first.click()
    except Exception:
        return False
    human_pause(0.8, 1.4)

    # text (avoid repeating the exact same sentence)
    text = compose_reply_text(topic)
    thash = sha(text)
    if thash in recent_text_hashes:
        page.keyboard.press("Escape")
        return False
    recent_text_hashes.add(thash)

    box_selectors = [
        "div[role='textbox'][data-testid='tweetTextarea_0']",
        "div[role='textbox'][data-testid='tweetTextarea_1']",
        "div[role='textbox']",
    ]
    typed = False
    for sel in box_selectors:
        try:
            if page.locator(sel).first.is_visible(timeout=1500):
                page.locator(sel).first.click()
                for ch in text:
                    page.keyboard.type(ch, delay=random.randint(20,55))
                typed = True
                break
        except Exception:
            continue
    if not typed:
        page.keyboard.press("Escape")
        return False

    # optional media
    maybe_attach_media(page, topic, reply_idx)

    # single-shot post
    posted = click_post_once(page)

    # close composer if still open
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    return posted

def bot_loop(page):
    dedup_tweets = load_json(DEDUP_TWEETS, {})
    recent_text_hashes = set(load_json(DEDUP_TEXTS, []))

    start_time = time.time()
    reply_counter = 0
    log("Starting smart reply loop")

    while True:
        if MAX_RUN_HOURS and (time.time() - start_time) > MAX_RUN_HOURS * 3600:
            log("⏱️ Max runtime reached—exiting.")
            break

        term = random.choice(SEARCH_TERMS)
        log(f"Searching live for … {term}")
        search_live(page, term)

        cards = collect_articles(page, limit=MAX_ARTICLES_SCAN)
        random.shuffle(cards)
        target = random.randint(*REPLIES_PER_TERM)
        sent = 0

        for card in cards:
            if sent >= target:
                break
            tid = extract_tweet_id(card)
            if not tid or tid in dedup_tweets:
                continue

            ok = reply_to_card(page, card, topic=term, recent_text_hashes=recent_text_hashes, reply_idx=reply_counter + 1)
            if ok:
                reply_counter += 1
                dedup_tweets[tid] = datetime.utcnow().isoformat() + "Z"
                save_json(DEDUP_TWEETS, dedup_tweets)
                save_json(DEDUP_TEXTS, list(recent_text_hashes))
                log(f"Posted: https://x.com/i/web/status/{tid}")
                human_pause(*DELAY_BETWEEN_REPLIES)
                sent += 1
            else:
                log("…couldn’t post—skipping.")
        human_pause(*DELAY_BETWEEN_TERMS)

def run_mock_cycle():
    log("Mock login mode enabled; skipping browser automation.")
    log("Logged in & ready")
    sample_term = SEARCH_TERMS[0] if SEARCH_TERMS else "perplexity"
    log(f"Searching live for … {sample_term}")
    log("Posted: mock-post-id")

def main():
    log(f"Using profile directory: {PROFILE_DIR}")
    if MOCK_LOGIN:
        run_mock_cycle()
        return
    with sync_playwright() as p:
        ctx = page = None
        try:
            ctx, page = launch_ctx(p)
            username = os.getenv("X_USERNAME")
            password = os.getenv("X_PASSWORD")
            alt_identifier = os.getenv("X_ALT_ID") or os.getenv("X_EMAIL")
            try:
                ensure_x_logged_in(page, username, password, alt_identifier)
            except XLoginError as exc:
                log(str(exc))
                raise
            if not ensure_login(page, ctx):
                sys.exit(1)
            log("Logged in & ready")
            bot_loop(page)
        finally:
            try:
                if ctx is not None:
                    ctx.close()
            except Exception:
                pass

if __name__ == "__main__":
    main()

