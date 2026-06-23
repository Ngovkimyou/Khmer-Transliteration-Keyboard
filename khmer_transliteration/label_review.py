"""Promote reviewed UI label rows into the ranking-training CSV."""

import argparse
import csv
import os

from khmer_transliteration.collection import FIELDNAMES, ensure_output_schema
from khmer_transliteration.paths import LABEL_DATA_FILE, RANKING_TRAINING_EXAMPLES_FILE


def read_rows(csv_file):
    """Return review/training rows from a CSV file, or an empty list."""
    if not os.path.exists(csv_file):
        return []

    ensure_output_schema(csv_file)

    with open(csv_file, "r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_rows(csv_file, rows):
    """Write rows with the shared manual-label schema."""
    os.makedirs(os.path.dirname(csv_file), exist_ok=True)

    with open(csv_file, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def clear_review_file(review_file):
    """Reset label_data.csv so the next UI collection starts fresh."""
    write_rows(review_file, [])


def promoted_label(row):
    """Turn the review inbox label into a training/UI decision."""
    label = row.get("label", "").strip()

    if label in {"0", "1"}:
        return label

    return None


def promote_label_data(
    review_file=LABEL_DATA_FILE,
    training_file=RANKING_TRAINING_EXAMPLES_FILE,
    clear_review=True,
):
    """Move reviewed label_data rows into ranking_training_examples."""
    review_rows = read_rows(review_file)
    training_rows = read_rows(training_file)
    training_by_key = {
        (row.get("input", ""), row.get("khmer", "")): row
        for row in training_rows
    }
    added = 0
    updated = 0
    positives = 0
    negatives = 0
    skipped_blank = 0

    for review_row in review_rows:
        key = (review_row.get("input", ""), review_row.get("khmer", ""))

        if not key[0] or not key[1]:
            continue

        label = promoted_label(review_row)

        if label is None:
            skipped_blank += 1
            continue

        if label == "1":
            positives += 1
        else:
            negatives += 1

        existing = training_by_key.get(key)

        promoted_row = {
            fieldname: review_row.get(fieldname, "")
            for fieldname in FIELDNAMES
        }
        promoted_row["label"] = label

        if existing:
            existing.update(promoted_row)
            updated += 1
        else:
            training_rows.append(promoted_row)
            training_by_key[key] = promoted_row
            added += 1

    write_rows(training_file, training_rows)

    if clear_review:
        clear_review_file(review_file)

    return {
        "reviewed": len(review_rows),
        "added": added,
        "updated": updated,
        "positives": positives,
        "negatives": negatives,
        "skipped_blank": skipped_blank,
        "cleared": clear_review,
        "review_file": str(review_file),
        "training_file": str(training_file),
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Promote data/label_data.csv into data/ranking_training_examples.csv. "
            "Label 1 stays good; label 0 becomes hidden; blank rows are ignored."
        ),
    )
    parser.add_argument("--review-file", default=LABEL_DATA_FILE)
    parser.add_argument("--training-file", default=RANKING_TRAINING_EXAMPLES_FILE)
    parser.add_argument(
        "--keep-review",
        action="store_true",
        help="Do not clear label_data.csv after promotion.",
    )
    args = parser.parse_args()

    summary = promote_label_data(
        review_file=args.review_file,
        training_file=args.training_file,
        clear_review=not args.keep_review,
    )

    print(
        "Promoted {reviewed} review rows: {positives} label 1, "
        "{negatives} label 0, {skipped_blank} blank skipped, "
        "{added} added, {updated} updated.".format(**summary)
    )

    if summary["cleared"]:
        print(f"Cleared {summary['review_file']}")

    print(f"Training labels saved to {summary['training_file']}")


if __name__ == "__main__":
    main()
