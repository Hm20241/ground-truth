#!/bin/bash
# Ground Truth: save the Global Fishing Watch API token where Ground Truth reads it
# (~/.config/globalfishingwatch/key, chmod 600). v1.0, 2026-11-16.
# You paste the token and it is never shown; the screen and scrollback are cleared afterwards.
# GFW tokens are long (several hundred characters), longer than macOS lets a normal
# terminal line hold, so the terminal is switched to character mode while you paste.
# A container deployment reads it from $GT_SEED/gfw.key instead (never printed).
set -uo pipefail
dir="$HOME/.config/globalfishingwatch"; f="$dir/key"
tty_saved="$(stty -g 2>/dev/null || true)"
restore() { [ -n "$tty_saved" ] && stty "$tty_saved" 2>/dev/null; }
trap restore EXIT INT TERM

echo "Paste your Global Fishing Watch API token (globalfishingwatch.org/our-apis/tokens) and press Return."
echo "What you paste stays hidden."
saved=0
for try in 1 2 3; do
  printf "API token: "
  stty -echo -icanon min 1 time 0 2>/dev/null
  IFS= read -r K
  restore; echo
  K="$(printf '%s' "$K" | tr -d '[:space:]')"
  dots="$(printf '%s' "$K" | tr -cd '.' | wc -c | tr -d ' ')"
  if [ ${#K} -lt 100 ] || [ "$dots" != 2 ]; then
    echo "That doesn't look like a whole token (it should be one long line with two dots). Attempt $try of 3."
    continue
  fi
  mkdir -p "$dir" && chmod 700 "$dir"
  ( umask 077; printf '%s' "$K" > "$f.tmp" ) && mv "$f.tmp" "$f" && chmod 600 "$f" && saved=1
  break
done
len=${#K}; unset K

clear; printf '\033[3J'   # remove the token from the screen and the scrollback
if [ "$saved" = 1 ]; then
  echo "Saved to $f (chmod 600, $len characters), and cleared from the screen."
  echo "The token may still be on your clipboard: copy something else to replace it. You can close this tab."
else
  echo "Nothing was saved. Run this again: bash $0"
  exit 1
fi
