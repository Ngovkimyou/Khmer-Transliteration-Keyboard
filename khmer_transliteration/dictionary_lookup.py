import csv
from khmer_transliteration.normalizer import normalize_input
from rapidfuzz import process, fuzz

from khmer_transliteration.paths import ALL_WORDS_FILE

DATASET_FILE = ALL_WORDS_FILE

def load_dataset():
    rows = []

    with open(DATASET_FILE, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            rows.append({
                "romanized": row["romanized"],
                "khmer": row["khmer"],
                "frequency": int(row["frequency"]),
            })

    return rows

def exact_lookup(user_input, dataset):
    normalized = normalize_input(user_input)

    matches = []

    for row in dataset:
        if row["romanized"] == normalized:
            matches.append(row)

    matches.sort(key=lambda row: row["frequency"], reverse=True)

    return matches

# Example usage:
# if __name__ == "__main__":
#     dataset = load_dataset()

#     while True:
#         user_input = input("Type romanized Khmer: ")

#         if user_input == "exit":
#             break

#         matches = exact_lookup(user_input, dataset)

#         if not matches:
#             print("No exact match found")
#         else:
#             for match in matches[:10]:
#                 print(match["khmer"], match["frequency"])

def get_romanized_words(dataset):
    return list(set(row["romanized"] for row in dataset))

def fuzzy_lookup(user_input, dataset, limit=5, min_score=80):
    normalized = normalize_input(user_input)
    romanized_words = get_romanized_words(dataset)

    fuzzy_matches = process.extract(
        normalized,
        romanized_words,
        scorer=fuzz.ratio,
        limit=limit
    )

    results = []

    for romanized_word, score, _ in fuzzy_matches:
        if score < min_score:
            continue

        matches = exact_lookup(romanized_word, dataset)

        for match in matches:
            result = match.copy()
            result["fuzzy_score"] = score
            results.append(result)

    results.sort(
        key=lambda row: (row["fuzzy_score"], row["frequency"]),
        reverse=True
    )

    return results


