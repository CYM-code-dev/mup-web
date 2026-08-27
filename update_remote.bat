@echo off
REM ============================================================
REM  mup-web remote update. Run from the dev/test machine over ssh.
REM  Default target: E:\server\mup-web\update_server.bat on the server.
REM  Pass another server-side .bat to update a different program:
REM    update_remote.bat E:\Management-of-Standard-Substance\update_server.bat
REM  One-time server setup (admin PowerShell on the server; done 2026-08 on 10.1.93.25):
REM    Add-WindowsCapability may FAKE-succeed on this network (no sshd.exe dropped).
REM    Proven route: download OpenSSH-Win64.zip from github.com/PowerShell/Win32-OpenSSH
REM    releases, Expand-Archive to C:\, then:
REM      powershell -ExecutionPolicy Bypass -File C:\OpenSSH-Win64\install-sshd.ps1
REM      Start-Service sshd ; Set-Service sshd -StartupType Automatic
REM    plus (or ssh logins get a UAC-filtered token, and nssm stop is denied):
REM      k = HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System
REM      Set-ItemProperty k LocalAccountTokenFilterPolicy 1 -Type DWord
REM ============================================================
setlocal
title mup-web remote update

set "SRV=10.1.93.25"
set "SUSER=Administrator"
set "CMD=cmd /c E:\server\mup-web\update_server.bat"
if not "%~1"=="" set "CMD=cmd /c %~1"

REM stdin for the ssh session is redirected from NUL so the trailing
REM 'pause' inside the remote bat cannot hang the session
ssh %SUSER%@%SRV% "%CMD% < NUL"
if errorlevel 1 ( echo [X] remote update FAILED & pause & exit /b 1 )

echo === waiting for service to come back ===
for /l %%i in (1,1,60) do (
  curl -s -o nul -m 3 http://%SRV%:8000/api/meta/constants && goto ok
  ping -n 4 127.0.0.1 >nul
)
echo [X] service did not come back within ~5min & exit /b 1
:ok
echo OK: http://%SRV%:8000/mup is back
pause
endlocal
