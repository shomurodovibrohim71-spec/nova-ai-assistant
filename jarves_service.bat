@echo off
cd /d "%~dp0"
if not exist "data" mkdir data
".venv\Scripts\python.exe" -m core.api.main 1>>"data\jarves.log" 2>>"data\jarves_err.log"
