@echo off
call "C:\Program Files\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
cd /d C:\Projects\Khmer-Transliteration-Keyboard
echo.
echo x64 build shell ready. Run: cl
echo.
%COMSPEC% /k
