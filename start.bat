@echo off
rem HADES OS v3 launcher - ASCII only on purpose.
rem A Persian string in a .bat file depends on the console codepage and breaks
rem silently on cp1252; every human-readable string lives in the UTF-8 docs instead.
rem Use Python 3.9+ on PATH; avoid hard-coded minor releases.
setlocal
rem Preserve child status before printing diagnostics.
set "sbo_exit=0"
cd /d "%~dp0"

rem Dispatch only supported actions; do not jump to arbitrary batch labels.
if "%~1"=="" goto menu
if /i "%~1"=="help" goto menu
if /i "%~1"=="--help" goto menu
if /i "%~1"=="check" goto check
if /i "%~1"=="index" goto index
if /i "%~1"=="build" goto build
if /i "%~1"=="wiki" goto wiki
if /i "%~1"=="test" goto test
if /i "%~1"=="all" goto all
echo Unknown launcher action. Run start.bat to list supported commands.
set "sbo_exit=2"
goto end

:menu
echo HADES OS v3
echo   check  - structure + registry verification (doctor)
echo   build  - index, wiki site
echo   index  - rebuild the local index
echo   wiki   - serve the local wiki
echo   test   - the gate test battery (scratch vaults only, never this vault)
echo   all    - check + build
echo.
echo run: start.bat check
goto end

:check
python 15_SYSTEM\scripts\hades.py doctor
set "sbo_exit=%errorlevel%"
if not "%sbo_exit%"=="0" (
    echo.
    echo DOCTOR REPORTED ERRORS - read the lines above
)
goto end

:index
python 15_SYSTEM\scripts\hades.py index
set "sbo_exit=%errorlevel%"
goto end

:build
python 15_SYSTEM\scripts\hades.py index
set "sbo_exit=%errorlevel%"
if not "%sbo_exit%"=="0" goto end
python 15_SYSTEM\scripts\wiki.py build
set "sbo_exit=%errorlevel%"
goto end

:wiki
python 15_SYSTEM\scripts\wiki.py serve
set "sbo_exit=%errorlevel%"
goto end

:test
python 15_SYSTEM\scripts\test_hades.py
set "sbo_exit=%errorlevel%"
goto end

:all
python 15_SYSTEM\scripts\hades.py doctor
set "sbo_exit=%errorlevel%"
if not "%sbo_exit%"=="0" goto end
python 15_SYSTEM\scripts\hades.py index
set "sbo_exit=%errorlevel%"
if not "%sbo_exit%"=="0" goto end
python 15_SYSTEM\scripts\wiki.py build
set "sbo_exit=%errorlevel%"
goto end

:end
endlocal & exit /b %sbo_exit%
