import pandas as pd

files = [
    "data/1-kh-en.csv",
    "data/2-kh-en.csv",
    "data/3-kh-en.csv",
    "data/4-kh-en.csv",
]

df = pd.concat([pd.read_csv(file) for file in files], ignore_index=True)

clean_df = (
    df.groupby(["romanized", "khmer"], as_index=False)
      .agg({"frequency": "sum"})
)

clean_df.to_csv("data/all_words.csv", index=False, encoding="utf-8-sig")

print("Before removing duplicates:", len(df))
print("After removing duplicates:", len(clean_df))
print("Removed duplicates:", len(df) - len(clean_df))
print("Saved clean dataset to data/all_words.csv")