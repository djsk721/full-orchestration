@echo off
setlocal
where pyw.exe >nul 2>nul
if errorlevel 1 (
  echo Install Python 3.11 or newer with Tcl/Tk and the Python launcher.
  pause
  exit /b 1
)
start "" pyw.exe -3 "%~dp0ModelOrchestration.pyw"
