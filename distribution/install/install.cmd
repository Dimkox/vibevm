@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "VIBEVM_INSTALL_EXIT=1"
set "VIBEVM_INSTALL_SCRIPT="
set "VIBEVM_INSTALL_SCRIPT_OWNED="
set "VIBEVM_INSTALL_POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

if "%VIBEVM_INSTALL_TEST_MODE%"=="1" if defined VIBEVM_INSTALL_TEST_SCRIPT (
  set "VIBEVM_INSTALL_SCRIPT=%VIBEVM_INSTALL_TEST_SCRIPT%"
  if defined VIBEVM_INSTALL_TEST_POWERSHELL set "VIBEVM_INSTALL_POWERSHELL=%VIBEVM_INSTALL_TEST_POWERSHELL%"
  goto run_installer
)

set "VIBEVM_INSTALL_SCRIPT=%TEMP%\vibevm-install-%RANDOM%-%RANDOM%.ps1"
set "VIBEVM_INSTALL_SCRIPT_OWNED=1"
curl.exe --fail --silent --show-error --location --connect-timeout 15 --max-time 60 --max-filesize 1048576 "https://vibevm.org/install.ps1" --output "%VIBEVM_INSTALL_SCRIPT%"
if errorlevel 1 (
  set "VIBEVM_INSTALL_EXIT=%ERRORLEVEL%"
  goto cleanup
)

:run_installer
set "VIBEVM_INSTALL_TEST_MODE="
set "VIBEVM_INSTALL_TEST_SCRIPT="
set "VIBEVM_INSTALL_TEST_POWERSHELL="
"%VIBEVM_INSTALL_POWERSHELL%" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%VIBEVM_INSTALL_SCRIPT%" %*
set "VIBEVM_INSTALL_EXIT=%ERRORLEVEL%"

:cleanup
if defined VIBEVM_INSTALL_SCRIPT_OWNED if exist "%VIBEVM_INSTALL_SCRIPT%" del /q "%VIBEVM_INSTALL_SCRIPT%" >nul 2>&1
endlocal & exit /b %VIBEVM_INSTALL_EXIT%
