@echo off
cd /d "%~dp0"
call venv\Scripts\activate
streamlit run ard\dashboard\app.py
pause
