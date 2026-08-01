@echo off
setlocal
if not defined TH06_GAME_DIR set "TH06_GAME_DIR=D:\Entertainment\Game\Touhou\th06"
if not defined TH06_PYTHON set "TH06_PYTHON=%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe"

set "GAME_DIR=%TH06_GAME_DIR%"
set "GAME_EXE=%GAME_DIR%\th06.exe"
set "PYTHON=%TH06_PYTHON%"
set "RUN_SECONDS=30"

if not "%~1"=="" set "RUN_SECONDS=%~1"

if not exist "%GAME_EXE%" (
  echo Missing exact TH06 executable: "%GAME_EXE%"
  exit /b 1
)
if not exist "%PYTHON%" (
  echo Missing Windows Python: "%PYTHON%"
  exit /b 1
)

start "" /D "%GAME_DIR%" "%GAME_EXE%"
"%PYTHON%" "%~dp0scripts\run_th06_agent.py" --game-dir "%GAME_DIR%" --seconds "%RUN_SECONDS%"
exit /b %errorlevel%
