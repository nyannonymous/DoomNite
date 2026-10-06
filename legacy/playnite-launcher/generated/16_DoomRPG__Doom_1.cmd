@echo off
rem DoomRPG (Doom 1) - Doom I version
rem start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" DoomRPG\DoomRPG.pk3 DoomRPG\DoomRPG-Extras.pk3 DoomRPG\DoomRPG-Brightmaps.pk3 DoomRPG\DoomRPG-Doom1.pk3 -iwad DOOM.WAD
cd /D "Z:\GAMES\BRUTAL_DOOM (uwu)"
if /I "%DOOMNITE_DRYRUN%"=="1" (
  echo start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" DoomRPG\DoomRPG.pk3 DoomRPG\DoomRPG-Extras.pk3 DoomRPG\DoomRPG-Brightmaps.pk3 DoomRPG\DoomRPG-Doom1.pk3 -iwad DOOM.WAD>>"%~dp0dryrun.log" 2>&1
  exit /b 0
)
start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" DoomRPG\DoomRPG.pk3 DoomRPG\DoomRPG-Extras.pk3 DoomRPG\DoomRPG-Brightmaps.pk3 DoomRPG\DoomRPG-Doom1.pk3 -iwad DOOM.WAD
