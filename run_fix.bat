@echo off
rem ================================================================
rem  GameVisual Fixer v2 - one-click bootstrap launcher
rem  Flow: detect Python >=3.10 -> (missing?) popup confirm ->
rem        download portable embeddable Python (no admin needed) ->
rem        run fix_gamevisual.py -> keep window open.
rem
rem  Internal self-test flags (SAFE: they never run the fixer):
rem    --bootstrap-selftest       detection only, prints BOOTSTRAP OK
rem    --bootstrap-download-test  download+extract into TEMP, verify,
rem                               cleanup, prints DOWNLOAD TEST OK
rem  NOTE: ASCII-only on purpose; non-ASCII breaks under cp936 console.
rem ================================================================
setlocal
cd /d "%~dp0"
title GameVisual Fixer v2
set "SCRIPT=%~dp0fix_gamevisual.py"
set "RUNTIME_DIR=%~dp0_python"
rem Download source ORDER MATTERS: CN mirrors first (python.org trickles
rem at ~16 KB/s from CN and stalls PS fallback indefinitely).
set "PY_URL_MIRROR1=https://mirrors.huaweicloud.com/python/3.12.10/python-3.12.10-embed-amd64.zip"
set "PY_URL_MIRROR2=https://registry.npmmirror.com/-/binary/python/3.12.10/python-3.12.10-embed-amd64.zip"
set "PY_URL=https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
set "NOCURL="
set "TESTMODE="
set "TESTDL="

if /i "%~1"=="--bootstrap-selftest" set "TESTMODE=1"
if /i "%~1"=="--bootstrap-download-test" set "TESTDL=1"

if not exist "%SCRIPT%" (
    echo [ERROR] %SCRIPT% not found. Re-extract the repository first.
    pause
    exit /b 1
)

echo === GameVisual Fixer v2 ========================================

where curl.exe >nul 2>nul || set "NOCURL=1"

if defined TESTDL (
    set "ZIP=%TEMP%\gvf-bootstrap-test\python-embed.zip"
    set "DEST=%TEMP%\gvf-bootstrap-test\_python"
    goto DO_INSTALL
)

:DETECT_PY
where py >nul 2>nul || goto TRY_PATH_PYTHON
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul || goto TRY_PATH_PYTHON
set "PY=py -3"
goto AFTER_DETECT

:TRY_PATH_PYTHON
where python >nul 2>nul || goto TRY_PORTABLE
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul || goto TRY_PORTABLE
set "PY=python"
goto AFTER_DETECT

:TRY_PORTABLE
if not exist "%RUNTIME_DIR%\python.exe" goto ASK_INSTALL
"%RUNTIME_DIR%\python.exe" -c "print('ok')" >nul 2>nul || goto ASK_INSTALL
set "PY=%RUNTIME_DIR%\python.exe"
goto AFTER_DETECT

:AFTER_DETECT
if defined TESTMODE (
    echo BOOTSTRAP OK: python=%PY%
    endlocal
    exit /b 0
)
goto RUN_FIXER

:ASK_INSTALL
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; $r=[System.Windows.Forms.MessageBox]::Show('Python runtime not detected. Automatically download portable Python (~11 MB)?','GameVisual Fixer',[System.Windows.Forms.MessageBoxButtons]::YesNo,[System.Windows.Forms.MessageBoxIcon]::Question); if($r -eq [System.Windows.Forms.DialogResult]::Yes){exit 0}else{exit 1}"
if errorlevel 1 goto DECLINED
set "ZIP=%TEMP%\gvf-python-embed.zip"
set "DEST=%RUNTIME_DIR%"
goto DO_INSTALL

:DO_INSTALL
for %%Z in ("%ZIP%") do set "ZIPDIR=%%~dpZ"
if not exist "%ZIPDIR%" mkdir "%ZIPDIR%"
call :FETCH "%PY_URL_MIRROR1%" && goto HAVE_ZIP
echo Mirror 1 failed, trying mirror 2 (npmmirror) ...
call :FETCH "%PY_URL_MIRROR2%" && goto HAVE_ZIP
echo Mirror 2 failed, trying official python.org (slow) ...
call :FETCH "%PY_URL%" && goto HAVE_ZIP
goto DOWNLOAD_FAILED

:HAVE_ZIP
echo Extracting to "%DEST%" ...
if not exist "%DEST%" mkdir "%DEST%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%ZIP%' -DestinationPath '%DEST%' -Force"
if errorlevel 1 goto DOWNLOAD_FAILED
"%DEST%\python.exe" -c "print('ok')" >nul 2>nul
if errorlevel 1 goto DOWNLOAD_FAILED
echo Portable Python installed at: %DEST%
if defined TESTDL (
    rd /s /q "%TEMP%\gvf-bootstrap-test" >nul 2>nul
    echo DOWNLOAD TEST OK
    endlocal
    exit /b 0
)
set "PY=%RUNTIME_DIR%\python.exe"
goto RUN_FIXER

:DECLINED
echo.
echo Declined. Python 3.10+ is required to run the fixer.
echo Install Python manually, then run this file again.
goto END_FAIL

:DOWNLOAD_FAILED
echo.
echo [ERROR] Portable Python download or extraction failed.
echo Check your network connection, or download manually:
echo   %PY_URL%
echo then extract the zip into this folder: %DEST%
goto END_FAIL

:RUN_FIXER
echo Using python: %PY%
echo ---------------------------------------------------------------
%PY% "%SCRIPT%" %*
set "EC=%errorlevel%"
echo.
echo Fixer exited with code %EC%.
pause
endlocal & exit /b %EC%

:FETCH
rem %1 = url; curl preferred (low-speed abort kills stalled links);
rem PowerShell fallback ONLY for ancient systems without curl.exe.
if exist "%ZIP%" del "%ZIP%" >nul 2>nul
echo   fetching %~1
if defined NOCURL goto FETCH_PS
curl.exe -L --fail --connect-timeout 15 --max-time 600 --speed-time 20 --speed-limit 1024 -o "%ZIP%" "%~1" >nul 2>nul
if errorlevel 1 exit /b 1
goto FETCH_VERIFY
:FETCH_PS
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -TimeoutSec 300 -Uri '%~1' -OutFile '%ZIP%' -UseBasicParsing"
if errorlevel 1 exit /b 1
:FETCH_VERIFY
if not exist "%ZIP%" exit /b 1
rem reject tiny error pages: the real embeddable zip is ~11 MB
for %%F in ("%ZIP%") do if %%~zF LSS 1000000 exit /b 1
exit /b 0

:END_FAIL
pause
exit /b 1
