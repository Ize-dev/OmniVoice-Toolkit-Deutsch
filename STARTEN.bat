@echo off
rem ===========================================================
rem   OMNIVOICE STUDIO
rem
rem   Einfach diese Datei doppelklicken. Mehr ist nicht noetig.
rem   Beim ersten Mal richtet sich alles ein, danach startet
rem   OmniVoice damit direkt.
rem ===========================================================

cd /d "%~dp0"

if not exist "%~dp0system\start.bat" (
    echo.
    echo   FEHLER: Der Ordner "system" fehlt oder ist unvollstaendig.
    echo   Bitte den kompletten Ordner "toolkit" erneut entpacken.
    echo.
    pause
    exit /b 1
)

call "%~dp0system\start.bat" %*
exit /b %ERRORLEVEL%
