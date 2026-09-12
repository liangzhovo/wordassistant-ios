@echo off
echo Starting APK build process...

cd /d "%~dp0"

echo Cleaning previous build...
call gradlew clean

echo Building APK...
call gradlew assembleDebug

if %ERRORLEVEL% NEQ 0 (
    echo Build failed!
    pause
    exit /b 1
)

echo Build completed!
echo APK location: app\build\outputs\apk\debug\app-debug.apk
pause