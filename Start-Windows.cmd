@echo off
setlocal
cd /d "%~dp0"
rem Use inbox Windows PowerShell and modules even when launched from PowerShell 7.
set "WINPS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if exist "%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe" set "WINPS=%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
set "PSModulePath=%SystemRoot%\System32\WindowsPowerShell\v1.0\Modules"
"%WINPS%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows_setup.ps1" %*
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" echo Setup or startup did not complete. See the message above.
pause
exit /b %APP_EXIT%
