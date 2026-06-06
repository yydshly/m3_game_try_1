@echo off
setlocal
cd /d "%~dp0\.."

echo ==========================================
echo   停止孤岛晚宴 Web 服务
echo ==========================================

python scripts\stop_dev_server.py --port 8000

echo.
pause
endlocal
