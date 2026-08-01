@echo off
setlocal
set "GAME_DIR=D:\Entertainment\Game\Touhou\th06"
set "GAME_EXE=%GAME_DIR%\th06.exe"
set "PYTHON=%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe"

if not exist "%GAME_EXE%" (
  echo Missing exact TH06 executable: "%GAME_EXE%"
  exit /b 1
)
if not exist "%PYTHON%" (
  echo Missing Windows Python: "%PYTHON%"
  exit /b 1
)

start "" /D "%GAME_DIR%" "%GAME_EXE%"
"%PYTHON%" "%~dp0scripts\run_th06_agent.py" --game-dir "%GAME_DIR%" --patch-lives --start-hard --armed %*
exit /b %errorlevel%
