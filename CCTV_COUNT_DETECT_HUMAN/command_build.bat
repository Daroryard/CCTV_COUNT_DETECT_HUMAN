@echo off
echo ===================================================
echo  Starting PyInstaller Build Process for CCTV-YOLO
echo ===================================================

cd source_code


py -m PyInstaller --onefile --windowed --icon=cctv-camera.ico --distpath=..\dist --name=CCTV_AI_Analytics cctv_app.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Build completed! Copying resource files to 'dist' folder...
    
    copy "yolov8n.pt" "..\dist\"
    copy "multi_config.json" "..\dist\"
    copy "test.mp4" "..\dist\"
    copy "test1.mp4" "..\dist\"
    
    echo [SUCCESS] All files are ready in the main 'dist' folder!
) else (
    echo.
    echo [ERROR] Build failed.
)

echo.
pause