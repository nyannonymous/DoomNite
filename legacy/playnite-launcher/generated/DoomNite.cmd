@echo off
setlocal enabledelayedexpansion
title DoomNite
set DOOMNITE_DRYRUN=0
if /I "%~1"=="--dryrun" set DOOMNITE_DRYRUN=1
set "pick=%~2"
set "oneshot=0"
if not defined pick goto :top
set "oneshot=1"
goto dispatch
:top
cls
echo ======================================================
echo                    D O O M N I T E
echo ======================================================
echo
echo  1. Brutal Doom (metal)
echo       Brutal Doom 22 + Doom Metal vol5
echo  2. Brutal Doom (music)
echo       Brutal Doom 22 on Ultimate Doom
echo  3. DukeBoomem
echo       Duke Nukem as Boomstick guy
echo  4. Aliens: Eradication TC
echo       Full 8-level campaign
echo  5. Aliens: Eradication TC (D2 only)
echo       TC without the mapset
echo  6. Aliens: Eradication TC (UD only)
echo       TC without the mapset
echo  7. QuakinDoom: Total 3-D Edition
echo       Quake 1 in Doom II
echo  8. QuakinDoom (Ultimate Doom)
echo       Quake 1 on Ultimate Doom
echo  9. QuakinDoom (weapons only)
echo       No QuakinMobs
echo  10. Shadow Warrior (Doom II)
echo       Full conversion
echo  11. Shadow Warrior (mod only)
echo       No Enter-the-Wang mappack
echo  12. Call of Doom: Black Warfare
echo       CoD-style campaign
echo  13. The Bikini Bottom Massacre
echo       SpongeBob, but in Doom
echo  14. DoomRPG
echo       Doom II
echo  15. DoomRPG + Brutal Doom (experimental)
echo       Playnite flags this combo as unsupported
echo  16. DoomRPG (Doom 1)
echo       Doom I version
echo  17. Hocus Pocus 3D
echo       Hocus Pocus in Doom
echo  18. DN3DooM (Doom II)
echo       Duke 3D in Doom II
echo  19. DN3DooM (Ultimate Doom)
echo       Duke 3D in Ultimate Doom
echo  20. MyHouse.pk3
echo       Recreation of a childhood home
echo  21. MoonMan Doom 2
echo  22. MoonMan (Ultimate Doom)
echo  23. BDBE - Enhanced Episode 1
echo       Brutal Doom Black Edition, E1
echo  24. BDBE - HontE Remastered
echo       Brutal Doom Black Edition, HontE
echo  25. DBP37: Auger;Zenith
echo       2023 Doom II mod
echo  26. Half Life in Doom
echo       HL1 in Doom
echo  27. Sonic Robo Blast 2 (Doom)
echo       SRB2, Doom-style build
echo.
echo   0. Exit
echo.
set "pick="
set /p "pick=Number, then Enter: "
if not defined pick exit /b 0
for /f "tokens=1" %%a in ("!pick!") do set "pick=%%a"
echo !pick!|findstr /x /c:"0" /c:"1" /c:"2" /c:"3" /c:"4" /c:"5" /c:"6" /c:"7" /c:"8" /c:"9" /c:"10" /c:"11" /c:"12" /c:"13" /c:"14" /c:"15" /c:"16" /c:"17" /c:"18" /c:"19" /c:"20" /c:"21" /c:"22" /c:"23" /c:"24" /c:"25" /c:"26" /c:"27" >nul
if errorlevel 1 goto bad
if "!pick!"=="0" exit /b 0
if "%DOOMNITE_DRYRUN%"=="1" goto dispatch
echo.
echo Type the number again to launch it, anything else to go back.
set "confirm="
set /p "confirm=Launch? (number again): "
for /f "tokens=1" %%a in ("!confirm!") do set "confirm=%%a"
if "!confirm!"=="!pick!" goto dispatch
goto top
:bad
echo Not one of the numbers above.
pause
goto top
:dispatch
if "!pick!"=="1" call "%~dp001_Brutal_Doom__metal.cmd"
if "!pick!"=="2" call "%~dp002_Brutal_Doom__music.cmd"
if "!pick!"=="3" call "%~dp003_DukeBoomem.cmd"
if "!pick!"=="4" call "%~dp004_Aliens__Eradication_TC.cmd"
if "!pick!"=="5" call "%~dp005_Aliens__Eradication_TC__D2_only.cmd"
if "!pick!"=="6" call "%~dp006_Aliens__Eradication_TC__UD_only.cmd"
if "!pick!"=="7" call "%~dp007_QuakinDoom__Total_3_D_Edition.cmd"
if "!pick!"=="8" call "%~dp008_QuakinDoom__Ultimate_Doom.cmd"
if "!pick!"=="9" call "%~dp009_QuakinDoom__weapons_only.cmd"
if "!pick!"=="10" call "%~dp010_Shadow_Warrior__Doom_II.cmd"
if "!pick!"=="11" call "%~dp011_Shadow_Warrior__mod_only.cmd"
if "!pick!"=="12" call "%~dp012_Call_of_Doom__Black_Warfare.cmd"
if "!pick!"=="13" call "%~dp013_The_Bikini_Bottom_Massacre.cmd"
if "!pick!"=="14" call "%~dp014_DoomRPG.cmd"
if "!pick!"=="15" call "%~dp015_DoomRPG___Brutal_Doom__experimental.cmd"
if "!pick!"=="16" call "%~dp016_DoomRPG__Doom_1.cmd"
if "!pick!"=="17" call "%~dp017_Hocus_Pocus_3D.cmd"
if "!pick!"=="18" call "%~dp018_DN3DooM__Doom_II.cmd"
if "!pick!"=="19" call "%~dp019_DN3DooM__Ultimate_Doom.cmd"
if "!pick!"=="20" call "%~dp020_MyHouse_pk3.cmd"
if "!pick!"=="21" call "%~dp021_MoonMan_Doom_2.cmd"
if "!pick!"=="22" call "%~dp022_MoonMan__Ultimate_Doom.cmd"
if "!pick!"=="23" call "%~dp023_BDBE___Enhanced_Episode_1.cmd"
if "!pick!"=="24" call "%~dp024_BDBE___HontE_Remastered.cmd"
if "!pick!"=="25" call "%~dp025_DBP37__Auger_Zenith.cmd"
if "!pick!"=="26" call "%~dp026_Half_Life_in_Doom.cmd"
if "!pick!"=="27" call "%~dp027_Sonic_Robo_Blast_2__Doom.cmd"
if "!oneshot!"=="1" exit /b 0
goto top
