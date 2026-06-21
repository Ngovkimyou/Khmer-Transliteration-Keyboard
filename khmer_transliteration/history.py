import csv
from datetime import datetime, timezone

from khmer_transliteration.normalizer import normalize_input
from khmer_transliteration.paths import (
    USER_SELECTION_HISTORY_FILE,
    WORD_PAIR_FREQUENCY_FILE,
)

SELECTION_FIELDNAMES = ["input", "khmer", "count", "last_selected"]
PAIR_FIELDNAMES = ["previous_khmer", "current_khmer", "count", "last_selected"]


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_counter_rows(path, fieldnames):
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = []

        for row in reader:
            rows.append({
                fieldname: row.get(fieldname, "")
                for fieldname in fieldnames
            })

        return rows


def write_counter_rows(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def increment_row(rows, key_fields, key_values):
    now = utc_timestamp()

    for row in rows:
        if all(row.get(field) == value for field, value in zip(key_fields, key_values)):
            row["count"] = str(int(row.get("count") or 0) + 1)
            row["last_selected"] = now
            return row

    row = {
        field: value
        for field, value in zip(key_fields, key_values)
    }
    row["count"] = "1"
    row["last_selected"] = now
    rows.append(row)
    return row


def record_selection(user_input, khmer, previous_khmer=""):
    normalized = normalize_input(user_input)

    if not normalized or not khmer:
        return {
            "selection_count": 0,
            "pair_count": 0,
        }

    selection_rows = read_counter_rows(
        USER_SELECTION_HISTORY_FILE,
        SELECTION_FIELDNAMES,
    )
    selection_row = increment_row(
        selection_rows,
        ["input", "khmer"],
        [normalized, khmer],
    )
    write_counter_rows(
        USER_SELECTION_HISTORY_FILE,
        SELECTION_FIELDNAMES,
        selection_rows,
    )

    pair_count = 0

    if previous_khmer:
        pair_rows = read_counter_rows(
            WORD_PAIR_FREQUENCY_FILE,
            PAIR_FIELDNAMES,
        )
        pair_row = increment_row(
            pair_rows,
            ["previous_khmer", "current_khmer"],
            [previous_khmer, khmer],
        )
        write_counter_rows(
            WORD_PAIR_FREQUENCY_FILE,
            PAIR_FIELDNAMES,
            pair_rows,
        )
        pair_count = int(pair_row["count"])

    return {
        "selection_count": int(selection_row["count"]),
        "pair_count": pair_count,
    }


def load_selection_history(path=USER_SELECTION_HISTORY_FILE):
    history = {}

    for row in read_counter_rows(path, SELECTION_FIELDNAMES):
        count = int(row.get("count") or 0)
        history[(row["input"], row["khmer"])] = count

    return history


def load_word_pair_frequencies(path=WORD_PAIR_FREQUENCY_FILE):
    pairs = {}

    for row in read_counter_rows(path, PAIR_FIELDNAMES):
        count = int(row.get("count") or 0)
        pairs[(row["previous_khmer"], row["current_khmer"])] = count

    return pairs
