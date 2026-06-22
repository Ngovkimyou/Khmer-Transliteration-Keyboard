@echo off
if exist "%~dp0build\ime_tsf_key_events.log" (
    type "%~dp0build\ime_tsf_key_events.log"
) else (
    echo No key event log yet. Select the IME and press a few keys first.
)
