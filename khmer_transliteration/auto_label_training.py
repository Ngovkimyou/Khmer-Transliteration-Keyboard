"""Auto-label ranking-training rows by comparing suggestions to the dataset.

Default mode works on rows already collected from the UI. Dataset-wide row
generation is available, but must be requested by the wrapper script.
"""

import argparse
import csv
import os
from collections import defaultdict

from khmer_transliteration.collection import (
    FIELDNAMES,
    ensure_output_schema,
    get_category,
)
from khmer_transliteration.dictionary_lookup import load_dataset
from khmer_transliteration.mapping_rules import load_mapping_rules
from khmer_transliteration.normalizer import normalize_input, normalize_phrase_input
from khmer_transliteration.paths import RANKING_TRAINING_EXAMPLES_FILE
from khmer_transliteration.suggestion_engine import get_suggestions


DEFAULT_SUGGESTION_LIMIT = 50
PROGRESS_EVERY = 250


def log_progress(message):
    print(message, flush=True)


def group_valid_outputs(dataset):
    """Map each normalized romanized input to all Khmer outputs in the dataset."""
    valid_outputs = defaultdict(set)

    for row in dataset:
        romanized = normalize_input(row["romanized"])

        if not romanized or not row["khmer"]:
            continue

        valid_outputs[romanized].add(row["khmer"])

    return dict(valid_outputs)


def load_existing_rows(output_file):
    """Load review rows keyed by (input, khmer) for merge/update operations."""
    rows_by_key = {}

    if not os.path.exists(output_file):
        return rows_by_key

    ensure_output_schema(output_file)

    with open(output_file, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            rows_by_key[(row["input"], row["khmer"])] = {
                fieldname: row.get(fieldname, "")
                for fieldname in FIELDNAMES
            }

    return rows_by_key


def normalize_review_input(input_text):
    """Use phrase normalization only when a review input contains spaces."""
    if " " in input_text.strip():
        return normalize_phrase_input(input_text)

    return normalize_input(input_text)


def load_ordered_existing_rows(output_file):
    """Read review rows in file order so auto-labeling can preserve UI ranking."""
    if not os.path.exists(output_file):
        return []

    ensure_output_schema(output_file)

    with open(output_file, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return [
            {
                fieldname: row.get(fieldname, "")
                for fieldname in FIELDNAMES
            }
            for row in reader
        ]


def write_ordered_rows(output_file, rows):
    """Write rows back in their current order after updating labels."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows([
            {
                fieldname: row.get(fieldname, "")
                for fieldname in FIELDNAMES
            }
            for row in rows
        ])


def can_replace_label(row, overwrite_auto=False):
    """Protect human labels unless the caller explicitly overwrites auto labels."""
    existing_label = row.get("label", "").strip()
    existing_note = row.get("note", "")

    if existing_label not in {"0", "1"}:
        return True

    return overwrite_auto and existing_note.startswith("auto_")


def collect_existing_inputs(rows, selected_inputs=None):
    """Return unique UI-collected inputs, optionally filtered by user request."""
    selected = None

    if selected_inputs:
        selected = {
            normalize_review_input(input_text)
            for input_text in selected_inputs
        }

    inputs = []
    seen = set()

    for row in rows:
        input_text = normalize_review_input(row.get("input", ""))

        if not input_text:
            continue

        if selected is not None and input_text not in selected:
            continue

        if input_text in seen:
            continue

        seen.add(input_text)
        inputs.append(input_text)

    return inputs


def auto_label_existing_training_examples(
    output_file=RANKING_TRAINING_EXAMPLES_FILE,
    max_inputs=None,
    selected_inputs=None,
    overwrite_auto=False,
    dry_run=False,
):
    """Label existing UI-collected rows without generating new candidates."""
    dataset = load_dataset()
    valid_outputs = group_valid_outputs(dataset)
    rows = load_ordered_existing_rows(output_file)
    inputs = collect_existing_inputs(rows, selected_inputs=selected_inputs)

    if max_inputs is not None:
        inputs = inputs[:max_inputs]

    selected_input_set = set(inputs)
    rows_by_input = defaultdict(list)

    for row in rows:
        normalized_input = normalize_review_input(row.get("input", ""))

        if normalized_input in selected_input_set:
            rows_by_input[normalized_input].append(row)

    totals = {
        "inputs": len(inputs),
        "with_labels": 0,
        "missing_dataset_input": 0,
        "missing_correct": 0,
        "positive": 0,
        "negative": 0,
        "generated_rows": 0,
        "added": 0,
        "updated": 0,
        "skipped": 0,
    }

    log_progress(
        f"Auto-labeling existing UI-collected rows for {len(inputs):,} inputs..."
    )

    for index, input_text in enumerate(inputs, start=1):
        valid_khmers = valid_outputs.get(input_text)

        if not valid_khmers:
            totals["missing_dataset_input"] += 1
            continue

        input_rows = rows_by_input[input_text]
        valid_indexes = [
            row_index
            for row_index, row in enumerate(input_rows)
            if row.get("khmer", "") in valid_khmers
        ]

        if not valid_indexes:
            totals["missing_correct"] += 1
            continue

        cutoff_index = max(valid_indexes)
        input_had_update = False

        for row_index, row in enumerate(input_rows[:cutoff_index + 1]):
            if not can_replace_label(row, overwrite_auto=overwrite_auto):
                totals["skipped"] += 1
                continue

            if row.get("khmer", "") in valid_khmers:
                row["label"] = "1"
                row["note"] = "auto_existing_dataset_match"
                totals["positive"] += 1
            else:
                row["label"] = "0"
                row["note"] = "auto_existing_above_or_between_dataset_match"
                totals["negative"] += 1

            totals["updated"] += 1
            input_had_update = True

        if input_had_update:
            totals["with_labels"] += 1

        if index % PROGRESS_EVERY == 0 or index == len(inputs):
            log_progress(
                f"  inputs: {index:,}/{len(inputs):,} "
                f"-> {totals['updated']:,} labels updated, "
                f"{totals['missing_correct']:,} inputs missing collected correct row"
            )

    if not dry_run:
        write_ordered_rows(output_file, rows)
        log_progress(f"Saved labels to existing rows in {output_file}")
    else:
        log_progress("Dry run only; no file was written.")

    return totals


def serialize_suggestion(input_text, suggestion, label, note):
    """Convert one suggestion into the shared ranking-training CSV schema."""
    return {
        "input": input_text,
        "khmer": suggestion["khmer"],
        "label": str(label),
        "category": get_category(suggestion["source"]),
        "source": suggestion["source"],
        "score": suggestion.get("score", ""),
        "ml_score": suggestion.get("ml_score", ""),
        "frequency": suggestion.get("frequency", ""),
        "rule_score": suggestion.get("rule_score", ""),
        "dataset_match_score": suggestion.get("dataset_match_score", ""),
        "dataset_similarity": suggestion.get("dataset_similarity", ""),
        "dataset_romanized": suggestion.get("dataset_romanized", ""),
        "dataset_frequency": suggestion.get("dataset_frequency", ""),
        "tokens": " ".join(suggestion.get("tokens", [])),
        "chunks": repr(suggestion.get("chunks", suggestion.get("compound_segments", ""))),
        "note": note,
    }


def make_auto_labeled_rows(
    input_text,
    valid_khmers,
    suggestions,
):
    """Label generated suggestions up to the lowest correct dataset match."""
    valid_indexes = [
        index
        for index, suggestion in enumerate(suggestions)
        if suggestion["khmer"] in valid_khmers
    ]

    if not valid_indexes:
        return [], {
            "missing_correct": 1,
            "positive": 0,
            "negative": 0,
        }

    cutoff_index = max(valid_indexes)
    rows = []
    positive_count = 0
    negative_count = 0

    for index, suggestion in enumerate(suggestions[:cutoff_index + 1]):
        if suggestion["khmer"] in valid_khmers:
            label = 1
            note = "auto_dataset_match"
            positive_count += 1
        else:
            label = 0
            note = "auto_above_or_between_dataset_match"
            negative_count += 1

        rows.append(serialize_suggestion(input_text, suggestion, label, note))

    return rows, {
        "missing_correct": 0,
        "positive": positive_count,
        "negative": negative_count,
    }


def merge_rows(existing_rows, new_rows, overwrite_auto=False):
    """Merge generated auto-label rows while protecting human labels."""
    added_count = 0
    updated_count = 0
    skipped_count = 0

    for row in new_rows:
        key = (row["input"], row["khmer"])
        existing = existing_rows.get(key)

        if existing is None:
            existing_rows[key] = row
            added_count += 1
            continue

        existing_label = existing.get("label", "").strip()
        existing_note = existing.get("note", "")

        if existing_label in {"0", "1"} and not (
            overwrite_auto and existing_note.startswith("auto_")
        ):
            skipped_count += 1
            continue

        existing_rows[key] = row
        updated_count += 1

    return {
        "added": added_count,
        "updated": updated_count,
        "skipped": skipped_count,
    }


def write_rows(output_file, rows_by_key):
    """Write generated auto-label rows sorted by input/label/Khmer."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    rows = sorted(
        rows_by_key.values(),
        key=lambda row: (
            row["input"],
            row.get("label", ""),
            row["khmer"],
        ),
    )

    with open(output_file, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def auto_label_training_examples(
    output_file=RANKING_TRAINING_EXAMPLES_FILE,
    max_inputs=None,
    selected_inputs=None,
    suggestion_limit=DEFAULT_SUGGESTION_LIMIT,
    enable_fuzzy=False,
    enable_compound=False,
    overwrite_auto=False,
    dry_run=False,
):
    """Generate suggestions from dataset inputs, then auto-label correct matches."""
    dataset = load_dataset()
    rules = load_mapping_rules()
    valid_outputs = group_valid_outputs(dataset)
    if selected_inputs:
        inputs = [
            normalize_input(input_text)
            for input_text in selected_inputs
            if normalize_input(input_text) in valid_outputs
        ]
        missing_inputs = sorted({
            normalize_input(input_text)
            for input_text in selected_inputs
            if normalize_input(input_text) not in valid_outputs
        })

        if missing_inputs:
            log_progress(
                "Skipped inputs with no dataset match: "
                + ", ".join(missing_inputs[:20])
            )
    else:
        inputs = sorted(valid_outputs)

    if max_inputs is not None:
        inputs = inputs[:max_inputs]

    existing_rows = load_existing_rows(output_file)
    totals = {
        "inputs": len(inputs),
        "with_labels": 0,
        "missing_correct": 0,
        "positive": 0,
        "negative": 0,
        "generated_rows": 0,
        "added": 0,
        "updated": 0,
        "skipped": 0,
    }

    log_progress(
        f"Auto-labeling {len(inputs):,} romanized inputs "
        f"(limit {suggestion_limit}, fuzzy={enable_fuzzy}, compound={enable_compound})..."
    )

    for index, input_text in enumerate(inputs, start=1):
        suggestions = get_suggestions(
            input_text,
            dataset=dataset,
            rules=rules,
            use_ml=False,
            enable_fuzzy=enable_fuzzy,
            enable_compound=enable_compound,
            limit=suggestion_limit,
            min_rule_score=None,
            hide_manual_bad=False,
        )
        new_rows, stats = make_auto_labeled_rows(
            input_text,
            valid_outputs[input_text],
            suggestions,
        )

        totals["missing_correct"] += stats["missing_correct"]
        totals["positive"] += stats["positive"]
        totals["negative"] += stats["negative"]
        totals["generated_rows"] += len(new_rows)

        if new_rows:
            totals["with_labels"] += 1

        merge_stats = merge_rows(
            existing_rows,
            new_rows,
            overwrite_auto=overwrite_auto,
        )

        for key, value in merge_stats.items():
            totals[key] += value

        if index % PROGRESS_EVERY == 0 or index == len(inputs):
            log_progress(
                f"  inputs: {index:,}/{len(inputs):,} "
                f"-> +{totals['added']:,} added, "
                f"{totals['updated']:,} updated, "
                f"{totals['missing_correct']:,} missing correct"
            )

    if not dry_run:
        write_rows(output_file, existing_rows)
        log_progress(f"Saved auto-labeled rows to {output_file}")
    else:
        log_progress("Dry run only; no file was written.")

    return totals


def main():
    """CLI entry point used by scripts/auto_label_training_examples.py."""
    parser = argparse.ArgumentParser(
        description="Auto-label ranking examples using dataset matches as the answer key.",
    )
    parser.add_argument("--output", default=RANKING_TRAINING_EXAMPLES_FILE)
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Optional specific romanized inputs from the existing training CSV to auto-label.",
    )
    parser.add_argument("--max-inputs", type=int, default=None)
    parser.add_argument("--limit", type=int, default=DEFAULT_SUGGESTION_LIMIT)
    parser.add_argument("--include-fuzzy", action="store_true")
    parser.add_argument("--include-compound", action="store_true")
    parser.add_argument(
        "--from-dataset",
        action="store_true",
        help=(
            "Generate auto-label rows from all_words.csv. By default, only existing "
            "UI-collected rows in ranking_training_examples.csv are labeled."
        ),
    )
    parser.add_argument(
        "--overwrite-auto",
        action="store_true",
        help="Replace previous auto_* labels, but never human labels.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.from_dataset:
        totals = auto_label_training_examples(
            output_file=args.output,
            max_inputs=args.max_inputs,
            selected_inputs=args.inputs,
            suggestion_limit=args.limit,
            enable_fuzzy=args.include_fuzzy,
            enable_compound=args.include_compound,
            overwrite_auto=args.overwrite_auto,
            dry_run=args.dry_run,
        )
    else:
        totals = auto_label_existing_training_examples(
            output_file=args.output,
            max_inputs=args.max_inputs,
            selected_inputs=args.inputs,
            overwrite_auto=args.overwrite_auto,
            dry_run=args.dry_run,
        )

    log_progress(
        "Summary: "
        f"{totals['with_labels']:,}/{totals['inputs']:,} inputs labeled, "
        f"{totals['positive']:,} positives, "
        f"{totals['negative']:,} negatives, "
        f"{totals['added']:,} added, "
        f"{totals['updated']:,} updated, "
        f"{totals['skipped']:,} skipped, "
        f"{totals.get('missing_dataset_input', 0):,} missing dataset input, "
        f"{totals.get('missing_correct', 0):,} missing collected correct row."
    )


if __name__ == "__main__":
    main()
