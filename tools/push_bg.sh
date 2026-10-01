# Run the R2 upload to completion, logging progress to a file.
#
#   bash tools/push_bg.sh
#
# Two differences from tools/push.sh, both learned the hard way:
#
# 1. python -u. Without it stdout is block-buffered when piped, so the log
#    shows nothing for minutes and a stalled upload is indistinguishable from a
#    slow one. This writes each line as it happens.
# 2. Log to a file, not through `tail`. Piping to tail buffers everything until
#    the process exits, which defeats the point of watching progress.
set -euo pipefail

PACK="$(cd "$(dirname "$0")/.." && pwd)"
SEC="$HOME/Desktop/R2 secrets.txt"
LOG="$PACK/upload.log"

[ -f "$SEC" ] || { echo "no secrets file at $SEC" >&2; exit 1; }

export AWS_ACCESS_KEY_ID="$(sed -n 's/^Access Key ID=//p' "$SEC" | head -1 | tr -d '\r')"
export AWS_SECRET_ACCESS_KEY="$(sed -n 's/^Secret Access Key=//p' "$SEC" | head -1 | tr -d '\r')"
export R2_ACCOUNT_ID="$(sed -n 's#.*dash\.cloudflare\.com/\([0-9a-f]\{32\}\).*#\1#p' "$SEC" | head -1 | tr -d '\r')"

for v in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY R2_ACCOUNT_ID; do
  [ -n "${!v}" ] || { echo "could not read $v from the secrets file" >&2; exit 1; }
done

PY="/c/Users/Serge/AppData/Local/Programs/Python/Python311/python.exe"
cd "$PACK"

echo "creds loaded (lengths only): key=${#AWS_ACCESS_KEY_ID} secret=${#AWS_SECRET_ACCESS_KEY} account=${#R2_ACCOUNT_ID}"
echo "logging to $LOG"

# Unbuffered, line-buffered log, no pipe. Already-uploaded files are skipped by
# the size check in upload.py, so this is safe to re-run after any interruption.
"$PY" -u tools/upload.py "$@" >>"$LOG" 2>&1

echo "upload finished; tail of log:"
tail -5 "$LOG"