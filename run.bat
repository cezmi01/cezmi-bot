@echo off
setlocal

set "VENV_PY=.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
  goto :create_venv
)

"%VENV_PY%" -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo [WARN] Existing .venv looks broken. Recreating...
  rmdir /s /q ".venv"
  goto :create_venv
)
goto :install_deps

:create_venv
echo [INFO] Creating local virtual environment...
py -3 -m venv .venv
if errorlevel 1 (
  echo [ERROR] Failed to create .venv. Check your Python installation.
  exit /b 1
)

:install_deps
if exist "requirements.txt" (
  echo [INFO] Installing dependencies from requirements.txt...
  "%VENV_PY%" -m pip install --upgrade pip
  "%VENV_PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    exit /b 1
  )
)

if not exist "app.py" (
  echo [ERROR] app.py not found in project root.
  exit /b 1
)

echo [INFO] Starting app.py...
"%VENV_PY%" app.py
