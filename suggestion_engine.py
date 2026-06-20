import os
import csv

import joblib
from rapidfuzz import fuzz

from candidate_generator import generate_ranked_candidates
from data.load_mapping_rules import load_mapping_rules
from dictionary_lookup import exact_lookup, load_dataset
from normalizer import normalize_input
from ranking_features import extract_ranking_features


EXACT_BASE_SCORE = 3.0
COMPLETION_BASE_SCORE = 2.5
RULE_BASE_SCORE = 1.0
DIRECT_TOKEN_BASE_SCORE = 4.0
DIRECT_TOKEN_PRIORITY = 5
EXACT_PRIORITY = 4
COMPLETION_PRIORITY = 3
RULE_PRIORITY = 1
DEFAULT_SUGGESTION_LIMIT = 10
MIN_RULE_DISPLAY_SCORE = 1.60
MAX_COMPLETION_EXTRA_CHARS = 2
DATASET_KHMER_EXISTS_BOOST = 0.25
DATASET_ROMANIZED_SIMILARITY_BOOST = 0.75
DATASET_FREQUENCY_BOOST_FACTOR = 0.001
RANKING_MODEL_FILE = "models/ranking_model.joblib"
MANUAL_RANKING_EXAMPLES_FILE = "data/ranking_training_examples.csv"


# Convert one exact dictionary row into the shared suggestion format.
def make_exact_suggestion(row):
    return {
        "khmer": row["khmer"],
        "romanized": row["romanized"],
        "source": "dictionary_exact",
        "source_priority": EXACT_PRIORITY,
        "frequency": row["frequency"],
        "score": EXACT_BASE_SCORE + row["frequency"] * 0.001,
    }


# Convert one left-to-right prefix match into the shared suggestion format.
def make_completion_suggestion(row, normalized):
    remaining_length = len(row["romanized"]) - len(normalized)

    return {
        "khmer": row["khmer"],
        "romanized": row["romanized"],
        "source": "dictionary_completion",
        "source_priority": COMPLETION_PRIORITY,
        "frequency": row["frequency"],
        "remaining_length": remaining_length,
        "score": COMPLETION_BASE_SCORE + row["frequency"] * 0.001 - remaining_length * 0.01,
    }


# Convert one generated rule candidate into the shared suggestion format.
def make_rule_suggestion(candidate, normalized):
    return {
        "khmer": candidate["khmer"],
        "romanized": normalized,
        "source": candidate["source"],
        "source_priority": RULE_PRIORITY,
        "tokens": candidate["tokens"],
        "chunks": candidate.get("chunks", []),
        "rule_score": candidate["rule_score"],
        "score": RULE_BASE_SCORE + candidate["final_score"],
    }


# Convert one direct token mapping into the shared suggestion format.
def make_direct_token_suggestion(khmer, normalized, token_type):
    return {
        "khmer": khmer,
        "romanized": normalized,
        "source": f"direct_{token_type}",
        "source_priority": DIRECT_TOKEN_PRIORITY,
        "score": DIRECT_TOKEN_BASE_SCORE,
    }


# Return direct consonant/independent-vowel options, plus vowel signs when allowed.
def direct_token_lookup(normalized, rules, allow_vowels=False):
    suggestions = []

    for khmer in rules.get("consonants", {}).get(normalized, []):
        suggestions.append(make_direct_token_suggestion(
            khmer,
            normalized,
            "consonant",
        ))

    for khmer in rules.get("independent_vowels", {}).get(normalized, []):
        suggestions.append(make_direct_token_suggestion(
            khmer,
            normalized,
            "independent_vowel",
        ))

    if allow_vowels:
        vowel_options = []
        vowel_options.extend(rules.get("vowels", {}).get(normalized, []))

        class_vowels = rules.get("vowels_by_consonant_class", {}).get(normalized, {})
        for options in class_vowels.values():
            vowel_options.extend(options)

        for khmer in dict.fromkeys(vowel_options):
            if khmer == "":
                continue

            suggestions.append(make_direct_token_suggestion(
                khmer,
                normalized,
                "vowel",
            ))

    return suggestions


# Find dictionary words that continue the typed input from left to right.
def completion_lookup(normalized, dataset):
    matches = []

    if not normalized:
        return matches

    for row in dataset:
        romanized = row["romanized"]

        if romanized == normalized:
            continue

        extra_chars = len(romanized) - len(normalized)

        if romanized.startswith(normalized) and extra_chars <= MAX_COMPLETION_EXTRA_CHARS:
            matches.append(row)

    matches.sort(
        key=lambda row: (
            -row["frequency"],
            len(row["romanized"]),
            row["romanized"],
        ),
    )

    return matches


# Keep the highest-scoring suggestion for each Khmer output.
def dedupe_suggestions(suggestions):
    best_by_khmer = {}

    for suggestion in suggestions:
        khmer = suggestion["khmer"]
        current = best_by_khmer.get(khmer)

        if current is None:
            best_by_khmer[khmer] = suggestion
            continue

        suggestion_rank = (
            suggestion["source_priority"],
            suggestion["score"],
            suggestion.get("frequency", 0),
        )
        current_rank = (
            current["source_priority"],
            current["score"],
            current.get("frequency", 0),
        )

        if suggestion_rank > current_rank:
            best_by_khmer[khmer] = suggestion

    return list(best_by_khmer.values())


def build_dataset_index(dataset):
    index = {}

    for row in dataset:
        index.setdefault(row["khmer"], []).append(row)

    return index


def apply_dataset_match_scores(user_input, suggestions, dataset_index):
    for suggestion in suggestions:
        rows = dataset_index.get(suggestion["khmer"], [])

        if not rows:
            suggestion["dataset_match_score"] = 0
            continue

        best_similarity = 0
        best_frequency = 0
        best_romanized = ""

        for row in rows:
            similarity = fuzz.ratio(user_input, normalize_input(row["romanized"])) / 100

            if (
                similarity > best_similarity
                or (
                    similarity == best_similarity
                    and row["frequency"] > best_frequency
                )
            ):
                best_similarity = similarity
                best_frequency = row["frequency"]
                best_romanized = row["romanized"]

        dataset_score = (
            DATASET_KHMER_EXISTS_BOOST
            + best_similarity * DATASET_ROMANIZED_SIMILARITY_BOOST
            + best_frequency * DATASET_FREQUENCY_BOOST_FACTOR
        )

        suggestion["dataset_match_score"] = round(dataset_score, 4)
        suggestion["dataset_similarity"] = round(best_similarity, 4)
        suggestion["dataset_romanized"] = best_romanized
        suggestion["dataset_frequency"] = best_frequency
        suggestion["score"] += dataset_score

    return suggestions


# Load the trained ranking model when it exists.
def load_ranking_model(model_file=RANKING_MODEL_FILE):
    if not os.path.exists(model_file):
        return None

    return joblib.load(model_file)


# Add ML probability scores to suggestions.
def apply_ml_scores(user_input, suggestions, ranking_model):
    if ranking_model is None or not suggestions:
        return suggestions

    features = [
        extract_ranking_features(user_input, suggestion)
        for suggestion in suggestions
    ]
    probabilities = ranking_model.predict_proba(features)[:, 1]

    for suggestion, probability in zip(suggestions, probabilities):
        suggestion["ml_score"] = round(float(probability), 4)

    return suggestions


# Load manual labels so reviewed examples can directly influence UI ranking.
def load_manual_label_map(manual_file=MANUAL_RANKING_EXAMPLES_FILE):
    labels = {}

    if not os.path.exists(manual_file):
        return labels

    with open(manual_file, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            label = row.get("label", "").strip()

            if label not in {"0", "1"}:
                continue

            labels[(row["input"], row["khmer"])] = int(label)

    return labels


# Attach manual labels from the review CSV; label 1 boosts, label 0 demotes.
def apply_manual_labels(user_input, suggestions, manual_labels=None):
    manual_labels = manual_labels if manual_labels is not None else load_manual_label_map()

    for suggestion in suggestions:
        label = manual_labels.get((user_input, suggestion["khmer"]))

        if label is None:
            suggestion["manual_label_score"] = 0
            continue

        suggestion["manual_label"] = label
        suggestion["manual_label_score"] = 1 if label == 1 else -1

    return suggestions


# Add human-readable ranking information for the UI/debug reports.
def apply_rank_metadata(suggestions):
    for suggestion in suggestions:
        rank_score = (
            suggestion["source_priority"] * 100
            + suggestion.get("manual_label_score", 0) * 10
            + suggestion["score"]
            + suggestion.get("ml_score", 0) * 0.01
        )
        suggestion["rank_score"] = round(rank_score, 4)

        if suggestion.get("manual_label") == 1:
            suggestion["rank_reason"] = "manual good label"
        elif suggestion.get("manual_label") == 0:
            suggestion["rank_reason"] = "manual bad label"
        elif suggestion["source"] == "dictionary_exact":
            suggestion["rank_reason"] = "exact dictionary"
        elif suggestion["source"] == "dictionary_completion":
            suggestion["rank_reason"] = "left-to-right completion"
        elif suggestion["source"].startswith("direct_"):
            suggestion["rank_reason"] = "direct token"
        else:
            suggestion["rank_reason"] = "rule generated"

    return suggestions


# Merge exact dictionary, left-to-right completion, and generated rule candidates.
def get_suggestions(
    user_input,
    dataset=None,
    rules=None,
    ranking_model=None,
    manual_labels=None,
    use_ml=True,
    allow_vowels=False,
    limit=DEFAULT_SUGGESTION_LIMIT,
    min_rule_score=MIN_RULE_DISPLAY_SCORE,
):
    normalized = normalize_input(user_input)
    dataset = dataset or load_dataset()
    rules = rules or load_mapping_rules()
    ranking_model = ranking_model or (load_ranking_model() if use_ml else None)
    dataset_index = build_dataset_index(dataset)
    suggestions = []

    exact_matches = exact_lookup(normalized, dataset)
    direct_matches = direct_token_lookup(normalized, rules, allow_vowels=allow_vowels)
    completion_matches = completion_lookup(normalized, dataset)
    rule_limit = max(limit or 0, 300) if limit is not None else 300
    rule_candidates = generate_ranked_candidates(normalized, rules, limit=rule_limit)

    suggestions.extend(direct_matches)

    for row in exact_matches:
        suggestions.append(make_exact_suggestion(row))

    for row in completion_matches:
        suggestions.append(make_completion_suggestion(row, normalized))

    for candidate in rule_candidates:
        suggestion = make_rule_suggestion(candidate, normalized)

        if min_rule_score is not None and suggestion["score"] < min_rule_score:
            continue

        suggestions.append(suggestion)

    suggestions = dedupe_suggestions(suggestions)
    suggestions = apply_dataset_match_scores(normalized, suggestions, dataset_index)
    suggestions = apply_manual_labels(normalized, suggestions, manual_labels)
    suggestions = apply_ml_scores(normalized, suggestions, ranking_model)
    suggestions = apply_rank_metadata(suggestions)
    suggestions.sort(
        key=lambda suggestion: (
            suggestion["source_priority"],
            suggestion.get("manual_label_score", 0),
            suggestion["score"],
            suggestion.get("ml_score", -1),
            suggestion.get("frequency", 0),
        ),
        reverse=True,
    )

    if limit is None or limit <= 0:
        return suggestions

    return suggestions[:limit]


# Simple terminal tester for Step 7.
if __name__ == "__main__":
    dataset = load_dataset()
    rules = load_mapping_rules()
    ranking_model = load_ranking_model()

    while True:
        user_input = input("Type romanized Khmer: ")

        if user_input == "exit":
            break

        for suggestion in get_suggestions(user_input, dataset, rules, ranking_model=ranking_model):
            print(
                suggestion["khmer"],
                suggestion["source"],
                round(suggestion["score"], 4),
                suggestion.get("ml_score", ""),
            )
