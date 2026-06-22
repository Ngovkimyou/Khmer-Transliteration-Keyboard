# Windows IME

This folder contains the Windows TSF input-method prototype.

Current architecture:

```text
Windows TSF IME DLL
-> local named pipe: \\.\pipe\KhmerRomanizedIme
-> Python pipe engine
-> rules + dictionary + ranking model + local history
```

The TSF IME no longer depends on port `8000` for suggestions. The FastAPI
server is still useful for browser UI testing, but the Windows IME uses the
pipe engine.

## Folders

- `prototype/` - C++ TSF text service and build/register helper commands
- `engine/` - Python named-pipe engine used by the TSF prototype
- `docs/` - TSF architecture notes and learning notes

## Engine Behavior

The pipe engine loads the mapping rules, dictionary, ranking model, selection
history, and word-pair frequency files once, then waits for IME requests.

It records selected candidates into:

```text
data/user_selection_history.csv
data/word_pair_frequency.csv
```

Both files are capped at 10,000 rows when written.

## Common Commands

Start the pipe engine manually:

```cmd
windows_ime\engine\start_pipe_engine.cmd
```

Install the pipe engine at Windows login:

```cmd
windows_ime\engine\install_login_startup.cmd
```

Remove login startup:

```cmd
windows_ime\engine\uninstall_login_startup.cmd
```

Rebuild/register the TSF IME from an x64 Developer shell:

```cmd
cd /d C:\Projects\Khmer-Transliteration-Keyboard\windows_ime\prototype
reregister
```

## Current IME Behavior

```text
type romanized letters -> visible TSF composition
pipe engine returns suggestions asynchronously
candidate popup appears near the caret
Enter -> commit selected candidate
1-9 -> commit that candidate
0 -> commit row 10
Backspace -> edit romanized buffer
Esc -> clear composition
```

When a candidate is committed, the IME records the selection and tracks the
previous selected Khmer word so word-pair context can influence future ranking.
