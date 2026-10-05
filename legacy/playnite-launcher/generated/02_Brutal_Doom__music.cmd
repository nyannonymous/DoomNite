@echo off
rem Brutal Doom (music) - Brutal Doom 22 on Ultimate Doom
rem start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" brutal22test6.pk3 -iwad DOOM.WAD -file DoomMetalVol5_44100.wad
cd /D "Z:\GAMES\BRUTAL_DOOM (uwu)"
if /I "%DOOMNITE_DRYRUN%"=="1" (
  echo start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" brutal22test6.pk3 -iwad DOOM.WAD -file DoomMetalVol5_44100.wad>>"%~dp0dryrun.log" 2>&1
  exit /b 0
)
start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" brutal22test6.pk3 -iwad DOOM.WAD -file DoomMetalVol5_44100.wad
