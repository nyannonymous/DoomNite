@echo off
rem Shadow Warrior (Doom II) - Full conversion
rem start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" ShadowWarriorBackup.pk3 SWMapPack.pk3 ShadowWarriorMusic.pk3 -iwad DOOM2.WAD
cd /D "Z:\GAMES\BRUTAL_DOOM (uwu)"
if /I "%DOOMNITE_DRYRUN%"=="1" (
  echo start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" ShadowWarriorBackup.pk3 SWMapPack.pk3 ShadowWarriorMusic.pk3 -iwad DOOM2.WAD>>"%~dp0dryrun.log" 2>&1
  exit /b 0
)
start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" ShadowWarriorBackup.pk3 SWMapPack.pk3 ShadowWarriorMusic.pk3 -iwad DOOM2.WAD
