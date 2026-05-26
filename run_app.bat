@echo off
setlocal
cd /d "%~dp0"

if not exist outputs mkdir outputs

echo Starting OmniScribe Gatekeeper...
echo.
echo Keep this window open while using OmniScribe.
echo If this window closes, http://127.0.0.1:7860 will stop working.
echo.
echo Open this after the "Running on local URL" line appears:
echo http://127.0.0.1:7860
echo.

".venv\Scripts\python.exe" -u app.py

echo.
echo OmniScribe stopped. Error log:
if exist outputs\omniscribe.err.log type outputs\omniscribe.err.log
echo.
pause
