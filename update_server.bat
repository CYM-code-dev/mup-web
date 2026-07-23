@echo off
REM ============================================================
REM  mup-web one-shot update. Copy onto the server (E:\mup-web)
REM  and double-click / run. Order: stop service -> pull -> deps -> start.
REM  gc.auto=0 cuts pack churn, but it does NOT by itself stop the Windows
REM  "Unlink of file failed - try again?" prompt -- that fires during fetch
REM  when AV / a file watcher holds a .git pack open. So fetch is wrapped:
REM    echo n|  -> answers the prompt (skip locked file, no hang), and
REM    4x retry + 3s wait -> rides out transient AV/watcher locks.
REM ============================================================
setlocal
title mup-web update
set "PROJECT_DIR=%~dp0."
set "BRANCH=main"
set "SVC_NAME=MupWeb"
cd /d "%PROJECT_DIR%"

REM ---- locate nssm (on PATH, or nssm.exe next to this script) ----
set "NSSM="
for /f "delims=" %%i in ('where nssm 2^>nul') do set "NSSM=%%i"
if not defined NSSM if exist "%PROJECT_DIR%\nssm.exe" set "NSSM=%PROJECT_DIR%\nssm.exe"

echo === [0/4] stop service %SVC_NAME% (release file locks) ===
if defined NSSM (%NSSM% stop %SVC_NAME% >nul 2>&1) else (echo     [!] nssm not found - service not managed)

echo === [1/4] git pull (gc off; retry rides out AV/watcher locks) ===
git config gc.auto 0
set /a FETCH_TRIES=0
:fetchretry
set /a FETCH_TRIES+=1
REM echo n| auto-answers "Unlink failed - try again?" -> skip the locked
REM file (harmless orphan) so the script can't hang. Retry clears transient
REM AV / watcher handles that hold .git packs open.
echo n|git -c gc.auto=0 fetch origin
if errorlevel 1 if %FETCH_TRIES% LSS 4 (
  echo     [!] fetch attempt %FETCH_TRIES% hit a file lock, retry in 3s...
  ping -n 4 127.0.0.1 >nul
  goto fetchretry
)
git -c gc.auto=0 reset --hard origin/%BRANCH%

echo === [2/4] install deps + import check ===
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\pip install -r requirements.txt
  .venv\Scripts\python.exe -c "import fastapi,uvicorn,docx,openpyxl,PIL,requests; print('imports OK')"
) else (echo     [!] .venv not found - deps skipped)

echo === [3/4] start service %SVC_NAME% ===
if defined NSSM (%NSSM% start %SVC_NAME%) else (echo     [!] nssm not found - start it manually)

echo.
echo ============================================================
echo  Done. http://localhost:8000/  (or SERVER_IP:8000)
echo ============================================================
endlocal
pause
