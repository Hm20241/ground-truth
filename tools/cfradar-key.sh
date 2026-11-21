#!/bin/bash
# Ground Truth: save a Cloudflare Radar API token where Ground Truth reads it
# (~/.config/cloudflare/radar_token, chmod 600), then check it with Cloudflare. v1.0, 2026-11-21.
# The token must be a Custom Token with Account > Radar > Read (dash.cloudflare.com > My Profile > API Tokens).
# You paste it and it is never shown; the screen and scrollback are cleared afterwards. The check sends it only
# to api.cloudflare.com, from a header file (not the command line), and prints only Cloudflare's verdict.
set -uo pipefail
dir="$HOME/.config/cloudflare"; f="$dir/radar_token"
tty_saved="$(stty -g 2>/dev/null || true)"
hdr=""
restore() { [ -n "$tty_saved" ] && stty "$tty_saved" 2>/dev/null; [ -n "$hdr" ] && rm -f "$hdr"; }
trap restore EXIT INT TERM

echo "Paste your Cloudflare Radar API token and press Return. What you paste stays hidden."
saved=0
for try in 1 2 3; do
  printf "API token: "
  stty -echo 2>/dev/null
  IFS= read -r K
  stty echo 2>/dev/null; echo
  K="$(printf '%s' "$K" | tr -d '[:space:]')"
  if [ ${#K} -lt 30 ] || printf '%s' "$K" | grep -q '[^A-Za-z0-9_-]'; then
    echo "That doesn't look like a Cloudflare API token (one line of letters, digits, - and _). Attempt $try of 3."
    continue
  fi
  mkdir -p "$dir" && chmod 700 "$dir"
  ( umask 077; printf '%s' "$K" > "$f.tmp" ) && mv "$f.tmp" "$f" && chmod 600 "$f" && saved=1
  break
done
len=${#K}; unset K

clear; printf '\033[3J'   # remove the token from the screen and the scrollback
if [ "$saved" != 1 ]; then
  echo "Nothing was saved. Run this again: bash $0"
  exit 1
fi
echo "Saved to $f (chmod 600, $len characters), and cleared from the screen."

hdr="$(umask 077; mktemp)"
printf 'Authorization: Bearer %s\n' "$(cat "$f")" > "$hdr"
v="$(curl -s --max-time 20 -H @"$hdr" https://api.cloudflare.com/client/v4/user/tokens/verify)"
r="$(curl -s --max-time 20 -o /dev/null -w '%{http_code}' -H @"$hdr" \
  'https://api.cloudflare.com/client/v4/radar/annotations/outages?limit=1&format=json')"
rm -f "$hdr"; hdr=""
st="$(printf '%s' "$v" | /usr/bin/python3 -c 'import json,sys
try:
    d = json.load(sys.stdin); print((d.get("result") or {}).get("status") or ("error: " + "; ".join(e.get("message", "") for e in d.get("errors") or [])))
except Exception:
    print("no answer")')"
echo "Cloudflare says the token is: $st. Radar outage annotations: HTTP $r (200 = Radar Read works)."
echo "The token may still be on your clipboard: copy something else to replace it. You can close this tab."
[ "$st" = active ] && [ "$r" = 200 ]
