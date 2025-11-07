#!/usr/bin/env python3
# social_agent.py — Chrome persistent login + smart replies + robust posting + optional media

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Error as PWError
from pathlib import Path
import time, sys, json, random, re, os
from datetime import datetime

# ====================== CONFIG ======================

REFERRAL_LINK = "https://pplx.ai/ssj4shamil93949"

SEARCH_TERMS = [
    "new browser automation",
    "AI browser automation",
    "productivity browser",
    "perplexity browser",
    "comet browser automation",
    "automate my workflow",
    "research workflow browser",
    "best browser for ai",
]

REPLY_TEMPLATES = [
    "If you want a browser that actually helps with research + small automations, try this. It’s free to start and the automation features are simple to use: {link}",
    "For light automation and quick research, this is what I recommend. No heavy setup, just works in the browser: {link}",
    "I’ve been using this for repetitive tasks + research summaries inside the browser. Worth a look: {link}",
    "Not a sales pitch—just something useful for me when juggling tasks and research: {link}",
]

# Activity / pacing
REPLIES_PER_TERM      = (1, 2)
DELAY_BETWEEN_REPLIES = (45, 90)
DELAY_BETWEEN_TERMS   = (20, 45)
MAX_ARTICLES_SCAN     = 20
MAX_RUN_HOURS         = 0  # 0 = run forever

# Media (off by default — flip to True if you add files)
ENABLE_IMAGES       = False
ENABLE_VIDEOS       = False
MEDIA_ATTACH_RATE   = 0.35   # chance to attach media on a reply
IMAGES_DIR          = Path("media/images")
VIDEOS_DIR          = Path("media/videos")

# ====================================================

PROFILE_DIR  = Path.home() / ".pw-chrome-referral"
STORAGE_PATH = Path("storage/x.json")
DEDUP_PATH   = Path("storage/replied.json")
LOG_PATH     = Path("logs/run.log")

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
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
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

def human_type(page, locator_str: str, text: str):
    loc = page.locator(locator_str).first
    loc.click()
    for ch in text:
        page.keyboard.type(ch, delay=random.randint(20, 55))
    human_pause(0.2, 0.6)

def list_files(folder: Path, exts):
    if not folder.exists():
        return []
    return [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts]

def find_file_input(page):
    for sel in ("input[data-testid='fileInput']", "input[type='file']"):
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible(timeout=1000):
                return el
        except Exception:
            continue
    # sometimes it's hidden but still accepts set_input_files
    for sel in ("input[data-testid='fileInput']", "input[type='file']"):
        try:
            el = page.locator(sel).first
            if el.count():
                return el
        except Exception:
            continue
    return None

def maybe_attach_media(page):
    if random.random() > MEDIA_ATTACH_RATE:
        return
    try:
        if ENABLE_IMAGES:
            imgs = list_files(IMAGES_DIR, {".jpg", ".jpeg", ".png"})
            if imgs:
                file_input = find_file_input(page)
                if file_input:
                    file_input.set_input_files(str(random.choice(imgs)))
                    human_pause(0.8, 1.6)
                    return
        if ENABLE_VIDEOS:
            vids = list_files(VIDEOS_DIR, {".mp4", ".mov"})
            if vids:
                file_input = find_file_input(page)
                if file_input:
                    file_input.set_input_files(str(random.choice(vids)))
                    human_pause(1.2, 2.0)
                    return
    except Exception as e:
        log(f"Media attach skipped: {e}")

def launch_ctx(p):
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
    page.add_init_script("""
        window.chrome = window.chrome || {};
        Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
    """)
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
        for s in (
            '[data-testid="SideNav_NewTweet_Button"]',
            '[aria-label="Post"]',
            'a[href="/home"][aria-current="page"]',
        ):
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
        log("⚠️ Still not on Home. Try: rm -rf ~/.pw-chrome-referral  and run again.")
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

def compose_reply_text() -> str:
    return sanitize(random.choice(REPLY_TEMPLATES).format(link=REFERRAL_LINK))

def click_post_or_fallback(page) -> bool:
    # Try multiple possible post/reply buttons
    selectors = [
        "button[data-testid='tweetButtonInline']",
        "div[data-testid='tweetButtonInline']",
        "button[data-testid='tweetButton']",
        "div[data-testid='tweetButton']",
        "button[data-testid='reply']",
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.count() and btn.is_enabled():
                btn.click()
                human_pause(0.6, 1.2)
                return True
        except Exception:
            continue
    # Keyboard fallback (Mac + generic)
    try:
        page.keyboard.press("Meta+Enter")  # macOS
        human_pause(0.6, 1.0)
        return True
    except Exception:
        pass
    try:
        page.keyboard.press("Control+Enter")  # fallback
        human_pause(0.6, 1.0)
        return True
    except Exception:
        return False

def reply_to_card(page, card) -> bool:
    try:
        card.locator('[data-testid="reply"]').first.click()
    except Exception:
        return False
    human_pause(0.8, 1.4)

    text = compose_reply_text()
    box_selectors = [
        "div[role='textbox'][data-testid='tweetTextarea_0']",
        "div[role='textbox'][data-testid='tweetTextarea_1']",
        "div[role='textbox']",
    ]
    typed = False
    for sel in box_selectors:
        try:
            if page.locator(sel).first.is_visible(timeout=1500):
                human_type(page, sel, text)
                typed = True
                break
        except Exception:
            continue
    if not typed:
        page.keyboard.press("Escape")
        return False

    # Optional media
    maybe_attach_media(page)

    posted = click_post_or_fallback(page)

    # Close composer if still open; we assume success if we attempted a post
    try:
        page.keyboard.press("Escape")
        human_pause(0.3, 0.6)
    except Exception:
        pass
    return posted

def bot_loop(page):
    dedup = load_json(DEDUP_PATH, default={})
    start_time = time.time()
    log("✅ Logged in & ready. Starting smart reply loop…")

    while True:
        if MAX_RUN_HOURS and (time.time() - start_time) > MAX_RUN_HOURS * 3600:
            log("⏱️ Max runtime reached—exiting.")
            break

        term = random.choice(SEARCH_TERMS)
        log(f"🔎 Searching live for: {term}")
        search_live(page, term)

        cards = collect_articles(page, limit=MAX_ARTICLES_SCAN)
        random.shuffle(cards)
        target_count = random.randint(*REPLIES_PER_TERM)
        sent = 0

        for card in cards:
            if sent >= target_count:
                break
            tid = extract_tweet_id(card)
            if not tid or tid in dedup:
                continue

            ok = reply_to_card(page, card)
            if ok:
                dedup[tid] = datetime.utcnow().isoformat() + "Z"
                save_json(DEDUP_PATH, dedup)
                log(f"💬 Replied to tweet {tid}")
                human_pause(*DELAY_BETWEEN_REPLIES)
                sent += 1
            else:
                log("…couldn’t post—skipping.")
        human_pause(*DELAY_BETWEEN_TERMS)

def main():
    with sync_playwright() as p:
        ctx = page = None
        try:
            ctx, page = launch_ctx(p)
            if not ensure_login(page, ctx):
                sys.exit(1)
            bot_loop(page)
        finally:
            pass

if __name__ == "__main__":
    main()

