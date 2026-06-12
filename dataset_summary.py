import csv
import re
from collections import Counter, defaultdict


INPUT_FILE = "data/all_words.csv"
OUTPUT_FILE = "data/dataset_summary.txt"


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def is_punctuation_only(value):
    return bool(value) and not re.search(r"[A-Za-z0-9]", value)


with open(INPUT_FILE, "r", encoding="utf-8-sig", newline="") as csv_file:
    reader = csv.DictReader(csv_file)
    rows = list(reader)


romanized_values = [row["romanized"].strip() for row in rows]
khmer_values = [row["khmer"].strip() for row in rows]
frequencies = [to_int(row.get("frequency")) for row in rows]

pair_counts = Counter((row["romanized"].strip(), row["khmer"].strip()) for row in rows)
duplicate_pairs = sum(count - 1 for count in pair_counts.values() if count > 1)

khmer_by_romanized = defaultdict(set)
romanized_by_khmer = defaultdict(set)

for romanized, khmer in zip(romanized_values, khmer_values):
    khmer_by_romanized[romanized].add(khmer)
    romanized_by_khmer[khmer].add(romanized)

ambiguous_inputs = {
    romanized: khmer_set
    for romanized, khmer_set in khmer_by_romanized.items()
    if len(khmer_set) > 1
}

khmer_with_variants = {
    khmer: romanized_set
    for khmer, romanized_set in romanized_by_khmer.items()
    if len(romanized_set) > 1
}

punctuation_only = [value for value in romanized_values if is_punctuation_only(value)]
uppercase_inputs = [value for value in romanized_values if value != value.lower()]
empty_romanized = [value for value in romanized_values if not value]
empty_khmer = [value for value in khmer_values if not value]

top_frequencies = sorted(
    rows,
    key=lambda row: to_int(row.get("frequency")),
    reverse=True,
)[:10]

report_lines = [
    "Khmer Transliteration Dataset Summary",
    "======================================",
    "",
    f"Source file: {INPUT_FILE}",
    "",
    f"Rows: {len(rows):,}",
    f"Unique romanized inputs: {len(set(romanized_values)):,}",
    f"Unique Khmer words: {len(set(khmer_values)):,}",
    f"Total frequency count: {sum(frequencies):,}",
    f"Exact duplicate romanized+Khmer pairs: {duplicate_pairs:,}",
    "",
    "Data Quality Checks",
    "-------------------",
    f"Empty romanized values: {len(empty_romanized):,}",
    f"Empty Khmer values: {len(empty_khmer):,}",
    f"Punctuation-only romanized values: {len(punctuation_only):,}",
    f"Romanized values containing uppercase letters: {len(uppercase_inputs):,}",
    "",
    "Ambiguity Checks",
    "----------------",
    f"Romanized inputs with multiple Khmer candidates: {len(ambiguous_inputs):,}",
    f"Khmer words with multiple romanized spellings: {len(khmer_with_variants):,}",
    "",
    "Top Frequency Rows",
    "------------------",
]

for row in top_frequencies:
    report_lines.append(
        f"{row['romanized']} -> {row['khmer']} (frequency: {row['frequency']})"
    )

with open(OUTPUT_FILE, "w", encoding="utf-8") as report_file:
    report_file.write("\n".join(report_lines) + "\n")

print(f"Saved dataset summary to {OUTPUT_FILE}")
