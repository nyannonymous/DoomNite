@echo off
rem Half Life in Doom - HL1 in Doom
rem start "" /D "Z:\GAMES\DOOM HALF LIFE" "Z:\GAMES\DOOM HALF LIFE\hl2doom.exe"
cd /D "Z:\GAMES\DOOM HALF LIFE"
if /I "%DOOMNITE_DRYRUN%"=="1" (
  echo start "" /D "Z:\GAMES\DOOM HALF LIFE" "Z:\GAMES\DOOM HALF LIFE\hl2doom.exe">>"%~dp0dryrun.log" 2>&1
  exit /b 0
)
start "" /D "Z:\GAMES\DOOM HALF LIFE" "Z:\GAMES\DOOM HALF LIFE\hl2doom.exe"
