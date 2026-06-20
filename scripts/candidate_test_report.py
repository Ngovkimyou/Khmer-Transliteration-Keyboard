from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from khmer_transliteration.candidate_generator import (
    tokenize_all,
    generate_candidates_from_tokens,
)
from khmer_transliteration.candidate_generator import generate_ranked_candidates
from khmer_transliteration.normalizer import normalize_input
from khmer_transliteration.mapping_rules import load_mapping_rules, get_all_patterns


from khmer_transliteration.paths import CANDIDATE_TEST_REPORT_FILE

OUTPUT_FILE = CANDIDATE_TEST_REPORT_FILE


def main():
    rules = load_mapping_rules()
    patterns = get_all_patterns(rules)

    examples = [
        "somtos",
        "bea",
        "bear",
        "bum",
        "bur",
        "ba",
        "bam",
        "pam",
        "pi",
        "pu",
        "pur",
        "per",
        "pea",
        "lery",
        "neang",
        "kom",
        "mj",
        "kr",
        "kok",
        "ngong",
        "chom",
    ]

    html = """
<!DOCTYPE html>
<html lang="km">
<head>
    <meta charset="UTF-8">
    <title>Candidate Generator Test</title>
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
        .tokens {
            color: #555;
            margin-top: 12px;
        }
        .candidate {
            display: inline-block;
            font-size: 28px;
            padding: 8px 12px;
            margin: 6px;
            border-radius: 6px;
            background: #eef3ff;
            border: 1px solid #ccd8ff;
        }
        .meta {
            font-size: 13px;
            color: #666;
        }
        .ranked {
            background: #f4fff4;
            border: 1px solid #c8e6c9;
            border-radius: 6px;
            padding: 10px;
            margin-top: 12px;
        }
    </style>
</head>
<body>
<h1>Candidate Generator Test</h1>
"""

    for example in examples:
        normalized = normalize_input(example)
        tokenizations = tokenize_all(normalized, patterns)
        ranked_candidates = generate_ranked_candidates(example, rules)

        html += f"""
<div class="case">
    <div class="input">Input: {example}</div>
    <div>Normalized: <b>{normalized}</b></div>
    <div class="ranked">
        <b>Ranked candidates</b>
"""

        if not ranked_candidates:
            html += """
        <div class="meta">No ranked candidates generated.</div>
"""
        else:
            for candidate in ranked_candidates[:10]:
                html += f"""
        <div class="candidate">{candidate["khmer"]}</div>
        <div class="meta">
            source: {candidate["source"]},
            final score: {candidate["final_score"]},
            rule score: {candidate["rule_score"]},
            tokens: {candidate["tokens"]}
        </div>
"""

        html += """
    </div>
"""

        for tokens in tokenizations[:10]:
            candidates = generate_candidates_from_tokens(tokens, rules)

            html += f"""
    <div class="tokens">Tokens: {tokens}</div>
"""

            if not candidates:
                html += """
    <div class="meta">No candidates generated for this tokenization.</div>
"""
                continue

            for candidate in candidates[:10]:
                html += f"""
    <div class="candidate">{candidate["khmer"]}</div>
    <div class="meta">
        source: {candidate["source"]},
        score: {candidate["rule_score"]}
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
