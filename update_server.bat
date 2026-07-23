@echo off
REM mup-web update. Run from inside the project dir on the server (E:\mup-web).
REM Pulls latest from GitHub, reinstalls deps, restarts NSSM service MupWeb.
title mup-web update
setlocal
set "PROJECT_DIR=%~dp0."
set "BRANCH=main"
set "SVC_NAME=MupWeb"
cd /d "%PROJECT_DIR%"

echo === [1/3] git pull ===
git config gc.auto 0
git -c gc.auto=0 fetch origin
git -c gc.auto=0 reset --hard origin/%BRANCH%

echo === [2/3] deps + import check ===
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python.exe -c "import fastapi,uvicorn,docx,openpyxl,PIL,requests; print('imports OK')"

echo === [3/3] restart service ===
set "NSSM="
for /f "delims=" %%i in ('where nssm 2^>nul') do set "NSSM=%%i"
if not defined NSSM if exist "%PROJECT_DIR%\nssm.exe" set "NSSM=%PROJECT_DIR%\nssm.exe"
if not defined NSSM (echo [X] nssm not found & exit /b 1)
%NSSM% restart %SVC_NAME%
echo === done. http://LOCAL_IP:8000/ ===
endlocal
