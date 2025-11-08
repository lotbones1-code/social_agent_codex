#!/usr/bin/env python3
# social_agent.py — Chrome persistent login + anti-duplicate posting + image/video generator hooks

import asyncio
from playwright.async_api import async_playwright, TimeoutError as PWTimeout, Error as PWError
from playwright.sync_api import sync_playwright, Error as SyncPWError
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
    PROFILE_DIR = (BASE_DIR / ".pwprofile_live").resolve()
os.environ.setdefault("PW_PROFILE_DIR", str(PROFILE_DIR))
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

FORCE_ONE_REPLY = bool(int(os.getenv("FORCE_ONE_REPLY", "0")))

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.open("a", encoding="utf-8").write(line + "\n")
    except Exception:
        pass


def debug_log(stage: str, **fields):
    details = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    log(f"[debug] stage={stage} {details}".rstrip())

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

async def human_pause(a: float, b: float):
    await asyncio.sleep(random.uniform(a, b))

def sanitize(text: str) -> str:
    text = re.sub(r"[^\S\r\n]+", " ", text).strip()
    return text.replace("\u200b", "").replace("\u2060", "")

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _build_launch_kwargs():
    return dict(
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


async def launch_ctx(p):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    launch_kwargs = _build_launch_kwargs()
    user_data_dir = os.environ["PW_PROFILE_DIR"]
    try:
        ctx = await p.chromium.launch_persistent_context(user_data_dir, channel="chrome", **launch_kwargs)
    except PWError:
        ctx = await p.chromium.launch_persistent_context(user_data_dir, **launch_kwargs)
    pages = ctx.pages
    page = pages[0] if pages else await ctx.new_page()
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
    await page.add_init_script("window.chrome = window.chrome || {};")
    return ctx, page


def ensure_manual_login():
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    launch_kwargs = _build_launch_kwargs()
    user_data_dir = os.environ["PW_PROFILE_DIR"]
    with sync_playwright() as sp:
        ctx = None
        try:
            try:
                ctx = sp.chromium.launch_persistent_context(user_data_dir, channel="chrome", **launch_kwargs)
            except SyncPWError:
                ctx = sp.chromium.launch_persistent_context(user_data_dir, **launch_kwargs)
            pages = ctx.pages
            page = pages[0] if pages else ctx.new_page()
            ensure_x_logged_in(page)
        finally:
            if ctx is not None:
                ctx.close()

async def stable_goto(page, url, timeout=120_000):
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except (PWTimeout, PWError):
        pass

async def on_home(page):
    try:
        if page.url.startswith(HOME_URL):
            return True
        for s in ('[data-testid="SideNav_NewTweet_Button"]','[aria-label="Post"]','a[href="/home"][aria-current="page"]'):
            locator = page.locator(s).first
            if await locator.count() and await locator.is_visible(timeout=0):
                return True
    except Exception:
        return False
    return False

async def wait_until_home(page, max_seconds=600):
    start = time.time()
    while time.time() - start < max_seconds:
        if await on_home(page):
            return True
        await asyncio.sleep(1.5)
    return False

async def ensure_login(page, ctx):
    await stable_goto(page, HOME_URL)
    if await on_home(page):
        try:
            STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
            await ctx.storage_state(path=str(STORAGE_PATH))
            log(f"✅ Saved cookies to {STORAGE_PATH}")
        except Exception as e:
            log(f"⚠️ Could not save storage: {e}")
        return True
    await stable_goto(page, LOGIN_URL)
    log("👉 Login required. Sign in in the Chrome window; I’ll auto-detect Home.")
    if not await wait_until_home(page, max_seconds=600):
        log(f"⚠️ Still not on Home. Try removing the profile at {PROFILE_DIR} and run again.")
        return False
    try:
        STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        await ctx.storage_state(path=str(STORAGE_PATH))
        log(f"✅ Saved cookies to {STORAGE_PATH}")
    except Exception as e:
        log(f"⚠️ Could not save storage: {e}")
    return True

async def search_live(page, query: str, max_wait_seconds: float = 12.0):
    url = SEARCH_URL.format(q=query.replace(" ", "%20"))
    await stable_goto(page, url)
    await human_pause(0.4, 0.8)
    start = time.time()
    while True:
        try:
            if await page.locator('article[data-testid="tweet"]').count() > 0:
                break
        except Exception:
            pass
        if time.time() - start >= max_wait_seconds:
            break
        await human_pause(0.25, 0.45)

async def collect_articles(page, limit=20):
    cards = page.locator('article[data-testid="tweet"]')
    count = await cards.count()
    n = min(count, limit)
    return [cards.nth(i) for i in range(n)]

async def extract_tweet_id(card):
    try:
        a = card.locator('a[href*="/status/"]').first
        href = await a.get_attribute("href") or ""
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

async def find_file_input(page):
    for sel in ("input[data-testid='fileInput']", "input[type='file']"):
        try:
            el = page.locator(sel).first
            if await el.count():
                return el
        except Exception:
            continue
    return None

async def run_wrapper(wrapper: Path, out_path: Path, topic: str, timeout_sec=300) -> bool:
    """Run generator wrapper with the venv python."""
    if not wrapper.exists():
        return False
    cmd = [sys.executable, str(wrapper), "--out", str(out_path), "--topic", topic]
    try:
        log(f"🎨 Running generator: {' '.join(cmd)}")
        await asyncio.to_thread(subprocess.run, cmd, timeout=timeout_sec, check=True)
        ok = out_path.exists() and out_path.stat().st_size > 0
        log("✅ Generator output ready" if ok else "⚠️ Generator ran but no output")
        return ok
    except Exception as e:
        log(f"⚠️ Generator failed: {e}")
        return False

async def maybe_generate_media(topic: str, reply_idx: int):
    generated = False
    if ENABLE_IMAGES and reply_idx % max(1, GENERATE_IMAGE_EVERY_N_REPLIES) == 0:
        out = IMAGES_DIR / f"auto_{int(time.time())}.png"
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        generated |= await run_wrapper(IMAGE_WRAPPER, out, topic)
    if ENABLE_VIDEOS and reply_idx % max(1, GENERATE_VIDEO_EVERY_N_REPLIES) == 0:
        out = VIDEOS_DIR / f"auto_{int(time.time())}.mp4"
        VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        generated |= await run_wrapper(VIDEO_WRAPPER, out, topic)
    return generated

async def maybe_attach_media(page, topic: str, reply_idx: int):
    if random.random() > MEDIA_ATTACH_RATE:
        return
    await maybe_generate_media(topic, reply_idx)

    try:
        if ENABLE_IMAGES:
            imgs = [p for p in IMAGES_DIR.glob("*") if p.suffix.lower() in {".png",".jpg",".jpeg"}]
            if imgs:
                file_input = await find_file_input(page)
                if file_input:
                    await file_input.set_input_files(str(random.choice(imgs)))
                    await human_pause(0.9, 1.6)
                    return
        if ENABLE_VIDEOS:
            vids = [p for p in VIDEOS_DIR.glob("*") if p.suffix.lower() in {".mp4",".mov"}]
            if vids:
                file_input = await find_file_input(page)
                if file_input:
                    await file_input.set_input_files(str(random.choice(vids)))
                    await human_pause(1.5, 3.0)
                    return
    except Exception as e:
        log(f"Media attach skipped: {e}")

async def click_post_once(page) -> bool:
    """Click a single button if present; only use keyboard if no button is clickable."""
    send_btn = page.locator("[data-testid='tweetButtonInline']").first
    if not await send_btn.count():
        send_btn = page.locator("div[data-testid='tweetButtonInline']").first
    if not await send_btn.count():
        send_btn = page.locator("[data-testid='tweetButton']").first
    if not await send_btn.count():
        send_btn = page.locator("div[data-testid='tweetButton']").first
    if not await send_btn.count():
        send_btn = page.locator("div[role='button']:has-text('Reply')").first
    if await send_btn.count():
        try:
            await send_btn.click()
            try:
                await send_btn.wait_for(state="detached", timeout=4000)
            except Exception:
                pass
            return True
        except Exception:
            pass
    try:
        await page.keyboard.press("Meta+Enter")  # macOS
        return True
    except Exception:
        try:
            await page.keyboard.press("Control+Enter")
            return True
        except Exception:
            return False

async def reply_to_card(page, card, tid: str, topic: str, recent_text_hashes: set, reply_idx: int) -> bool:
    # open composer
    reply_button = card.locator("[data-testid='reply']").first
    if not await reply_button.count():
        reply_button = card.locator("button[aria-label*='Reply']").first
    if not await reply_button.count():
        reply_button = card.locator("button:has-text('Reply')").first
    if not await reply_button.count():
        return False
    try:
        await reply_button.click()
    except Exception:
        return False
    await human_pause(0.8, 1.4)

    # text (avoid repeating the exact same sentence)
    text = compose_reply_text(topic)
    thash = sha(text)
    if thash in recent_text_hashes and not FORCE_ONE_REPLY:
        await page.keyboard.press("Escape")
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
            locator = page.locator(sel).first
            if await locator.is_visible(timeout=1500):
                await locator.click()
                for ch in text:
                    await page.keyboard.type(ch, delay=random.randint(20,55))
                typed = True
                break
        except Exception:
            continue
    if not typed:
        await page.keyboard.press("Escape")
        return False

    debug_log("queue", tid=tid, topic=topic, reply_idx=reply_idx)

    await maybe_attach_media(page, topic, reply_idx)

    posted = await click_post_once(page)

    debug_log("post", tid=tid, status="success" if posted else "failed", reply_idx=reply_idx)

    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    return posted

async def bot_loop(page, startup_ts: float):
    dedup_tweets = load_json(DEDUP_TWEETS, {})
    recent_text_hashes = set(load_json(DEDUP_TEXTS, []))

    start_time = time.time()
    initial_deadline = startup_ts + 10
    reply_counter = 0
    log("Starting smart reply loop")

    first_attempt_done = False
    while True:
        if MAX_RUN_HOURS and (time.time() - start_time) > MAX_RUN_HOURS * 3600:
            log("⏱️ Max runtime reached—exiting.")
            break

        term = random.choice(SEARCH_TERMS)
        log(f"Searching live for … {term}")
        if not first_attempt_done:
            remaining = max(0.0, initial_deadline - time.time())
            if remaining:
                search_wait = max(0.1, min(4.0, remaining))
            else:
                search_wait = 0.1
            await search_live(page, term, max_wait_seconds=search_wait)
        else:
            await search_live(page, term)

        cards = await collect_articles(page, limit=MAX_ARTICLES_SCAN)
        random.shuffle(cards)
        target = random.randint(*REPLIES_PER_TERM)
        sent = 0

        if not cards and not first_attempt_done and time.time() < initial_deadline:
            log("[debug] stage=queue no-cards yet; retrying search immediately to meet startup deadline")
            continue

        for card in cards:
            if sent >= target:
                break
            tid = await extract_tweet_id(card)
            if not tid or tid in dedup_tweets:
                continue

            if not first_attempt_done:
                if time.time() - startup_ts > 10:
                    debug_log("queue", tid=tid, topic=term, warning="startup-deadline-missed")
                first_attempt_done = True
            ok = await reply_to_card(
                page,
                card,
                tid=tid,
                topic=term,
                recent_text_hashes=recent_text_hashes,
                reply_idx=reply_counter + 1,
            )
            if ok:
                reply_counter += 1
                dedup_tweets[tid] = datetime.utcnow().isoformat() + "Z"
                save_json(DEDUP_TWEETS, dedup_tweets)
                save_json(DEDUP_TEXTS, list(recent_text_hashes))
                log(f"Posted: https://x.com/i/web/status/{tid}")
                await human_pause(*DELAY_BETWEEN_REPLIES)
                sent += 1
            else:
                log("…couldn’t post—skipping.")
        await human_pause(*DELAY_BETWEEN_TERMS)

async def run_mock_cycle():
    log("Mock login mode enabled; skipping browser automation.")
    log("Logged in & ready")
    debug_log("login", status="complete", mode="mock")
    sample_term = SEARCH_TERMS[0] if SEARCH_TERMS else "perplexity"
    log(f"Searching live for … {sample_term}")
    debug_log("queue", tid="mock", topic=sample_term, reply_idx=1, mode="mock")
    log("Posted: mock-post-id")
    debug_log("post", tid="mock", status="success", reply_idx=1, mode="mock")

def main_sync_exit(code: int):
    sys.exit(code)

def main():
    log(f"Using profile directory: {PROFILE_DIR}")
    if MOCK_LOGIN:
        asyncio.run(run_mock_cycle())
        return

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    launch_kwargs = _build_launch_kwargs()
    user_data_dir = os.environ["PW_PROFILE_DIR"]

    def _launch_persistent(playwright):
        try:
            return playwright.chromium.launch_persistent_context(
                user_data_dir,
                channel="chrome",
                **launch_kwargs,
            )
        except SyncPWError:
            return playwright.chromium.launch_persistent_context(
                user_data_dir,
                **launch_kwargs,
            )

    with sync_playwright() as playwright:
        ctx = None
        try:
            ctx = _launch_persistent(playwright)
            pages = ctx.pages
            page = pages[0] if pages else ctx.new_page()
            ensure_x_logged_in(page)
        finally:
            if ctx is not None:
                try:
                    ctx.close()
                except Exception:
                    pass

    async def _run_bot_loop():
        async with async_playwright() as playwright_async:
            ctx = None
            try:
                ctx, page = await launch_ctx(playwright_async)
                log("Logged in & ready")
                debug_log("login", status="complete", mode="live")
                live_ts = time.time()
                await bot_loop(page, startup_ts=live_ts)
            finally:
                if ctx is not None:
                    try:
                        await ctx.close()
                    except Exception:
                        pass

    asyncio.run(_run_bot_loop())


if __name__ == "__main__":
    main()
