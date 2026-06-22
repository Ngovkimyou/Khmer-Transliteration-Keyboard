# TSF Prototype Build

This folder contains the C++ Windows TSF text-service prototype.

Use an **x64 Developer Command Prompt/PowerShell**. The project includes short
helper commands for the common build/register loop.

## Build

```cmd
cd /d C:\Projects\Khmer-Transliteration-Keyboard\windows_ime\prototype
build
```

This creates:

```text
build\ime_smoke_test.exe
build\ime_api_smoke_test.exe
build\ime_tsf_skeleton_YYYYMMDD_HHMMSS.dll
build\ime_tsf_profile_check.exe
build\ime_register_tool.exe
```

The versioned DLL name avoids Windows DLL locking while TSF has an older build
loaded. The latest DLL path is written to:

```text
build\current_skeleton_dll.txt
```

## Register

Register the current TSF DLL:

```cmd
register
```

Unregister:

```cmd
unregister
```

Fast development loop:

```cmd
reregister
```

This runs build, register, clearlogs, and current.

## Check And Logs

Check whether TSF sees the profile:

```cmd
check
```

Show registration log:

```cmd
log
```

Show key-event log:

```cmd
keylog
```

Clear logs:

```cmd
clearlogs
```

## Current IME Behavior

The prototype is registered as `Khmer Romanized IME`.

```text
type romanized letters -> visible composition in the active app
Space -> add a space to the romanized buffer
Backspace -> delete one romanized character
Esc -> clear composition
candidate popup -> shown near caret, flips above/below based on screen space
Enter -> commit selected candidate
1-9 -> commit that row
0 -> commit row 10
Up/Down -> move selection
mouse click -> commit hovered row
```

Suggestions are fetched asynchronously through the local named pipe:

```text
\\.\pipe\KhmerRomanizedIme
```

The IME attempts to auto-start the pipe engine if it is missing. The pipe engine
can also be started manually:

```cmd
cd /d C:\Projects\Khmer-Transliteration-Keyboard
windows_ime\engine\start_pipe_engine.cmd
```

The prototype no longer depends on port `8000` for normal IME suggestions.

## Personalization

When a candidate is committed, the IME records the selected candidate through
the pipe engine. This updates:

```text
data/user_selection_history.csv
data/word_pair_frequency.csv
```

The IME tracks the previous committed Khmer candidate and sends it as context
for the next suggestion request, allowing word-pair ranking to improve over
time.

## Smoke Tests

C++ Unicode smoke test:

```cmd
build\ime_smoke_test.exe
```

Legacy HTTP API smoke test:

```cmd
build\ime_api_smoke_test.exe somtos
```

The API smoke test is kept for debugging the old HTTP path, but the active TSF
IME uses the named pipe.
