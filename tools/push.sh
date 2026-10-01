# Push the pack to Cloudflare R2.
#
#   bash tools/push.sh [extra upload.py args...]
#
# Credentials come from the secrets file on the Desktop and are exported into
# this shell only -- they are never echoed, logged, or passed on a command line
# where they would land in shell history. The account id is read from the same
# file token-URL line, since the S3 endpoint cannot do without it.
#
# This pushes objects but does NOT make anything public. Publishing the
# base_url into sources.json is a separate, deliberate step:
#   python tools/upload.py --bucket doomnite --write-url --public-url <url>
set -euo pipefail

SEC="$HOME/Desktop/R2 secrets.txt"
[ -f "$SEC" ] || { echo "no secrets file at $SEC" >&2; exit 1; }

export AWS_ACCESS_KEY_ID="$(sed -n 's/^Access Key ID=//p' "$SEC" | head -1 | tr -d '\r')"
export AWS_SECRET_ACCESS_KEY="$(sed -n 's/^Secret Access Key=//p' "$SEC" | head -1 | tr -d '\r')"
export R2_ACCOUNT_ID="$(sed -n 's#.*dash\.cloudflare\.com/\([0-9a-f]\{32\}\).*#\1#p' "$SEC" | head -1 | tr -d '\r')"

for v in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY R2_ACCOUNT_ID; do
  [ -n "${!v}" ] || { echo "could not read $v from the secrets file" >&2; exit 1; }
done

# Report only lengths. Never print a credential.
echo "creds loaded: key=${#AWS_ACCESS_KEY_ID} secret=${#AWS_SECRET_ACCESS_KEY} account=${#R2_ACCOUNT_ID} chars"

PY="/c/Users/Serge/AppData/Local/Programs/Python/Python311/python.exe"
cd "$(dirname "$0")/.."
exec "$PY" tools/upload.py "$@"