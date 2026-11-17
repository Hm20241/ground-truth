#!/bin/bash
# Ground Truth: save the AISStream.io API key where Ground Truth reads it
# (~/.config/aisstream/key, chmod 600). v1.0, 2026-11-16.
# You paste the key and it is never shown; the screen and scrollback are cleared afterwards.
# A container deployment reads it from $GT_SEED/aisstream.key instead (never printed).
set -uo pipefail
dir="$HOME/.config/aisstream"; f="$dir/key"

echo "Paste your AISStream API key (from aisstream.io > API Keys) and press Return."
echo "What you paste stays hidden."
saved=0
for try in 1 2 3; do
  read -rs -p "API key: " K; echo
  K="$(printf '%s' "$K" | tr -d '[:space:]')"
  if [ ${#K} -lt 20 ]; then echo "That's too short to be the key (attempt $try of 3)."; continue; fi
  mkdir -p "$dir" && chmod 700 "$dir"
  ( umask 077; printf '%s' "$K" > "$f.tmp" ) && mv "$f.tmp" "$f" && chmod 600 "$f" && saved=1
  break
done
unset K

clear; printf '\033[3J'   # remove the key from the screen and the scrollback
if [ "$saved" = 1 ]; then
  echo "Saved to $f (chmod 600), and cleared from the screen. You can close this tab."
else
  echo "Nothing was saved. Run this again: bash $0"
  exit 1
fi
