#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <profile_dir>" >&2
}

if [ "$#" -lt 1 ] || [ -z "${1:-}" ]; then
  usage
  exit 1
fi

profile_dir="${1}"
# Resolve to absolute path for reliable matching
if [ ! "${profile_dir}" = "/" ] && [ -d "${profile_dir}" ]; then
  profile_dir="$(cd "${profile_dir}" && pwd)"
else
  profile_dir="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "${profile_dir}")"
fi

if [ -z "${profile_dir}" ]; then
  exit 0
fi

pids=$(ps -eo pid=,args= | grep -F "${profile_dir}" | grep -E "(chrome|chromium|playwright)" | awk '{print $1}' || true)

if [ -n "${pids}" ]; then
  while IFS= read -r pid; do
    if [ -n "${pid}" ]; then
      kill "${pid}" 2>/dev/null || true
    fi
  done <<< "${pids}"
  sleep 1
  # Force kill any remaining processes
  remaining=$(ps -eo pid=,args= | grep -F "${profile_dir}" | grep -E "(chrome|chromium|playwright)" | awk '{print $1}' || true)
  if [ -n "${remaining}" ]; then
    while IFS= read -r pid; do
      if [ -n "${pid}" ]; then
        kill -9 "${pid}" 2>/dev/null || true
      fi
    done <<< "${remaining}"
  fi
fi

if [ -d "${profile_dir}" ]; then
  find "${profile_dir}" -maxdepth 1 -type f -name 'Singleton*' -exec rm -f {} + 2>/dev/null || true
fi

exit 0
