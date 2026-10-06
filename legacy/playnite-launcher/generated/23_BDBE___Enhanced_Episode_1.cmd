@echo off
rem BDBE - Enhanced Episode 1 - Brutal Doom Black Edition, E1
rem start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)\BDBE 3.38 Build v3 by RaZZoR" "Z:\GAMES\BRUTAL_DOOM (uwu)\BDBE 3.38 Build v3 by RaZZoR\doom.exe" -file enh_e1v1.8c.wad
cd /D "Z:\GAMES\BRUTAL_DOOM (uwu)\BDBE 3.38 Build v3 by RaZZoR"
if /I "%DOOMNITE_DRYRUN%"=="1" (
  echo start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)\BDBE 3.38 Build v3 by RaZZoR" "Z:\GAMES\BRUTAL_DOOM (uwu)\BDBE 3.38 Build v3 by RaZZoR\doom.exe" -file enh_e1v1.8c.wad>>"%~dp0dryrun.log" 2>&1
  exit /b 0
)
start "" /D "Z:\GAMES\BRUTAL_DOOM (uwu)\BDBE 3.38 Build v3 by RaZZoR" "Z:\GAMES\BRUTAL_DOOM (uwu)\BDBE 3.38 Build v3 by RaZZoR\doom.exe" -file enh_e1v1.8c.wad
