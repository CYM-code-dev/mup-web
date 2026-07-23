@echo off
REM ============================================================
REM  mup-web one-shot update. Copy onto the server (E:\mup-web)
REM  and double-click / run. Git gc is disabled so the
REM  "Unlink of file failed ... try again?" prompt can NOT hang.
REM  Order: stop service -> pull -> deps -> start service.
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

echo === [1/4] git pull (gc disabled - no hang) ===
git config gc.auto 0
git -c gc.auto=0 fetch origin
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
