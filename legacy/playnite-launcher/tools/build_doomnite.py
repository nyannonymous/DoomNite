"""Build the DoomNite launcher: a batch menu + one .cmd per entry.

Input:  data/doomnite.json  -- [label, cwd, exe, args, note] per entry
Output: <out>/DoomNite.cmd, <out>/NN_<slug>.cmd, <out>/dryrun.log (dry runs)

The cwd/exe of every entry are machine-specific, so --out defaults to the
repo's generated/ dir and can be pointed anywhere (e.g. Z:\\GAMES\\DoomNite).
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def slugify(label):
    return "".join(c if c.isalnum() else "_" for c in label).strip("_")


def start_cmd(cwd, exe, args):
    """The exact line a user would run by hand."""
    tail = (" " + args) if args else ""
    return f'start "" /D "{cwd}" "{exe}"{tail}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(REPO, "data", "doomnite.json"))
    ap.add_argument("--out", default=os.path.join(REPO, "generated"))
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as fh:
        games = json.load(fh)

    out = args.out
    os.makedirs(out, exist_ok=True)
    # Relative to the launcher itself, so a generated/ copy and a deployed
    # copy both write their dryrun log beside their own .cmd files.
    drylog = r"%~dp0dryrun.log"

    # ---------------------------------------------------------- launchers
    for idx, (label, cwd, exe, argv, note) in enumerate(games, start=1):
        body = "\n".join([
            "@echo off",
            f"rem {label}" + (f" - {note}" if note else ""),
            "rem " + start_cmd(cwd, exe, argv),
            f'cd /D "{cwd}"',
            'if /I "%DOOMNITE_DRYRUN%"=="1" (',
            f'  echo {start_cmd(cwd, exe, argv)}>>"{drylog}" 2>&1',
            "  exit /b 0",
            ")",
            f'start "" /D "{cwd}" "{exe}"' + (f" {argv}" if argv else ""),
            "",
        ])
        path = os.path.join(out, f"{idx:02d}_{slugify(label)}.cmd")
        with open(path, "w", newline="\r\n") as fh:
            fh.write(body)

    # ------------------------------------------------------------- the menu
    t = [
        "@echo off",
        "setlocal enabledelayedexpansion",
        "title DoomNite",
        "set DOOMNITE_DRYRUN=0",
        'if /I "%~1"=="--dryrun" set DOOMNITE_DRYRUN=1',
        'set "pick=%~2"',
        'set "oneshot=0"',
        "if not defined pick goto :top",
        'set "oneshot=1"',
        "goto dispatch",
        ":top",
        "cls",
        "echo ======================================================",
        "echo                    D O O M N I T E",
        "echo ======================================================",
        "echo",
    ]
    for idx, (label, cwd, exe, argv, note) in enumerate(games, start=1):
        t.append(f"echo  {idx}. {label}")
        if note:
            t.append(f"echo       {note}")
    t += [
        "echo.",
        "echo   0. Exit",
        "echo.",
        'set "pick="',
        'set /p "pick=Number, then Enter: "',
        # set /p leaves pick empty at EOF (piped stdin, closed console) and the
        # menu would redraw forever, so an empty read is an exit.
        'if not defined pick exit /b 0',
        # Strip stray CR/LF (piped stdin keeps the newline in the variable).
        'for /f "tokens=1" %%a in ("!pick!") do set "pick=%%a"',
        # Whitelist: one /c: option per valid number (findstr treats "|" literally).
        "echo !pick!|findstr /x "
        + " ".join(f'/c:"{i}"' for i in range(len(games) + 1))
        + " >nul",
        "if errorlevel 1 goto bad",
        'if "!pick!"=="0" exit /b 0',
        'if "%DOOMNITE_DRYRUN%"=="1" goto dispatch',
        "echo.",
        "echo Type the number again to launch it, anything else to go back.",
        'set "confirm="',
        'set /p "confirm=Launch? (number again): "',
        'for /f "tokens=1" %%a in ("!confirm!") do set "confirm=%%a"',
        'if "!confirm!"=="!pick!" goto dispatch',
        "goto top",
        ":bad",
        "echo Not one of the numbers above.",
        "pause",
        "goto top",
        ":dispatch",
    ]
    for idx, (label, cwd, exe, argv, note) in enumerate(games, start=1):
        t.append(f'if "!pick!"=="{idx}" call "%~dp0{idx:02d}_{slugify(label)}.cmd"')
    t.append('if "!oneshot!"=="1" exit /b 0')
    t.append("goto top")
    t.append("")

    with open(os.path.join(out, "DoomNite.cmd"), "w", newline="\r\n") as fh:
        fh.write("\n".join(t))

    print(f"wrote {len(games)} launchers + DoomNite.cmd to {out}")


if __name__ == "__main__":
    main()
