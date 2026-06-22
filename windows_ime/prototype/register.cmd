@echo off
set /p SKELETON_DLL=<"%~dp0build\current_skeleton_dll.txt"
"%~dp0build\ime_register_tool.exe" register "%SKELETON_DLL%"
