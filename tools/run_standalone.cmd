@echo off
setlocal
set "n=%~1"

if "%n%"=="6" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "Z:\GAMES\DOOM HALF LIFE" "Z:\GAMES\DOOM HALF LIFE\hl2doom.exe">>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "Z:\GAMES\DOOM HALF LIFE" "Z:\GAMES\DOOM HALF LIFE\hl2doom.exe"
  exit /b 0
)

if "%n%"=="7" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\eduke32\duke3d" "runtime\eduke32\duke3d\eduke32.exe">>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\eduke32\duke3d" "runtime\eduke32\duke3d\eduke32.exe"
  exit /b 0
)

if "%n%"=="8" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\eduke32\duke64" "runtime\eduke32\duke64\eduke32.exe">>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\eduke32\duke64" "runtime\eduke32\duke64\eduke32.exe"
  exit /b 0
)

if "%n%"=="9" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\eduke32\kickass" "runtime\eduke32\kickass\eduke32.exe">>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\eduke32\kickass" "runtime\eduke32\kickass\eduke32.exe"
  exit /b 0
)

exit /b 0
