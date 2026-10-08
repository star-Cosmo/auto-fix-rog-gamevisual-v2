@echo off
rem ================================================================
rem  GameVisual Fixer v2 - one-click UNINSTALL / restore script
rem
rem  What it does:
rem    1. Finds the newest GameVisual_backup_<timestamp> snapshot
rem    2. Removes the ICC files the fixer placed into GameVisual
rem    3. Restores the backup (the pre-fix state) into GameVisual
rem
rem  Safe by design: never touches anything outside GameVisual dir.
rem  Requires admin (the fixer ran with admin, so restoring does too).
rem ================================================================
setlocal enabledelayedexpansion
title GameVisual Fixer v2 - Uninstall

set "BASE=C:\ProgramData\ASUS"
set "GV=%BASE%\GameVisual"

chcp 65001 >nul 2>nul

echo === GameVisual Fixer v2 - 卸载 / 还原 ================================

if not exist "%GV%" (
    echo [INFO] %GV% does not exist - nothing to restore.
    pause
    exit /b 0
)

rem -- self-elevate to admin if needed --------------------------------
net session >nul 2>nul
if errorlevel 1 (
    echo Requesting administrator rights...
    powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b 0
)

rem -- locate the newest backup ----------------------------------------
set "NEWEST="
for /f "delims=" %%d in ('dir /b /ad /o-d "%BASE%\GameVisual_backup_*" 2^>nul') do (
    if not defined NEWEST set "NEWEST=%%d"
)
if not defined NEWEST (
    echo [ERROR] 找不到备份目录 （%BASE%\GameVisual_backup_*）。
    echo         如果你从未运行过本修复工具，则没有需要还原的内容。
    pause
    exit /b 1
)

set "BACKUP=%BASE%\%NEWEST%"
echo 找到备份: %BACKUP%
echo.
echo 即将执行：
echo   1. 删除 %GV% 中修复工具放入的文件
echo   2. 用备份完整恢复 %GV%
echo.
echo 注意：如果你在修复后又手动改过 GameVisual 配置，还原会覆盖这些改动。
echo.

choice /c YN /n /m "确认执行还原? [Y=是 / N=否]: "
if errorlevel 2 (
    echo 已取消，未做任何修改。
    pause
    exit /b 0
)

rem -- wipe current files then restore from backup ---------------------
echo 正在清理 %GV% ...
del /q "%GV%\*" >nul 2>nul

echo 正在从备份恢复 ...
xcopy /e /y /i "%BACKUP%" "%GV%" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] 恢复失败。备份仍完整保留在 %BACKUP%，可手动恢复。
    pause
    exit /b 1
)

echo.
echo 还原完成！建议：
echo   1. 断网
echo   2. 完全关机再开机
echo   3. 打开奥创中心检查 GameVisual 是否恢复原状
echo.
echo 如需彻底清理备份目录，可手动删除:
echo   %BACKUP%
pause
exit /b 0