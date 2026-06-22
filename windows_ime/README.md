# Windows IME Prototype

This folder is for the real Windows input method integration.

The current Python transliteration engine remains the source of truth:

- dictionary lookup
- rule-based candidate generation
- fuzzy matching
- ML ranking
- user history and previous-word context

The first Windows IME prototype should be a small TSF text service that proves
the Windows integration layer works before connecting the full engine.

## Milestones

1. Build/register a minimal TSF text service.
2. Make it appear as a switchable input method in Windows.
3. Commit a fixed Khmer character, such as `k -> ក`.
4. Add a romanized composition buffer.
5. Call the local Python API for suggestions.
6. Display candidates.
7. Commit the selected Khmer candidate.

During early development, keep the local Python engine running:

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Later, the engine can become a background service or be started silently by the
IME/launcher.
