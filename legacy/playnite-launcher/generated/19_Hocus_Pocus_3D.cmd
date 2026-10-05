@echo off
rem Hocus Pocus 3D - Hocus Pocus in Doom
rem start "" /D "Z:\GAMES\Hocus Doom" "Z:\GAMES\BRUTAL_DOOM (uwu)\..\Hocus Doom\doom.exe" HOCUS.pk3 -iwad DOOM2.WAD
cd /D "Z:\GAMES\Hocus Doom"
if /I "%DOOMNITE_DRYRUN%"=="1" (
  echo start "" /D "Z:\GAMES\Hocus Doom" "Z:\GAMES\BRUTAL_DOOM (uwu)\..\Hocus Doom\doom.exe" HOCUS.pk3 -iwad DOOM2.WAD>>"%~dp0dryrun.log" 2>&1
  exit /b 0
)
start "" /D "Z:\GAMES\Hocus Doom" "Z:\GAMES\BRUTAL_DOOM (uwu)\..\Hocus Doom\doom.exe" HOCUS.pk3 -iwad DOOM2.WAD
