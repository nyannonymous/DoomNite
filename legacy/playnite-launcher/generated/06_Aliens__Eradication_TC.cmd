@echo off
rem Aliens: Eradication TC - Full 8-level campaign
rem start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" ALIENS_ERADICATION_TC_2_0.pk3 ERADICATION_MAPSET_2_0.wad -iwad DOOM2.WAD
cd /D "Z:\GAMES\BRUTAL_DOOM (uwu)"
if /I "%DOOMNITE_DRYRUN%"=="1" (
  echo start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" ALIENS_ERADICATION_TC_2_0.pk3 ERADICATION_MAPSET_2_0.wad -iwad DOOM2.WAD>>"%~dp0dryrun.log" 2>&1
  exit /b 0
)
start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" ALIENS_ERADICATION_TC_2_0.pk3 ERADICATION_MAPSET_2_0.wad -iwad DOOM2.WAD
