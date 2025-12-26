.PHONY: deps kill x-login-test start

deps:
	python3 -m venv venv && source venv/bin/activate && \
	pip install -U pip wheel setuptools && \
	pip install -r requirements.txt && \
	python -m playwright install chromium

kill:
	pkill -f 'social_agent.py' || true
	osascript -e 'quit app "Google Chrome"' || true
	pkill -9 -f 'Google Chrome Helper' || true
	pkill -9 -f 'Chrom(e|ium)' || true
	pkill -9 -f 'crashpad|playwright' || true
	rm -rf .pwprofile_live/Singlet* "$$HOME/Library/Application Support/Chromium/Singleton*" "$$HOME/.config/chromium/Singleton*" 2>/dev/null || true

x-login-test:
	# launches normal Chrome on our profile so user can login once
	export PW_PROFILE_DIR="$$(pwd)/.pwprofile_live"; \
	open -n -a "Google Chrome" --args --user-data-dir="$$PW_PROFILE_DIR"

start:
	bash ./run.sh
