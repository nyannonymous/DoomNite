#!/usr/bin/env bash
# Create (or refresh) a Desktop shortcut for the DoomNite unpacked build.
#
# The shortcut points at a release/win-unpacked*/DoomNite.exe tree, NOT the
# installer and NOT a zip. Picking the newest exe rather than a hardcoded folder
# matters: this used to name win-unpacked-v2, which was left behind at the
# October v1 build, so the shortcut kept launching an app three versions old
# while the freshly packed tree went unused.
#
# Running the unpacked tree from inside the pack folder also keeps it on the
# LIVE pack: main.js resolvePackRoot() walks up from the exe looking for
# serve.py and finds the repo root three levels up, so the window shows the
# current roster instead of the app's bundled 16-game bootstrap seed.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DESKTOP="${USERPROFILE:-$HOME}/Desktop"
LINK="$DESKTOP/DoomNite.lnk"
ICON="$(cygpath -w "$HERE/icon.ico" 2>/dev/null || echo "$HERE/icon.ico")"

# Newest DoomNite.exe among release/win-unpacked*/, by modification time.
EXE=""
for cand in "$HERE"/../release/win-unpacked*/DoomNite.exe; do
  [ -f "$cand" ] || continue
  if [ -z "$EXE" ] || [ "$cand" -nt "$EXE" ]; then EXE="$cand"; fi
done
[ -n "$EXE" ] || { echo "FATAL: no release/win-unpacked*/DoomNite.exe found (run: cd desktop && npm run pack)" >&2; exit 1; }

EXE_W="$(cygpath -w "$EXE")"
ROOT="$(dirname "$EXE")"
ROOT_W="$(cygpath -w "$ROOT")"

# Recreate from scratch so a stale path/working-dir never survives a rebuild.
rm -f "$LINK"

powershell.exe -NoProfile -NonInteractive -Command "
\$s = (New-Object -ComObject WScript.Shell).CreateShortcut('$LINK')
\$s.TargetPath       = '$EXE_W'
\$s.WorkingDirectory = '$ROOT_W'
\$s.IconLocation     = '$ICON,0'
\$s.Description      = 'DoomNite -- portable Doom mod launcher'
\$s.Save()
" >/dev/null

if [ -f "$LINK" ]; then
  echo "OK  $LINK"
  powershell.exe -NoProfile -NonInteractive -Command "
  \$s = (New-Object -ComObject WScript.Shell).CreateShortcut('$LINK')
  '     target: ' + \$s.TargetPath
  '     icon:   ' + \$s.IconLocation
  " | tr -d '\r'
else
  echo "FAILED to create $LINK" >&2
  exit 1
fi
