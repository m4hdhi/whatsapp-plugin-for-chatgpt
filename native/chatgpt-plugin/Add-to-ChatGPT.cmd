@echo off
cd /d "%~dp0"
echo WhatsApp - Made by Mahdhi
echo https://www.linkedin.com/in/m4hdhi/
echo Adding the private plugin. This may take a minute.
"%~dp0bin\GroupBriefLink.exe" --register
if errorlevel 1 echo Could not add the plugin. Extract the complete ZIP and try again.
pause
