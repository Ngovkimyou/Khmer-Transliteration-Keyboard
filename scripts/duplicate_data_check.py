from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import csv
from collections import defaultdict

from khmer_transliteration.paths import (
    ALL_WORDS_FILE,
    CUSTOM_WORDS_FILE as CUSTOM_WORDS_PATH,
)

DATASET_FILE = ALL_WORDS_FILE
CUSTOM_WORDS_FILE = CUSTOM_WORDS_PATH


def normalize_row(row):
    return {
        "romanized": row["romanized"].strip(),
        "khmer": row["khmer"].strip(),
        "frequency": int(row["frequency"]),
    }


def read_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return [normalize_row(row) for row in reader]


def sync_custom_words(rows):
    if not CUSTOM_WORDS_FILE.exists():
        return rows

    custom_rows = read_rows(CUSTOM_WORDS_FILE)
    custom_pairs = {
        (row["romanized"], row["khmer"])
        for row in custom_rows
    }

    base_rows = [
        row for row in rows
        if (row["romanized"], row["khmer"]) not in custom_pairs
    ]

    return base_rows + custom_rows


def remove_duplicate_pairs(rows):
    frequencies = defaultdict(int)

    for row in rows:
        key = (row["romanized"], row["khmer"])
        frequencies[key] += row["frequency"]

    return [
        {
            "romanized": romanized,
            "khmer": khmer,
            "frequency": frequency,
        }
        for (romanized, khmer), frequency in sorted(frequencies.items())
    ]


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["romanized", "khmer", "frequency"])
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows = read_rows(DATASET_FILE)
    before_custom_sync = len(rows)
    rows = sync_custom_words(rows)
    clean_rows = remove_duplicate_pairs(rows)

    write_rows(DATASET_FILE, clean_rows)

    print("Before custom sync:", before_custom_sync)
    print("After custom sync:", len(rows))
    print("Custom words synced from:", CUSTOM_WORDS_FILE)
    print("Before removing duplicates:", len(rows))
    print("After removing duplicates:", len(clean_rows))
    print("Removed duplicates:", len(rows) - len(clean_rows))
    print(f"Saved clean dataset to {DATASET_FILE}")


if __name__ == "__main__":
    main()
