SHELL := /bin/bash
PYTHON ?= python3
VENV ?= .venv
VENVPY := $(VENV)/bin/python
PW_PROFILE_DIR ?= .pwprofile_live

.PHONY: deps kill x-login-test start

$(VENVPY):
	$(PYTHON) -m venv "$(VENV)"

deps: $(VENVPY)
	@. "$(VENV)/bin/activate" && python -m pip install --upgrade pip
	@. "$(VENV)/bin/activate" && python -m pip install -r requirements.txt
	@. "$(VENV)/bin/activate" && python -m playwright install chromium

kill:
	@PW_PROFILE_DIR="$(PW_PROFILE_DIR)" scripts/kill_profile.sh "$(PW_PROFILE_DIR)"
	@if [ -f .agent.pid ]; then \
		PID=$$(cat .agent.pid); \
		if kill $$PID 2>/dev/null; then \
			echo "Stopped agent PID $$PID"; \
		fi; \
		rm -f .agent.pid; \
	fi

x-login-test: deps
	@PW_PROFILE_DIR="$$PWD/.pwprofile_login_test" "$(VENVPY)" - <<'LOGIN'
import os
from playwright.sync_api import sync_playwright
from social_agent import launch_ctx, log
from x_login import ensure_x_logged_in, XLoginError

username = os.getenv("X_USERNAME")
password = os.getenv("X_PASSWORD")
alt_identifier = os.getenv("X_ALT_ID") or os.getenv("X_EMAIL")

if not username or not password:
    raise SystemExit("X_USERNAME and X_PASSWORD must be set for x-login-test")

with sync_playwright() as p:
    ctx, page = launch_ctx(p)
    try:
        ensure_x_logged_in(page, username, password, alt_identifier)
        log("Logged in & ready")
    except XLoginError as exc:
        raise SystemExit(str(exc))
    finally:
        try:
            ctx.close()
        except Exception:
            pass
LOGIN

start: deps
	@if [ "${RUN:-}" != "1" ]; then \
		echo "Refusing to start; set RUN=1"; \
		exit 1; \
	fi
	@PW_PROFILE_DIR="$(PW_PROFILE_DIR)" "$(VENVPY)" social_agent.py
