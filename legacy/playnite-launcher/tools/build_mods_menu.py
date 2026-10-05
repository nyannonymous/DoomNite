"""Build the DoomNite "MODS" menu: ghost cards for not-yet-installed TCs.

A ghost card is a catalog entry whose payload is not in the mods folder. It is
listed with its artwork, and its action is Install (not Play), so the launcher
stays one interface: dimmed card, Install where Play normally sits.

The launcher is still plain batch — the ghost/opacity distinction is carried in
the generated .cmd names and in the menu text, and the renderer (a future GUI
pass) reads data/catalog.json for the same info.

  python tools/build_mods_menu.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
MODS_DIR = os.environ.get("DOOMNITE_MODS_DIR", r"Z:\GAMES\BRUTAL_DOOM (uwu)")


def human(n):
    return f"{n/1e6:.1f} MB" if n >= 1e6 else f"{n/1e3:.0f} kB"


def main():
    with open(os.path.join(REPO, "data", "catalog.json"), encoding="utf-8") as fh:
        catalog = json.load(fh)

    out = os.path.join(REPO, "generated")
    os.makedirs(out, exist_ok=True)
    mods = []

    for e in catalog:
        if e.get("source") != "direct":
            continue                      # not auto-installable; excluded by design
        installed = os.path.exists(os.path.join(MODS_DIR, e["install"]["filename"]))
        # A ghost is anything not on disk.  Playable entries get a launcher too,
        # but only ghosts advertise Install.
        kind = "play" if installed else "ghost"
        body = "\n".join([
            "@echo off",
            f"rem {e['title']} [{kind}] - {e['summary']}",
            f"rem art: {e['art']}",
            f'rem {human(e["asset"]["bytes"])} from {e["repo"]} @ {e["release_tag"]}',
        ])
        if installed:
            body += "\n".join([
                f'cd /D "{MODS_DIR}"',
                f'start "" "{MODS_DIR}\\doom.exe" -iwad {e["iwad"]} '
                f'-file "{e["asset"]["name"]}"',
            ])
        else:
            body += "\n".join([
                f'echo   {e["title"]} is not installed yet.',
                f'echo   {human(e["asset"]["bytes"])} will download from GitHub.',
                "echo.",
                'python "%~dp0..\\tools\\install_mod.py" --install ' + e["id"],
                "pause",
            ])
        name = f"MOD_{kind}_{e['id']}.cmd"
        with open(os.path.join(out, name), "w", newline="\r\n") as fh:
            fh.write(body + "\n")
        mods.append((e, kind, name))

    t = [
        "@echo off",
        "setlocal enabledelayedexpansion",
        "title DoomNite - Mods",
        "cls",
        "echo ======================================================",
        "echo       D O O M N I T E  -  M O D S",
        "echo ======================================================",
        "echo",
        "echo  Ghosted cards are not installed. Choosing one downloads",
        "echo  it from GitHub and installs it; then it becomes playable.",
        "echo",
    ]
    n = 0
    for e, kind, name in mods:
        n += 1
        mark = " " if kind == "play" else "~"
        t.append(f"echo  {mark} {n}. {e['title']}  ({human(e['asset']['bytes'])})")
        t.append(f"echo       {'Installed - Play' if kind == 'play' else 'Not installed - Install'}   {e['summary']}")
    t += [
        "echo",
        "echo  (~ = ghost card, not installed yet)",
        "echo  0. Back",
        "echo",
        'set "pick="',
        'set /p "pick=Number, then Enter: "',
        'if not defined pick exit /b 0',
        'for /f "tokens=1" %%a in ("!pick!") do set "pick=%%a"',
        'if "!pick!"=="0" exit /b 0',
    ]
    for i, (e, kind, name) in enumerate(mods, start=1):
        t.append(f'if "!pick!"=="{i}" call "%~dp0{name}"')
    t.append("exit /b 0")
    t.append("")

    with open(os.path.join(out, "DoomNiteMods.cmd"), "w", newline="\r\n") as fh:
        fh.write("\n".join(t))

    ghosts = sum(1 for _, k, _ in mods if k == "ghost")
    print(f"wrote {len(mods)} mod cards ({ghosts} ghost) + DoomNiteMods.cmd to {out}")


if __name__ == "__main__":
    main()