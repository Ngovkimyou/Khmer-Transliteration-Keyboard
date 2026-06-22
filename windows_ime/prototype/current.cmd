@echo off
if exist "%~dp0build\current_skeleton_dll.txt" (
    type "%~dp0build\current_skeleton_dll.txt"
) else (
    echo No current skeleton DLL file. Run build first.
)
