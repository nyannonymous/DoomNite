@echo off
setlocal enabledelayedexpansion
title DoomNite - Mods
cls
echo ======================================================
echo       D O O M N I T E  -  M O D S
echo ======================================================
echo
echo  Ghosted cards are not installed. Choosing one downloads
echo  it from GitHub and installs it; then it becomes playable.
echo
echo  ~ 1. Brutal Doom Community Expansion  (120.7 MB)
echo       Not installed - Install   Combined community expansion for Brutal Doom v21 - all the latest fixes and features in one file.
echo  ~ 2. Brutal Doom Platinum  (204.7 MB)
echo       Not installed - Install   EmeraldCoasttt's heavily reworked Brutal Doom fork.
echo    3. DOOM 64 EX-Plus  (4.1 MB)
echo       Installed - Play   Modernised DOOM 64 source port with fixes, modern video and new features.
echo  ~ 4. DOOM 64 EX-Plus Enhanced  (18.0 MB)
echo       Not installed - Install   Community fork of EX+ with new content, options and features.
echo  ~ 5. Doom RPG Remake Project  (70.6 MB)
echo       Not installed - Install   Total conversion remake of Doom RPG on GZDoom, MIT licensed.
echo    6. ALIENS: Eradication TC  (184.8 MB)
echo       Installed - Play   Full 8-level Aliens campaign TC built on the Aliens Trilogy / Ultimate Doom mod.
echo
echo  (~ = ghost card, not installed yet)
echo  0. Back
echo
set "pick="
set /p "pick=Number, then Enter: "
if not defined pick exit /b 0
for /f "tokens=1" %%a in ("!pick!") do set "pick=%%a"
if "!pick!"=="0" exit /b 0
if "!pick!"=="1" call "%~dp0MOD_ghost_brutal_community.cmd"
if "!pick!"=="2" call "%~dp0MOD_ghost_brutal_platinum.cmd"
if "!pick!"=="3" call "%~dp0MOD_play_doom64ex_plus.cmd"
if "!pick!"=="4" call "%~dp0MOD_ghost_doom64ex_enhanced.cmd"
if "!pick!"=="5" call "%~dp0MOD_ghost_drrp.cmd"
if "!pick!"=="6" call "%~dp0MOD_play_aliens_eradication.cmd"
exit /b 0
