@echo off
chcp 65001 >nul
echo ========================================================
echo   真太阳时与真北防磁罗盘 - 独立 REST API 服务端
echo ========================================================
echo.
echo 正在启动 FastAPI 后端服务 (端口 8000)...
echo 本地访问地址: http://127.0.0.1:8000
echo API 文档地址: http://127.0.0.1:8000/docs
echo Android 调试: 请确保手机与电脑在同一局域网 WiFi 下，手机端填入电脑 IP:8000
echo.

.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
