@echo off
if exist "C:\Jarvis\HELENA_OFF" del /f /q "C:\Jarvis\HELENA_OFF"
powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\Jarvis\scripts\start_helena.ps1" -NoIDE
