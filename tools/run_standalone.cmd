@echo off
setlocal
set "n=%~1"

if "%n%"=="42" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\srb2" "runtime\srb2\srb2win.exe" -window -width 1600 -height 900 -center>>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\srb2" "runtime\srb2\srb2win.exe" -window -width 1600 -height 900 -center
  exit /b 0
)

if "%n%"=="43" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "Z:\GAMES\DOOM HALF LIFE" "Z:\GAMES\DOOM HALF LIFE\hl2doom.exe">>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "Z:\GAMES\DOOM HALF LIFE" "Z:\GAMES\DOOM HALF LIFE\hl2doom.exe"
  exit /b 0
)

if "%n%"=="44" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\eduke32\duke3d" "runtime\eduke32\duke3d\eduke32.exe" -usecwd>>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\eduke32\duke3d" "runtime\eduke32\duke3d\eduke32.exe" -usecwd
  exit /b 0
)

if "%n%"=="45" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\eduke32\duke64" "runtime\eduke32\duke64\eduke32.exe" -usecwd>>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\eduke32\duke64" "runtime\eduke32\duke64\eduke32.exe" -usecwd
  exit /b 0
)

if "%n%"=="46" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\eduke32\kickass" "runtime\eduke32\kickass\eduke32.exe" /gKADuke_Data.zip -usecwd>>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\eduke32\kickass" "runtime\eduke32\kickass\eduke32.exe" /gKADuke_Data.zip -usecwd
  exit /b 0
)

if "%n%"=="47" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\eduke32\legacy" "runtime\eduke32\legacy\eduke32.exe" -usecwd>>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\eduke32\legacy" "runtime\eduke32\legacy\eduke32.exe" -usecwd
  exit /b 0
)

if "%n%"=="48" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\eduke32\dnf" "runtime\eduke32\dnf\_eduke32.exe" -gDNF.GRP -xDNFGAME.con>>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\eduke32\dnf" "runtime\eduke32\dnf\_eduke32.exe" -gDNF.GRP -xDNFGAME.con
  exit /b 0
)

if "%n%"=="49" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\isodoom" "runtime\isodoom\IsoDoom.exe">>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\isodoom" "runtime\isodoom\IsoDoom.exe"
  exit /b 0
)

exit /b 0
