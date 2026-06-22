# Prototype Build

This folder starts with a tiny C++ smoke test before TSF code.

Open **x64 Native Tools Command Prompt/PowerShell for VS 2022**, then run:

```powershell
cd C:\Projects\Khmer-Transliteration-Keyboard\windows_ime\prototype
build
.\build\ime_smoke_test.exe
```

Expected output:

```text
Khmer IME C++ smoke test
k -> ក
```

If this works, the C++ compiler and Unicode output path are ready for the next
TSF prototype step.

## API Smoke Test

Start the Python engine in another terminal:

```powershell
cd C:\Projects\Khmer-Transliteration-Keyboard
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Then run:

```powershell
cd C:\Projects\Khmer-Transliteration-Keyboard\windows_ime\prototype
.\build\ime_api_smoke_test.exe somtos
```

Expected result: the C++ program prints the JSON returned from
`/api/suggest`. This proves the future Windows IME shell can talk to the Python
engine before TSF registration starts.

## COM DLL Skeleton

Build the placeholder COM DLL:

```powershell
build
```

Use the x64 Developer shell. A 32-bit TSF DLL can build, but it is not the
right first target for the Windows input switcher on modern 64-bit Windows.

This creates:

```text
build\ime_tsf_skeleton_YYYYMMDD_HHMMSS.dll
```

The build writes the latest DLL path to `build\current_skeleton_dll.txt`.
This avoids Windows DLL locking while TSF has an older prototype loaded.

Register it for the current user:

```powershell
register
```

Unregister it:

```powershell
unregister
```

The short `register` and `unregister` commands use `ime_register_tool.exe` so
the exact `DllRegisterServer` / `DllUnregisterServer` HRESULT is visible.

If registration fails, print the step-by-step DLL registration log:

```powershell
log
```

## Key Event Sink Test

The skeleton now implements `ITfKeyEventSink` and logs key events without
intercepting them.

After registering:

```powershell
build
register
```

During rapid development, use:

```powershell
reregister
```

This runs `build`, `register`, `clearlogs`, and prints the DLL path that should
be loaded next.

Switch to `Khmer Romanized IME`, type a few keys in Notepad, then run:

```powershell
keylog
```

To clear old log noise before a test:

```powershell
clearlogs
```

Expected: entries such as `Activate`, `OnSetFocus`, `OnTestKeyDown`,
`OnKeyDown`, `OnTestKeyUp`, and `OnKeyUp`.

The current typing behavior uses the Python API:

```text
type romanized letters -> buffer
typed romanized text appears in the active input field
visible romanized text is maintained as a TSF composition range
Space -> add a space to the romanized buffer
after each edit -> call http://127.0.0.1:8000/api/suggest?limit=20
show a candidate popup near the caret
Enter -> commit the first candidate
1-9 -> commit that candidate
0 -> commit candidate row 10
```

Backspace edits the romanized buffer. Esc clears it.
When a candidate is committed, the visible romanized text is replaced by Khmer.

Example:

```text
type somtos then Enter -> សុំទោស
type chnang touch then Enter -> phrase suggestion from the Python engine
```

The candidate popup appears below the caret by default and flips above when
there is not enough screen space below.

The local Python server must be running for API-backed commits:

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

This skeleton registers:

- a placeholder COM class under `HKCU\Software\Classes\CLSID`
- a TSF text service profile for Khmer/Cambodia
- the TSF keyboard category

It may appear in Windows language/input settings after registration. It still
does not process keystrokes or commit text yet.

Check whether TSF sees the profile:

```powershell
check
```

If `IsEnabledLanguageProfile` returns `S_OK` and `enabled: yes`, TSF registered
the profile even if Windows Settings does not show it yet.

The COM object now implements a stub `ITfTextInputProcessor`:

```text
Activate(...)
Deactivate()
```

The methods only store/release the TSF thread manager for now. The next step is
keystroke handling through TSF sinks.
