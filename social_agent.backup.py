from __future__ import annotations

import os
import json
import time
import random
import datetime as dt
from pathlib import Path
from typing import Optional, List

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

# ===== paths & env =====

BASE = Path(__file__).resolve().parent

MEDIA = BASE / "media"
IMG_DIR = MEDIA / "images"
VID_DIR = MEDIA / "videos"

USED_POSTS = BASE / "used_posts.json"
COPY_BANK = BASE / "copy_bank.json"
ACTIVITY_LOG = BASE / "activity_log.txt"

PROFILE_DIR = BASE / ".chrome_profile"

for p in (MEDIA, IMG_DIR, VID_DIR):
    p.mkdir(parents=True, exist_ok=True)

# ---- env helper ----


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v not in (None, "") else default


# human pacing / behavior (overridable via .env)
REF_LINK = _env("REF_LINK", "").strip()

MIN_WAIT = int(_env("MIN_WAIT", "180"))          # 3 min
MAX_WAIT = int(_env("MAX_WAIT", "480"))          # 8 min

LINK_RATE = float(_env("LINK_RATE", "0.12"))     # chance to include link
VIDEO_RATE = float(_env("VIDEO_RATE", "0.10"))   # chance of video attach
IMAGE_RATE = float(_env("IMAGE_RATE", "0.08"))   # chance of image attach
MEDIA_MIN_GAP_MIN = int(_env("MEDIA_MIN_GAP_MIN", "45"))

# optional Replicate auto-media
REPLICATE_API_TOKEN = _env("REPLICATE_API_TOKEN", "")
REPLICATE_IMAGE_MODEL = _env("REPLICATE_IMAGE_MODEL", "")
REPLICATE_VIDEO_MODEL = _env("REPLICATE_VIDEO_MODEL", "")

# ===== media_generate integration =====

try:
    from media_generate import generate_image, generate_video
except Exception:
    # Soft fallback so script never crashes if helper is missing
    def generate_image(prompt: str):
        return None

    def generate_video(prompt: str):
        return None


# ===== logging & json helpers =====


def _log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with ACTIVITY_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _jload(path: Path, default):
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        _log(f"Error reading {path.name}: {e}")
    return default


def _jsave(path: Path, data) -> None:
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _log(f"Error writing {path.name}: {e}")


# ===== copy / text logic =====


def _load_posts() -> List[str]:
    posts: List[str] = []

    # external copy_bank.json (optional)
    cb = _jload(COPY_BANK, [])
    if isinstance(cb, list):
        posts.extend(str(x) for x in cb if str(x).strip())

    # fallback templates if no copy_bank or empty
    if not posts:
        posts = [
            "🤖 Discovering how AI browsers + agents can save hours every day. Real workflows, real output.",
            "⚙️ Automating my routine with AI copilots, custom browsers and agents — sharing experiments.",
            "🚀 Building an AI-powered browser stack: less clicking, more outcomes. No fluff.",
        ]

    # append REF_LINK if set
    if REF_LINK:
        updated = []
        for p in posts:
            p = p.strip()
            if "{REF}" in p:
                updated.append(p.replace("{REF}", REF_LINK))
            else:
                updated.append(f"{p} {REF_LINK}")
        posts = updated

    return posts


def _load_used() -> List[str]:
    used = _jload(USED_POSTS, [])
    return used if isinstance(used, list) else []


def _pick_post() -> str:
    posts = _load_posts()
    used = _load_used()

    choices = [p for p in posts if p not in used]
    if not choices:
        used = []
        choices = posts

    text = random.choice(choices).strip()
    used.append(text)
    used = used[-400:]
    _jsave(USED_POSTS, used)

    return text


# ===== Playwright helpers =====


def _is_login_page(page) -> bool:
    try:
        url = page.url or ""
    except Exception:
        url = ""
    if "login" in url or "signup" in url:
        return True
    try:
        return page.locator("text='Sign in to X'").count() > 0
    except Exception:
        return False


def _is_login_blocked(page) -> bool:
    try:
        return page.locator("text='Could not log you in now'").count() > 0
    except Exception:
        return False


def _close_center_modals(page) -> None:
    # Best-effort close of pop-up modals
    try:
        selectors = [
            "div[role='dialog'] div[aria-label='Close']",
            "div[role='dialog'] svg[aria-label='Close']",
            "div[role='dialog'] div[role='button'][data-testid='app-bar-close']",
        ]
        for sel in selectors:
            loc = page.locator(sel)
            count = min(loc.count(), 5)
            for i in range(count):
                try:
                    loc.nth(i).click(timeout=1500)
                except Exception:
                    pass
    except Exception:
        pass


def _goto_home(page) -> None:
    try:
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=45000)
    except Exception:
        pass


def _get_inline_composer(page):
    # Prefer inline composer in primary column and NOT inside a dialog.
    try:
        composer = (
            page.locator("div[role='textbox']")
            .filter(has=page.locator("[data-testid='primaryColumn']"))
            .filter(has_not=page.locator("div[role='dialog']"))
            .first
        )
        if composer.count():
            return composer
    except Exception:
        pass

    # Fallback: any non-dialog textbox
    try:
        cand = (
            page.locator("div[role='textbox']")
            .filter(has_not=page.locator("div[role='dialog']"))
            .first
        )
        if cand.count():
            return cand
    except Exception:
        pass

    return None


# ===== media handling =====

_prev_media_ts: float = 0.0


def _list_files(folder: Path) -> List[Path]:
    return [p for p in folder.glob("*") if p.is_file()]


def _maybe_generate_and_list_media(kind: str) -> List[Path]:
    files: List[Path] = []
    if kind == "image":
        files = _list_files(IMG_DIR)
        if not files and REPLICATE_API_TOKEN and REPLICATE_IMAGE_MODEL:
            p = "clean AI + automation themed banner"
            out = generate_image(p)
            if out:
                files = [Path(out)]
    else:
        files = _list_files(VID_DIR)
        if not files and REPLICATE_API_TOKEN and REPLICATE_VIDEO_MODEL:
            p = "short looping AI automation teaser"
            out = generate_video(p)
            if out:
                files = [Path(out)]
    return files


def _attach_media(page) -> None:
    global _prev_media_ts

    now = time.time()
    if now - _prev_media_ts < MEDIA_MIN_GAP_MIN * 60:
        return

    r = random.random()
    if r < VIDEO_RATE:
        kind = "video"
    elif r < VIDEO_RATE + IMAGE_RATE:
        kind = "image"
    else:
        return

    try:
        file_input = page.locator("input[data-testid='fileInput']").first
        if not file_input or not file_input.count():
            return
    except Exception:
        return

    files = _maybe_generate_and_list_media(kind)
    if not files:
        return

    path = random.choice(files)
    try:
        file_input.set_input_files(str(path))
        _prev_media_ts = now
        _log(f"Media attached: {path.name}")
    except Exception as e:
        _log(f"Media attach failed: {e}")


# ===== login/session flow =====


def _ensure_logged_in(page) -> bool:
    """Handle login / soft-block logic once at startup."""

    _goto_home(page)
    time.sleep(5)

    if _is_login_blocked(page):
        _log("⚠️ X shows 'Could not log you in now' on startup. Stopping (wait & retry later).")
        return False

    if _is_login_page(page):
        _log("Detected X login page. Please log in manually in the Chromium window.")
        _log("After you reach your Home timeline, return here and press Enter.")
        input("Press Enter once you see your Home timeline... ")

        _goto_home(page)
        time.sleep(5)

        if _is_login_blocked(page):
            _log("Still 'Could not log you in now' after manual login. Stopping.")
            return False

        if _is_login_page(page):
            _log("Login still not successful; stopping to avoid repeated attempts.")
            return False

    _log("✅ Logged in via saved session.")
    return True


# ===== main loop =====


def main_loop() -> None:
    global _prev_media_ts
    _prev_media_ts = 0.0

    with sync_playwright() as p:
        _log("Launching Social Agent (persistent Chrome profile)...")
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            args=["--no-sandbox"],
        )
        page = browser.new_page()

        if not _ensure_logged_in(page):
            try:
                browser.close()
            except Exception:
                pass
            _log("Social Agent stopped (login not available).")
            return

        cycle = 0

        while True:
            try:
                cycle += 1

                _close_center_modals(page)
                _goto_home(page)

                if _is_login_blocked(page):
                    _log("⚠️ 'Could not log you in now' detected mid-run. Exiting cleanly.")
                    break

                if _is_login_page(page):
                    _log("Login lost mid-run. Exiting to avoid hammering.")
                    break

                composer = _get_inline_composer(page)
                if not composer:
                    # Smart handling when composer is missing
                    if _is_login_blocked(page):
                        _log("⚠️ X shows 'Could not log you in now'. Stopping.")
                        break

                    if _is_login_page(page):
                        _log("Detected X login screen while running.")
                        _log("Log in manually in the Chromium window, reach Home, then press Enter here.")
                        input("Press Enter once you see your Home timeline... ")

                        _goto_home(page)
                        time.sleep(5)

                        if _is_login_blocked(page):
                            _log("Still 'Could not log you in now' after manual login. Stopping.")
                            break
                        if _is_login_page(page):
                            _log("Login still not successful; stopping.")
                            break

                        _log("Login successful; resuming.")
                        continue

                    _log("Composer not found; backing off 60s then retrying Home.")
                    time.sleep(60)
                    continue

                # Type a post
                text = _pick_post()
                _log(f"Composing new post (cycle {cycle})...")

                composer.click(timeout=5000)
                # clear existing
                page.keyboard.press("Meta+A")
                page.keyboard.press("Backspace")

                delay = random.uniform(0.03, 0.11)
                for ch in text:
                    page.keyboard.type(ch, delay=delay)

                # maybe attach media
                _attach_media(page)

                # click Post
                posted = False
                try:
                    btn = page.locator(
                        "div[data-testid='tweetButtonInline'], div[data-testid='tweetButton']"
                    ).first
                    if btn and btn.is_enabled():
                        btn.click(timeout=5000)
                        posted = True
                except Exception:
                    posted = False

                if posted:
                    preview = text.replace("\n", " ")
                    if len(preview) > 90:
                        preview = preview[:90] + "..."
                    _log(f"✅ Posted: {preview}")
                else:
                    _log("Post click failed; will retry next cycle.")

                # wait human-ish time
                wait_s = random.randint(MIN_WAIT, MAX_WAIT)
                _log(f"⏱ Waiting {wait_s // 60}m {wait_s % 60:02d}s before next cycle.")
                time.sleep(wait_s)

            except KeyboardInterrupt:
                _log("Stopped by user.")
                break
            except PWTimeoutError as e:
                _log(f"Timeout error: {e}; sleeping 30s then retry.")
                time.sleep(30)
            except Exception as e:
                _log(f"Unexpected error: {e!r}; sleeping 30s then retry.")
                time.sleep(30)

        try:
            browser.close()
        except Exception:
            pass
        _log("Social Agent stopped.")


if __name__ == "__main__":
    main_loop()

