#!/bin/bash
# Ground Truth analyst: get a long-lived Claude token on your subscription and save it where the
# runner reads it (~/.config/ground-truth/claude_token, chmod 600). v1.0, 2026-11-15.
# You paste the token and it is never shown; the screen and scrollback are cleared afterwards,
# so the token isn't left on screen. Re-run this to renew it (the token lasts about a year) or
# after switching Claude accounts.
set -uo pipefail
dir="$HOME/.config/ground-truth"; f="$dir/claude_token"

echo "Step 1 of 2: sign in. In the browser, choose \"Sign in with Claude.ai\" (not Console / API key)."
echo
if ! /opt/homebrew/bin/claude setup-token; then
  echo; echo "setup-token did not finish, so nothing was saved. Run this again when ready."; exit 1
fi

echo
echo "Step 2 of 2: copy the token printed above (it starts with sk-ant-) and paste it here."
echo "What you paste stays hidden; just press Return after pasting."
saved=0
for try in 1 2 3; do
  read -rs -p "Paste token: " T; echo
  T="$(printf '%s' "$T" | tr -d '[:space:]')"
  if [ ${#T} -lt 40 ]; then echo "That's too short to be the token (attempt $try of 3)."; continue; fi
  case "$T" in sk-ant-*) ;; *) echo "Note: it doesn't start with sk-ant-, saving it anyway." ;; esac
  mkdir -p "$dir" && chmod 700 "$dir"
  ( umask 077; printf '%s' "$T" > "$f.tmp" ) && mv "$f.tmp" "$f" && chmod 600 "$f" && saved=1
  break
done
unset T

clear; printf '\033[3J'   # remove the token from the screen and the scrollback
if [ "$saved" = 1 ]; then
  echo "Saved to $f (chmod 600), and cleared from the screen."
  echo "Claude Code will pick it up and run the first real analysis. You can close this tab."
else
  echo "Nothing was saved. Run this again: bash $0"
  exit 1
fi
