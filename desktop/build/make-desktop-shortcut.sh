#!/usr/bin/env bash
# Create (or refresh) a Desktop shortcut for the DoomNite v2 unpacked build.
#
# Points at release/win-unpacked-v2/DoomNite.exe -- the freshly built v2 tree --
# NOT the installer in release/, and not release/win-unpacked/ which is still
# the October v1.0.0 build. Running the unpacked tree avoids needing the pack to
# be reinstalled just to launch the new UI.
set -euo pipefail

ROOT="Z:/github/APP · DOOMNITE-PACK/desktop/release/win-unpacked-v2"
EXE="$ROOT/DoomNite.exe"
ICON="Z:/github/APP · DOOMNITE-PACK/desktop/build/icon.ico"
DESKTOP="$USERPROFILE/Desktop"
LINK="$DESKTOP/DoomNite.lnk"

[ -f "$EXE" ] || { echo "FATAL: $EXE not found" >&2; exit 1; }

# Recreate from scratch so a stale path/working-dir never survives a rebuild.
rm -f "$LINK"

powershell.exe -NoProfile -NonInteractive -Command "
\$s = (New-Object -ComObject WScript.Shell).CreateShortcut('$LINK')
\$s.TargetPath       = '$EXE'
\$s.WorkingDirectory = '$ROOT'
\$s.IconLocation     = '$ICON,0'
\$s.Description      = 'DoomNite 2.0.0 -- portable Doom mod launcher'
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