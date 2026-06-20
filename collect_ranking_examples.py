import argparse
import csv
import os

from data.load_mapping_rules import load_mapping_rules
from dictionary_lookup import load_dataset
from suggestion_engine import get_suggestions


OUTPUT_FILE = "data/ranking_training_examples.csv"
FIELDNAMES = [
    "input",
    "khmer",
    "label",
    "category",
    "source",
    "score",
    "ml_score",
    "frequency",
    "rule_score",
    "dataset_match_score",
    "dataset_similarity",
    "dataset_romanized",
    "dataset_frequency",
    "tokens",
    "chunks",
    "note",
]


# Group suggestions into human-friendly review categories.
def get_category(source):
    if source == "dictionary_exact":
        return "exact_dictionary"

    if source == "dictionary_completion":
        return "dictionary_completion"

    if source.startswith("direct_"):
        return "direct_token"

    if source.startswith("rule_"):
        return "rule_generated"

    return "other"


# Read existing input/Khmer pairs so repeated collection does not duplicate rows.
def load_existing_keys(output_file):
    keys = set()

    if not os.path.exists(output_file):
        return keys

    with open(output_file, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            keys.add((row["input"], row["khmer"]))

    return keys


def ensure_output_schema(output_file):
    if not os.path.exists(output_file):
        return

    with open(output_file, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        existing_fieldnames = reader.fieldnames or []

        if existing_fieldnames == FIELDNAMES:
            return

        rows = list(reader)

    with open(output_file, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()

        for row in rows:
            writer.writerow({
                fieldname: row.get(fieldname, "")
                for fieldname in FIELDNAMES
            })


def append_examples(inputs, output_file=OUTPUT_FILE, limit=None, allow_vowels=False):
    dataset = load_dataset()
    rules = load_mapping_rules()
    ensure_output_schema(output_file)
    existing_keys = load_existing_keys(output_file)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    file_exists = os.path.exists(output_file)
    added_count = 0

    with open(output_file, "a", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)

        if not file_exists:
            writer.writeheader()

        for user_input in inputs:
            suggestions = get_suggestions(
                user_input,
                dataset=dataset,
                rules=rules,
                use_ml=False,
                allow_vowels=allow_vowels,
                limit=limit,
                min_rule_score=None,
            )

            for suggestion in suggestions:
                key = (user_input, suggestion["khmer"])

                if key in existing_keys:
                    continue

                writer.writerow({
                    "input": user_input,
                    "khmer": suggestion["khmer"],
                    "label": "",
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
                    "chunks": repr(suggestion.get("chunks", "")),
                    "note": "",
                })
                existing_keys.add(key)
                added_count += 1

    return added_count


def main():
    parser = argparse.ArgumentParser(
        description="Collect generated suggestions into a manual ranking-label CSV.",
    )
    parser.add_argument("inputs", nargs="*", help="Romanized inputs to collect.")
    parser.add_argument("--output", default=OUTPUT_FILE, help="Output CSV path.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Suggestions per input. Use 0 for all generated suggestions.",
    )
    parser.add_argument(
        "--allow-vowels",
        action="store_true",
        help="Include dependent vowel direct-token suggestions.",
    )
    args = parser.parse_args()
    inputs = args.inputs

    if not inputs:
        print("Type romanized words. Press Enter on an empty line to finish.")

        while True:
            user_input = input("Input: ").strip()

            if not user_input:
                break

            inputs.append(user_input)

    if not inputs:
        print("No inputs provided.")
        return

    added_count = append_examples(
        inputs,
        output_file=args.output,
        limit=args.limit or None,
        allow_vowels=args.allow_vowels,
    )

    print(f"Added {added_count} rows to {args.output}")


if __name__ == "__main__":
    main()
