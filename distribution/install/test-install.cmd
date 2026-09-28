@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "VIBEVM_INSTALL_TEST_ROOT=%TEMP%\vibevm-install-cmd-test-%RANDOM%-%RANDOM%"
mkdir "%VIBEVM_INSTALL_TEST_ROOT%" || exit /b 1
set "VIBEVM_INSTALL_TEST_RUNNER=%VIBEVM_INSTALL_TEST_ROOT%\powershell.cmd"
set "VIBEVM_INSTALL_TEST_SCRIPT=%VIBEVM_INSTALL_TEST_ROOT%\install.ps1"
(
  echo @echo off
  echo if defined VIBEVM_INSTALL_TEST_MODE exit /b 91
  echo exit /b 37
) > "%VIBEVM_INSTALL_TEST_RUNNER%"
type nul > "%VIBEVM_INSTALL_TEST_SCRIPT%"

set "VIBEVM_INSTALL_TEST_MODE=1"
set "VIBEVM_INSTALL_TEST_POWERSHELL=%VIBEVM_INSTALL_TEST_RUNNER%"
call "%~dp0install.cmd"
set "VIBEVM_INSTALL_ACTUAL_EXIT=%ERRORLEVEL%"
set "VIBEVM_INSTALL_TEST_MODE="
set "VIBEVM_INSTALL_TEST_POWERSHELL="
set "VIBEVM_INSTALL_TEST_SCRIPT="
rmdir /s /q "%VIBEVM_INSTALL_TEST_ROOT%"
if not "%VIBEVM_INSTALL_ACTUAL_EXIT%"=="37" (
  echo install.cmd did not preserve the PowerShell child exit code: expected 37, got %VIBEVM_INSTALL_ACTUAL_EXIT% 1>&2
  exit /b 1
)
findstr /L /C:"https://vibevm.org/install.ps1" "%~dp0install.cmd" >nul || (
  echo install.cmd does not delegate to the published install.ps1 1>&2
  exit /b 1
)
findstr /L /C:"--max-filesize 1048576" "%~dp0install.cmd" >nul || (
  echo install.cmd does not bound the installer-script download 1>&2
  exit /b 1
)
findstr /L /C:"--max-time 60" "%~dp0install.cmd" >nul || (
  echo install.cmd does not bound the installer-script transfer time 1>&2
  exit /b 1
)
findstr /L /C:"endlocal & exit /b %%VIBEVM_INSTALL_EXIT%%" "%~dp0install.cmd" >nul || (
  echo install.cmd does not preserve its child exit code across endlocal 1>&2
  exit /b 1
)

cmd.exe /d /c "cmd.exe /c exit 22 && call \"%~dp0install.cmd\""
if not "%ERRORLEVEL%"=="22" (
  echo the advertised download-then-call shape did not preserve producer failure 1>&2
  exit /b 1
)

echo install.cmd offline tests passed
exit /b 0
