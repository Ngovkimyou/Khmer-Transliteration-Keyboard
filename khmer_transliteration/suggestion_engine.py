import os
import csv

import joblib
from rapidfuzz import fuzz, process

from khmer_transliteration.candidate_generator import generate_ranked_candidates
from khmer_transliteration.mapping_rules import load_mapping_rules
from khmer_transliteration.dictionary_lookup import exact_lookup, load_dataset
from khmer_transliteration.normalizer import normalize_input
from khmer_transliteration.paths import (
    RANKING_MODEL_FILE as RANKING_MODEL_FILE_PATH,
    RANKING_TRAINING_EXAMPLES_FILE,
)
from khmer_transliteration.ranking_features import extract_ranking_features


EXACT_BASE_SCORE = 3.0
COMPLETION_BASE_SCORE = 2.5
RULE_BASE_SCORE = 1.0
DIRECT_TOKEN_BASE_SCORE = 4.0
DIRECT_TOKEN_PRIORITY = 5
EXACT_PRIORITY = 4
COMPLETION_PRIORITY = 3
COMPOUND_PRIORITY = 2.5
RULE_PRIORITY = 1
FUZZY_PRIORITY = RULE_PRIORITY
DEFAULT_SUGGESTION_LIMIT = 10
MIN_RULE_DISPLAY_SCORE = 1.60
MAX_COMPLETION_EXTRA_CHARS = 2
COMPOUND_MIN_INPUT_LENGTH = 6
COMPOUND_MIN_SEGMENT_LENGTH = 2
COMPOUND_MAX_SEGMENTS = 3
COMPOUND_MAX_OPTIONS_PER_SEGMENT = 4
COMPOUND_MAX_SUGGESTIONS = 80
COMPOUND_RULE_MIN_SCORE = 0.78
COMPOUND_FUZZY_MIN_SEGMENT_LENGTH = 4
COMPOUND_FUZZY_MIN_SCORE = 80
FUZZY_MIN_INPUT_LENGTH = 5
FUZZY_MIN_SCORE = 80
FUZZY_LIMIT = 20
DATASET_KHMER_EXISTS_BOOST = 0.25
DATASET_ROMANIZED_SIMILARITY_BOOST = 0.75
DATASET_FREQUENCY_BOOST_FACTOR = 0.001
RANKING_MODEL_FILE = str(RANKING_MODEL_FILE_PATH)
MANUAL_RANKING_EXAMPLES_FILE = str(RANKING_TRAINING_EXAMPLES_FILE)


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


def make_fuzzy_suggestion(row, normalized):
    fuzzy_similarity = fuzz.ratio(normalized, row["romanized"]) / 100

    return {
        "khmer": row["khmer"],
        "romanized": row["romanized"],
        "source": "dictionary_fuzzy",
        "source_priority": FUZZY_PRIORITY,
        "frequency": row["frequency"],
        "fuzzy_score": round(fuzzy_similarity, 4),
        "score": 1.0 + fuzzy_similarity * 0.4 + row["frequency"] * 0.001,
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


def fuzzy_dictionary_lookup(normalized, dataset):
    if len(normalized) < FUZZY_MIN_INPUT_LENGTH:
        return []

    romanized_words = sorted({row["romanized"] for row in dataset})
    fuzzy_matches = process.extract(
        normalized,
        romanized_words,
        scorer=fuzz.ratio,
        limit=FUZZY_LIMIT,
    )
    matched_words = {
        romanized_word
        for romanized_word, score, _ in fuzzy_matches
        if score >= FUZZY_MIN_SCORE and romanized_word != normalized
    }

    if not matched_words:
        return []

    matches = [
        row
        for row in dataset
        if row["romanized"] in matched_words
    ]
    matches.sort(
        key=lambda row: (
            fuzz.ratio(normalized, row["romanized"]),
            row["frequency"],
        ),
        reverse=True,
    )

    return matches


def build_romanized_index(dataset):
    index = {}

    for row in dataset:
        index.setdefault(row["romanized"], []).append(row)

    for rows in index.values():
        rows.sort(key=lambda row: row["frequency"], reverse=True)

    return index


def get_compound_segment_options(segment, romanized_index, romanized_words, rules):
    options = []
    exact_rows = romanized_index.get(segment, [])

    for row in exact_rows[:COMPOUND_MAX_OPTIONS_PER_SEGMENT]:
        options.append({
            "khmer": row["khmer"],
            "romanized": row["romanized"],
            "source": "dictionary_exact",
            "frequency": row["frequency"],
            "score": 1.2 + row["frequency"] * 0.001,
        })

    if options:
        return options

    for candidate in generate_ranked_candidates(
        segment,
        rules,
        limit=COMPOUND_MAX_OPTIONS_PER_SEGMENT,
    ):
        if candidate["final_score"] < COMPOUND_RULE_MIN_SCORE:
            continue

        options.append({
            "khmer": candidate["khmer"],
            "romanized": segment,
            "source": candidate["source"],
            "frequency": 0,
            "score": candidate["final_score"],
            "tokens": candidate.get("tokens", []),
            "chunks": candidate.get("chunks", []),
        })

    if options:
        return options

    if len(segment) >= COMPOUND_FUZZY_MIN_SEGMENT_LENGTH:
        fuzzy_matches = process.extract(
            segment,
            romanized_words,
            scorer=fuzz.ratio,
            limit=COMPOUND_MAX_OPTIONS_PER_SEGMENT,
        )

        for romanized_word, score, _ in fuzzy_matches:
            if score < COMPOUND_FUZZY_MIN_SCORE:
                continue

            for row in romanized_index.get(romanized_word, [])[:1]:
                options.append({
                    "khmer": row["khmer"],
                    "romanized": row["romanized"],
                    "source": "dictionary_fuzzy",
                    "frequency": row["frequency"],
                    "score": 0.95 + (score / 100) * 0.25 + row["frequency"] * 0.001,
                })

    return options


def compound_segment_lookup(normalized, dataset, rules):
    if len(normalized) < COMPOUND_MIN_INPUT_LENGTH:
        return []

    romanized_index = build_romanized_index(dataset)
    romanized_words = sorted(romanized_index.keys())
    suggestions = []

    def backtrack(start_index, current_segments):
        if len(suggestions) >= COMPOUND_MAX_SUGGESTIONS:
            return

        if start_index == len(normalized):
            if len(current_segments) < 2:
                return

            khmer = "".join(segment["khmer"] for segment in current_segments)
            romanized = "+".join(segment["romanized"] for segment in current_segments)
            frequency = sum(segment.get("frequency", 0) for segment in current_segments)
            segment_score = sum(segment["score"] for segment in current_segments)
            segment_score = segment_score / len(current_segments)
            score = 2.0 + segment_score - (len(current_segments) - 1) * 0.08

            suggestions.append({
                "khmer": khmer,
                "romanized": normalized,
                "source": "dictionary_compound",
                "source_priority": COMPOUND_PRIORITY,
                "frequency": frequency,
                "compound_romanized": romanized,
                "compound_segments": [
                    {
                        "romanized": segment["romanized"],
                        "khmer": segment["khmer"],
                        "source": segment["source"],
                    }
                    for segment in current_segments
                ],
                "score": score,
            })
            return

        if len(current_segments) >= COMPOUND_MAX_SEGMENTS:
            return

        for end_index in range(start_index + COMPOUND_MIN_SEGMENT_LENGTH, len(normalized) + 1):
            segment = normalized[start_index:end_index]
            segment_options = get_compound_segment_options(
                segment,
                romanized_index,
                romanized_words,
                rules,
            )

            for option in segment_options:
                current_segments.append(option)
                backtrack(end_index, current_segments)
                current_segments.pop()

    backtrack(0, [])

    suggestions.sort(
        key=lambda suggestion: (
            suggestion["score"],
            suggestion.get("frequency", 0),
            -len(suggestion["compound_segments"]),
        ),
        reverse=True,
    )

    return suggestions[:COMPOUND_MAX_SUGGESTIONS]


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
        elif suggestion["source"] == "dictionary_compound":
            suggestion["rank_reason"] = "compound segmentation"
        elif suggestion["source"] == "dictionary_fuzzy":
            suggestion["rank_reason"] = "fuzzy dictionary"
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
    compound_matches = compound_segment_lookup(normalized, dataset, rules)
    fuzzy_matches = fuzzy_dictionary_lookup(normalized, dataset)
    rule_limit = max(limit or 0, 300) if limit is not None else 300
    rule_candidates = generate_ranked_candidates(normalized, rules, limit=rule_limit)

    suggestions.extend(direct_matches)

    for row in exact_matches:
        suggestions.append(make_exact_suggestion(row))

    for row in completion_matches:
        suggestions.append(make_completion_suggestion(row, normalized))

    suggestions.extend(compound_matches)

    for row in fuzzy_matches:
        suggestions.append(make_fuzzy_suggestion(row, normalized))

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
