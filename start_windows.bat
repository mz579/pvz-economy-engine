@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

set "PYTHON_CMD=python"
where py >nul 2>&1 && set "PYTHON_CMD=py"

%PYTHON_CMD% --version >nul 2>&1
if errorlevel 1 goto no_python

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] 正在创建本地 Python 环境...
  %PYTHON_CMD% -m venv .venv || goto failed
)

call ".venv\Scripts\activate.bat"
echo [2/3] 正在检查运行依赖，第一次启动可能需要几分钟...
python -m pip install -r requirements.txt || goto failed

echo [3/3] 正在启动末日菜园，浏览器会自动打开...
python -m streamlit run app.py
goto end

:no_python
echo 未找到 Python。请先安装 Python 3.10 或更高版本，并勾选 Add Python to PATH。
pause
exit /b 1

:failed
echo 启动失败，请检查网络、Python 版本和上方错误信息。
pause
exit /b 1

:end
endlocal
