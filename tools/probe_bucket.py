"""Find which R2 bucket this token can reach, and whether we can write to it.

A per-bucket R2 API token is not granted list_buckets (that needs admin), so
there is no way to enumerate. Instead: try to CREATE a bucket, and if that is
refused, probe plausible names with head_bucket until one answers.

Prints only bucket names and result codes. Never a key or secret.
"""
import os
import re
import sys

SEC = os.path.join(os.path.expanduser("~"), "Desktop", "R2 secrets.txt")


def load():
    vals = {}
    for line in open(SEC, encoding="utf-8", errors="replace"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" in s:
            k, v = s.split("=", 1)
        elif ":" in s:
            k, v = s.split(":", 1)
        else:
            continue
        vals[k.strip().strip('"').strip("'").lower()] = v.strip().strip('"').strip("'")
    raw = open(SEC, encoding="utf-8", errors="replace").read()
    key = next((v for k, v in vals.items() if "access key id" in k), None)
    sec = next((v for k, v in vals.items() if k.startswith("secret")), None)
    acct = next((v for k, v in vals.items() if "account" in k), None)
    if not acct:
        m = re.search(r"dash\.cloudflare\.com/([0-9a-f]{32})", raw)
        acct = m.group(1) if m else None
    return key, sec, acct


def main():
    key, sec, acct = load()
    if not (key and sec and acct):
        sys.exit("missing credentials or account id")
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{acct}.r2.cloudflarestorage.com",
        aws_access_key_id=key,
        aws_secret_access_key=sec,
        config=Config(signature_version="s3v4",
                      retries={"max_attempts": 2, "mode": "standard"}),
    )

    print(f"account {acct}\n")
    print("--- list_buckets ---")
    try:
        r = s3.list_buckets()
        names = [b["Name"] for b in r.get("Buckets", [])]
        print(f"  OK, {len(names)} bucket(s): {', '.join(names) or '(none)'}")
        if names:
            for n in names:
                _report(s3, n)
            return 0
    except ClientError as e:
        print(f"  {e.response['Error']['Code']} "
              f"(expected for a per-bucket token)")

    print("\n--- create_bucket probe (name 'doomnite') ---")
    # A token scoped to Object Read&Write on a bucket cannot create one, but a
    # token with admin/storage rights can -- and then we know the exact name we
    # control rather than guessing at one.
    created = False
    try:
        s3.create_bucket(Bucket="doomnite")
        print("  created 'doomnite'")
        created = True
    except ClientError as e:
        print(f"  {e.response['ResponseMetadata']['HTTPStatusCode']} "
              f"{e.response['Error']['Code']}: "
              f"{e.response['Error'].get('Message','')[:90]}")

    print("\n--- head_bucket probe ---")
    cands = ["doomnite", "doom", "doom-pack", "doompack", "doom-nite",
             "wad", "wads", "doom-wads", "doomnite-pack", "r2", "test"]
    if created:
        cands.insert(0, "doomnite")
    found = []
    for b in cands:
        try:
            s3.head_bucket(Bucket=b)
            print(f"  ACCESS  {b}")
            found.append(b)
        except ClientError as e:
            code = e.response["Error"]["Code"]
            st = e.response["ResponseMetadata"]["HTTPStatusCode"]
            print(f"  {st} {code:<22} {b}")
        except Exception as e:
            print(f"  ERR {type(e).__name__} {b}")

    for b in found:
        _report(s3, b)
    return 0


def _report(s3, bucket):
    """Confirm we can actually write, which is what the upload needs."""
    from botocore.exceptions import ClientError
    key = "doomnite/_probe/.keep"
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=b"probe", ContentType="text/plain")
        print(f"  {bucket}: WRITE OK")
        s3.delete_object(Bucket=bucket, Key=key)
        print(f"  {bucket}: delete OK (probe removed)")
    except ClientError as e:
        print(f"  {bucket}: WRITE FAILED "
              f"{e.response['Error']['Code']}")


if __name__ == "__main__":
    sys.exit(main())