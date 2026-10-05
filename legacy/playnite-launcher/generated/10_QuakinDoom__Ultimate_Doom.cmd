@echo off
rem QuakinDoom (Ultimate Doom) - Quake 1 on Ultimate Doom
rem start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" QuakinDoomT3DE.pk3 QuakinMobs.pk3 -iwad DOOM.WAD
cd /D "Z:\GAMES\BRUTAL_DOOM (uwu)"
if /I "%DOOMNITE_DRYRUN%"=="1" (
  echo start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" QuakinDoomT3DE.pk3 QuakinMobs.pk3 -iwad DOOM.WAD>>"%~dp0dryrun.log" 2>&1
  exit /b 0
)
start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" QuakinDoomT3DE.pk3 QuakinMobs.pk3 -iwad DOOM.WAD
