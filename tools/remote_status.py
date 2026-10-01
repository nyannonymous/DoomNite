"""Compare the R2 bucket against sources.json.

Reports, from the bucket side: how many expected objects are present, how many
bytes, and which files are missing or the wrong size. Vetoed files are expected
to be absent and are not counted as failures.

Run via tools/remote_status.sh, which supplies the credentials and bucket.
"""
import json
import os
import sys

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0


def main():
    bucket = os.environ.get("R2_BUCKET", "doomnite")
    acct = os.environ["R2_ACCOUNT_ID"]
    doc = json.load(open(os.path.join(PACK, "sources.json"), encoding="utf-8"))
    files = doc["files"]
    want = {r: v for r, v in files.items() if not v.get("no_host")}
    vetoed = {r for r, v in files.items() if v.get("no_host")}

    import boto3
    from botocore.config import Config
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{acct}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4",
                      retries={"max_attempts": 3, "mode": "standard"}),
    )

    # ListObjectsV2 is paginated at 1000; the pack is 66 objects but be correct
    # anyway rather than silently truncating if it grows.
    have = {}
    token = None
    while True:
        kw = dict(Bucket=bucket, MaxKeys=1000)
        if token:
            kw["ContinuationToken"] = token
        r = s3.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            have[o["Key"]] = o["Size"]
        if not r.get("IsTruncated"):
            break
        token = r.get("NextContinuationToken")
        if not token:
            break

    print(f"bucket {bucket}: {len(have)} object(s), {human(sum(have.values()))}\n")

    ok, bad_size, absent = [], [], []
    for rel, rec in want.items():
        size = rec.get("size")
        if rel not in have:
            absent.append(rel)
        elif size is not None and have[rel] != size:
            bad_size.append((rel, have[rel], size))
        else:
            ok.append(rel)

    total = sum(v.get("size") or 0 for v in want.values())
    # Tally only what actually landed. Summing every wanted file regardless of
    # presence reports "3.4 GB of 3.4 GB" when one object is up, which is worse
    # than no progress line at all -- it hides a stalled upload.
    got = sum((want[r].get("size") or 0) for r in want if r in have)
    pct = (100.0 * len(ok) / len(want)) if want else 0.0
    print(f"  complete      {len(ok)}/{len(want)} ({pct:.0f}%)   "
          f"{human(got)} of {human(total)}")
    if bad_size:
        print(f"\n  WRONG SIZE ({len(bad_size)}):")
        for rel, g, w in bad_size:
            print(f"    {rel}: remote {g} != manifest {w}")
    if absent:
        print(f"\n  missing ({len(absent)}):")
        for rel in absent[:12]:
            print(f"    {rel}  {human(want[rel].get('size') or 0)}")
        if len(absent) > 12:
            print(f"    ... and {len(absent) - 12} more")

    stray = [k for k in have if k not in files]
    if stray:
        print(f"\n  not in manifest ({len(stray)}): {stray[:5]}")

    # The veto must be enforced on the far side too, not just at upload time.
    leaked = [r for r in vetoed if r in have]
    print(f"\n  vetoed files in bucket: {len(leaked)} "
          + ("LEAK: " + ", ".join(leaked) if leaked else "(correct -- none)"))

    return 0 if not absent and not bad_size and not leaked else 1


if __name__ == "__main__":
    sys.exit(main())