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

if exist "%LOCALAPPDATA%\Programs\nodejs\node.exe" (
    set "NODE_EXE=%LOCALAPPDATA%\Programs\nodejs\node.exe"
    goto :FoundNode
)

echo [错误] 未在系统中检测到 Node.js 运行时环境！
pause
exit /b 1

:FoundNode
rem 双击运行时没有任何参数 -> 先明确确认，再以 --yes 执行；传了参数则原样转发。
if "%~1"=="" (
    echo 将执行：清理本插件自动生成的运行时/配置文件，并从 DSH profile 中解除挂载。
    echo 不会删除任何 CAD 文件（.SLDPRT/.SLDASM/.SLDDRW）、模型目录或 config-backups\。
    echo 仅预览请改用：node scripts\uninstall.js --dry-run
    echo.
    set /p CONFIRM=确认执行卸载清理？输入 y 回车继续，其它任意键取消：
    if /i not "%CONFIRM%"=="y" (
        echo 已取消，未做任何改动。
        pause
        exit /b 0
    )
    "%NODE_EXE%" "%~dp0scripts\uninstall.js" --yes
) else (
    "%NODE_EXE%" "%~dp0scripts\uninstall.js" %*
)
set UN_EXIT_CODE=%errorlevel%

echo.
pause
exit /b %UN_EXIT_CODE%
