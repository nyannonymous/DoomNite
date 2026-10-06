@echo off
rem Aliens: Eradication TC (UD only) - TC without the mapset
rem start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" ALIENS_ERADICATION_TC_2_0.pk3 -iwad DOOM.WAD
cd /D "Z:\GAMES\BRUTAL_DOOM (uwu)"
if /I "%DOOMNITE_DRYRUN%"=="1" (
  echo start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" ALIENS_ERADICATION_TC_2_0.pk3 -iwad DOOM.WAD>>"%~dp0dryrun.log" 2>&1
  exit /b 0
)
start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" ALIENS_ERADICATION_TC_2_0.pk3 -iwad DOOM.WAD
