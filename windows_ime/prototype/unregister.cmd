@echo off
if exist "%~dp0build\current_skeleton_dll.txt" (
    set /p SKELETON_DLL=<"%~dp0build\current_skeleton_dll.txt"
) else (
    set SKELETON_DLL=%~dp0build\ime_tsf_skeleton.dll
)
"%~dp0build\ime_register_tool.exe" unregister "%SKELETON_DLL%"
