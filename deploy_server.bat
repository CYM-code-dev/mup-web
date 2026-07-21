@echo off
REM mup-web first-time deploy. Place this file in an empty dir on the server
REM (e.g. E:\), run it; it clones E:\<dir>\mup-web and registers NSSM service MupWeb.
title mup-web deploy
setlocal

set "PROJECT_DIR=%~dp0mup-web"
set "REPO_URL=https://github.com/CYM-code-dev/mup-web.git"
set "BRANCH=main"
set "SVC_NAME=MupWeb"
set "SVC_PORT=8000"

echo === [1/6] prerequisites ===
where git >nul 2>&1   || (echo [X] git not found. Run the portal deploy_server.bat, or: winget install Git.Git & exit /b 1)
where python >nul 2>&1 || (echo [X] python not found. winget install Python.Python.3.12 & exit /b 1)

echo === [2/6] clone repo ===
if exist "%PROJECT_DIR%\.git" (echo already cloned, skip) else (git clone -b %BRANCH% %REPO_URL% "%PROJECT_DIR%" || exit /b 1)
cd /d "%PROJECT_DIR%"

echo === [3/6] venv + deps ===
if not exist ".venv\Scripts\python.exe" (python -m venv .venv)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt

echo === [4/6] local config check (gitignored secrets) ===
if not exist "ai_config.toml"   (echo [!] ai_config.toml missing  - AI autofill disabled. Copy ai_config.example.toml -^> ai_config.toml and fill in.)
if not exist "lims_config.toml" (echo [!] lims_config.toml missing - LIMS features disabled. Copy lims_config.example.toml -^> lims_config.toml and fill in.)

echo === [5/6] locate nssm ===
set "NSSM="
for /f "delims=" %%i in ('where nssm 2^>nul') do set "NSSM=%%i"
if not defined NSSM if exist "%PROJECT_DIR%\nssm.exe" set "NSSM=%PROJECT_DIR%\nssm.exe"
if not defined NSSM (echo [X] nssm not found. Copy nssm.exe from E:\Management-of-Standard-Substance\ into %PROJECT_DIR% or PATH. & exit /b 1)

echo === [6/6] register service %SVC_NAME% ===
if not exist logs mkdir logs
sc query %SVC_NAME% >nul 2>&1
if errorlevel 1 (
    %NSSM% install %SVC_NAME% "%PROJECT_DIR%\.venv\Scripts\python.exe" "-m uvicorn server:app --host 0.0.0.0 --port %SVC_PORT%"
    %NSSM% set    %SVC_NAME% AppDirectory "%PROJECT_DIR%"
    %NSSM% set    %SVC_NAME% AppStdout "%PROJECT_DIR%\logs\stdout.log"
    %NSSM% set    %SVC_NAME% AppStderr "%PROJECT_DIR%\logs\stderr.log"
    %NSSM% set    %SVC_NAME% AppExit Default Restart
    %NSSM% set    %SVC_NAME% Start SERVICE_AUTO_START
    %NSSM% start  %SVC_NAME%
    echo service installed and started
) else (
    %NSSM% start %SVC_NAME% >nul 2>&1
    echo service already exists, started
)
echo.
echo === done. open http://LOCAL_IP:%SVC_PORT%/ ===
echo to update later: cd "%PROJECT_DIR%" ^&^& update_server.bat
endlocal
