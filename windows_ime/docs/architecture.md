# Windows IME Architecture

The first real IME should be split into two layers.

## IME Frontend

Implemented with Windows TSF, likely in C++.

Responsibilities:

- register as a Windows input method
- receive keyboard input
- maintain composition text
- show or delegate candidate UI
- commit selected Khmer text into the active application
- handle cancel, backspace, selection keys, and focus changes

Current prototype status:

- COM DLL skeleton builds
- COM class registers under the current user
- `ITfTextInputProcessor` is stubbed
- TSF language profile/category registration is wired
- `ITfKeyEventSink` receives keys
- romanized letters are buffered
- romanized letters are maintained in the active field as a TSF composition range
- Space is kept inside the romanized buffer for phrase input
- after each buffer edit, the local Python `/api/suggest` endpoint is called with limit 20
- a simple topmost candidate popup appears near the caret
- Enter commits the first candidate
- number keys commit a specific candidate
- commit replaces the visible romanized text with the selected Khmer candidate
- commit ends the active TSF composition

## Python Engine

Already implemented in the main project.

Responsibilities:

- normalize romanized input
- dictionary lookup
- rule-based candidate generation
- fuzzy lookup
- ML ranking
- previous-word context
- user selection history

## First Bridge

The TSF frontend calls the local FastAPI engine:

```text
TSF IME -> http://127.0.0.1:8000/api/suggest?q=somtos
```

The engine returns ranked suggestions:

```json
{
  "query": "somtos",
  "normalized": "somtos",
  "suggestions": [
    {
      "khmer": "សុំទោស",
      "source": "dictionary_exact",
      "rank_score": 6.2
    }
  ]
}
```

After the user chooses a candidate, the IME can notify the engine:

```text
POST http://127.0.0.1:8000/api/select
```

This keeps user history and previous-word context compatible with the existing
overlay and web UI.

Before building TSF, the `windows_ime/prototype/ime_api_smoke_test.cpp` program
tests this same bridge from C++ using WinHTTP.

## Long-Term Options

The local HTTP bridge is a practical first version. Later choices:

- keep a hidden local service
- auto-start the Python engine with Windows
- package the engine with the IME installer
- rewrite or port performance-critical engine parts if needed
