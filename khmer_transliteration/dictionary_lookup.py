"""Dictionary loading, exact lookup, and fuzzy lookup helpers."""

import csv
from khmer_transliteration.normalizer import normalize_input
from rapidfuzz import process, fuzz

from khmer_transliteration.paths import ALL_WORDS_FILE

DATASET_FILE = ALL_WORDS_FILE


def load_dataset():
    """Read data/all_words.csv into normalized dictionaries used by the engine."""
    rows = []

    with open(DATASET_FILE, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            rows.append({
                "romanized": row["romanized"],
                "khmer": row["khmer"],
                "frequency": int(row["frequency"]),
            })

    return rows


def exact_lookup(user_input, dataset):
    """Return dataset rows whose romanized form exactly matches the input."""
    normalized = normalize_input(user_input)

    matches = []

    for row in dataset:
        if row["romanized"] == normalized:
            matches.append(row)

    matches.sort(key=lambda row: row["frequency"], reverse=True)

    return matches


# For quick manual debugging, load_dataset() + exact_lookup("som", dataset)
# shows the dictionary rows before rule generation or ranking is involved.
def get_romanized_words(dataset):
    """Return unique romanized entries for RapidFuzz candidate search."""
    return list(set(row["romanized"] for row in dataset))


def fuzzy_lookup(user_input, dataset, limit=5, min_score=80):
    """Find near-matching romanized dictionary rows for typo-tolerant lookup."""
    normalized = normalize_input(user_input)
    romanized_words = get_romanized_words(dataset)

    fuzzy_matches = process.extract(
        normalized,
        romanized_words,
        scorer=fuzz.ratio,
        limit=limit
    )

    results = []

    for romanized_word, score, _ in fuzzy_matches:
        if score < min_score:
            continue

        matches = exact_lookup(romanized_word, dataset)

        for match in matches:
            result = match.copy()
            result["fuzzy_score"] = score
            results.append(result)

    results.sort(
        key=lambda row: (row["fuzzy_score"], row["frequency"]),
        reverse=True
    )

    return results


