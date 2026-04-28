@echo off
chcp 65001 >nul
echo ========================================
echo ZWCAD Mechanical MCP Server 快速启动
echo ========================================
echo.

echo 正在检查依赖...
python -c "import fastmcp" 2>nul
if errorlevel 1 (
    echo [警告] 未找到 fastmcp，正在安装依赖...
    pip install -r requirements.txt
    echo.
)

echo 启动 ZWCAD Mechanical MCP Server...
echo 按 Ctrl+C 可停止服务器
echo.
python server.py
pause
