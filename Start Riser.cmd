@echo off
setlocal
cd /d "%~dp0"
if not exist node_modules\vite\bin\vite.js (
  echo Dependencies are missing. Run npm ci in this folder first.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:5173/#/project in your browser.
echo Keep this window open while using the workspace.
call npm.cmd run dev
if errorlevel 1 pause
