import json

MAPPING_RULES_FILE = "data/mapping_rules.json"


def load_mapping_rules():
    with open(MAPPING_RULES_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def get_all_patterns(rules):
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
