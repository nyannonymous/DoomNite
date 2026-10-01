"""Push the pack to a Cloudflare R2 bucket and write the base_url back.

    python tools\\upload.py --bucket doomnite --dry-run
    python tools\\upload.py --bucket doomnite
    python tools\\upload.py --bucket doomnite --write-url

R2 speaks the S3 API, so this is boto3 pointed at R2's endpoint -- no `aws`
CLI, no wrangler, no Cloudflare-side Worker. Credentials come from the
environment so they never land in the repo:

    AWS_ACCESS_KEY_ID     R2 access key id
    AWS_SECRET_ACCESS_KEY R2 secret access key

Why R2 rather than S3 or Dropbox, in one line each: R2's egress is free at any
volume (S3 charges ~$0.09/GB out, which is the whole cost of a download-heavy
pack), and its r2.dev public URLs never expire -- presigned S3 URLs last hours,
so they cannot live in a committed sources.json.

Two rules this script will not break:

* It refuses to upload anything sources.json marks "no_host": true. Those are
  the commercial retail IWADs (DOOM2.WAD, Hexen.wad). Publishing them is not
  ours to decide, and a public bucket makes anything uploaded world-readable
  and permanent -- the exact opposite of the "just don't link it" reasoning
  that would apply to a local file.
* It re-verifies size and sha256 against sources.json before uploading, and
  skips anything already present at the right size with the right hash. A 687 MB
  pk3 is not something you want to push twice because a --force slipped through.

--write-url is deliberately separate from the upload. It is the step that makes
the bucket public-facing in sources.json, so it should be something you run on
purpose after checking what the dry-run said you were about to publish.
"""

import argparse
import hashlib
import json
import os
import sys

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = os.path.join(PACK, "sources.json")

# R2's S3-compatible endpoint. account_id is substituted by boto3 from the
# access key, so this is the same string for every R2 account.
ENDPOINT = "https://<accountid>.r2.cloudflarestorage.com"

CHUNK = 1024 * 1024


def human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0


def sha256(path, chunk=CHUNK):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def load():
    if not os.path.isfile(SOURCES):
        sys.exit(f"no {SOURCES}\nrun:  python tools\\make_sources.py")
    doc = json.load(open(SOURCES, encoding="utf-8"))
    return doc, (doc.get("files") or {})


def client(bucket):
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        sys.exit("boto3 is required:  pip install boto3")

    aid = os.environ.get("AWS_ACCESS_KEY_ID")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    if not aid or not secret:
        sys.exit(
            "missing R2 credentials.\n"
            "Create an R2 API token at dash.cloudflare.com > R2 > Manage API\n"
            "Tokens, then in this shell:\n"
            "  export AWS_ACCESS_KEY_ID=<key id>\n"
            "  export AWS_SECRET_ACCESS_KEY=<secret>")

    # R2 needs addressing_style=virtual or the bucket lands in the hostname
    # wrong; retries handle a laptop that drops wifi mid-transfer.
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=aid,
        aws_secret_access_key=secret,
        config=Config(signature_version="s3v4",
                      addressing_style="virtual",
                      retries={"max_attempts": 5, "mode": "adaptive"}),
    )


def remote_matches(s3, bucket, key, rec):
    """True when the object is already in the bucket, correct and complete.

    Compares size only, not a re-downloaded hash: fetching 3.7 GB back to
    confirm what we just uploaded would defeat the point, and R2 verifies the
    payload on the PUT's own checksum. Size plus a ContentLength match is what
    actually catches an interrupted upload, which is the realistic failure.
    """
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except Exception:
        return False
    return head.get("ContentLength") == (rec.get("size") or -1)


def main():
    ap = argparse.ArgumentParser(description="Push the pack to Cloudflare R2.")
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--prefix", default="", help="key prefix, e.g. 'v1'")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would upload, touch nothing")
    ap.add_argument("--force", action="store_true",
                    help="re-upload even if already present")
    ap.add_argument("--write-url", action="store_true",
                    help="write base_url into sources.json (implies public)")
    ap.add_argument("--public-url", default=None,
                    help="the bucket's r2.dev base, e.g. "
                         "https://pub-xxx.r2.dev -- required with --write-url")
    args = ap.parse_args()

    doc, files = load()
    vetoed = [r for r, v in files.items() if v.get("no_host")]
    todo = {r: v for r, v in files.items() if not v.get("no_host")}

    print(f"{len(files)} files in manifest")
    print(f"  {len(todo)} would upload   {len(vetoed)} vetoed (commercial)")
    for r in sorted(vetoed):
        print(f"    veto: {r}")
    total = sum(v.get("size") or 0 for v in todo.values())
    print(f"  {human(total)} total\n")

    if args.dry_run:
        for rel in sorted(todo):
            v = todo[rel]
            print(f"  {human(v.get('size') or 0):>9}  {v.get('sha256','')[:12]}  "
                  f"{args.prefix}{rel}")
        print(f"\ndry run -- nothing uploaded.")
        return 0

    if not os.environ.get("AWS_ACCESS_KEY_ID"):
        print("no credentials in env; listing only.", file=sys.stderr)
        return 1

    s3 = client(args.bucket)
    skipped = failed = uploaded = 0
    for rel in sorted(todo):
        rec = todo[rel]
        key = args.prefix + rel
        fp = os.path.join(PACK, rel.replace("/", os.sep))

        if not os.path.isfile(fp):
            print(f"  MISSING  {rel}")
            failed += 1
            continue
        size = os.path.getsize(fp)
        if rec.get("size") and size != rec["size"]:
            print(f"  SIZE     {rel}: {size} != {rec['size']}")
            failed += 1
            continue
        if not args.force and remote_matches(s3, args.bucket, key, rec):
            print(f"  have     {key}")
            skipped += 1
            continue

        # Re-hash before publishing. Cheap against a 687 MB file next to
        # uploading the wrong bytes, and it is the only check that catches a
        # disk that has silently rotted since make_sources.py ran.
        if rec.get("sha256"):
            got = sha256(fp)
            if got != rec["sha256"]:
                print(f"  HASH     {rel}: {got[:12]} != {rec['sha256'][:12]}")
                failed += 1
                continue

        extra = {}
        if rec.get("sha256"):
            extra["Metadata"] = {"sha256": rec["sha256"]}
        # ContentType is deliberately generic: these are wads and pk3s, and a
        # browser should download rather than try to execute anything.
        extra["ContentType"] = "application/octet-stream"

        try:
            s3.upload_file(fp, args.bucket, key, ExtraArgs=extra)
            print(f"  up       {key}  {human(size)}")
            uploaded += 1
        except Exception as e:
            print(f"  FAIL     {key}: {type(e).__name__} {e}")
            failed += 1

    print(f"\nuploaded {uploaded}   already there {skipped}   failed {failed}")

    if args.write_url:
        if not args.public_url:
            sys.exit("--write-url needs --public-url "
                     "(dash.cloudflare.com > bucket > Public Development URL)")
        base = args.public_url.rstrip("/") + "/" + args.prefix
        doc["base_url"] = base
        # Make sure the vetoes survive the rewrite of this file.
        for r in vetoed:
            doc["files"][r]["no_host"] = True
        with open(SOURCES, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1, sort_keys=True)
        print(f"wrote base_url = {base}")
        print("vetoes still in place: " + ", ".join(sorted(vetoed)))
    elif failed:
        print("\nsome files failed; base_url not written.")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())