@echo off
rem DukeBoomem - Duke Nukem as Boomstick guy
rem start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" Duke-Textures.pk3 -iwad DOOM.WAD -file Duke-Boomem-2.5D.wad
cd /D "Z:\GAMES\BRUTAL_DOOM (uwu)"
if /I "%DOOMNITE_DRYRUN%"=="1" (
  echo start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" Duke-Textures.pk3 -iwad DOOM.WAD -file Duke-Boomem-2.5D.wad>>"%~dp0dryrun.log" 2>&1
  exit /b 0
)
start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)" "Z:\GAMES\BRUTAL_DOOM (uwu)\doom.exe" Duke-Textures.pk3 -iwad DOOM.WAD -file Duke-Boomem-2.5D.wad
