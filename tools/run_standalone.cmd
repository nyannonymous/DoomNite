@echo off
setlocal
set "n=%~1"

if "%n%"=="25" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)\SRB2 v2.2" "Z:\GAMES\BRUTAL_DOOM (uwu)\SRB2 v2.2\srb2win.exe">>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)\SRB2 v2.2" "Z:\GAMES\BRUTAL_DOOM (uwu)\SRB2 v2.2\srb2win.exe"
  exit /b 0
)

if "%n%"=="26" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "Z:\GAMES\DOOM HALF LIFE" "Z:\GAMES\DOOM HALF LIFE\hl2doom.exe">>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "Z:\GAMES\DOOM HALF LIFE" "Z:\GAMES\DOOM HALF LIFE\hl2doom.exe"
  exit /b 0
)

exit /b 0
