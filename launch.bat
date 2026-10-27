@echo off
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
call C:\venvs\SDD-Agent\Scripts\activate
python -B -m streamlit run ard\dashboard\app.py
pause
