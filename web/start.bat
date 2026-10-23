@echo off
rem 一键启动 Web 看板本地演示(静态服务器)
cd /d "%~dp0"
set PORT=8000

where python >nul 2>nul
if %errorlevel%==0 (
    set PY=python
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set PY=py -3
    ) else (
        echo [错误] 未找到 Python,请先安装 Python 3 后重试。
        pause
        exit /b 1
    )
)

echo Web 看板已启动: http://127.0.0.1:%PORT%   ^(按 Ctrl+C 停止^)
start "" "http://127.0.0.1:%PORT%"
%PY% -m http.server %PORT%
