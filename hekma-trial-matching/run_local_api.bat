@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python 3.10 venv...
  py -3.10 -m venv .venv
  if errorlevel 1 (
    echo Failed to create venv. Install Python 3.10 first.
    exit /b 1
  )
)

echo Using: .venv\Scripts\python.exe
".venv\Scripts\python.exe" --version

if not exist ".env" (
  echo .env missing. Running setup...
  ".venv\Scripts\python.exe" scripts\setup_local.py
)

for /f "usebackq tokens=1,* delims==" %%A in (`findstr /B "OPENAI_API_KEY=" .env`) do set OPENAI_VAL=%%B
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /B "ANTHROPIC_API_KEY=" .env`) do set ANTHROPIC_VAL=%%B

if "%OPENAI_VAL%"=="" (
  echo.
  echo ERROR: OPENAI_API_KEY is empty in .env
  echo Edit .env and set OPENAI_API_KEY=sk-...
  exit /b 1
)
if "%ANTHROPIC_VAL%"=="" (
  echo.
  echo ERROR: ANTHROPIC_API_KEY is empty in .env
  echo Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
  exit /b 1
)

echo.
echo Starting TrialGPT API at http://127.0.0.1:8000
echo Health: http://127.0.0.1:8000/health
echo.
".venv\Scripts\python.exe" -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
