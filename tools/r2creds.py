"""Load R2 credentials from the pack's .env.

Kept in one place so tools/push.sh, check_r2.py, probe_bucket.py and
remote_status.py do not each grow their own half-correct parser. Values are
returned, never printed; callers report only lengths.

.env is the source of truth. The original Desktop "R2 secrets.txt" was a
bootstrapping convenience and can be deleted -- if the scripts still needed it
they would fail here rather than silently fall back.

    from r2creds import load
    key, sec, acct = load()
"""
import os
import re

# Pack root, i.e. the parent of tools/.
PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(PACK, ".env")


def _parse(text):
    vals = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" in s:
            k, v = s.split("=", 1)
        elif ":" in s:
            k, v = s.split(":", 1)
        else:
            continue
        k = k.strip().strip('"').strip("'").strip()
        if k:
            vals[k.lower()] = v.strip().strip('"').strip("'")
    return vals


def load(env_path=None):
    """Return (access_key_id, secret_access_key, account_id).

    Raises RuntimeError naming the missing variable rather than returning
    None: a half-configured upload is worse than a loud failure, since the
    alternative is boto3 quietly targeting AWS S3 instead of R2.
    """
    path = env_path or ENV
    if not os.path.isfile(path):
        raise RuntimeError(
            f"no {os.path.basename(path)} in the pack root.\n"
            "Create it with:\n"
            "  R2_ACCOUNT_ID=<32 hex from dash.cloudflare.com > R2>\n"
            "  AWS_ACCESS_KEY_ID=<R2 access key id>\n"
            "  AWS_SECRET_ACCESS_KEY=<R2 secret access key>\n"
            "(R2 > Manage API Tokens > Create, scoped to the bucket.)")

    raw = open(path, encoding="utf-8", errors="replace").read()
    vals = _parse(raw)

    key = vals.get("aws_access_key_id") or vals.get("r2_access_key_id")
    sec = vals.get("aws_secret_access_key") or vals.get("r2_secret_access_key")
    acct = vals.get("r2_account_id")

    # Fall back to the account id embedded in a token-creation URL, because
    # people paste that line out of the dashboard and it is the one value that
    # cannot be derived from the key itself.
    if not acct:
        m = re.search(r"dash\.cloudflare\.com/([0-9a-f]{32})", raw)
        acct = m.group(1) if m else None

    missing = [n for n, v in (("AWS_ACCESS_KEY_ID", key),
                               ("AWS_SECRET_ACCESS_KEY", sec),
                               ("R2_ACCOUNT_ID", acct)) if not v]
    if missing:
        raise RuntimeError(f"{os.path.basename(path)} is missing: "
                           + ", ".join(missing))
    return key, sec, acct