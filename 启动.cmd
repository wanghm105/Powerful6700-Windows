@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" main.py %*
) else (
  echo 未找到内置运行环境，请先执行一次安装步骤。
  pause
)
endlocal
