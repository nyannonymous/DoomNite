# Push the pack to Cloudflare R2.
#
#   bash tools/push.sh [extra upload.py args...]
#
# Credentials come from the pack's .env, which is gitignored. They are exported
# into this shell only and never echoed, never passed on a command line where
# they would land in shell history, and never printed -- only lengths are.
#
# This pushes objects but does NOT make anything public. Publishing the
# base_url into sources.json is a separate, deliberate step:
#   python tools/upload.py --bucket doomnite --write-url --public-url <url>
set -euo pipefail

PACK="$(cd "$(dirname "$0")/.." && pwd)"
ENV="$PACK/.env"
[ -f "$ENV" ] || { echo "no .env in $PACK" >&2; exit 1; }

# Read the three values without sourcing the file: sourcing would execute
# whatever else is in it, and a .env is not guaranteed to be shell-safe.
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

# Report only lengths. Never print a credential.
echo "creds loaded from .env (lengths only): account=${#R2_ACCOUNT_ID} key=${#AWS_ACCESS_KEY_ID} secret=${#AWS_SECRET_ACCESS_KEY}"

PY="${R2_PYTHON:-/c/Users/Serge/AppData/Local/Programs/Python/Python311/python.exe}"
cd "$PACK"
exec "$PY" tools/upload.py "$@"