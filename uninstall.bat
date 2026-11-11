@echo off
chcp 65001 >nul
title DSH-SolidWorks 安全卸载与清理工具

echo ======================================================
echo    DSH-SolidWorks 插件安全卸载与清理工具
echo ======================================================
echo.

set NODE_EXE=
where node >nul 2>nul
if %errorlevel% equ 0 (
    set NODE_EXE=node
    goto :FoundNode
)

if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe" (
    set "NODE_EXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
    goto :FoundNode
)

if exist "C:\Program Files\nodejs\node.exe" (
    set "NODE_EXE=C:\Program Files\nodejs\node.exe"
    goto :FoundNode
)

if exist "D:\Node.js\node.exe" (
    set "NODE_EXE=D:\Node.js\node.exe"
    goto :FoundNode
)

echo [错误] 未在系统中检测到 Node.js 运行时环境！
pause
exit /b 1

:FoundNode
"%NODE_EXE%" "%~dp0scripts\uninstall.js" %*
set UN_EXIT_CODE=%errorlevel%

echo.
pause
exit /b %UN_EXIT_CODE%
