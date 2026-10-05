@echo off
rem Sonic Robo Blast 2 (Doom) - SRB2, Doom-style build
rem start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)\SRB2 v2.2" "Z:\GAMES\BRUTAL_DOOM (uwu)\SRB2 v2.2\srb2win.exe"
cd /D "Z:\GAMES\BRUTAL_DOOM (uwu)\SRB2 v2.2"
if /I "%DOOMNITE_DRYRUN%"=="1" (
  echo start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)\SRB2 v2.2" "Z:\GAMES\BRUTAL_DOOM (uwu)\SRB2 v2.2\srb2win.exe">>"%~dp0dryrun.log" 2>&1
  exit /b 0
)
start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)\SRB2 v2.2" "Z:\GAMES\BRUTAL_DOOM (uwu)\SRB2 v2.2\srb2win.exe"
