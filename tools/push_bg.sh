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
ENV="$PACK/.env"
LOG="$PACK/upload.log"

[ -f "$ENV" ] || { echo "no .env in $PACK" >&2; exit 1; }

# Parsed, not sourced -- a .env is not required to be shell-safe.
r2_get() {
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$ENV" \
    | head -1 | tr -d '\r' | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"
}

export R2_ACCOUNT_ID="$(r2_get R2_ACCOUNT_ID)"
export AWS_ACCESS_KEY_ID="$(r2_get AWS_ACCESS_KEY_ID)"
export AWS_SECRET_ACCESS_KEY="$(r2_get AWS_SECRET_ACCESS_KEY)"

for v in R2_ACCOUNT_ID AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY; do
  [ -n "${!v}" ] || { echo "$v missing from .env" >&2; exit 1; }
done

PY="${R2_PYTHON:-/c/Users/Serge/AppData/Local/Programs/Python/Python311/python.exe}"
cd "$PACK"

echo "creds loaded (lengths only): key=${#AWS_ACCESS_KEY_ID} secret=${#AWS_SECRET_ACCESS_KEY} account=${#R2_ACCOUNT_ID}"
echo "logging to $LOG"

# Unbuffered, line-buffered log, no pipe. Already-uploaded files are skipped by
# the size check in upload.py, so this is safe to re-run after any interruption.
"$PY" -u tools/upload.py "$@" >>"$LOG" 2>&1

echo "upload finished; tail of log:"
tail -5 "$LOG"