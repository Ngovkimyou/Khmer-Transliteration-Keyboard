from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import argparse
import json
import os
import csv
from collections import defaultdict

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from khmer_transliteration.mapping_rules import load_mapping_rules
from khmer_transliteration.dictionary_lookup import exact_lookup, load_dataset
from khmer_transliteration.history import (
    load_selection_history,
    load_word_pair_frequencies,
)
from khmer_transliteration.normalizer import normalize_input
from khmer_transliteration.paths import (
    MODELS_DIR,
    RANKING_MODEL_FILE,
    RANKING_MODEL_METADATA_FILE,
    RANKING_MODEL_REPORT_FILE,
    RANKING_TRAINING_EXAMPLES_FILE,
)
from khmer_transliteration.ranking_features import FEATURE_NAMES, extract_ranking_features
from khmer_transliteration.suggestion_engine import get_suggestions


HISTORY_TRAINING_CANDIDATES_PER_INPUT = 50
PROGRESS_EVERY = 250


MODEL_DIR = MODELS_DIR
MODEL_FILE = RANKING_MODEL_FILE
METADATA_FILE = RANKING_MODEL_METADATA_FILE
REPORT_FILE = RANKING_MODEL_REPORT_FILE
MANUAL_EXAMPLES_FILE = RANKING_TRAINING_EXAMPLES_FILE


def log_progress(message):
    print(message, flush=True)


def copy_suggestions(suggestions):
    return [suggestion.copy() for suggestion in suggestions]


def get_cached_suggestions(cache, key, **kwargs):
    if key not in cache:
        cache[key] = get_suggestions(**kwargs)

    return copy_suggestions(cache[key])


# Use one row per unique Romanized/Khmer pair so repeated dataset rows do not dominate.
def get_unique_training_rows(dataset, max_rows=5000):
    seen = set()
    rows = []

    for row in dataset:
        normalized = normalize_input(row["romanized"])
        key = (normalized, row["khmer"])

        if not normalized or key in seen:
            continue

        seen.add(key)
        clean_row = row.copy()
        clean_row["romanized"] = normalized
        rows.append(clean_row)

        if len(rows) >= max_rows:
            break

    return rows


# Add both full-input cases and prefix-completion cases for each target word.
def build_training_cases(dataset, max_rows=5000):
    cases = []

    for row in get_unique_training_rows(dataset, max_rows=max_rows):
        romanized = row["romanized"]
        khmer = row["khmer"]

        cases.append({
            "input": romanized,
            "positive_khmer": khmer,
            "case_type": "full",
        })

        if len(romanized) >= 4:
            prefix_length = max(2, len(romanized) // 2)
            prefix = romanized[:prefix_length]

            if prefix != romanized:
                cases.append({
                    "input": prefix,
                    "positive_khmer": khmer,
                    "case_type": "prefix",
                })

    return cases


# Build supervised rows: exact Khmer matches are positive, other candidates are negative.
def build_training_data(
    dataset,
    rules,
    max_inputs=5000,
    candidates_per_input=20,
    enable_fuzzy=False,
    enable_compound=False,
):
    features = []
    labels = []
    rows = []
    training_cases = build_training_cases(dataset, max_rows=max_inputs)
    total_cases = len(training_cases)
    cases_by_input = defaultdict(list)

    for case in training_cases:
        cases_by_input[case["input"]].append(case)

    unique_inputs = sorted(cases_by_input)
    total_unique_inputs = len(unique_inputs)
    log_progress(
        f"Building base training data from {total_cases:,} cases "
        f"across {total_unique_inputs:,} unique inputs "
        f"(max {candidates_per_input} candidates each)..."
    )

    for index, user_input in enumerate(unique_inputs, start=1):
        cases = cases_by_input[user_input]
        positive_khmers = {
            case["positive_khmer"]
            for case in cases
        }
        case_types = ",".join(sorted({
            case["case_type"]
            for case in cases
        }))

        suggestions = get_suggestions(
            user_input,
            dataset=dataset,
            rules=rules,
            use_ml=False,
            enable_fuzzy=enable_fuzzy,
            enable_compound=enable_compound,
            limit=candidates_per_input,
        )

        for suggestion in suggestions:
            label = 1 if suggestion["khmer"] in positive_khmers else 0

            features.append(extract_ranking_features(user_input, suggestion))
            labels.append(label)
            rows.append({
                "input": user_input,
                "khmer": suggestion["khmer"],
                "source": suggestion["source"],
                "case_type": case_types,
                "label": label,
            })

        if index % PROGRESS_EVERY == 0 or index == total_unique_inputs:
            log_progress(
                f"  base inputs: {index:,}/{total_unique_inputs:,} "
                f"-> {len(labels):,} candidate rows"
            )

    return features, labels, rows


# Add human-labeled examples from the review CSV when label is 0 or 1.
def add_manual_training_data(features, labels, rows, manual_file=MANUAL_EXAMPLES_FILE):
    if not os.path.exists(manual_file):
        log_progress("Manual labels: no CSV found, skipping.")
        return 0

    added_count = 0
    log_progress("Adding manual labeled rows...")

    with open(manual_file, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            label = row.get("label", "").strip()

            if label not in {"0", "1"}:
                continue

            suggestion = {
                "khmer": row["khmer"],
                "romanized": row["input"],
                "source": row.get("source", ""),
                "score": float(row["score"] or 0),
                "frequency": int(row["frequency"] or 0),
                "rule_score": float(row["rule_score"] or 0),
                "remaining_length": 0,
                "tokens": row.get("tokens", "").split(),
                "chunks": [],
            }

            features.append(extract_ranking_features(row["input"], suggestion))
            labels.append(int(label))
            rows.append({
                "input": row["input"],
                "khmer": row["khmer"],
                "source": row.get("source", ""),
                "case_type": "manual",
                "label": int(label),
            })
            added_count += 1

    log_progress(f"  manual rows added: {added_count:,}")
    return added_count


def add_selection_history_training_data(
    features,
    labels,
    rows,
    dataset,
    rules,
    enable_fuzzy=False,
    enable_compound=False,
):
    selection_history = load_selection_history()
    added_count = 0
    total_items = len(selection_history)

    if not selection_history:
        log_progress("Selection history: no rows found, skipping.")
        return 0

    log_progress(f"Adding selection-history training data from {total_items:,} selections...")

    selections_by_input = defaultdict(dict)

    for (user_input, selected_khmer), count in selection_history.items():
        selections_by_input[user_input][selected_khmer] = count

    total_inputs = len(selections_by_input)

    for index, (user_input, selected_khmers) in enumerate(
        sorted(selections_by_input.items()),
        start=1,
    ):
        suggestions = get_suggestions(
            user_input,
            dataset=dataset,
            rules=rules,
            selection_history=selection_history,
            use_ml=False,
            enable_fuzzy=enable_fuzzy,
            enable_compound=enable_compound,
            limit=HISTORY_TRAINING_CANDIDATES_PER_INPUT,
            min_rule_score=None,
        )

        for suggestion in suggestions:
            label = 1 if suggestion["khmer"] in selected_khmers else 0

            features.append(extract_ranking_features(user_input, suggestion))
            labels.append(label)
            rows.append({
                "input": user_input,
                "khmer": suggestion["khmer"],
                "source": suggestion.get("source", ""),
                "case_type": "selection_history",
                "label": label,
                "history_count": selected_khmers.get(suggestion["khmer"], 0),
            })
            added_count += 1

        if index % PROGRESS_EVERY == 0 or index == total_inputs:
            log_progress(
                f"  selection history inputs: {index:,}/{total_inputs:,} "
                f"-> +{added_count:,} rows"
            )

    return added_count


def build_khmer_to_romanized_index(dataset):
    index = {}

    for row in dataset:
        normalized = normalize_input(row["romanized"])

        if not normalized:
            continue

        index.setdefault(row["khmer"], []).append({
            **row,
            "romanized": normalized,
        })

    for romanized_rows in index.values():
        romanized_rows.sort(
            key=lambda row: (
                -row["frequency"],
                len(row["romanized"]),
            ),
        )

    return index


def add_word_pair_training_data(
    features,
    labels,
    rows,
    dataset,
    rules,
    enable_fuzzy=False,
    enable_compound=False,
):
    pair_frequencies = load_word_pair_frequencies()
    khmer_to_romanized = build_khmer_to_romanized_index(dataset)
    added_count = 0
    total_pairs = len(pair_frequencies)
    suggestion_cache = {}

    if not pair_frequencies:
        log_progress("Word-pair context: no rows found, skipping.")
        return 0

    log_progress(f"Adding word-pair context training data from {total_pairs:,} pairs...")

    for index, ((previous_khmer, current_khmer), count) in enumerate(
        pair_frequencies.items(),
        start=1,
    ):
        romanized_rows = khmer_to_romanized.get(current_khmer, [])

        for romanized_row in romanized_rows[:3]:
            user_input = romanized_row["romanized"]
            suggestions = get_cached_suggestions(
                suggestion_cache,
                (previous_khmer, user_input),
                user_input=user_input,
                dataset=dataset,
                rules=rules,
                pair_frequencies=pair_frequencies,
                previous_word=previous_khmer,
                use_ml=False,
                enable_fuzzy=enable_fuzzy,
                enable_compound=enable_compound,
                limit=HISTORY_TRAINING_CANDIDATES_PER_INPUT,
                min_rule_score=None,
            )

            for suggestion in suggestions:
                label = 1 if suggestion["khmer"] == current_khmer else 0

                features.append(extract_ranking_features(user_input, suggestion))
                labels.append(label)
                rows.append({
                    "input": user_input,
                    "khmer": suggestion["khmer"],
                    "source": suggestion.get("source", ""),
                    "case_type": "previous_word_context",
                    "label": label,
                    "previous_khmer": previous_khmer,
                    "pair_count": count,
                })
                added_count += 1

        if index % PROGRESS_EVERY == 0 or index == total_pairs:
            log_progress(
                f"  word pairs: {index:,}/{total_pairs:,} "
                f"-> +{added_count:,} rows"
            )

    return added_count


# Train a simple classifier that predicts whether a candidate is the intended output.
def train_model(features, labels):
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("classifier", LogisticRegression(
            class_weight="balanced",
            max_iter=1000,
            random_state=42,
        )),
    ])

    model.fit(features, labels)
    return model


# Measure ranking quality by grouping candidates for the same user input.
def evaluate_ranking(model, features, labels, rows):
    probabilities = model.predict_proba(features)[:, 1]
    groups = {}

    for feature, label, row, probability in zip(features, labels, rows, probabilities):
        groups.setdefault(row["input"], []).append({
            "label": label,
            "row": row,
            "probability": probability,
        })

    evaluated_groups = 0
    top_1_hits = 0
    top_3_hits = 0
    reciprocal_rank_sum = 0

    for candidates in groups.values():
        if not any(candidate["label"] == 1 for candidate in candidates):
            continue

        evaluated_groups += 1
        ranked = sorted(
            candidates,
            key=lambda candidate: candidate["probability"],
            reverse=True,
        )

        if ranked[0]["label"] == 1:
            top_1_hits += 1

        if any(candidate["label"] == 1 for candidate in ranked[:3]):
            top_3_hits += 1

        for index, candidate in enumerate(ranked, start=1):
            if candidate["label"] == 1:
                reciprocal_rank_sum += 1 / index
                break

    if evaluated_groups == 0:
        return {
            "ranking_groups": 0,
            "top_1_accuracy": 0,
            "top_3_accuracy": 0,
            "mrr": 0,
        }

    return {
        "ranking_groups": evaluated_groups,
        "top_1_accuracy": top_1_hits / evaluated_groups,
        "top_3_accuracy": top_3_hits / evaluated_groups,
        "mrr": reciprocal_rank_sum / evaluated_groups,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Train the suggestion ranking model.")
    parser.add_argument(
        "--max-inputs",
        type=int,
        default=5000,
        help="Maximum unique dictionary rows to use for base training data.",
    )
    parser.add_argument(
        "--candidates-per-input",
        type=int,
        default=20,
        help="Maximum suggestions generated per training input.",
    )
    parser.add_argument(
        "--include-fuzzy",
        action="store_true",
        help="Include fuzzy dictionary candidates during training. Slower.",
    )
    parser.add_argument(
        "--include-compound",
        action="store_true",
        help="Include compound segmentation candidates during training. Slower.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    log_progress("Loading dataset and mapping rules...")
    dataset = load_dataset()
    rules = load_mapping_rules()
    log_progress(
        f"Training settings: max_inputs={args.max_inputs:,}, "
        f"candidates_per_input={args.candidates_per_input:,}, "
        f"include_fuzzy={args.include_fuzzy}, "
        f"include_compound={args.include_compound}"
    )
    features, labels, rows = build_training_data(
        dataset,
        rules,
        max_inputs=args.max_inputs,
        candidates_per_input=args.candidates_per_input,
        enable_fuzzy=args.include_fuzzy,
        enable_compound=args.include_compound,
    )
    manual_count = add_manual_training_data(features, labels, rows)
    selection_history_count = add_selection_history_training_data(
        features,
        labels,
        rows,
        dataset,
        rules,
        enable_fuzzy=args.include_fuzzy,
        enable_compound=args.include_compound,
    )
    word_pair_count = add_word_pair_training_data(
        features,
        labels,
        rows,
        dataset,
        rules,
        enable_fuzzy=args.include_fuzzy,
        enable_compound=args.include_compound,
    )

    if not features:
        raise RuntimeError("No training data was generated.")

    positive_count = sum(labels)
    negative_count = len(labels) - positive_count

    if positive_count == 0 or negative_count == 0:
        raise RuntimeError("Training data needs both positive and negative labels.")

    log_progress(
        f"Training rows ready: {len(labels):,} "
        f"({positive_count:,} positive / {negative_count:,} negative)"
    )
    log_progress("Splitting train/test data...")

    split_data = train_test_split(
        features,
        labels,
        rows,
        test_size=0.2,
        random_state=42,
        stratify=labels,
    )
    X_train, X_test, y_train, y_test, rows_train, rows_test = split_data

    log_progress("Training LogisticRegression model...")
    model = train_model(X_train, y_train)
    log_progress("Evaluating model...")
    predictions = model.predict(X_test)
    probabilities = model.predict_proba(X_test)[:, 1]

    accuracy = accuracy_score(y_test, predictions)
    roc_auc = roc_auc_score(y_test, probabilities)
    report = classification_report(y_test, predictions, digits=4)
    ranking_metrics = evaluate_ranking(model, X_test, y_test, rows_test)

    log_progress("Saving model and report...")
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, MODEL_FILE)

    metadata = {
        "feature_names": FEATURE_NAMES,
        "training_candidates": len(labels),
        "manual_candidates": manual_count,
        "selection_history_candidates": selection_history_count,
        "word_pair_candidates": word_pair_count,
        "positive_candidates": positive_count,
        "negative_candidates": negative_count,
        "train_candidates": len(y_train),
        "test_candidates": len(y_test),
        "accuracy": accuracy,
        "roc_auc": roc_auc,
        **ranking_metrics,
        "model_file": str(MODEL_FILE),
    }

    with open(METADATA_FILE, "w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2)

    with open(REPORT_FILE, "w", encoding="utf-8") as file:
        file.write("Ranking Model Report\n")
        file.write("====================\n\n")
        file.write(f"Training candidates: {len(labels)}\n")
        file.write(f"Manual candidates: {manual_count}\n")
        file.write(f"Selection history candidates: {selection_history_count}\n")
        file.write(f"Word-pair context candidates: {word_pair_count}\n")
        file.write(f"Positive candidates: {positive_count}\n")
        file.write(f"Negative candidates: {negative_count}\n")
        file.write(f"Accuracy: {accuracy:.4f}\n")
        file.write(f"ROC AUC: {roc_auc:.4f}\n\n")
        file.write("Ranking metrics\n")
        file.write("---------------\n")
        file.write(f"Ranking groups: {ranking_metrics['ranking_groups']}\n")
        file.write(f"Top-1 accuracy: {ranking_metrics['top_1_accuracy']:.4f}\n")
        file.write(f"Top-3 accuracy: {ranking_metrics['top_3_accuracy']:.4f}\n")
        file.write(f"MRR: {ranking_metrics['mrr']:.4f}\n\n")
        file.write(report)

    print(f"Saved model to {MODEL_FILE}")
    print(f"Saved metadata to {METADATA_FILE}")
    print(f"Saved report to {REPORT_FILE}")


if __name__ == "__main__":
    main()
