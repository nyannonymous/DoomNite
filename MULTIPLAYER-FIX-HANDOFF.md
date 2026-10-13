# Handoff: multiplayer asks for the IWAD folder, and the panel says "not set up"

Written for another agent working on a **second copy** of this pack (a different
machine, different paths, probably no NukemNet and no engine `.ini`). Everything
here was found and verified on the first copy; the edits are small and
mechanical. Read section 1 for the symptom, section 3 for the exact edits,
section 4 for how to prove each one.

Do not skip section 5 — it lists the things that look like the bug but are not.

---

## 1. Symptom (what the user actually reports)

Press **MULTIPLAYER → Host a game**, and Zandronum opens a dialog:

> **Welcome to Zandronum!** — "To play, please point us to your Doom directory."
> [ Browse… ]

Pointing it at the folder containing `DOOM2.WAD` does not stop it from coming
back on the next launch. The dialog also looks **clipped** at the bottom.

Secondary symptom: the panel can read as unconfigured on a machine where
multiplayer works fine.

---

## 2. Root cause

Four separate defects. The first is what the user sees; the others are why it
looked unfixable.

1. **The base WAD is passed to the engine as a bare NAME, not a path.**
   `mp_session.base_argv()` emitted `-iwad DOOM2.WAD`. A name only resolves if
   the engine's own IWAD search list happens to name the folder holding the WAD.
   The bundled engine lives in `runtime/zandronum/` and its WADs live one level
   up in `iwads/`, which is not in that list. On a machine that had a leftover
   `zandronum-<user>.ini` carrying an old `Path=` line it worked by accident;
   the shipped pack strips `runtime/zandronum/*.ini` (`desktop/build/stage-pack.js`),
   so a fresh unpack has no such line at all.

2. **The base WAD was also passed a SECOND time as `-file`.**
   `files_for_entry()` reads the pack's own launcher `.bat`, and that file names
   its IWAD too (`-iwad "%~dp0..\iwads\DOOM2.WAD"`), so the WAD came back out of
   the file list and onto the command line again. The engine loaded the base game
   twice: once as the game, once as a mod stacked on itself.

3. **`describe()` raised for an entry that cannot be played online.**
   `files_for_entry()` raises `ValueError` for a standalone game (SRB2, Half-Life
   Doom), and `describe()` called it unguarded. `mp_http.setup()` turned that
   exception into a 500, and a 500 makes the panel hide Host/Join entirely.

4. **`/api/multiplayer/setup`'s `ok` meant "the NukemNet step succeeded".**
   Multiplayer does not need NukemNet — it starts Zandronum directly — but the
   route reported `ok: false` and logged "NukemNet was not found on this
   machine" on a perfectly working machine without NN. Anything reading that
   field fails closed on a fresh install.

---

## 3. The edits

### 3.1 `tools/mp_session.py` — resolve the IWAD to a real file

Add `import iwadfinder as _iwad` next to the `serve` / `nn_preset` imports, then
add these two functions:

```python
def iwad_path_for_entry(idx):
    """Absolute path to the IWAD that entry needs, or "" if it cannot be found."""
    name = os.path.basename(iwad_for_entry(idx) or "")
    if not name:
        return ""
    return _iwad.available(name) or ""


def launch_env():
    """os.environ plus DOOMWADDIR pointing at the pack's IWADs.

    $DOOMWADDIR is one of the engine's OWN default IWAD search directories, so
    this teaches the engine where the pack keeps its WADs rather than depending
    on the argument alone.
    """
    env = dict(os.environ)
    env["DOOMWADDIR"] = os.path.join(PACK, "iwads")
    return env
```

In `base_argv()`, replace the bare-name IWAD and drop the duplicate `-file`:

```python
    argv = [exe]
    iwad = iwad_for_entry(idx)
    base_wad = ""
    if iwad:
        base_wad = iwad_path_for_entry(idx)
        if not base_wad:
            # Refuse rather than launch: a name the engine cannot resolve is
            # what opens its "point us to your Doom directory" dialog.
            raise ValueError(
                os.path.basename(iwad) + " was not found, so Zandronum cannot "
                "start. Put it in the pack's iwads folder, or point the "
                "launcher at your Doom install, then try again.")
        argv += ["-iwad", base_wad]
    # The base game is passed ONCE. entry_files() reads the launcher .bat, which
    # names its IWAD too, so it used to be added again here as -file and loaded
    # twice. Every OTHER file keeps its exact position: the order is the entry's
    # own and is load-bearing.
    # normcase+abspath because one file reaches here by two spellings.
    skip = os.path.normcase(os.path.abspath(base_wad)) if base_wad else ""
    for f in files:
        if skip and os.path.normcase(os.path.abspath(f)) == skip:
            continue
        argv += ["-file", f]
    argv += ["+name", hostname]
    return argv
```

Add the readiness verdict the panel renders. **It must not mention NukemNet:**

```python
def can_play(idx):
    """(ok, why) -- can this machine actually start a game for this entry?

    Deliberately silent about NukemNet: multiplayer runs Zandronum directly, so
    a machine without NN is a normal, working machine. Never raises -- this is
    the readiness answer the panel renders, and an entry that cannot be played
    online has to come back as a readable reason, not an exception.
    """
    try:
        files = files_for_entry(idx)
    except ValueError as e:
        return False, str(e)
    if not files:
        return False, "that entry loads no files"
    name = os.path.basename(iwad_for_entry(idx) or "")
    if not name:
        return False, "that entry has no IWAD, so Zandronum cannot start it"
    try:
        if not zandronum_exe():
            return False, ("Zandronum was not found on this machine, so a "
                           "game cannot be started yet.")
    except Exception:
        return False, ("Zandronum could not be located on this machine, so a "
                       "game cannot be started yet.")
    if not iwad_path_for_entry(idx):
        return False, (name + " was not found, so Zandronum cannot start. Put "
                       "it in the pack's iwads folder, or point the launcher "
                       "at your Doom install.")
    return True, ""
```

In `describe()`, publish it and stop raising:

```python
    playable, why = can_play(idx)
    info = { "ok": True, ..., "can_play": playable, "why": why, "files": [] }
    if entry.get("kind") == "pack":
        try:
            info["files"] = [_nn.mask(f) for f in files_for_entry(idx)]
        except ValueError:
            pass
```

In `_ensure_ready()`, NukemNet being absent is **not** a failure:

```python
    nn_user = _nn.find_nn()
    if not nn_user:
        return True, ["NukemNet is not installed. Multiplayer does not need "
                      "it: the engine is started directly, so there is "
                      "nothing to set up here."]
    zdir = _nn.nn_zandronum_dir(nn_user)
    if not zdir:
        return True, ["NukemNet has no Zandronum path set, which is fine -- "
                      "multiplayer does not use it. Nothing to set up here."]
```

Finally, both launch sites pass the environment:
`mp_session.main()`'s `subprocess.Popen(...)` and `mp_http._launch()`'s both get
`env=launch_env()` / `env=mp_session.launch_env()`.

### 3.2 `tools/mp_http.py` — `ok` means "can this machine play?"

```python
        _prepared, lines = mp_session._ensure_ready()   # prep first, then:
        ready = mp_session.describe(idx)                # nn.linked is post-state
        ok = bool(ready.get("can_play"))
        return 200, {"ok": ok,
                     "error": None if ok else (ready.get("why") or
                                               "Multiplayer is not set up on "
                                               "this machine."),
                     "ready": ready,
                     "log": lines}
```

### 3.3 `ui/src/MultiplayerButton.jsx` — status line, not NukemNet

Replace the two separate status blocks (a Zandronum warning and an
`nn?.found && nn?.linked` reassurance line) with ONE line driven by playability:

```jsx
{ready.ready && (!ready.ready.zandronum ? (
  <p className="mp-warn">
    Zandronum was not found on this machine, so a game cannot be
    started yet.
  </p>
) : ready.ready.can_play ? (
  <p className="mp-ok">
    Multiplayer is set up. Nothing else to configure.
  </p>
) : ready.ready.can_play === false ? (
  <p className="mp-warn">
    {ready.ready.why || "This game cannot be started yet."}
  </p>
) : null)}
```

Note the explicit `=== false`. A rebuilt UI against a server that has not been
restarted yet does not send `can_play` at all, and a truthiness test would then
show "This game cannot be started yet." on a machine where everything is fine.
Only claim a game cannot start when the server actually says so.

The panel's phase stays gated on the **entry resolving** (`d.ready.ok`), never
on whether this machine can play: a missing engine or WAD is the status line's
reason, with Host/Join still in front of the user.

**Rebuild is mandatory** — `serve.py` serves the built bundle in `app/`, not
`ui/src`:

```sh
cd ui && npm install && npm run build      # vite writes ../app
```

Repair in the same file: `ui/verify-mp-button.mjs` ended with
`if (fail) process.exit(1);`, so a fully PASSING run fell off the end and hung
forever on a keep-alive socket — the exit status never came back. Change the
last line to `process.exit(fail ? 1 : 0);`, as `ui/verify.mjs` already does.
While there, both harnesses take `process.env.DOOMNITE_BASE` so they can run
against a second server on another port.

---

## 4. How to prove each fix (do all three)

**A. Offline suite** — pins the absolute IWAD, the single base-WAD load, the
refusal, and the no-NukemNet payload:

```sh
python tools/selftest_mp.py          # 125/125 on a complete pack; exit 0
```

The bar is **zero FAILs and exit 0**. The count can differ slightly on a copy
whose mods or IWADs are not all downloaded (the fingerprint checks report
entries with no code rather than failing them), and a pack missing real content
will fail the `-file` checks — which is the check doing its job.

**B. The engine itself, on the condition that broke.** Remove (move away) the
engine's `.ini` to simulate a fresh install, then watch the game port:

```python
# launch with mp_session.host_argv(0, 23513) + launch_env(),
# poll `netstat -an` for UDP 23513, then taskkill zandronum.exe
```

Measured on the first copy: **before** the fix, `-iwad DOOM.WAD` with no
`DOOMWADDIR` sat alive for 20 s with the port never bound (that is the dialog);
**after**, the port bound in 3 s and the game hosted. Restore the `.ini`
afterwards. Launching the real engine opens a window on the desktop for ~20 s —
that is expected.

**C. The panel, in jsdom against a live server:**

```sh
python serve.py --port 8766 &        # a second server, so you do not disturb
cd ui && DOOMNITE_BASE=http://127.0.0.1:8766 node verify-mp-button.mjs ../app/assets/<bundle>.js
cd ui && DOOMNITE_BASE=http://127.0.0.1:8766 node verify.mjs ../app/assets/<bundle>.js
```

Expect **32/32** and **21/21**, both exit 0.

## 5. Future builds and installers are already guarded against this

The first copy added three build-time guards, so a regression fails the BUILD
instead of shipping an installer whose Multiplayer button opens the folder
dialog again. If your copy diverged, re-apply these too:

1. **`tools/check_mp_command.py`** builds the real multiplayer command line
   from the pack's own data (no pack content needed — the engine path and the
   IWAD resolution are the only stubs) and asserts the shape: one absolute
   `-iwad`, the base WAD exactly once, the remaining `-file` list in the
   entry's own order, host/join args intact, `DOOMWADDIR` set. Run it:
   `python tools/check_mp_command.py` — expect exit 0 (`10/10` on a complete
   pack; exact count can differ on an incomplete copy).
2. **`desktop/build/stage-pack.js` runs it inside the electron-builder
   after:stagePack hook**, so a regression (or the guard itself failing to
   run) ABORTS staging with the guard's output instead of packaging a bad
   installer. It does not launch the engine and needs no WADs on disk.
3. **`desktop/preflight.js`** additionally requires `tools/` in the packaged
   bootstrap (it is runtime code — serve.py imports `mp_http` from it) and a
   playable manifest: at least one `games[].actions[]` naming both an `iwad`
   and a `bat`. A stub manifest is refused with exit 1 instead of shipping an
   empty grid.

Maintenance rules:

* If you change how the multiplayer command line is built, `check_mp_command.py`
  is the spec — update its assertions in the same commit.
* If preflight's `checkBootstrap` fires on tools/ or the playable-manifest
  check, the pack root is stale: `python tools/build.py`, not a code change.
* `desktop/build/pack/runtime/zandronum/` must contain **0** `.ini` files after
  staging (stage-pack.js filters them out on purpose). If one sneaks in, the
  bug this document is about can come back.

---

## 6. Things that look like the bug but are not

- **The clipped dialog is Zandronum's own window.** It is laid out for a
  default-DPI window and gets cut off on a scaled display; it is not the pack's
  dialog and cannot be restyled from Python or CSS. The correct fix is that
  DoomNite no longer provokes it — after section 3 the engine always has its
  IWAD by absolute path. If someone launches
  `runtime/zandronum/zandronum.exe` **by hand** with no config, they will still
  see it; the Windows workaround is Compatibility → "Change high DPI settings" →
  override as "Application".
- **The NukemNet junction step can fail and it does not matter.** Observed on
  the first copy: `%LOCALAPPDATA%\Zandronum` no longer exists (there is a
  `Zandronum.bak`), so `mklink /J` fails with "The system cannot find the path
  specified" and `describe().nn.linked` stays `false`. That step only exists so
  NukemNet's own Play button can see the pack's files. Multiplayer does not use
  it, so it must not gate the panel — which is exactly why `ok` is `can_play`
  and not `_ensure_ready()`'s return value.
- **Do not "fix" it by copying WADs next to the engine exe, or by editing the
  engine `.ini`.** The pack strips that `.ini` on purpose, so any fix that relies
  on it is machine-local and will not survive shipping. Passing the path is the
  fix.
- **Do not make the panel require NukemNet to say "set up".** A fresh install
  does not have it; that was the bug.
