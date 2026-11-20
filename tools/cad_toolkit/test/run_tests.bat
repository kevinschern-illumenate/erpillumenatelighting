@echo off
rem Runs the AutoLISP golden cases in AutoCAD's console (draw-to-quote plan 3.10).
rem Usage: run_tests.bat "C:\Program Files\Autodesk\AutoCAD 2025\accoreconsole.exe"
rem Commit tools\cad_toolkit\test\report.txt with the release it was run for.
set IL_TOOLKIT=%~dp0..
set IL_TOOLKIT=%IL_TOOLKIT:\=/%
%1 /s "%~dp0run_tests.scr" /l en-US
type "%~dp0report.txt"
