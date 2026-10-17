@echo off
setlocal enabledelayedexpansion
title 单词助手 - 一键构建APK

rem 注意：本脚本最终保存为 GBK 编码 + CRLF 行尾（cmd 在中文 Windows 下才能正常解析中文）。
rem 若用 UTF-8 另存会导致中文乱码、命令错乱，请勿随意改编码。

cd /d "%~dp0"

rem ---- 单一代码源同步：从仓库根同步 Android 前端/后端（改根目录代码，构建前自动生效）----
if exist "..\脚本\sync_all.py" (
    python "..\脚本\sync_all.py"
    if errorlevel 1 (
        echo [错误] 同步脚本执行失败，请检查根目录 index.html / app.py 是否完整。
        pause
        exit /b 1
    )
) else (
    echo [警告] 未找到 ..\脚本\sync_all.py，跳过同步（请确认脚本存在）。
)


echo ============================================
echo    单词助手 - 一键构建APK
echo ============================================
echo.

rem ---- 参数解析: debug=调试版  install=构建后自动安装  check=仅检查环境 ----
set "VARIANT=release"
set "DO_INSTALL=0"
set "DO_CHECK=0"
echo %* | findstr /i "debug"   >nul && set "VARIANT=debug"
echo %* | findstr /i "install" >nul && set "DO_INSTALL=1"
echo %* | findstr /i "check"   >nul && set "DO_CHECK=1"

rem ---- 从 local.properties 读取 SDK 路径（供 adb 使用）----
set "SDK_DIR="
if exist "local.properties" (
    for /f "usebackq tokens=1,* delims==" %%a in ("local.properties") do (
        if "%%a"=="sdk.dir" set "SDK_DIR=%%b"
    )
)
if defined SDK_DIR (
    set "SDK_DIR=!SDK_DIR:\\=\!"
    set "SDK_DIR=!SDK_DIR:\:=:!"
)

rem ---- 检测 JDK 17（AGP 8.x 必须使用 JDK 17）----
set "JDK_DIR="
if exist "C:\Program Files\Java\jdk-17\bin\java.exe" (
    set "JDK_DIR=C:\Program Files\Java\jdk-17"
) else if defined JAVA_HOME (
    if exist "!JAVA_HOME!\bin\java.exe" set "JDK_DIR=!JAVA_HOME!"
)
if defined JDK_DIR (
    set "JAVA_HOME=!JDK_DIR!"
    echo [Java] 使用: !JAVA_HOME!
    "!JAVA_HOME!\bin\java" -version
) else (
    echo [警告] 未找到 JDK 17，将尝试使用 PATH 中的 java（若失败请安装 JDK 17）
)
if defined SDK_DIR (
    echo [SDK] 路径: !SDK_DIR!
    if exist "!SDK_DIR!\platform-tools\adb.exe" (
        echo [SDK] adb 就绪: !SDK_DIR!\platform-tools\adb.exe
    ) else (
        echo [警告] 未找到 platform-tools\adb.exe（install 模式将不可用）
    )
) else (
    echo [警告] 未从 local.properties 读取到 SDK 路径
)

rem ---- check 模式: 只输出环境信息，不构建 ----
if "!DO_CHECK!"=="1" (
    echo.
    echo [检查] 环境信息输出完毕，本次未执行构建。
    pause
    exit /b 0
)

rem ---- 执行构建（增量构建，不清理）----
echo.
echo [构建] 开始构建 !VARIANT! 版 APK（首次较慢，之后为增量）...
echo.
if "!VARIANT!"=="debug" (
    call gradlew.bat assembleDebug --console=plain
) else (
    call gradlew.bat assembleRelease --console=plain
)
if errorlevel 1 (
    echo.
    echo [失败] 构建出错，请查看上方日志。
    pause
    exit /b 1
)

rem ---- 定位 APK 输出 ----
if "!VARIANT!"=="debug" (
    set "APK_PATH=app\build\outputs\apk\debug\app-debug.apk"
) else (
    set "APK_PATH=app\build\outputs\apk\release\app-release.apk"
)
if not exist "!APK_PATH!" (
    echo [失败] 未找到 APK 文件: !APK_PATH!
    pause
    exit /b 1
)
for /f "delims=" %%s in ('powershell -NoProfile -Command "$i=Get-Item '!APK_PATH!'; [math]::Round($i.Length/1MB,1)"') do set "APK_SIZE_MB=%%s"

echo.
echo ============================================
echo   构建成功！
echo ============================================
echo   输出: %CD%\!APK_PATH!
echo   大小: !APK_SIZE_MB! MB
echo   签名: !VARIANT! 版使用正式签名，可直接安装到手机
echo.

rem ---- 可选：自动安装 ----
if "!DO_INSTALL!"=="1" (
    if defined SDK_DIR (
        set "ADB=!SDK_DIR!\platform-tools\adb.exe"
    ) else (
        set "ADB=adb"
    )
    echo [安装] 正在通过 adb 安装到设备...
    "!ADB!" install -r "!APK_PATH!"
    if errorlevel 1 (
        echo [错误] adb 安装失败，请确认手机已连接、已开启 USB 调试。
    ) else (
        echo [安装] 安装成功！
    )
) else (
    echo [提示] 构建后自动安装到手机，请运行: %~nx0 install
    echo        adb 手动安装: "!SDK_DIR!\platform-tools\adb.exe" install -r "!APK_PATH!"
)

echo.
pause
