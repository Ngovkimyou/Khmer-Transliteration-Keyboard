# TSF Learning Notes

TSF means Text Services Framework. It is the Windows framework for advanced text
input services and real input methods.

## Concepts To Learn

- COM server registration
- text service / text input processor
- input processor profile
- language profile
- keyboard activation
- composition text
- edit sessions
- candidate lists
- committing text
- preserving behavior across different apps

## First Prototype Goal

Do not start with the full Khmer engine.

Start with:

```text
type k -> commit ក
```

Then add:

```text
type s o m -> composition buffer "som"
```

Then connect:

```text
composition buffer -> local API -> candidate list
```

## Current Prototype State

The first COM skeleton lives in:

```text
windows_ime/prototype/ime_tsf_skeleton.cpp
```

It exports the base COM DLL functions:

```text
DllMain
DllCanUnloadNow
DllGetClassObject
DllRegisterServer
DllUnregisterServer
```

It currently registers only a placeholder COM class for the current user. The
COM object now implements a stub `ITfTextInputProcessor` with `Activate` and
`Deactivate`.

The skeleton now also attempts TSF profile/category registration through:

```text
ITfInputProcessorProfiles::Register
ITfInputProcessorProfiles::AddLanguageProfile
ITfInputProcessorProfiles::EnableLanguageProfile
ITfCategoryMgr::RegisterCategory
```

The next TSF step is keystroke handling through `ITfKeyEventSink`, so the text
service can receive keys and eventually commit Khmer text.

## Key Event Sink

The skeleton now implements `ITfKeyEventSink`.

Current behavior:

- subscribe during `Activate` through `ITfKeystrokeMgr::AdviseKeyEventSink`
- unsubscribe during `Deactivate`
- log key events to `build\ime_tsf_key_events.log`
- return `eaten = FALSE` so normal typing is not intercepted yet

Current behavior:

```text
type romanized letters -> buffer
visible romanized text appears in the target field
visible romanized text is tracked as a TSF composition
Space -> add a word separator to the buffer
after each edit -> call local Python API -> show popup candidates
Enter / number key -> commit a candidate
```

This uses:

- `OnTestKeyDown` / `OnKeyDown` to mark `k` as eaten
- `ITfContext::RequestEditSession`
- `ITfInsertAtSelection::InsertTextAtSelection`
- `ITfContextComposition::StartComposition`
- `ITfCompositionSink::OnCompositionTerminated`

The prototype keeps a small romanized buffer and calls the Python suggestion
API. The C++ layer should avoid duplicating `mapping_rules.json`.

## Development Notes

- Use Visual Studio with Desktop development with C++.
- Install the Windows 10/11 SDK.
- Expect registration and debugging to be harder than a normal desktop app.
- Keep the Python engine separate so retraining the model does not require
  rewriting IME code.
