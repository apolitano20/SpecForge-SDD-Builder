@echo off
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
call venv\Scripts\activate
python -B -m streamlit run ard\dashboard\app.py
pause
