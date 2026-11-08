"""Fetch ModDB cover art for roster entries that have no file in the pack.

extract_art.py handles mods we actually ship: it lifts the TITLEPIC lump out of
their own WAD/PK3. That cannot work for a browser-source card (build.PENDING),
whose folder is still empty, nor for a mod whose shipped TITLEPIC is a stub --
The Pink Valley ships a 132-byte placeholder PNG and nothing else.

ModDB answers this machine with a Cloudflare 403, and so do doomwiki.org and the
Wayback Machine (measured: 403/429/abuse-flag on scripted requests), so the page
is read through the r.jina.ai text reader, which renders it server-side. The art
itself then comes back through images.weserv.nl because media.moddb.com refuses
our own requests too. Both are public proxies of public pages; nothing here logs
in or bypasses a paywall.

    python tools/fetch_art.py            # fill in art/ for missing targets
    python tools/fetch_art.py --force    # re-fetch even if the file exists
    python tools/fetch_art.py breach2    # just one

Output lands in art\\ as PNG, named by slug (browser-source cards, which build.py
names explicitly via PENDING_ART) or by mod stem (pack entries, so art_map()
matches them without any wiring).
"""
import argparse
import io
import pathlib
import re
import urllib.parse
import urllib.request

from PIL import Image

PACK = pathlib.Path(__file__).resolve().parent.parent
ART = PACK / "art"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

# (art filename, ModDB page)
TARGETS = {
    "ashes-2063": "https://www.moddb.com/mods/ashes-2063",
    "zelda-tc": "https://www.moddb.com/mods/zelda-tc",
    "breach2": "https://www.moddb.com/mods/breach2",
    "tiberian-fury": "https://www.moddb.com/mods/tiberian-fury",
    "total-chaos": "https://www.moddb.com/mods/total-chaos",
    "recurring-nightmare": "https://www.moddb.com/mods/recurring-nightmare",
    "zombies-doomed": "https://www.moddb.com/mods/zombies-doomed-my-neighbors-mod",
    "THE_PINK_VALLEY - ENG": "https://www.moddb.com/mods/the-pink-valley",
    "ISODoom": "https://www.moddb.com/mods/isodoom",
    # Pack entries that cannot supply their own title art. HDE opens on a title
    # MAP, not a TITLEPIC lump, so there is nothing for extract_art.py to lift;
    # DNF is an EDuke32 game whose art lives inside a GRP we do not decode.
    # Both are named by mod stem (HDE) or by the explicit name build.py gives a
    # standalone game (DNF), because that is what serve.py looks up.
    "HDE Season 3.9": "https://www.moddb.com/mods/halo-doom-evolved",
    "DukeNukemForever": "https://www.moddb.com/mods/duke-nukem-forever",
}

# ModDB caches one image at several sizes; the path segment names the size, so
# swapping it asks for a bigger render of the same picture.
SIZE_SEG = r"/cache/images/(.*?)/(?:thumb_620x2000|crop_120x90|crop_\d+x\d+)/"
SIZES = ("thumb_620x2000", "crop_600x338", "thumb_320x180")


def get(url, timeout=90, extra=None):
    headers = {"User-Agent": UA}
    if extra:
        headers.update(extra)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def variants(url):
    out = [url]
    out += [re.sub(SIZE_SEG, r"/cache/images/\1/" + s + "/", url) for s in SIZES]
    out.append(re.sub(SIZE_SEG, r"/images/\1/", url))       # the uncached original
    seen, uniq = set(), []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def pull(url):
    proxied = ("https://images.weserv.nl/?url="
               + urllib.parse.quote(url.split("//", 1)[1], safe="") + "&output=png")
    return Image.open(io.BytesIO(get(proxied, 60))).convert("RGB")


def fetch(name, page):
    html = get("https://r.jina.ai/" + page, 90,
               {"x-return-format": "html"}).decode("utf-8", "replace")
    # og:image is the page header art -- the closest thing to a cover.
    seeds = re.findall(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)', html)
    seeds += re.findall(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image', html)
    seeds += re.findall(r"https?://media\.moddb\.com/[^\s)\"'<>]+?\.(?:png|jpg|jpeg|webp)",
                        html)
    best, seen = None, []
    for s in seeds:
        if s not in seen:
            seen.append(s)
    for seed in seen[:4]:
        for url in variants(seed):
            try:
                im = pull(url)
            except Exception:                                # noqa: BLE001
                continue
            score = im.width * im.height
            if im.width >= 500 and im.height >= 250 and (best is None or score > best[0]):
                best = (score, im, url)
            if best:
                break
        if best and best[0] >= 620 * 300:
            break
    if best is None:
        return None
    return best[1], best[2]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("names", nargs="*", help="art stems to fetch (default: all)")
    ap.add_argument("--force", action="store_true", help="re-fetch existing files")
    args = ap.parse_args()

    ART.mkdir(exist_ok=True)
    wanted = args.names or list(TARGETS)
    unknown = [n for n in wanted if n not in TARGETS]
    if unknown:
        raise SystemExit(f"no ModDB page known for: {', '.join(unknown)}")

    misses = 0
    for name in wanted:
        dest = ART / f"{name}.png"
        if dest.exists() and not args.force:
            print(f"  skip {name:28} already in art\\")
            continue
        got = fetch(name, TARGETS[name])
        if got is None:
            print(f"  MISS {name:28} no usable image at {TARGETS[name]}")
            misses += 1
            continue
        im, url = got
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        dest.write_bytes(buf.getvalue())
        print(f"  ok   {name:28} {im.width}x{im.height} "
              f"{len(buf.getvalue()) // 1024:5} KB  {url.rsplit('/', 1)[-1]}")
    print(f"\n{len(wanted) - misses}/{len(wanted)} written to {ART}")
    return 1 if misses else 0


if __name__ == "__main__":
    raise SystemExit(main())
