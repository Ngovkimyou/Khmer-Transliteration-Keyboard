import csv

input_file = "data/original_data/4-kh-en.txt"
output_file = "data/4-kh-en.csv"

with open(input_file, "r", encoding="utf-8") as txt_file, \
     open(output_file, "w", encoding="utf-8", newline="") as csv_file:

    writer = csv.writer(csv_file)
    writer.writerow(["romanized", "khmer", "frequency"])

    for line in txt_file:
        line = line.strip()

        if not line:
            continue

        khmer, romanized_list = line.split(":", 1)

        khmer = khmer.strip()
        romanized_words = romanized_list.split(",")

        for romanized in romanized_words:
            romanized = romanized.strip()

            if romanized:
                writer.writerow([romanized, khmer, 1])