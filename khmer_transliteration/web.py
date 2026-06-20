from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from khmer_transliteration.collection import append_examples
from khmer_transliteration.mapping_rules import load_mapping_rules
from khmer_transliteration.dictionary_lookup import load_dataset
from khmer_transliteration.normalizer import normalize_input
from khmer_transliteration.paths import ASSETS_DIR, STATIC_DIR
from khmer_transliteration.suggestion_engine import get_suggestions, load_ranking_model


app = FastAPI(title="Khmer Transliteration Keyboard")

dataset = load_dataset()
rules = load_mapping_rules()
ranking_model = load_ranking_model()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/suggest")
def suggest(
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=0, ge=0, le=500),
    allow_vowels: bool = Query(default=False),
):
    normalized = normalize_input(q)

    if not normalized:
        return {
            "query": q,
            "normalized": normalized,
            "suggestions": [],
        }

    suggestions = get_suggestions(
        normalized,
        dataset=dataset,
        rules=rules,
        ranking_model=ranking_model,
        allow_vowels=allow_vowels,
        limit=limit or None,
        min_rule_score=None,
    )

    return {
        "query": q,
        "normalized": normalized,
        "suggestions": suggestions,
    }


@app.post("/api/collect")
def collect(q: str = Query(default="", max_length=80), limit: int = Query(default=0, ge=0, le=500)):
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
