from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import json
import os
import csv

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from khmer_transliteration.mapping_rules import load_mapping_rules
from khmer_transliteration.dictionary_lookup import exact_lookup, load_dataset
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


MODEL_DIR = MODELS_DIR
MODEL_FILE = RANKING_MODEL_FILE
METADATA_FILE = RANKING_MODEL_METADATA_FILE
REPORT_FILE = RANKING_MODEL_REPORT_FILE
MANUAL_EXAMPLES_FILE = RANKING_TRAINING_EXAMPLES_FILE


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
def build_training_data(dataset, rules, max_inputs=5000, candidates_per_input=20):
    features = []
    labels = []
    rows = []
    training_cases = build_training_cases(dataset, max_rows=max_inputs)

    for case in training_cases:
        user_input = case["input"]
        positive_khmer = {case["positive_khmer"]}

        suggestions = get_suggestions(
            user_input,
            dataset=dataset,
            rules=rules,
            use_ml=False,
            limit=candidates_per_input,
        )

        for suggestion in suggestions:
            label = 1 if suggestion["khmer"] in positive_khmer else 0

            features.append(extract_ranking_features(user_input, suggestion))
            labels.append(label)
            rows.append({
                "input": user_input,
                "khmer": suggestion["khmer"],
                "source": suggestion["source"],
                "case_type": case["case_type"],
                "label": label,
            })

    return features, labels, rows


# Add human-labeled examples from the review CSV when label is 0 or 1.
def add_manual_training_data(features, labels, rows, manual_file=MANUAL_EXAMPLES_FILE):
    if not os.path.exists(manual_file):
        return 0

    added_count = 0

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


def main():
    dataset = load_dataset()
    rules = load_mapping_rules()
    features, labels, rows = build_training_data(dataset, rules)
    manual_count = add_manual_training_data(features, labels, rows)

    if not features:
        raise RuntimeError("No training data was generated.")

    positive_count = sum(labels)
    negative_count = len(labels) - positive_count

    if positive_count == 0 or negative_count == 0:
        raise RuntimeError("Training data needs both positive and negative labels.")

    split_data = train_test_split(
        features,
        labels,
        rows,
        test_size=0.2,
        random_state=42,
        stratify=labels,
    )
    X_train, X_test, y_train, y_test, rows_train, rows_test = split_data

    model = train_model(X_train, y_train)
    predictions = model.predict(X_test)
    probabilities = model.predict_proba(X_test)[:, 1]

    accuracy = accuracy_score(y_test, predictions)
    roc_auc = roc_auc_score(y_test, probabilities)
    report = classification_report(y_test, predictions, digits=4)
    ranking_metrics = evaluate_ranking(model, X_test, y_test, rows_test)

    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, MODEL_FILE)

    metadata = {
        "feature_names": FEATURE_NAMES,
        "training_candidates": len(labels),
        "manual_candidates": manual_count,
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
