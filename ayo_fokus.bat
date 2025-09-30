@echo off
REM === Masuk ke folder project ===
cd /d "%~dp0"

REM === Aktifkan virtual environment ===
call venv\Scripts\activate.bat

REM === Set environment variables ===
set DB_ENGINE=mysql
set DB_HOST=localhost
set DB_PORT=3306
set DB_NAME=ayo_fokus_db
set DB_USER=ayo_fokus_user
set DB_PASSWORD=password123

REM === Jalankan aplikasi ===
python app.py

REM === Agar window tidak langsung tertutup setelah selesai ===
pause
