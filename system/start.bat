@echo off
rem ===========================================================
rem  OMNIVOICE STUDIO - Startprogramm (Bootstrap)
rem  Sucht ein passendes Python und startet danach sofort die
rem  grafische Oberflaeche (omnivoice_toolkit.py).
rem  Bewusst nur ASCII, damit es in jeder Konsole lesbar bleibt.
rem ===========================================================
setlocal EnableExtensions EnableDelayedExpansion

chcp 65001 >nul 2>&1
title OmniVoice Studio - iZE
color 0F

rem Die Fenstergroesse setzt die Oberflaeche selbst. Sie erkennt dabei, ob
rem Windows Terminal oder die alte Konsole laeuft - "mode con" wuerde im
rem Windows Terminal nur den Puffer verstellen und die Anzeige zerreissen.

set "SYS_DIR=%~dp0"
if "%SYS_DIR:~-1%"=="\" set "SYS_DIR=%SYS_DIR:~0,-1%"
set "APP=%SYS_DIR%\omnivoice_toolkit.py"
set "DATEN=%SYS_DIR%\daten"
set "PY_VERSION=3.12.10"
set "PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/python-%PY_VERSION%-amd64.exe"

if not exist "%DATEN%" mkdir "%DATEN%" >nul 2>&1

if not exist "%APP%" (
    echo.
    echo   FEHLER: "%APP%" wurde nicht gefunden.
    echo   Bitte den Ordner "toolkit" komplett neu entpacken.
    echo.
    pause
    exit /b 1
)

:NEUSTART
call :FINDE_PYTHON
if not defined PYEXE goto :KEIN_PYTHON

cls
echo.
echo   OmniVoice Studio wird geladen ...
echo.

"%PYEXE%" %PYARG% "%APP%" %*
set "RC=!ERRORLEVEL!"

rem Rueckgabecode 10 = die Oberflaeche bittet um eine Python-Installation
if "!RC!"=="10" (
    call :PYTHON_INSTALLIEREN
    goto :NEUSTART
)

rem Rueckgabecode 20 = ein geprueftes Toolkit-Update nach Programmende anwenden
if "!RC!"=="20" (
    set "UPDATE_SCRIPT=%DATEN%\update-bereit\anwenden.ps1"
    if exist "!UPDATE_SCRIPT!" (
        start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "!UPDATE_SCRIPT!"
        exit /b 0
    )
    cls
    echo.
    echo  ============================================================
    echo    Das Update wurde vorbereitet, der Anwender fehlt aber.
    echo  ============================================================
    echo.
    echo    Bitte im Hauptmenue erneut nach Updates suchen.
    echo.
    pause
    exit /b 1
)

if "!RC!"=="0" goto :ENDE

cls
echo.
echo  ============================================================
echo    OmniVoice Studio wurde unerwartet beendet ^(Code !RC!^)
echo  ============================================================
echo.
echo    Details stehen in:
echo      %DATEN%\protokolle
echo.
pause
goto :ENDE


rem -----------------------------------------------------------
rem  Sucht ein Python 3.10 - 3.13 (torch braucht diesen Bereich)
rem -----------------------------------------------------------
:FINDE_PYTHON
set "PYEXE="
set "PYARG="

for %%V in (3.12 3.11 3.13 3.10) do (
    if not defined PYEXE (
        py -%%V -c "import sys" >nul 2>&1
        if not errorlevel 1 (
            set "PYEXE=py"
            set "PYARG=-%%V"
        )
    )
)
if defined PYEXE goto :eof

for %%D in (
    "%LOCALAPPDATA%\Programs\Python\Python312"
    "%LOCALAPPDATA%\Programs\Python\Python311"
    "%LOCALAPPDATA%\Programs\Python\Python313"
    "%LOCALAPPDATA%\Programs\Python\Python310"
    "%ProgramFiles%\Python312"
    "%ProgramFiles%\Python311"
    "%ProgramFiles%\Python313"
    "%ProgramFiles%\Python310"
) do (
    if not defined PYEXE (
        if exist "%%~D\python.exe" set "PYEXE=%%~D\python.exe"
    )
)
if defined PYEXE goto :eof

rem Irgendein Python im PATH (die Oberflaeche prueft die Version selbst)
python -c "import sys" >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined PYEXE set "PYEXE=%%P"
    )
)
if defined PYEXE goto :eof

py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PYEXE=py"
    set "PYARG=-3"
)
goto :eof


rem -----------------------------------------------------------
rem  Kein Python vorhanden -> anbieten es zu installieren
rem -----------------------------------------------------------
:KEIN_PYTHON
cls
echo.
echo  ============================================================
echo                     O M N I V O I C E
echo                  Ein-Klick-Installation
echo  ============================================================
echo.
echo    Auf diesem PC wurde kein Python gefunden.
echo    Python ist die Grundlage, ohne die nichts laeuft.
echo.
echo    Soll Python %PY_VERSION% jetzt automatisch installiert
echo    werden? ^(ca. 27 MB, dauert 1-2 Minuten^)
echo.
echo    Es wird nur fuer deinen Benutzer installiert und
echo    veraendert sonst nichts am System.
echo.
choice /C JN /N /M "   Python jetzt installieren?  [J] Ja   [N] Nein : "
if errorlevel 2 goto :ABBRUCH_PYTHON

call :PYTHON_INSTALLIEREN
call :FINDE_PYTHON
if defined PYEXE goto :NEUSTART

cls
echo.
echo  ============================================================
echo    Python konnte nicht automatisch installiert werden.
echo  ============================================================
echo.
echo    Bitte einmal von Hand installieren:
echo      1. Seite oeffnen:  https://www.python.org/downloads/
echo      2. Python 3.12 herunterladen und starten
echo      3. WICHTIG: Haken bei "Add python.exe to PATH" setzen
echo      4. Danach STARTEN.bat erneut doppelklicken
echo.
pause
exit /b 1

:ABBRUCH_PYTHON
echo.
echo    Abgebrochen. Ohne Python kann OmniVoice nicht laufen.
echo.
pause
exit /b 1


rem -----------------------------------------------------------
rem  Python automatisch installieren (winget, sonst Direktdownload)
rem -----------------------------------------------------------
:PYTHON_INSTALLIEREN
cls
echo.
echo  ============================================================
echo    Python %PY_VERSION% wird installiert - bitte warten
echo  ============================================================
echo.

where winget >nul 2>&1
if not errorlevel 1 (
    echo    [1/2] Versuch ueber den Windows-Paketmanager ^(winget^) ...
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements >nul 2>&1
    call :FINDE_PYTHON
    if defined PYEXE (
        echo    Python wurde installiert.
        timeout /t 2 >nul
        goto :eof
    )
    echo    winget hat nicht funktioniert - nutze Direktdownload.
) else (
    echo    [1/2] winget ist nicht vorhanden - nutze Direktdownload.
)

set "PYSETUP=%TEMP%\python-%PY_VERSION%-amd64.exe"
echo    [2/2] Lade Installationsdatei von python.org ...
curl -L --fail --retry 2 -o "%PYSETUP%" "%PY_URL%"
if not exist "%PYSETUP%" (
    echo    Download fehlgeschlagen ^(Internetverbindung pruefen^).
    timeout /t 3 >nul
    goto :eof
)

echo    Installiere Python - das Fenster bitte offen lassen ...
"%PYSETUP%" /passive InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1
del "%PYSETUP%" >nul 2>&1
call :FINDE_PYTHON
if defined PYEXE echo    Python wurde installiert.
timeout /t 2 >nul
goto :eof


:ENDE
endlocal
exit /b 0
