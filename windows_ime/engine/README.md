# Khmer IME Pipe Engine

This folder contains the local Windows named-pipe engine used by the TSF IME
prototype.

The TSF IME uses this pipe for suggestions and selection-history recording.
The TSF prototype can also launch `start_pipe_engine.cmd` automatically when
the pipe is missing.

## Pipe

```text
\\.\pipe\KhmerRomanizedIme
```

Suggestion request:

```json
{"q":"som","limit":20,"previous_word":""}
```

Suggestion response:

```json
{"ok":true,"query":"som","normalized":"som","suggestions":[]}
```

Selection-record request:

```json
{"action":"select","q":"som","khmer":"<selected-khmer>","previous_word":"<previous-khmer>"}
```

Selection recording updates:

```text
data/user_selection_history.csv
data/word_pair_frequency.csv
```

Both files are capped at 10,000 rows by `khmer_transliteration.history`.

## Run The Engine

Preferred launcher:

```cmd
windows_ime\engine\start_pipe_engine.cmd
```

This starts the engine hidden and writes logs to:

```text
tmp/khmer_pipe_engine.out.log
tmp/khmer_pipe_engine.err.log
```

Manual foreground run from the project root:

```powershell
python windows_ime/engine/khmer_engine_pipe.py
```

The server loads the same rule, dictionary, ranking model, history, and
pair-frequency data as the FastAPI app, then waits for named-pipe requests.

First startup can take several seconds because the engine warms the
dictionary/model once.

Stop the background engine:

```cmd
windows_ime\engine\stop_pipe_engine.cmd
```

Restart after Python rule/data/model changes:

```cmd
windows_ime\engine\stop_pipe_engine.cmd
windows_ime\engine\start_pipe_engine.cmd
```

## Test From Another Terminal

```powershell
python windows_ime/engine/test_pipe_client.py som --limit 10
```

The test client waits up to 30 seconds for the pipe, so it is okay if you run
it while the engine is still starting.

Try:

```powershell
python windows_ime/engine/test_pipe_client.py k --limit 10
python windows_ime/engine/test_pipe_client.py som --limit 10
python windows_ime/engine/test_pipe_client.py chnang --limit 10
```

## Start At Windows Login

Install login startup:

```cmd
windows_ime\engine\install_login_startup.cmd
```

Remove login startup:

```cmd
windows_ime\engine\uninstall_login_startup.cmd
```

## One-Shot Test Mode

For debugging, the server can handle one request and exit:

```powershell
python windows_ime/engine/khmer_engine_pipe.py --once
```

Then run the client in a second terminal before the server exits.

## IME Test Flow

The C++ TSF prototype uses this named pipe instead of port `8000`.

1. Optional: start the pipe engine yourself:

   ```cmd
   windows_ime\engine\start_pipe_engine.cmd
   ```

   The TSF prototype should auto-start it if you skip this, but manual start is
   useful for debugging.

2. In your x64 admin prototype shell, rebuild/register the IME:

   ```cmd
   cd /d C:\Projects\Khmer-Transliteration-Keyboard\windows_ime\prototype
   reregister
   ```

3. Switch away from the IME and back with `Win + Space`.

4. Type `k`, `som`, or `chnang`.

If the pipe engine is not running, the IME will try to start it automatically.
