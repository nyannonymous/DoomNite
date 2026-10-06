@echo off
rem DoomRPG + Brutal Doom (experimental) - Playnite flags this combo as unsupported
rem start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" brutal22test6.pk3 DoomRPG\DoomRPG.pk3 DoomRPG\DoomRPG-Extras.pk3 DoomRPG\DoomRPG-Brightmaps.pk3 -iwad DOOM2.WAD -file DoomMetalVol5_44100.wad
cd /D "Z:\GAMES\BRUTAL_DOOM (uwu)"
if /I "%DOOMNITE_DRYRUN%"=="1" (
  echo start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" brutal22test6.pk3 DoomRPG\DoomRPG.pk3 DoomRPG\DoomRPG-Extras.pk3 DoomRPG\DoomRPG-Brightmaps.pk3 -iwad DOOM2.WAD -file DoomMetalVol5_44100.wad>>"%~dp0dryrun.log" 2>&1
  exit /b 0
)
start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" brutal22test6.pk3 DoomRPG\DoomRPG.pk3 DoomRPG\DoomRPG-Extras.pk3 DoomRPG\DoomRPG-Brightmaps.pk3 -iwad DOOM2.WAD -file DoomMetalVol5_44100.wad
