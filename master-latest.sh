#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
KEY="$(cat "$HOME/.roex-key")"
SRC="${1:-}"

if [ -z "$SRC" ]; then
  SRC="$(ls -t /sdcard/Download/*.wav /sdcard/Download/*.wave \
              /sdcard/Download/*.mp3 /sdcard/Download/*.flac 2>/dev/null \
        | grep -viE '_MASTER|roex|_LOW\.|_HIGH\.|_MEDIUM\.' | head -1 || true)"
fi

[ -n "$SRC" ] && [ -f "$SRC" ] || { echo "No audio found. Usage: ./master-latest.sh '/sdcard/Download/Song.wav'"; exit 1; }

base="$(basename "$SRC")"; base="${base%.*}"
OUT="/sdcard/Download/${base}_MASTER.wav"

echo "INPUT : $SRC"
echo "OUTPUT: $OUT  (AFROBEAT / HIGH)"
echo

ROEX_API_KEY="$KEY" LOUDNESS=HIGH node master.mjs "$SRC" --save "$OUT"

echo
ls -lh "$OUT"
echo "→ Saved to your phone: $OUT"
