SHELL := /bin/bash
PYTHON ?= python3
VENV ?= .venv
VENVPY := $(VENV)/bin/python

.PHONY: deps kill start tail restart clean_profile

deps:
	@if [ ! -d "$(VENV)" ]; then \
	"$(PYTHON)" -m venv "$(VENV)"; \
	fi
	@. "$(VENV)/bin/activate" && python -m pip install --upgrade pip
	@. "$(VENV)/bin/activate" && python -m pip install -r requirements.txt
	@. "$(VENV)/bin/activate" && python -m pip install playwright==1.49.0
	@. "$(VENV)/bin/activate" && python -m playwright install chromium

kill:
	@bash bin/kill_chrome.sh
	@if [ -f .agent.pid ]; then \
	PID=$$(cat .agent.pid); \
	if kill $$PID 2>/dev/null; then \
	echo "Stopped agent PID $$PID"; \
	fi; \
	rm -f .agent.pid; \
	fi

start: deps kill
	@EPOCH_VALUE=$${EPOCHSECONDS:-}; \
	if [ -z "$$EPOCH_VALUE" ]; then \
		EPOCH_VALUE=`date +%s`; \
	fi; \
	PW_PROFILE_DIR=".pwprofile_$$EPOCH_VALUE"; \
	mkdir -p "$$PW_PROFILE_DIR"; \
	rm -f "$$PW_PROFILE_DIR"/Singleton*; \
	ln -sfn "$$PWD/$$PW_PROFILE_DIR" "$$HOME/.pw-chrome-referral"; \
	mkdir -p logs; \
	touch logs/session.log; \
	nohup env PW_PROFILE_DIR="$$PWD/$$PW_PROFILE_DIR" "$(VENVPY)" social_agent.py >> logs/session.log 2>&1 & \
	APP_PID=$$!; \
	echo $$APP_PID > .agent.pid; \
	echo "Started social_agent.py with PID $$APP_PID using profile $$PW_PROFILE_DIR"; \
	sleep 2; \
	tail -n 160 logs/session.log

tail:
	@if [ -f logs/session.log ]; then \
		tail -n 160 logs/session.log; \
	else \
		echo "logs/session.log not found"; \
	fi

restart: kill start

clean_profile:
	@rm -rf .pwprofile .pwprofile_* "$$HOME/.pw-chrome-referral"
