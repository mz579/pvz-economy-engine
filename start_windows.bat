@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "LOG_FILE=%~dp0startup.log"
> "%LOG_FILE%" echo PvZ Economy Engine startup log
>> "%LOG_FILE%" echo Started: %DATE% %TIME%
>> "%LOG_FILE%" echo Directory: %CD%

set "PYTHON_CMD="
py -3 -c "import sys; raise SystemExit(0 if sys.version_info.major == 3 and sys.version_info.minor in range(10, 100) else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"
if defined PYTHON_CMD goto python_found

python -c "import sys; raise SystemExit(0 if sys.version_info.major == 3 and sys.version_info.minor in range(10, 100) else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=python"
if defined PYTHON_CMD goto python_found
goto no_python

:python_found
>> "%LOG_FILE%" echo Python launcher: %PYTHON_CMD%
set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"

if exist "%VENV_PYTHON%" goto venv_ready
echo [1/3] Creating the local Python environment...
>> "%LOG_FILE%" echo Creating .venv
call %PYTHON_CMD% -m venv ".venv"
if errorlevel 1 goto venv_failed

:venv_ready
if not exist "%VENV_PYTHON%" goto venv_failed
echo [2/3] Checking runtime dependencies...
"%VENV_PYTHON%" -c "import pandas, pulp, requests, streamlit" >nul 2>&1
if not errorlevel 1 goto dependencies_ready

echo Installing dependencies. On a slow network this may take 5-15 minutes...
>> "%LOG_FILE%" echo Installing requirements.txt
"%VENV_PYTHON%" -m pip install --disable-pip-version-check -r "requirements.txt"
if errorlevel 1 goto install_failed

:dependencies_ready
>> "%LOG_FILE%" echo Dependencies are ready
echo [3/3] Starting the local web app...
echo Keep this window open while using the app.
echo Local URL: http://localhost:8501
>> "%LOG_FILE%" echo Starting Streamlit at http://localhost:8501
set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"
"%VENV_PYTHON%" -m streamlit run "app.py" --server.address localhost
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" goto app_failed

echo.
echo The application has stopped.
>> "%LOG_FILE%" echo Streamlit stopped normally
pause
exit /b 0

:no_python
echo.
echo Python 3.10 or newer was not found.
echo Install Python from https://www.python.org/downloads/windows/
echo During setup, enable "Add Python to PATH", then run this file again.
>> "%LOG_FILE%" echo ERROR: Python 3.10 or newer was not found
pause
exit /b 1

:venv_failed
echo.
echo Failed to create the local Python environment.
echo Delete the .venv folder and try again. Startup stage log: %LOG_FILE%
>> "%LOG_FILE%" echo ERROR: Failed to create .venv
pause
exit /b 1

:install_failed
echo.
echo Failed to install dependencies. Check your network and try again.
echo The error is shown above. Startup stage log: %LOG_FILE%
>> "%LOG_FILE%" echo ERROR: pip install failed
pause
exit /b 1

:app_failed
echo.
echo The web app exited with code %APP_EXIT%.
echo Review the error above and the startup log: %LOG_FILE%
>> "%LOG_FILE%" echo ERROR: Streamlit exited with code %APP_EXIT%
pause
exit /b %APP_EXIT%
