import pandas as pd
from pathlib import Path

DATASET_FILE = Path("data/all_words.csv")
CUSTOM_WORDS_FILE = Path("data/custom_words.csv")

df = pd.read_csv(DATASET_FILE)

df["romanized"] = df["romanized"].astype(str).str.strip()
df["khmer"] = df["khmer"].astype(str).str.strip()
df["frequency"] = df["frequency"].astype(int)

before_custom_sync = len(df)

if CUSTOM_WORDS_FILE.exists():
    custom_df = pd.read_csv(CUSTOM_WORDS_FILE)
    custom_df["romanized"] = custom_df["romanized"].astype(str).str.strip()
    custom_df["khmer"] = custom_df["khmer"].astype(str).str.strip()
    custom_df["frequency"] = custom_df["frequency"].astype(int)

    custom_pairs = set(zip(custom_df["romanized"], custom_df["khmer"]))
    df = df[
        ~df.apply(lambda row: (row["romanized"], row["khmer"]) in custom_pairs, axis=1)
    ]
    df = pd.concat([df, custom_df], ignore_index=True)

clean_df = (
    df.groupby(["romanized", "khmer"], as_index=False)
      .agg({"frequency": "sum"})
)

clean_df.to_csv(DATASET_FILE, index=False, encoding="utf-8-sig")

print("Before custom sync:", before_custom_sync)
print("After custom sync:", len(df))
print("Custom words synced from:", CUSTOM_WORDS_FILE)
print("Before removing duplicates:", len(df))
print("After removing duplicates:", len(clean_df))
print("Removed duplicates:", len(df) - len(clean_df))
print(f"Saved clean dataset to {DATASET_FILE}")
