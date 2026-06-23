"""Load transliteration mapping rules and expose token patterns for parsing."""

import json

from khmer_transliteration.paths import MAPPING_RULES_FILE


def load_mapping_rules():
    """Read data/mapping_rules.json once for generator/suggestion callers."""
    with open(MAPPING_RULES_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def get_all_patterns(rules):
    """Collect every romanized token and sort longest-first for tokenization."""
    patterns = []

    for group in [
        "special_patterns",
        "consonants",
        "vowels",
        "independent_vowels",
        "vowel_carriers",
        "triisap_vowel_carriers",
        "vowels_by_consonant_class",
        "muusikatoan_consonants",
        "triisap_consonants",
    ]:
        patterns.extend(rules.get(group, {}).keys())

    return sorted(set(patterns), key=len, reverse=True)
