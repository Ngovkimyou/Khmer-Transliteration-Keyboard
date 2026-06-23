"""FastAPI browser UI for suggestions, collection, and selection history."""

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from khmer_transliteration.collection import append_examples
from khmer_transliteration.history import record_selection
from khmer_transliteration.mapping_rules import load_mapping_rules
from khmer_transliteration.dictionary_lookup import load_dataset
from khmer_transliteration.normalizer import normalize_input, normalize_phrase_input
from khmer_transliteration.paths import ASSETS_DIR, STATIC_DIR
from khmer_transliteration.suggestion_engine import get_suggestions, load_ranking_model


app = FastAPI(title="Khmer Transliteration Keyboard")

# Load shared resources once at app startup so each request stays fast.
dataset = load_dataset()
rules = load_mapping_rules()
ranking_model = load_ranking_model()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


class SelectionEvent(BaseModel):
    """Payload sent when a user clicks a suggestion in the web UI."""
    q: str = ""
    khmer: str = ""
    previous_khmer: str = ""


@app.get("/")
def index():
    """Serve the single-page browser UI."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/suggest")
def suggest(
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=0, ge=0, le=500),
    allow_vowels: bool = Query(default=False),
    previous_word: str = Query(default="", max_length=80),
):
    """Return ranked suggestions for the current romanized input."""
    normalized = normalize_phrase_input(q)

    if not normalized:
        return {
            "query": q,
            "normalized": normalized,
            "suggestions": [],
        }

    suggestions = get_suggestions(
        q,
        dataset=dataset,
        rules=rules,
        ranking_model=ranking_model,
        allow_vowels=allow_vowels,
        previous_word=previous_word,
        limit=limit or None,
        min_rule_score=None,
    )

    return {
        "query": q,
        "normalized": normalized,
        "suggestions": suggestions,
    }


@app.post("/api/select")
def select(event: SelectionEvent):
    """Record user selection history and previous-word pair counts."""
    normalized = normalize_input(event.q)

    if not normalized or not event.khmer:
        return {
            "query": event.q,
            "normalized": normalized,
            "khmer": event.khmer,
            "recorded": False,
            "message": "No selection to record.",
        }

    counts = record_selection(
        normalized,
        event.khmer,
        previous_khmer=event.previous_khmer,
    )

    return {
        "query": event.q,
        "normalized": normalized,
        "khmer": event.khmer,
        "previous_khmer": event.previous_khmer,
        "recorded": True,
        **counts,
    }


@app.post("/api/collect")
def collect(q: str = Query(default="", max_length=80), limit: int = Query(default=0, ge=0, le=500)):
    """Append generated suggestions to data/ranking_training_examples.csv."""
    normalized = normalize_input(q)

    if not normalized:
        return {
            "query": q,
            "normalized": normalized,
            "added": 0,
            "message": "No input to collect.",
        }

    added_count = append_examples([normalized], limit=limit or None)

    return {
        "query": q,
        "normalized": normalized,
        "added": added_count,
        "message": f"Added {added_count} review rows.",
    }
