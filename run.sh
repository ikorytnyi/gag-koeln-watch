#!/usr/bin/env bash
# One full monitoring run: fetch listings, diff against state in the
# `claude/state` branch, notify Telegram about new ones, push updated state.
#
# Usage: TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... ./run.sh
#
# Order matters: state is pushed only after the Telegram message was sent,
# so a failed send is retried on the next run instead of being lost.
set -euo pipefail

: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is not set}"
: "${TELEGRAM_CHAT_ID:?TELEGRAM_CHAT_ID is not set}"

# The routine's cron is in UTC and covers both CEST and CET (06-17 UTC);
# only run inside the 08:xx-18:xx Europe/Berlin window, so DST needs no
# manual cron changes. Without tzdata TZ silently falls back to UTC, so
# the check is skipped (run anyway) unless the zone resolves to CET/CEST.
hour=$(TZ=Europe/Berlin date +%-H)
zone=$(TZ=Europe/Berlin date +%Z)
if [[ "$zone" == CET || "$zone" == CEST ]] && { [ "$hour" -lt 8 ] || [ "$hour" -gt 18 ]; }; then
  echo "Outside Berlin 08-18 window (now ${hour}:xx Europe/Berlin), skipping"
  exit 0
fi

BRANCH=claude/state
cd "$(dirname "$0")"

STATE_DIR=$(mktemp -d)
trap 'git worktree remove --force "$STATE_DIR" >/dev/null 2>&1 || true' EXIT

git fetch --quiet origin "$BRANCH"
git worktree add --quiet -B "$BRANCH" "$STATE_DIR" FETCH_HEAD

report=$(python3 check.py --state "$STATE_DIR/seen.json")

if [ -n "$report" ]; then
  curl -fsS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=${report}" >/dev/null
  echo "Telegram: sent"
  echo "$report"
else
  echo "Telegram: no new listings, nothing sent"
fi

cd "$STATE_DIR"
git add seen.json
if git diff --cached --quiet; then
  echo "State: unchanged, nothing to push"
  exit 0
fi

git config user.name >/dev/null || git config user.name "gag-koeln-watch"
git config user.email >/dev/null || git config user.email "gag-koeln-watch@users.noreply.github.com"

count=$(python3 -c 'import json; print(len(json.load(open("seen.json"))))')
git commit --quiet -m "State $(date -u +%Y-%m-%dT%H-%M): ${count} listings"
git push --quiet origin "HEAD:${BRANCH}"
echo "State: pushed to ${BRANCH} (${count} listings)"
