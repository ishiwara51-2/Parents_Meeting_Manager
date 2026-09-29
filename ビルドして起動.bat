@echo off
setlocal
cd /d "%~dp0"

echo ==============================
echo  アプリをビルドして起動します
echo  （終了するにはこのウィンドウで Ctrl+C を押してください）
echo ==============================
echo.

where pwsh >nul 2>nul
if %errorlevel%==0 (
    pwsh -NoLogo -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
) else (
    powershell -NoLogo -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
)

echo.
echo ==============================
echo  終了しました（エラーが表示されている場合は内容を確認してください）
echo ==============================
pause
