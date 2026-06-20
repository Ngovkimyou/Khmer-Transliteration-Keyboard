from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from khmer_transliteration.mapping_rules import load_mapping_rules
from khmer_transliteration.dictionary_lookup import load_dataset
from khmer_transliteration.normalizer import normalize_input
from khmer_transliteration.suggestion_engine import get_suggestions, load_ranking_model


from khmer_transliteration.paths import SUGGESTION_TEST_REPORT_FILE

OUTPUT_FILE = SUGGESTION_TEST_REPORT_FILE


def main():
    dataset = load_dataset()
    rules = load_mapping_rules()
    ranking_model = load_ranking_model()

    examples = [
        "k",
        "kh",
        "a",
        "aa",
        "u",
        "sala",
        "mong",
        "vav",
        "veav",
        "kra",
        "krom",
        "stra",
        "slabpra",
        "mj",
        "kom",
        "jong",
        "neang",
        "khuk",
        "chuch",
    ]

    html = """
<!DOCTYPE html>
<html lang="km">
<head>
    <meta charset="UTF-8">
    <title>Suggestion Engine Test</title>
    <style>
        body {
            font-family: "Khmer OS", "Noto Sans Khmer", Arial, sans-serif;
            padding: 24px;
            background: #f7f7f7;
        }
        .case {
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
        }
        .input {
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 8px;
        }
        .suggestion {
            display: inline-block;
            font-size: 28px;
            padding: 8px 12px;
            margin: 6px;
            border-radius: 6px;
            background: #f4fff4;
            border: 1px solid #c8e6c9;
        }
        .meta {
            font-size: 13px;
            color: #666;
            margin-bottom: 6px;
        }
    </style>
</head>
<body>
<h1>Suggestion Engine Test</h1>
"""

    for example in examples:
        normalized = normalize_input(example)
        suggestions = get_suggestions(
            example,
            dataset,
            rules,
            ranking_model=ranking_model,
            allow_vowels=True,
        )

        html += f"""
<div class="case">
    <div class="input">Input: {example}</div>
    <div>Normalized: <b>{normalized}</b></div>
"""

        if not suggestions:
            html += """
    <div class="meta">No suggestions generated.</div>
"""
        else:
            for index, suggestion in enumerate(suggestions, start=1):
                html += f"""
    <div class="suggestion">{index}. {suggestion["khmer"]}</div>
    <div class="meta">
        source: {suggestion["source"]},
        priority: {suggestion["source_priority"]},
        manual score: {round(suggestion["score"], 4)},
        rank score: {suggestion.get("rank_score", "")},
        rank reason: {suggestion.get("rank_reason", "")}
"""

                if "frequency" in suggestion:
                    html += f""",
        frequency: {suggestion["frequency"]}
"""

                if suggestion.get("dataset_match_score"):
                    html += f""",
        dataset score: {suggestion["dataset_match_score"]},
        dataset similarity: {suggestion.get("dataset_similarity", "")},
        dataset romanized: {suggestion.get("dataset_romanized", "")}
"""

                if "ml_score" in suggestion:
                    html += f""",
        ML score: {suggestion["ml_score"]}
"""

                if "manual_label" in suggestion:
                    html += f""",
        manual label: {suggestion["manual_label"]}
"""

                if "fuzzy_score" in suggestion:
                    html += f""",
        fuzzy score: {suggestion["fuzzy_score"]}
"""

                if "tokens" in suggestion:
                    html += f""",
        tokens: {suggestion["tokens"]}
"""

                html += """
    </div>
"""

        html += "</div>"

    html += """
</body>
</html>
"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        file.write(html)

    print(f"Saved report to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
