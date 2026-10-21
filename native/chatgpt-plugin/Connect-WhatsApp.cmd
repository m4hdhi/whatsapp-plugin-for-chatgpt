@echo off
cd /d "%~dp0"
"%~dp0bin\GroupBriefLink.exe" --setup
if errorlevel 1 pause
