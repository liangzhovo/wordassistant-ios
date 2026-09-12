@echo off
echo Building Python-based Android APK...

cd /d "%~dp0"

echo.
echo ========================================
echo Python + Android APK Build Script
echo ========================================
echo.
echo This script will build the Android APK with embedded Python
echo.
echo Prerequisites:
echo - Android Studio installed
echo - Java JDK 8 or later
echo - Android SDK configured
echo.
echo Starting build process...
echo.

echo Step 1: Cleaning previous builds...
call gradlew clean

echo.
echo Step 2: Building APK with Python support...
call gradlew assembleDebug

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo BUILD FAILED!
    echo Check the error messages above for details.
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD SUCCESSFUL!
echo ========================================
echo.
echo APK location: app\build\outputs\apk\debug\app-debug.apk
echo.
echo Features:
echo - Python Flask backend embedded in APK
echo - SQLite database included
echo - WebView frontend
echo - Full offline functionality
echo.
echo To install the APK:
echo 1. Connect Android device or start emulator
echo 2. Run: adb install app\build\outputs\apk\debug\app-debug.apk
echo.
echo To run in Android Studio:
echo 1. Open the project in Android Studio
echo 2. Click Run -> Run 'app'
echo.
echo Note: First build may take longer due to Python interpreter download.
echo.

pause