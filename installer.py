"""On-demand installers for the total conversions the pack ships without.

A total conversion is either a megawad (Requiem: a plain PWAD that sits on top
of DOOM2) or a standalone IPK3 (Adventures of Square, which must *be* the IWAD
and must not run on top of another one). The launcher shape in build.py assumes
"an IWAD plus a list of mods", so the standalone case needs its own path.

Everything here is deliberate about not damaging an existing install:

* downloads land in a temp file and are renamed into place only after the
  sha256 matches, so a partial or truncated download never looks installed;
* the sha256 is checked against a value recorded at build time, so a mirror
  serving something else is rejected rather than unpacked;
* extraction goes to a staging directory and is moved into place only when the
  whole extraction succeeded;
* an entry is never overwritten without an explicit reinstall, and the target
  directory is recorded so a reinstall can replace it cleanly.
"""

import hashlib
import io
import json
import os
import shutil
import ssl
import tempfile
import threading
import time
import urllib.request
from urllib.parse import urlsplit as _urlsplit
import zipfile

# installer.py lives IN the pack root, next to serve.py, so one dirname is the
# pack. Two levels up put every install at Z:\mods and Z:\downloads instead of
# inside the pack, which then looked like a corrupt install because the files
# were real but in the wrong place. Matches serve.py.
PACK = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(PACK, "downloads")
STAGING = os.path.join(PACK, ".staging")

# AoS ships an HTTP-only primary host, and Requiem's idgames mirrors are a mix of
# HTTP, TLS and FTP. TLS verification is disabled *for these downloads only*
# because several of the long-standing idgames mirrors serve certificates that
# no longer validate, and there is no alternative host for the same file. Every
# artifact is pinned by sha256, which is what actually provides integrity here:
# a tampered or corrupted download fails the hash and is discarded.
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# name -> install spec. Mirrors are tried in order; the first that works wins.
# size is used only to show progress; sha256 is what gates the install.
SPECS = {
    "adventures-of-square": {
        "label": "The Adventures of Square",
        "note": "Standalone total conversion. Ships as its own IWAD (PK3).",
        "kind": "ipk3",
        "zip": "square-ep2-pk3-2.1.zip",
        "size": 44161687,
        "sha256": "6cd3167f7d9eeb1ca288997d5a9d7d3a489563e4576ba36a9fc35501c91a0ea5",
        "mirrors": [
            "http://adventuresofsquare.com/downloads/square-ep2-pk3-2.1.zip",
            "https://mtrop.net/downloads/mirror/square-ep2-pk3-2.1.zip",
        ],
        # The one file to install; everything else in the zip is documentation.
        "want": {"square1.pk3"},
    },
    "requiem": {
        "label": "Requiem",
        "note": "1997 32-level megawad for Doom II.",
        "kind": "pwad",
        "zip": "requiem.zip",
        "size": 3987788,
        "sha256": "36c5e5a6f49203259479c943abc5c9f3369602e101ee9e36d49db59494b36c17",
        "mirrors": [
            "http://youfailit.net/pub/idgames/levels/doom2/megawads/requiem.zip",
        ],
        # REQUIEM.WAD is the megawad. The .TXT is the credits, the .BAT files
        # are DOS-era file-combining scripts that must never be run.
        "want": {"REQUIEM.WAD"},
        "extra": {"REQUIEM.TXT"},
        "reject": {"REQUIEM.BAT", "REQNOMUS.BAT"},
    },
}

# Install destinations, both under mods/ so a rebuild's copy step can see them.
DEST = {
    "adventures-of-square": os.path.join(PACK, "mods", "adventures-of-square"),
    "requiem": os.path.join(PACK, "mods", "requiem"),
}

_lock = threading.Lock()
_jobs = {}   # name -> job dict

# --------------------------------------------------------------- pack mods
#
# Everything above is for the two on-demand total conversions, which were the
# only mods with a tracked install location before this. Every OTHER mod is
# baked into mods/<slug>/ at build time by tools/build.py, straight from
# pack-manifest.json -- there was no uninstall path for those at all. Rather
# than inventing a second SPECS/DEST table that build.py would then have to be
# kept in sync with by hand, the registry below is DERIVED from
# pack-manifest.json itself, the same document serve.py's load_entries()
# already treats as the source of truth. A rebuild changes the manifest; this
# registry changes with it automatically, nothing here goes stale.
MANIFEST = os.path.join(PACK, "pack-manifest.json")


def _load_manifest():
    try:
        return json.load(open(MANIFEST, encoding="utf-8"))
    except (OSError, ValueError):
        return {"games": []}


def pack_mod_registry():
    """Map every baked-in game's name to the mods/<slug> folders it loads.

    Returns (per_game, owners):
      per_game: game name -> set of mod slugs that game's actions reference.
      owners:   mod slug -> set of game names that reference it.

    On-demand total conversions (needs_install actions -- Adventures of
    Square, Requiem) are skipped here; those are tracked by name directly via
    SPECS/DEST above and have their own install()/remove().

    A slug can appear under more than one game: Brutal Doom Black Edition's
    BDBE_v3.38.pk3 is shared between the "Enhanced Episode 1" and "HontE
    Remastered" entries. owners is what lets remove_pack_mod() tell a folder
    this game alone uses from one it shares, so uninstalling one game can
    never silently break another that still needs the same file.
    """
    man = _load_manifest()
    owners, per_game = {}, {}
    for g in man.get("games", []):
        name = g.get("name")
        folders = set()
        for a in g.get("actions", []):
            if a.get("needs_install"):
                continue
            for m in a.get("mods", []):
                # Stored as "mods\\<slug>\\<file>" or "mods/<slug>/<file>" --
                # the slug is always the second-to-last path component.
                parts = [p for p in m.replace("\\", "/").split("/") if p]
                if len(parts) >= 2:
                    folders.add(parts[-2])
        if folders:
            per_game[name] = folders
            for f in folders:
                owners.setdefault(f, set()).add(name)
    return per_game, owners


def pack_mod_status(name):
    """Install status for one baked-in game, or None if it has no mods/ at
    all (an on-demand entry, or a standalone exe outside the pack)."""
    per_game, owners = pack_mod_registry()
    folders = per_game.get(name)
    if folders is None:
        return None
    present = [f for f in folders
               if os.path.isdir(os.path.join(PACK, "mods", f))]
    shared = sorted(f for f in folders if len(owners.get(f, ())) > 1)
    exclusive = sorted(f for f in folders if f not in shared)
    freed = 0
    for f in folders:
        d = os.path.join(PACK, "mods", f)
        if os.path.isdir(d):
            for root, _dirs, files in os.walk(d):
                for fn in files:
                    try:
                        freed += os.path.getsize(os.path.join(root, fn))
                    except OSError:
                        pass
    return {
        "name": name,
        "folders": sorted(folders),
        "exclusive": exclusive,
        "shared": shared,
        "installed": bool(folders) and len(present) == len(folders),
        "partial": 0 < len(present) < len(folders),
        "size_h": _human(freed) if freed else None,
    }


def remove_pack_mod(name):
    """Delete the mods/<slug> folders a baked-in game owns EXCLUSIVELY.

    Mirrors remove() above: the only paths ever touched are
    PACK/mods/<slug>, and <slug> only ever comes from pack_mod_registry(),
    which is built from pack-manifest.json on the server -- never from
    anything a request supplied. An unknown game name is rejected exactly
    like an unknown SPECS name is.

    A slug shared with another game is skipped, not deleted, and reported
    back in "skipped" so the UI can say why nothing (or only part) of it was
    removed. There is no reinstall button for these: the pack's own copy was
    a build-time copy from the operator's source drive, so getting it back
    is `python tools\\build.py` -- the files are not re-fetched from a URL
    the way the two on-demand total conversions are. serve.py's load_entries()
    re-checks the filesystem on every /api/entries request, so the tile
    immediately reflects the removal as "missing" with no rebuild needed for
    that part.
    """
    per_game, owners = pack_mod_registry()
    folders = per_game.get(name)
    if folders is None:
        raise KeyError(name)
    mods_root = os.path.join(PACK, "mods")
    removed, skipped, freed = [], [], 0
    for f in sorted(folders):
        if len(owners.get(f, ())) > 1:
            skipped.append(f)
            continue
        dest = os.path.join(mods_root, f)
        # Defence in depth even though f is never client-supplied: refuse
        # anything that is not a direct child of mods\, and never follow a
        # symlink -- same two guards remove() uses for the on-demand case.
        if os.path.dirname(os.path.abspath(dest)) != os.path.abspath(mods_root):
            continue
        if os.path.islink(dest):
            continue
        if not os.path.isdir(dest):
            continue
        for root, _dirs, files in os.walk(dest):
            for fn in files:
                try:
                    freed += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
        shutil.rmtree(dest)
        removed.append(f)
    return {"name": name, "removed": removed, "skipped": skipped, "freed": freed}


def _human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0


def installed(name):
    """Is this entry ready to launch? Checks the files it needs actually exist."""
    spec = SPECS.get(name)
    if not spec:
        return False
    dest = DEST[name]
    return os.path.isdir(dest) and bool(spec["want"]) and all(
        os.path.isfile(os.path.join(dest, f)) for f in spec["want"])


def remove(name):
    """Delete an installed total conversion and reclaim its files.

    Only ever removes DEST[name] for a name in SPECS -- the same lookup that
    guards install(). Building the path from user input here would be a
    directory-traversal primitive, so it is deliberately never done: an
    unknown name is rejected rather than sanitised.

    The cache zip is kept. Removing it would save a little space but mean the
    next install has to re-download; the extracted tree is the part that
    actually costs the player disk.
    """
    spec = SPECS.get(name)
    if not spec:
        raise KeyError(name)
    if _jobs.get(name, {}).get("state") == "downloading":
        # Deleting the destination out from under a running extract would leave
        # a half-written directory that installed() then reports as broken.
        raise RuntimeError("install in progress")
    dest = DEST[name]
    freed = 0
    if os.path.isdir(dest):
        for root, _dirs, files in os.walk(dest):
            for f in files:
                try:
                    freed += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        # The destination is validated to sit under mods\ by DEST's
        # construction, and rmtree is refused for a symlinked root, so this
        # cannot escape the pack.
        if os.path.islink(dest):
            raise RuntimeError("refusing to remove a symlink")
        shutil.rmtree(dest)
    _jobs.pop(name, None)
    return {"removed": name, "freed": freed}


def status():
    """Every spec plus whatever is known about an in-flight job."""
    out = []
    for name, spec in SPECS.items():
        j = _jobs.get(name)
        out.append({
            "name": name,
            "label": spec["label"],
            "note": spec["note"],
            "kind": spec["kind"],
            "size": spec["size"],
            "size_h": _human(spec["size"]),
            # Where it will actually come from, so the consent prompt can name
            # the host instead of saying "the internet". First mirror only --
            # the fallbacks are transparent retries of the same artifact, not
            # a different thing the user is consenting to.
            "host": _urlsplit(spec["mirrors"][0]).netloc if spec.get("mirrors") else "",
            "files": sorted(spec.get("want", {})),
            "installed": installed(name),
            "state": (j or {}).get("state", "idle"),
            "received": (j or {}).get("received", 0),
            "error": (j or {}).get("error"),
        })
    return out


def _set(name, **kw):
    with _lock:
        _jobs.setdefault(name, {}).update(kw)


def _fetch(url, name, dest_path):
    """Stream a URL to dest_path, reporting progress. Returns the sha256."""
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120, context=_CTX) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(262144)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                got += len(chunk)
                _set(name, received=got, total=total or None,
                     state="downloading")
    return h.hexdigest(), got


def install(name, force=False):
    """Download, verify and unpack one entry. Safe to call from a thread."""
    spec = SPECS.get(name)
    if spec is None:
        return {"ok": False, "error": "no such entry"}
    if installed(name) and not force:
        return {"ok": True, "already": True}

    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(STAGING, exist_ok=True)
    dest = DEST[name]

    _set(name, state="downloading", received=0, error=None, state_at=time.time())
    tmp_zip = os.path.join(CACHE, spec["zip"] + ".part")

    # 1. Fetch to a temp file. Never straight onto the final cache path, so an
    #    interrupted download cannot masquerade as a complete one.
    digest = None
    errors = []
    for url in spec["mirrors"]:
        try:
            digest, _ = _fetch(url, name, tmp_zip)
            break
        except Exception as e:      # try the next mirror
            errors.append(f"{url.split('/')[2]}: {type(e).__name__} {e}")
    if digest is None:
        _set(name, state="error", error="; ".join(errors)[:300])
        return {"ok": False, "error": "; ".join(errors)[:300]}

    # 2. Verify before anything is unpacked. This is the only integrity gate.
    if digest != spec["sha256"]:
        os.remove(tmp_zip)
        msg = f"checksum mismatch (got {digest[:16]}..., want {spec['sha256'][:16]}...)"
        _set(name, state="error", error=msg)
        return {"ok": False, "error": msg}

    final_zip = os.path.join(CACHE, spec["zip"])
    os.replace(tmp_zip, final_zip)   # atomic within the same volume
    _set(name, state="extracting")

    # 3. Extract to staging, then move into place. A failure here leaves the
    #    existing install untouched.
    stage = tempfile.mkdtemp(prefix=name + "-", dir=STAGING)
    try:
        with zipfile.ZipFile(final_zip) as z:
            names = set(z.namelist())
            missing = spec["want"] - names
            if missing:
                raise RuntimeError(f"archive is missing {sorted(missing)}")
            # Refuse anything that would escape the destination directory.
            for member in z.namelist():
                if member.startswith(("/", "\\")) or ".." in member.split("/"):
                    raise RuntimeError(f"unsafe path in archive: {member}")
                base = os.path.basename(member)
                if base in spec.get("reject", ()):
                    continue     # DOS file-combining scripts, never wanted
                if base in spec["want"] or base in spec.get("extra", ()):
                    with z.open(member) as src, \
                            open(os.path.join(stage, base), "wb") as dst:
                        shutil.copyfileobj(src, dst)

        got = os.listdir(stage)
        if not all(f in got for f in spec["want"]):
            raise RuntimeError("extraction did not produce the expected files")

        # Replace atomically-ish: move the old tree aside, put the new one in
        # place, then delete the old. Nothing is overwritten in place.
        backup = None
        if os.path.isdir(dest):
            backup = dest + ".old"
            if os.path.isdir(backup):
                shutil.rmtree(backup)
            os.replace(dest, backup)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        try:
            os.replace(stage, dest)
        except Exception:
            if backup:
                os.replace(backup, dest)   # put it back
            raise
        if backup:
            shutil.rmtree(backup, ignore_errors=True)
    except Exception as e:
        shutil.rmtree(stage, ignore_errors=True)
        _set(name, state="error", error=f"{type(e).__name__}: {e}")
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    _set(name, state="installed", received=spec["size"], error=None)
    return {"ok": True, "installed": sorted(os.listdir(dest))}


def start(name, force=False):
    """Kick off an install in the background and return immediately.

    The UI polls status() for progress. Downloads are ~4 MB and ~44 MB, so a
    blocking request would be a poor fit.
    """
    if name not in SPECS:
        return {"ok": False, "error": "no such entry"}
    with _lock:
        cur = _jobs.get(name, {})
        if cur.get("state") in ("downloading", "extracting"):
            return {"ok": True, "already_running": True}
        if installed(name) and not force:
            return {"ok": True, "already": True}

    def run():
        try:
            install(name, force=force)
        except Exception as e:      # a worker must never die silently
            _set(name, state="error", error=f"{type(e).__name__}: {e}")

    threading.Thread(target=run, name=f"install-{name}", daemon=True).start()
    return {"ok": True, "started": True}