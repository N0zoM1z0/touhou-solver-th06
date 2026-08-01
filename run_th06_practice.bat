@echo off
setlocal
if not defined TH06_GAME_DIR set "TH06_GAME_DIR=D:\Entertainment\Game\Touhou\th06"
if not defined TH06_PYTHON set "TH06_PYTHON=%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe"

set "GAME_DIR=%TH06_GAME_DIR%"
set "GAME_EXE=%GAME_DIR%\th06.exe"
set "PYTHON=%TH06_PYTHON%"

if not exist "%GAME_EXE%" (
  echo Missing exact TH06 executable: "%GAME_EXE%"
  exit /b 1
)
if not exist "%PYTHON%" (
  echo Missing Windows Python: "%PYTHON%"
  exit /b 1
)
if "%~1"=="" (
  echo Usage: run_th06_practice.bat --practice-stage 1..6 [--seconds N]
  exit /b 2
)

start "" /D "%GAME_DIR%" "%GAME_EXE%"
"%PYTHON%" "%~dp0scripts\run_th06_agent.py" --game-dir "%GAME_DIR%" --patch-lives --armed --stop-game %*
exit /b %errorlevel%
