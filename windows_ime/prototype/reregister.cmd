@echo off
call "%~dp0build.cmd"
if errorlevel 1 exit /b %errorlevel%
call "%~dp0register.cmd"
if errorlevel 1 exit /b %errorlevel%
call "%~dp0clearlogs.cmd"
call "%~dp0current.cmd"
