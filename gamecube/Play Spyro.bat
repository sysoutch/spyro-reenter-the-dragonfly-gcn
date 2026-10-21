@echo off
rem Double-click to play: starts run-spyro.ps1 (Windows opens .ps1 files in
rem Notepad by default, and may block unsigned scripts).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-spyro.ps1"
