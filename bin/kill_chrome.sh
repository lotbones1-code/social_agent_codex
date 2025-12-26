#!/usr/bin/env bash
set -euo pipefail

pkill -9 -f 'Google Chrome' || true
pkill -9 -f 'Chromium' || true
pkill -9 -f 'chrome --type' || true
pkill -9 -f 'crashpad' || true
