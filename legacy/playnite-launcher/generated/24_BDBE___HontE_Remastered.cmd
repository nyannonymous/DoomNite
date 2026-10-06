@echo off
rem BDBE - HontE Remastered - Brutal Doom Black Edition, HontE
rem start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)\BDBE 3.38 Build v3 by RaZZoR" "Z:\GAMES\BRUTAL_DOOM (uwu)\BDBE 3.38 Build v3 by RaZZoR\doom.exe" -file HontE_remastered_Experimental_REV1.103.wad
cd /D "Z:\GAMES\BRUTAL_DOOM (uwu)\BDBE 3.38 Build v3 by RaZZoR"
if /I "%DOOMNITE_DRYRUN%"=="1" (
  echo start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)\BDBE 3.38 Build v3 by RaZZoR" "Z:\GAMES\BRUTAL_DOOM (uwu)\BDBE 3.38 Build v3 by RaZZoR\doom.exe" -file HontE_remastered_Experimental_REV1.103.wad>>"%~dp0dryrun.log" 2>&1
  exit /b 0
)
start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)\BDBE 3.38 Build v3 by RaZZoR" "Z:\GAMES\BRUTAL_DOOM (uwu)\BDBE 3.38 Build v3 by RaZZoR\doom.exe" -file HontE_remastered_Experimental_REV1.103.wad
