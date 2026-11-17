@echo off
rem HADES OS v3 launcher - ASCII only on purpose.
rem A Persian string in a .bat file depends on the console codepage and breaks
rem silently on cp1252; every human-readable string lives in the UTF-8 docs instead.
rem Use Python 3.9+ on PATH; avoid hard-coded minor releases.
setlocal
cd /d "%~dp0"

if "%1"=="" goto menu
goto %1

:menu
echo HADES OS v3
echo   check  - structure + registry verification (doctor)
echo   build  - index, wiki site
echo   test   - the gate test battery (scratch vaults only, never this vault)
echo   all    - check + build
echo.
echo run: start.bat check
goto end

:check
python 15_SYSTEM\scripts\hades.py doctor
if errorlevel 1 echo. & echo DOCTOR REPORTED ERRORS - read the lines above
goto end

:index
python 15_SYSTEM\scripts\hades.py index
goto end

:build
python 15_SYSTEM\scripts\hades.py index
python 15_SYSTEM\scripts\wiki.py build
goto end

:wiki
python 15_SYSTEM\scripts\wiki.py serve
goto end

:test
python 15_SYSTEM\scripts\test_hades.py
goto end

:all
python 15_SYSTEM\scripts\hades.py doctor
python 15_SYSTEM\scripts\hades.py index
python 15_SYSTEM\scripts\wiki.py build
goto end

:end
endlocal
