@echo off
title LimeWire 2.0.2 Studio Edition — Setup
echo.
echo  ============================================
echo   LimeWire 2.0.2 Studio Edition — Setup
echo  ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install Python 3.10+ from python.org
    echo          Make sure "Add to PATH" is checked during install.
    pause
    exit /b 1
)

:: Check FFmpeg
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo  [WARNING] FFmpeg not found. Audio conversion will not work.
    echo            Install with:  winget install ffmpeg
    echo.
)

:: Install dependencies
echo  Installing core dependencies...
pip install yt-dlp pillow requests mutagen pyglet --quiet
echo  Installing audio analysis...
pip install librosa soundfile pyloudnorm musicbrainzngs pyacoustid --quiet
echo  Installing audio editing...
pip install pydub sounddevice pyrubberband openai-whisper --quiet
echo  Installing effects...
pip install noisereduce pedalboard lyricsgenius --quiet
echo  Installing stem separation (this may take a while)...
pip install demucs --quiet

echo.
echo  ============================================
echo   Setup complete! Launching LimeWire...
echo  ============================================
echo.

python LimeWire.py
