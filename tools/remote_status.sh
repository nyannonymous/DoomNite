# Report what is currently in the R2 bucket, verified against sources.json.
#
#   bash tools/remote_status.sh [bucket]
#
# Lists objects via S3 ListObjectsV2, then cross-checks every object's size
# against sources.json and reports how many bytes are still missing. This is how
# progress gets confirmed during a long upload: it reads the bucket, not the
# upload log, so a silently-dead upload is visible.
#
# Prints only names, sizes, and counts. Never a credential.
set -euo pipefail
BUCKET="${1:-doomnite}"
PACK="$(cd "$(dirname "$0")/.." && pwd)"
ENV="$PACK/.env"
[ -f "$ENV" ] || { echo "no .env in $PACK" >&2; exit 1; }

# Parsed, not sourced -- a .env is not required to be shell-safe.
r2_get() {
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$ENV" \
    | head -1 | tr -d '\r' | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"
}

export R2_ACCOUNT_ID="$(r2_get R2_ACCOUNT_ID)"
export AWS_ACCESS_KEY_ID="$(r2_get AWS_ACCESS_KEY_ID)"
export AWS_SECRET_ACCESS_KEY="$(r2_get AWS_SECRET_ACCESS_KEY)"
export R2_BUCKET="$BUCKET"

PY="${R2_PYTHON:-/c/Users/Serge/AppData/Local/Programs/Python/Python311/python.exe}"
cd "$PACK"
exec "$PY" tools/remote_status.py