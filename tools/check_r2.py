"""Check R2 credentials from Desktop\\R2 secrets.txt without printing them.

Reads the two-line secrets file, resolves the account id, and lists buckets.
Only NAMES and counts are printed -- never a key, secret, or token.
"""
import os
import re
import sys

SECRETS = os.path.join(os.path.expanduser("~"), "Desktop", "R2 secrets.txt")

def load():
    vals = {}
    if not os.path.isfile(SECRETS):
        sys.exit(f"no secrets file at {SECRETS}")
    for line in open(SECRETS, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
        elif ":" in line:
            k, v = line.split(":", 1)
        else:
            continue
        vals[k.strip().strip('"').strip("'").lower()] = v.strip().strip('"').strip("'")
    # Match on the distinctive word in each label, not a substring of the other:
    # "secret access key" contains "access key", so filtering on the latter
    # first would swallow both lines and leave nothing.
    key = next((v for k, v in vals.items() if "access key id" in k), None)
    sec = next((v for k, v in vals.items() if k.startswith("secret")), None)
    acct = next((v for k, v in vals.items() if "account" in k), None)
    bucket = next((v for k, v in vals.items() if "bucket" in k), None)
    # The token-creation success URL carries the account id in its path
    # (https://dash.cloudflare.com/<account_id>/r2/api-tokens/success). That is
    # where this script gets it when the file has no explicit Account ID line,
    # which is the one value the S3 endpoint cannot do without and the API token
    # is not permitted to ask for.
    if not acct:
        m = re.search(r"dash\.cloudflare\.com/([0-9a-f]{32})",
                      " ".join(list(vals.values()) + list(vals.keys())))
        if m:
            acct = m.group(1)
            print(f"account id   : {acct}  (from the token URL)")
    if not key or not sec:
        sys.exit("could not find Access Key ID / Secret Access Key in the file")
    return key, sec, acct, bucket

key, sec, acct_file, bucket_file = load()
print(f"access key : len={len(key)}")
print(f"secret     : len={len(sec)}")
print(f"account id : {acct_file or '(not in file)'}")
print(f"bucket     : {bucket_file or '(not in file)'}")

# The account id is required in the S3 endpoint hostname. The API token is not
# the S3 key, so if the file lacks it we cannot talk to R2 at all.
if not acct_file:
    print("\nNo Cloudflare account id in the file.")
    print("R2's S3 endpoint is https://<accountid>.r2.cloudflarestorage.com")
    print("Account id: dash.cloudflare.com > R2 > Account > Account ID")
    sys.exit(2)

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{acct_file}.r2.cloudflarestorage.com",
    aws_access_key_id=key,
    aws_secret_access_key=sec,
    config=Config(signature_version="s3v4"),
)
try:
    r = s3.list_buckets()
except ClientError as e:
    print(f"\nlist_buckets FAILED: {e.response['Error']['Code']}")
    print(e.response["Error"].get("Message", "")[:200])
    sys.exit(1)

names = [b["Name"] for b in r.get("Buckets", [])]
print(f"\nAUTH OK. {len(names)} bucket(s):")
for n in names:
    print(f"  - {n}")