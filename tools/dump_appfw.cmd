@echo off
rem 只读 dump A6700 的明文 appFw.so（不写相机）。需要相机处于 MSC 模式。
rem 目标：..\firmware\appFw-2.00.so（约 89 MB）
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
set PYTHONPATH=%CD%\src
"%~dp0..\.venv\Scripts\python.exe" tools\dump_camera.py --path "/usr/lib/appFw.so" --out "..\firmware\appFw-2.00.so"
echo.
echo exit code %ERRORLEVEL%
pause
