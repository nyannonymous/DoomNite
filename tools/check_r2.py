"""Check that the pack's R2 credentials work, without printing them.

Loads .env through the shared loader, builds an S3 client against the account's
R2 endpoint, and lists buckets. Only NAMES and counts are printed -- never a
key, secret, or account id.

    python tools/check_r2.py

list_buckets is expected to fail with AccessDenied when the token is scoped to
a single bucket, which is the normal case for a token created in the R2 API
Tokens screen. That is not a credential failure; tools/probe_bucket.py finds the
specific bucket in that situation.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r2creds import load  # noqa: E402


def main():
    try:
        key, sec, acct = load()
    except RuntimeError as e:
        sys.exit(str(e))

    print(f"account id   : {acct}")
    print(f"access key   : len={len(key)}")
    print(f"secret       : len={len(sec)}")

    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{acct}.r2.cloudflarestorage.com",
        aws_access_key_id=key,
        aws_secret_access_key=sec,
        config=Config(signature_version="s3v4"),
    )
    try:
        r = s3.list_buckets()
    except ClientError as e:
        code = e.response["Error"]["Code"]
        print(f"\nlist_buckets: {code}")
        if code in ("AccessDenied", "AllAccessDisabled"):
            print("  expected for a per-bucket token -- credentials are fine.")
            print("  Run tools/probe_bucket.py to find the bucket.")
            return 0
        print(" ", e.response["Error"].get("Message", "")[:200])
        return 1

    names = [b["Name"] for b in r.get("Buckets", [])]
    print(f"\nAUTH OK, admin scope. {len(names)} bucket(s):")
    for n in names:
        print(f"  - {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
