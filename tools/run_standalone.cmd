@echo off
setlocal
set "n=%~1"

if "%n%"=="50" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\srb2" "runtime\srb2\srb2win.exe" -window -width 1600 -height 900 -center>>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\srb2" "runtime\srb2\srb2win.exe" -window -width 1600 -height 900 -center
  exit /b 0
)

if "%n%"=="51" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "Z:\GAMES\DOOM HALF LIFE" "Z:\GAMES\DOOM HALF LIFE\hl2doom.exe">>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "Z:\GAMES\DOOM HALF LIFE" "Z:\GAMES\DOOM HALF LIFE\hl2doom.exe"
  exit /b 0
)

if "%n%"=="52" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\eduke32\duke3d" "runtime\eduke32\duke3d\eduke32.exe" -usecwd>>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\eduke32\duke3d" "runtime\eduke32\duke3d\eduke32.exe" -usecwd
  exit /b 0
)

if "%n%"=="53" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\eduke32\duke64" "runtime\eduke32\duke64\eduke32.exe" -usecwd>>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\eduke32\duke64" "runtime\eduke32\duke64\eduke32.exe" -usecwd
  exit /b 0
)

if "%n%"=="54" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\eduke32\kickass" "runtime\eduke32\kickass\eduke32.exe" /gKADuke_Data.zip -usecwd>>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\eduke32\kickass" "runtime\eduke32\kickass\eduke32.exe" /gKADuke_Data.zip -usecwd
  exit /b 0
)

if "%n%"=="55" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\eduke32\legacy" "runtime\eduke32\legacy\eduke32.exe" -usecwd>>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\eduke32\legacy" "runtime\eduke32\legacy\eduke32.exe" -usecwd
  exit /b 0
)

if "%n%"=="56" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\eduke32\dnf" "runtime\eduke32\dnf\_eduke32.exe" -gDNF.GRP -xDNFGAME.con>>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\eduke32\dnf" "runtime\eduke32\dnf\_eduke32.exe" -gDNF.GRP -xDNFGAME.con
  exit /b 0
)

if "%n%"=="57" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "runtime\isodoom" "runtime\isodoom\IsoDoom.exe">>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "runtime\isodoom" "runtime\isodoom\IsoDoom.exe"
  exit /b 0
)

if "%n%"=="58" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "totalchaos_retro_1000\gamedata" "totalchaos_retro_1000\gamedata\gzdoom.exe" -iwad doom.wad -file totalchaos.pk3>>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "totalchaos_retro_1000\gamedata" "totalchaos_retro_1000\gamedata\gzdoom.exe" -iwad doom.wad -file totalchaos.pk3
  exit /b 0
)

if "%n%"=="59" (
  if /I "%DOOMNITE_DRYRUN%"=="1" (
    echo start "" /D "totalchaos_standalone_1000b\gamedata" "totalchaos_standalone_1000b\gamedata\gzdoom.exe" -iwad doom.wad -file totalchaos.pk3>>"%~dp0..\dryrun.log"
    exit /b 0
  )
  start "" /D "totalchaos_standalone_1000b\gamedata" "totalchaos_standalone_1000b\gamedata\gzdoom.exe" -iwad doom.wad -file totalchaos.pk3
  exit /b 0
)

exit /b 0
