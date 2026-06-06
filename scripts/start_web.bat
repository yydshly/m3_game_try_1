@echo off
setlocal
cd /d "%~dp0\.."

echo ==========================================
echo   孤岛晚宴 Web 启动脚本
echo ==========================================

python scripts\start_dev_server.py --stop-existing

if errorlevel 1 (
    echo.
    echo [ERROR] 启动失败，请检查 Python、依赖或端口占用。
    echo 可尝试：
    echo   pip install -r requirements.txt
    echo   python scripts\stop_dev_server.py --port 8000
    pause
)

endlocal
