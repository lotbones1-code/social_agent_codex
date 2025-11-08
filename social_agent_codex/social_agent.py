#!/usr/bin/env python3
# social_agent.py — Chrome persistent login + anti-duplicate posting + image/video generator hooks

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Error as PWError
from pathlib import Path
from dataclasses import dataclass
import os
import time
import sys
import json
import random
import re
import subprocess
import hashlib
from datetime import datetime
from typing import Optional

import requests
from dotenv import load_dotenv

# ====================== CONFIG ======================

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env", override=False)
load_dotenv(ROOT_DIR / ".env.replicate", override=False)

REFERRAL_LINK = os.getenv("REFERRAL_LINK", "https://pplx.ai/ssj4shamil93949")

SEARCH_TERMS = [
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
    "I’ve used this for repetitive tasks + research summaries inside the browser. Worth a look: {link}",
    "Not a sales pitch—just something useful when juggling tasks and research: {link}",
]

# pacing (anti-spam)
REPLIES_PER_TERM      = (1, 2)
DELAY_BETWEEN_REPLIES = (45, 90)
DELAY_BETWEEN_TERMS   = (20, 45)
MAX_ARTICLES_SCAN     = 20
MAX_RUN_HOURS         = 0  # 0 = run until Ctrl+C

# media toggles
ENABLE_IMAGES       = os.getenv("ENABLE_IMAGES", "1") not in {"0", "false", "False"}
ENABLE_VIDEOS       = os.getenv("ENABLE_VIDEOS", "0") not in {"0", "false", "False"}
MEDIA_ATTACH_RATE   = float(os.getenv("MEDIA_ATTACH_RATE", "0.30"))
IMAGES_DIR          = Path("media/images")
VIDEOS_DIR          = Path("media/videos")

# generator hooks (we call these wrappers; they load your old funcs from social_agent.backup.py)
IMAGE_WRAPPER = Path("generators/image_gen.py")
VIDEO_WRAPPER = Path("generators/video_gen.py")
GENERATE_IMAGE_EVERY_N_REPLIES = max(1, int(os.getenv("GENERATE_IMAGE_EVERY_N_REPLIES", "4")))
GENERATE_VIDEO_EVERY_N_REPLIES = max(1, int(os.getenv("GENERATE_VIDEO_EVERY_N_REPLIES", "10")))

HEADLESS = os.getenv("HEADLESS", "1") not in {"0", "false", "False"}

STRICT_MODE_DEFAULT = os.getenv("STRICT_MODE", "1") not in {"0", "false", "False"}
MIN_WORDS_DEFAULT = max(0, int(os.getenv("MIN_WORDS", "6")))
MIN_CHARACTERS_DEFAULT = max(0, int(os.getenv("MIN_CHARACTERS", "80")))
DUPLICATE_PROTECT_DEFAULT = os.getenv("DUPLICATE_PROTECT", "1") not in {"0", "false", "False"}

FILTER_LOOSEN_MIN = max(60, int(os.getenv("FILTER_LOOSEN_MIN", "300")))
FILTER_LOOSEN_MAX = max(FILTER_LOOSEN_MIN + 60, int(os.getenv("FILTER_LOOSEN_MAX", "480")))

REPLY_MODE = os.getenv("REPLY_MODE", "templates").strip().lower()

# ====================================================

PROFILE_DIR  = Path.home() / ".pw-chrome-referral"
STORAGE_PATH = Path("storage/x.json")
DEDUP_TWEETS = Path("storage/replied.json")
DEDUP_TEXTS  = Path("storage/text_hashes.json")   # avoid posting the exact same sentence back to back
LOG_PATH     = Path("logs/run.log")

HOME_URL   = "https://x.com/home"
LOGIN_URL  = "https://x.com/login"
SEARCH_URL = "https://x.com/search?q={q}&src=typed_query&f=live"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)


@dataclass
class FilterSettings:
    strict_mode: bool
    min_words: int
    min_characters: int
    duplicate_protect: bool

    def allows_text(self, text: str) -> bool:
        clean = sanitize(text)
        if self.strict_mode and not clean:
            return False
        if self.min_words and len(clean.split()) < self.min_words:
            return False
        if self.min_characters and len(clean) < self.min_characters:
            return False
        return True


class FilterController:
    def __init__(self) -> None:
        self.defaults = FilterSettings(
            strict_mode=STRICT_MODE_DEFAULT,
            min_words=MIN_WORDS_DEFAULT,
            min_characters=MIN_CHARACTERS_DEFAULT,
            duplicate_protect=DUPLICATE_PROTECT_DEFAULT,
        )
        self.current = FilterSettings(**vars(self.defaults))
        self.loosened = False
        self._restore_pending = False
        self._reset_deadline()

    def _reset_deadline(self) -> None:
        span = random.uniform(FILTER_LOOSEN_MIN, FILTER_LOOSEN_MAX)
        self._loosen_deadline = time.time() + span

    def should_allow_text(self, text: str) -> bool:
        return self.current.allows_text(text)

    def note_attempt(self) -> None:
        if not self.loosened and time.time() >= self._loosen_deadline:
            log("🕒 No replies recently — loosening filters for this cycle (STRICT_MODE=0, MIN_*=0, DUPLICATE_PROTECT=0)")
            self.current = FilterSettings(strict_mode=False, min_words=0, min_characters=0, duplicate_protect=False)
            self.loosened = True
            self._restore_pending = True

    def note_reply(self) -> None:
        self._reset_deadline()
        if self.loosened:
            self.restore()

    def restore(self) -> None:
        if self.loosened or self._restore_pending:
            log("🔒 Restoring strict reply filters to defaults")
        self.current = FilterSettings(**vars(self.defaults))
        self.loosened = False
        self._restore_pending = False
        self._reset_deadline()

    def maybe_restore_after_cycle(self) -> None:
        if self._restore_pending:
            self.restore()


class ReplyComposer:
    def __init__(self) -> None:
        self.mode = REPLY_MODE
        self._warned = False

    def compose(self, topic: str, tweet_text: str) -> str:
        if self.mode == "codex":
            generated = self._codex_reply(topic, tweet_text)
            if generated:
                return sanitize(generated)
        return sanitize(random.choice(REPLY_TEMPLATES).format(link=REFERRAL_LINK))

    def _codex_reply(self, topic: str, tweet_text: str) -> Optional[str]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            if not self._warned:
                log("⚠️ REPLY_MODE=codex but OPENAI_API_KEY is missing — falling back to templates")
                self._warned = True
            return None
        prompt = (
            "Write a concise, friendly reply (<=280 characters) for an X thread about '{topic}'. "
            "Reference this talking point: {tweet_text}. Mention this link exactly once: {link}."
        ).format(topic=topic, tweet_text=tweet_text[:400], link=REFERRAL_LINK)
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-5-codex",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are Codex, a helpful assistant composing social media replies. "
                                "Keep tone upbeat, avoid hashtags, and stay under 280 characters."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 180,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            try:
                return data["choices"][0]["message"]["content"].strip()
            except Exception:
                pass
            if isinstance(data, dict):
                for key in ("content", "output"):
                    chunk = data.get(key)
                    if isinstance(chunk, str) and chunk.strip():
                        return chunk.strip()
                    if isinstance(chunk, list) and chunk:
                        text = chunk[0]
                        if isinstance(text, str) and text.strip():
                            return text.strip()
                        if isinstance(text, dict):
                            for inner in ("text", "content"):
                                val = text.get(inner)
                                if isinstance(val, str) and val.strip():
                                    return val.strip()
        except Exception as e:
            if not self._warned:
                log(f"⚠️ Codex reply failed ({e}); using templates instead")
                self._warned = True
        return None

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

def clear_chrome_locks(profile_dir: Path) -> None:
    locks = ["SingletonLock", "SingletonCookie", "SingletonSocket"]
    for name in locks:
        target = profile_dir / name
        try:
            if target.exists():
                target.unlink()
                log(f"🧹 Removed Chrome singleton file: {target}")
        except Exception as e:
            log(f"⚠️ Could not remove {target}: {e}")


def launch_ctx(p):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    clear_chrome_locks(PROFILE_DIR)
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-features=IsolateOrigins,site-per-process",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if HEADLESS:
        args.append("--headless=new")
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        channel="chrome",
        headless=HEADLESS,
        viewport=None,
        user_agent=USER_AGENT,
        args=args,
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
                    chosen = random.choice(imgs)
                    file_input.set_input_files(str(chosen))
                    human_pause(0.9, 1.6)
                    log(f"📎 Attached media: {chosen}")
                    return
        if ENABLE_VIDEOS:
            vids = [p for p in VIDEOS_DIR.glob("*") if p.suffix.lower() in {".mp4",".mov"}]
            if vids:
                file_input = find_file_input(page)
                if file_input:
                    chosen = random.choice(vids)
                    file_input.set_input_files(str(chosen))
                    human_pause(1.5, 3.0)
                    log(f"📎 Attached media: {chosen}")
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

def extract_card_text(card) -> str:
    try:
        texts = card.locator('[data-testid="tweetText"]').all_inner_texts()
        combined = " ".join(t.strip() for t in texts if t and t.strip())
        if combined:
            return combined
    except Exception:
        pass
    try:
        raw = card.inner_text()
        if raw:
            return raw
    except Exception:
        pass
    return ""


def reply_to_card(page, card, topic: str, recent_text_hashes: set, reply_idx: int, filters: FilterController, composer: ReplyComposer, tweet_text: str) -> bool:
    # open composer
    try:
        card.locator('[data-testid="reply"]').first.click()
    except Exception:
        return False
    human_pause(0.8, 1.4)

    # text (avoid repeating the exact same sentence)
    text = composer.compose(topic, tweet_text)
    thash = sha(text)
    if filters.current.duplicate_protect and thash in recent_text_hashes:
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
    composer = ReplyComposer()
    filters = FilterController()

    start_time = time.time()
    reply_counter = 0
    log("✅ Logged in & ready. Starting smart reply loop…")

    while True:
        if MAX_RUN_HOURS and (time.time() - start_time) > MAX_RUN_HOURS * 3600:
            log("⏱️ Max runtime reached—exiting.")
            break

        filters.note_attempt()
        term = random.choice(SEARCH_TERMS)
        log(f"🔎 Searching live for: {term}")
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

            tweet_text = extract_card_text(card)
            if not filters.should_allow_text(tweet_text):
                continue

            ok = reply_to_card(
                page,
                card,
                topic=term,
                recent_text_hashes=recent_text_hashes,
                reply_idx=reply_counter + 1,
                filters=filters,
                composer=composer,
                tweet_text=tweet_text,
            )
            if ok:
                reply_counter += 1
                dedup_tweets[tid] = datetime.utcnow().isoformat() + "Z"
                save_json(DEDUP_TWEETS, dedup_tweets)
                save_json(DEDUP_TEXTS, list(recent_text_hashes))
                log(f"💬 Replied to tweet {tid}")
                filters.note_reply()
                human_pause(*DELAY_BETWEEN_REPLIES)
                sent += 1
            else:
                log("…couldn’t post—skipping.")
        filters.maybe_restore_after_cycle()
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

