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
SEC="$HOME/Desktop/R2 secrets.txt"

export AWS_ACCESS_KEY_ID="$(sed -n 's/^Access Key ID=//p' "$SEC" | head -1 | tr -d '\r')"
export AWS_SECRET_ACCESS_KEY="$(sed -n 's/^Secret Access Key=//p' "$SEC" | head -1 | tr -d '\r')"
export R2_ACCOUNT_ID="$(sed -n 's#.*dash\.cloudflare\.com/\([0-9a-f]\{32\}\).*#\1#p' "$SEC" | head -1 | tr -d '\r')"
export R2_BUCKET="$BUCKET"

PY="/c/Users/Serge/AppData/Local/Programs/Python/Python311/python.exe"
cd "$(dirname "$0")/.."
exec "$PY" tools/remote_status.py