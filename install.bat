@echo off
chcp 65001 >nul
title DSH-SolidWorks 安装与环境配置向导

echo ======================================================
echo    DSH-SolidWorks 插件自动安装与环境配置向导
echo ======================================================
echo.

:: 查找可用的 Node.js 解释器
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
echo.
echo 本安装向导需要 Node.js (>= 18.0.0 或更高版本) 运行。
echo 请前往 Node.js 官方网站下载安装 LTS 版本：
echo    👉 https://nodejs.org/
echo 安装后请重新双击运行 install.bat。
echo.
pause
exit /b 1

:FoundNode
echo [*] 正在使用 Node.js: %NODE_EXE%
echo [*] 启动自动化安装与 DSH 接入流程...
echo.

"%NODE_EXE%" "%~dp0scripts\setup.js" --verify %*
set SETUP_EXIT_CODE=%errorlevel%

echo.
if %SETUP_EXIT_CODE% equ 0 (
    echo [✔] 安装成功完成！您现在可以在 DeepSeek Harness (DSH) 中直接使用 SolidWorks CAD 插件。
) else (
    echo [✖] 安装过程中遇到异常 (错误码: %SETUP_EXIT_CODE%)，请查看上方详细输出。
)

echo.
pause
exit /b %SETUP_EXIT_CODE%
