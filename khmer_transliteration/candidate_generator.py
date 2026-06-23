"""Rule-based romanized Khmer candidate generation.

This module turns normalized roman input into Khmer script candidates using
mapping_rules.json. It handles tokenization, syllable patterns, subscript
clusters, independent/vowel-carrier forms, sequence composition, and scoring.
"""

from khmer_transliteration.normalizer import normalize_input
from khmer_transliteration.mapping_rules import load_mapping_rules, get_all_patterns


# Safety caps keep ambiguous inputs from exploding into too many combinations.
MAX_SEQUENCE_PARTITIONS = 120
MAX_SEQUENCE_COMBINATIONS = 120

# Small scoring constants used to prefer natural Khmer-looking structures.
VOWEL_CARRIER_AFTER_CLOSED_CHUNK_PENALTY = 0.10
SEQUENCE_CVC_CHUNK_BONUS = 0.01
STRUCTURAL_SEQUENCE_BONUS = 0.12
COMPOUND_VOWEL_BONUS = 0.08
BANTOC_SIGN = "់"
BANTOC_FINAL_CONSONANTS = {"ក", "ង", "ច", "ញ", "ត", "ន", "ប", "ល", "ស"}
COMPOUND_VOWEL_BONUS_TOKENS = {
    "am",
    "om",
    "um",
    "orm",
    "av",
    "ov",
    "os",
    "ous",
    "us",
    "as",
    "aes",
    "es",
    "is",
}
SPLIT_KNOWN_TOKEN_PENALTY = 0.22

VOWEL_CARRIER_SOURCES = {
    "rule_vowel_carrier",
    "rule_triisap_vowel_carrier",
    "rule_independent_vowel",
}
CLOSED_SYLLABLE_SOURCES = {
    "rule_cvc",
    "rule_cvc_bantoc",
    "rule_independent_vowel_final",
    "rule_ccvc_subscript",
    "rule_cccvc_subscript",
    "rule_inherent_vowel",
    "rule_or_carrier_final",
}
STRUCTURAL_SEQUENCE_SOURCES = {
    "rule_cv",
    "rule_cvc",
    "rule_cvc_bantoc",
    "rule_independent_vowel_final",
    "rule_cc_plain",
    "rule_cc_subscript",
    "rule_ccv_subscript",
    "rule_ccvc_subscript",
    "rule_cccv_subscript",
    "rule_cccvc_subscript",
    "rule_cccc_subscript",
    "rule_inherent_vowel",
}
VOWEL_CARRIER_PREFIXES = ("អ", "អ៊")


def is_vowel_carrier_like_chunk(candidate):
    khmer = candidate.get("khmer", "")
    return khmer.startswith(VOWEL_CARRIER_PREFIXES)


def is_independent_vowel_chunk(candidate):
    return candidate.get("source") == "rule_independent_vowel"

# Build one tokenization by always taking the longest matching Roman pattern first.
def tokenize_longest_first(text, patterns):
    tokens = []
    index = 0

    while index < len(text):
        matched = None

        for pattern in patterns:
            if text.startswith(pattern, index):
                matched = pattern
                break

        if matched:
            tokens.append(matched)
            index += len(matched)
        else:
            tokens.append(text[index])
            index += 1

    return tokens

# Build multiple possible tokenizations so ambiguous input can be tested both ways.
def tokenize_all(text, patterns, max_results=20):
    results = []

    def backtrack(index, current_tokens):
        if len(results) >= max_results:
            return

        if index == len(text):
            results.append(current_tokens.copy())
            return

        matched_any = False

        for pattern in patterns:
            if text.startswith(pattern, index):
                matched_any = True
                current_tokens.append(pattern)
                backtrack(index + len(pattern), current_tokens)
                current_tokens.pop()

        if not matched_any:
            current_tokens.append(text[index])
            backtrack(index + 1, current_tokens)
            current_tokens.pop()

    backtrack(0, [])
    return results

# Give longer token matches a slightly higher score than many small tokens.
def tokenization_score(tokens):
    return sum(len(token) for token in tokens) - len(tokens) * 0.1

# Normalize tokenization score into a small bonus used for final ranking.
def normalized_tokenization_score(tokens, normalized_text):
    if not normalized_text:
        return 0

    return tokenization_score(tokens) / len(normalized_text)


# Reward tokenizations that keep compound vowel sounds as one token, such as am or av.
def compound_vowel_bonus(tokens, rules):
    for token in tokens:
        if token in COMPOUND_VOWEL_BONUS_TOKENS:
            return COMPOUND_VOWEL_BONUS

    return 0


# Penalize tokenizations that split a known longer consonant token, such as n+h for nh.
def split_known_token_penalty(tokens, rules):
    patterns = set()
    for group in [
        "consonants",
        "vowels",
        "independent_vowels",
        "vowels_by_consonant_class",
        "vowel_carriers",
        "triisap_vowel_carriers",
        "muusikatoan_consonants",
        "triisap_consonants",
        "cluster_base_aliases",
    ]:
        patterns.update(rules.get(group, {}).keys())

    penalty = 0

    for index in range(len(tokens) - 1):
        combined_token = tokens[index] + tokens[index + 1]

        if (
            combined_token == "av"
            and index + 2 < len(tokens)
            and is_vowel_token(tokens[index + 2], rules)
        ):
            continue

        if (
            index > 0
            and is_consonant_token(tokens[index - 1], rules)
            and is_vowel_token(tokens[index], rules)
            and is_consonant_token(tokens[index + 1], rules)
        ):
            continue

        if combined_token in patterns:
            penalty += SPLIT_KNOWN_TOKEN_PENALTY

    return penalty


# Return every direct Khmer option for one Roman token, including consonant variants.
def get_token_options(token, rules):
    options = []

    for value in rules.get("consonants", {}).get(token, []):
        options.append({
            "type": "consonant",
            "value": value,
            "source": "consonants",
        })

    for value in rules.get("muusikatoan_consonants", {}).get(token, []):
        options.append({
            "type": "consonant",
            "value": value,
            "source": "muusikatoan_consonants",
        })

    for value in rules.get("triisap_consonants", {}).get(token, []):
        options.append({
            "type": "consonant",
            "value": value,
            "source": "triisap_consonants",
        })

    for value in rules.get("vowels", {}).get(token, []):
        options.append({
            "type": "vowel",
            "value": value,
            "source": "vowels",
        })

    for value in rules.get("independent_vowels", {}).get(token, []):
        options.append({
            "type": "independent_vowel",
            "value": value,
            "source": "independent_vowels",
        })

    return options

# Find the first-series or second-series class for a Khmer consonant.
def get_consonant_class(consonant, rules):
    overrides = rules.get("consonant_class_overrides", {})

    if consonant in overrides:
        return overrides[consonant]

    if consonant in rules.get("consonant_classes", {}).get("first_series", []):
        return "first_series"

    if consonant in rules.get("consonant_classes", {}).get("second_series", []):
        return "second_series"

    return None

# Check whether a Khmer consonant form came from the muusikatoan Roman mapping.
def is_muusikatoan_consonant(consonant, rules):
    for consonants in rules.get("muusikatoan_consonants", {}).values():
        if consonant in consonants:
            return True

    return False


def is_triisap_consonant(consonant, rules):
    for consonants in rules.get("triisap_consonants", {}).values():
        if consonant in consonants:
            return True

    return False


def merge_unique_values(*value_groups):
    merged_values = []

    for values in value_groups:
        for value in values:
            if value not in merged_values:
                merged_values.append(value)

    return merged_values


def remove_muusikatoan_blocked_vowels(vowels, consonant, rules):
    blocked_vowels = rules.get("muusikatoan_blocked_vowels", [])
    allowed_blocked_vowels = rules.get(
        "muusikatoan_allowed_blocked_vowels_by_consonant",
        {},
    ).get(consonant, [])

    return [
        vowel
        for vowel in vowels
        if not any(
            blocked_vowel in vowel and blocked_vowel not in allowed_blocked_vowels
            for blocked_vowel in blocked_vowels
        )
    ]


def remove_triisap_blocked_vowels(vowels, rules):
    blocked_vowels = rules.get("triisap_blocked_vowels", [])

    return [
        vowel
        for vowel in vowels
        if not any(blocked_vowel in vowel for blocked_vowel in blocked_vowels)
    ]


# Pick vowel signs using consonant class rules before falling back to general vowels.
def get_vowels_for_consonant(vowel_token, consonant, rules):
    consonant_class = get_consonant_class(consonant, rules)
    muusikatoan_vowels = []
    is_muusikatoan = is_muusikatoan_consonant(consonant, rules)
    triisap_vowels = []
    is_triisap = is_triisap_consonant(consonant, rules)

    if is_muusikatoan:
        muusikatoan_vowels = rules.get("muusikatoan_vowels", {}).get(vowel_token, [])

    if (
        is_triisap
        and consonant not in rules.get("triisap_vowel_excluded_consonants", [])
    ):
        triisap_vowels = rules.get("triisap_vowels", {}).get(vowel_token, [])

    class_rules = rules.get("vowels_by_consonant_class", {}).get(vowel_token)

    if consonant_class and class_rules:
        class_vowels = class_rules.get(consonant_class, [])
        vowels = merge_unique_values(class_vowels, muusikatoan_vowels, triisap_vowels)
    else:
        vowels = merge_unique_values(
            rules.get("vowels", {}).get(vowel_token, []),
            muusikatoan_vowels,
            triisap_vowels,
        )

    if is_muusikatoan:
        vowels = remove_muusikatoan_blocked_vowels(vowels, consonant, rules)

    if is_triisap:
        vowels = remove_triisap_blocked_vowels(vowels, rules)

    return vowels

# Check whether a Roman token can behave as a consonant in generated patterns.
def is_consonant_token(token, rules):
    return (
        token in rules.get("consonants", {})
        or token in rules.get("muusikatoan_consonants", {})
        or token in rules.get("triisap_consonants", {})
    )


def is_cluster_base_token(token, rules):
    return is_consonant_token(token, rules) or token in rules.get("cluster_base_aliases", {})


# Check whether a Roman token can behave as a dependent vowel.
def is_vowel_token(token, rules):
    return (
        token in rules.get("vowels", {})
        or token in rules.get("vowels_by_consonant_class", {})
    )

# Return consonants allowed in initial position, including muusikatoan and triisap forms.
def get_consonants_for_token(token, rules):
    consonants = []

    consonants.extend(rules.get("consonants", {}).get(token, []))
    consonants.extend(rules.get("muusikatoan_consonants", {}).get(token, []))
    consonants.extend(rules.get("triisap_consonants", {}).get(token, []))

    return consonants

# Generate candidates for the C + V pattern, such as consonant plus dependent vowel.
def generate_cv_candidates(tokens, rules):
    if len(tokens) != 2:
        return []

    consonant_token, vowel_token = tokens

    if not is_consonant_token(consonant_token, rules):
        return []

    if not is_vowel_token(vowel_token, rules):
        return []

    candidates = []

    consonants = get_consonants_for_token(consonant_token, rules)

    for consonant in consonants:
        vowel_options = get_vowels_for_consonant(vowel_token, consonant, rules)

        for vowel in vowel_options:
            if vowel == "":
                continue

            candidates.append({
                "khmer": consonant + vowel,
                "source": "rule_cv",
                "tokens": tokens,
                "rule_score": 0.70,
            })

    return candidates

# Generate candidates for the C + V + C pattern with vowel-aware final consonant rules.
def generate_cvc_candidates(tokens, rules):
    if len(tokens) != 3:
        return []

    first_token, vowel_token, final_token = tokens

    if not is_consonant_token(first_token, rules):
        return []

    if not is_vowel_token(vowel_token, rules):
        return []

    if not is_consonant_token(final_token, rules):
        return []

    candidates = []

    first_consonants = get_consonants_for_token(first_token, rules)
    for first_consonant in first_consonants:
        vowel_options = get_vowels_for_consonant(vowel_token, first_consonant, rules)

        for vowel in vowel_options:
            if vowel == "":
                continue

            final_consonants = get_final_consonants_for_token(final_token, rules, vowel)

            for final_consonant in final_consonants:
                candidates.append({
                    "khmer": first_consonant + vowel + final_consonant,
                    "source": "rule_cvc",
                    "tokens": tokens,
                    "rule_score": 0.75,
                })

    return candidates


# Generate C + V + doubled final C as bantoc, such as leakk -> លាក់.
def generate_cvc_bantoc_candidates(tokens, rules):
    if len(tokens) != 4:
        return []

    first_token, vowel_token, final_token, repeated_final_token = tokens

    if final_token != repeated_final_token:
        return []

    if not is_consonant_token(first_token, rules):
        return []

    if not is_vowel_token(vowel_token, rules):
        return []

    if not is_consonant_token(final_token, rules):
        return []

    candidates = []

    for first_consonant in get_consonants_for_token(first_token, rules):
        vowel_options = get_vowels_for_consonant(vowel_token, first_consonant, rules)

        for vowel in vowel_options:
            if vowel == "":
                continue

            final_consonants = get_final_consonants_for_token(final_token, rules, vowel)

            for final_consonant in final_consonants:
                if final_consonant not in BANTOC_FINAL_CONSONANTS:
                    continue

                candidates.append({
                    "khmer": first_consonant + vowel + final_consonant + BANTOC_SIGN,
                    "source": "rule_cvc_bantoc",
                    "tokens": tokens,
                    "rule_score": 0.78,
                })

    return candidates

# Final consonant rules used by CVC, CC, subscript CC, and inherent-vowel patterns.
FINAL_CONSONANTS_BLOCKED = {
    "អ",
    "ខ",
    "គ",
    "ឃ",
    "ឆ",
    "ជ",
    "ឈ",
    "ដ",
    "ឋ",
    "ឌ",
    "ណ",
    "ផ",
    "ព",
    "ភ",
    "ហ",
    "ឡ",
}

FINAL_CONSONANTS_ALLOWED_WITH_U_VOWEL = {"ខ", "ជ", "ដ"}
U_VOWELS_FOR_FINAL_EXCEPTIONS = {"ុ", "ូ"}
FINAL_CONSONANTS_ALLOWED_WITH_AA_VOWEL = {"ភ"}
AA_VOWELS_FOR_FINAL_EXCEPTIONS = {"ា"}
FINAL_CONSONANT_ALIASES = {}

# Return normal consonants allowed in final position; variants are intentionally skipped.
def get_final_consonants_for_token(token, rules, vowel=None):
    allowed_consonants = []
    consonants = list(rules.get("consonants", {}).get(token, []))
    consonants.extend(FINAL_CONSONANT_ALIASES.get(token, []))

    for consonant in consonants:
        if consonant not in FINAL_CONSONANTS_BLOCKED:
            allowed_consonants.append(consonant)
            continue

        if (
            consonant in FINAL_CONSONANTS_ALLOWED_WITH_U_VOWEL
            and vowel in U_VOWELS_FOR_FINAL_EXCEPTIONS
        ):
            allowed_consonants.append(consonant)
            continue

        if (
            consonant in FINAL_CONSONANTS_ALLOWED_WITH_AA_VOWEL
            and vowel in AA_VOWELS_FOR_FINAL_EXCEPTIONS
        ):
            allowed_consonants.append(consonant)

    return allowed_consonants

# Return the coeng sign used to create subscript consonant clusters.
def get_coeng(rules):
    return rules.get("subscript", {}).get("coeng", "្")

# Check whether one consonant is allowed to take another as a subscript.
def is_allowed_subscript_pair(base_consonant, subscript_consonant, rules):
    allowed_rules = rules.get("subscript", {}).get("allowed_following_consonants", {})
    allowed_following = allowed_rules.get(base_consonant)

    if allowed_following is None:
        return True

    return subscript_consonant in allowed_following

# Check every adjacent pair in a subscript cluster.
def is_allowed_subscript_cluster(consonants, rules):
    for index in range(len(consonants) - 1):
        if not is_allowed_subscript_pair(consonants[index], consonants[index + 1], rules):
            return False

    return True

# Generate plain and subscript candidates for the C + C pattern.
def generate_cc_candidates(tokens, rules):
    if len(tokens) != 2:
        return []

    first_token, second_token = tokens

    if not is_cluster_base_token(first_token, rules):
        return []

    if not is_consonant_token(second_token, rules):
        return []

    candidates = []
    coeng = get_coeng(rules)

    # Plain CC: first consonant can use variants, second consonant normal only.
    plain_first_consonants = get_consonants_for_token(first_token, rules)
    plain_second_consonants = get_final_consonants_for_token(second_token, rules)

    for first_consonant in plain_first_consonants:
        for second_consonant in plain_second_consonants:
            candidates.append({
                "khmer": first_consonant + second_consonant,
                "source": "rule_cc_plain",
                "tokens": tokens,
                "rule_score": 0.45,
            })

    # Subscript CC: both consonants are normal; no muusikatoan/triisap variants.
    subscript_first_consonants = get_cluster_base_consonants_for_token(first_token, rules)
    subscript_second_consonants = get_cluster_subscript_consonants_for_token(second_token, rules)

    for first_consonant in subscript_first_consonants:
        for second_consonant in subscript_second_consonants:
            if not is_allowed_subscript_pair(first_consonant, second_consonant, rules):
                continue

            candidates.append({
                "khmer": first_consonant + coeng + second_consonant,
                "source": "rule_cc_subscript",
                "tokens": tokens,
                "rule_score": 0.70,
            })

    return candidates

# Return normal consonants that can start a subscript cluster.
def get_cluster_base_consonants_for_token(token, rules):
    consonants = list(rules.get("consonants", {}).get(token, []))
    consonants.extend(rules.get("cluster_base_aliases", {}).get(token, []))

    return merge_unique_values(consonants)


# Return normal consonants for subscript positions; variants are intentionally skipped.
def get_cluster_subscript_consonants_for_token(token, rules):
    return rules.get("consonants", {}).get(token, [])

# Build C + coeng C + ... cluster text from normal consonants only.
def build_subscript_cluster(consonants, coeng):
    if not consonants:
        return ""

    cluster = consonants[0]

    for consonant in consonants[1:]:
        cluster += coeng + consonant

    return cluster

# Cluster syllables often need the written vowel sign even when class rules return inherent vowel.
def get_vowels_for_cluster(vowel_token, first_consonant, rules):
    vowel_options = get_vowels_for_consonant(vowel_token, first_consonant, rules)

    if any(vowel != "" for vowel in vowel_options):
        return vowel_options

    return rules.get("vowels", {}).get(vowel_token, [])

# Generate C + subscript C + V candidates.
def generate_ccv_candidates(tokens, rules):
    if len(tokens) != 3:
        return []

    first_token, second_token, vowel_token = tokens

    if not is_cluster_base_token(first_token, rules):
        return []

    if not is_consonant_token(second_token, rules):
        return []

    if not is_vowel_token(vowel_token, rules):
        return []

    candidates = []
    coeng = get_coeng(rules)

    for first_consonant in get_cluster_base_consonants_for_token(first_token, rules):
        for second_consonant in get_cluster_subscript_consonants_for_token(second_token, rules):
            if not is_allowed_subscript_pair(first_consonant, second_consonant, rules):
                continue

            cluster = build_subscript_cluster([first_consonant, second_consonant], coeng)
            vowel_options = get_vowels_for_cluster(vowel_token, first_consonant, rules)

            for vowel in vowel_options:
                if vowel == "":
                    continue

                candidates.append({
                    "khmer": cluster + vowel,
                    "source": "rule_ccv_subscript",
                    "tokens": tokens,
                    "rule_score": 0.72,
                })

    return candidates

# Generate C + subscript C + V + final C candidates.
def generate_ccvc_candidates(tokens, rules):
    if len(tokens) != 4:
        return []

    first_token, second_token, vowel_token, final_token = tokens

    if not is_cluster_base_token(first_token, rules):
        return []

    if not is_consonant_token(second_token, rules):
        return []

    if not is_vowel_token(vowel_token, rules):
        return []

    if not is_consonant_token(final_token, rules):
        return []

    candidates = []
    coeng = get_coeng(rules)

    for first_consonant in get_cluster_base_consonants_for_token(first_token, rules):
        for second_consonant in get_cluster_subscript_consonants_for_token(second_token, rules):
            if not is_allowed_subscript_pair(first_consonant, second_consonant, rules):
                continue

            cluster = build_subscript_cluster([first_consonant, second_consonant], coeng)
            vowel_options = get_vowels_for_cluster(vowel_token, first_consonant, rules)

            for vowel in vowel_options:
                if vowel == "":
                    continue

                for final_consonant in get_final_consonants_for_token(final_token, rules, vowel):
                    candidates.append({
                        "khmer": cluster + vowel + final_consonant,
                        "source": "rule_ccvc_subscript",
                        "tokens": tokens,
                        "rule_score": 0.84,
                    })

    return candidates

# Generate C + subscript C + subscript C + V candidates.
def generate_cccv_candidates(tokens, rules):
    if len(tokens) != 4:
        return []

    first_token, second_token, third_token, vowel_token = tokens

    if not is_cluster_base_token(first_token, rules):
        return []

    if not all(is_consonant_token(token, rules) for token in [second_token, third_token]):
        return []

    if not is_vowel_token(vowel_token, rules):
        return []

    candidates = []
    coeng = get_coeng(rules)

    for first_consonant in get_cluster_base_consonants_for_token(first_token, rules):
        for second_consonant in get_cluster_subscript_consonants_for_token(second_token, rules):
            for third_consonant in get_cluster_subscript_consonants_for_token(third_token, rules):
                cluster_consonants = [first_consonant, second_consonant, third_consonant]

                if not is_allowed_subscript_cluster(cluster_consonants, rules):
                    continue

                cluster = build_subscript_cluster(
                    cluster_consonants,
                    coeng,
                )
                vowel_options = get_vowels_for_cluster(vowel_token, first_consonant, rules)

                for vowel in vowel_options:
                    if vowel == "":
                        continue

                    candidates.append({
                        "khmer": cluster + vowel,
                        "source": "rule_cccv_subscript",
                        "tokens": tokens,
                        "rule_score": 0.68,
                    })

    return candidates

# Generate C + subscript C + subscript C + V + final C candidates.
def generate_cccvc_candidates(tokens, rules):
    if len(tokens) != 5:
        return []

    first_token, second_token, third_token, vowel_token, final_token = tokens

    if not is_cluster_base_token(first_token, rules):
        return []

    if not all(is_consonant_token(token, rules) for token in [second_token, third_token]):
        return []

    if not is_vowel_token(vowel_token, rules):
        return []

    if not is_consonant_token(final_token, rules):
        return []

    candidates = []
    coeng = get_coeng(rules)

    for first_consonant in get_cluster_base_consonants_for_token(first_token, rules):
        for second_consonant in get_cluster_subscript_consonants_for_token(second_token, rules):
            for third_consonant in get_cluster_subscript_consonants_for_token(third_token, rules):
                cluster_consonants = [first_consonant, second_consonant, third_consonant]

                if not is_allowed_subscript_cluster(cluster_consonants, rules):
                    continue

                cluster = build_subscript_cluster(
                    cluster_consonants,
                    coeng,
                )
                vowel_options = get_vowels_for_cluster(vowel_token, first_consonant, rules)

                for vowel in vowel_options:
                    if vowel == "":
                        continue

                    for final_consonant in get_final_consonants_for_token(final_token, rules, vowel):
                        candidates.append({
                            "khmer": cluster + vowel + final_consonant,
                            "source": "rule_cccvc_subscript",
                            "tokens": tokens,
                            "rule_score": 0.80,
                        })

    return candidates

# Generate four-consonant subscript cluster candidates.
def generate_cccc_candidates(tokens, rules):
    if len(tokens) != 4:
        return []

    if not is_cluster_base_token(tokens[0], rules):
        return []

    if not all(is_consonant_token(token, rules) for token in tokens[1:]):
        return []

    candidates = []
    coeng = get_coeng(rules)
    consonant_options = [
        get_cluster_base_consonants_for_token(tokens[0], rules),
        *[
            get_cluster_subscript_consonants_for_token(token, rules)
            for token in tokens[1:]
        ],
    ]

    if any(not options for options in consonant_options):
        return []

    for first_consonant in consonant_options[0]:
        for second_consonant in consonant_options[1]:
            for third_consonant in consonant_options[2]:
                for fourth_consonant in consonant_options[3]:
                    cluster_consonants = [
                        first_consonant,
                        second_consonant,
                        third_consonant,
                        fourth_consonant,
                    ]

                    if not is_allowed_subscript_cluster(cluster_consonants, rules):
                        continue

                    cluster = build_subscript_cluster(
                        cluster_consonants,
                        coeng,
                    )
                    candidates.append({
                        "khmer": cluster,
                        "source": "rule_cccc_subscript",
                        "tokens": tokens,
                        "rule_score": 0.55,
                    })

    return candidates

# Roman tokens treated as typed inherent vowels between two consonants.
INHERENT_VOWEL_TOKENS = {"o", "or"}

# Generate C + inherent vowel + C candidates by omitting the explicit vowel sign.
def generate_inherent_vowel_candidates(tokens, rules):
    if len(tokens) != 3:
        return []

    first_token, vowel_token, final_token = tokens

    if vowel_token not in INHERENT_VOWEL_TOKENS:
        return []

    if not is_consonant_token(first_token, rules):
        return []

    if not is_consonant_token(final_token, rules):
        return []

    candidates = []

    first_consonants = get_consonants_for_token(first_token, rules)
    final_consonants = get_final_consonants_for_token(final_token, rules)

    for first_consonant in first_consonants:
        for final_consonant in final_consonants:
            candidates.append({
                "khmer": first_consonant + final_consonant,
                "source": "rule_inherent_vowel",
                "tokens": tokens,
                "rule_score": 0.65,
            })

    return candidates


# Generate special អ inherent candidates where romanized input starts with or + C.
def generate_or_carrier_final_candidates(tokens, rules):
    if len(tokens) != 2:
        return []

    vowel_token, final_token = tokens

    if vowel_token != "or":
        return []

    if not is_consonant_token(final_token, rules):
        return []

    candidates = []

    for final_consonant in get_final_consonants_for_token(final_token, rules):
        candidates.append({
            "khmer": "អ" + final_consonant,
            "source": "rule_or_carrier_final",
            "tokens": tokens,
            "rule_score": 0.62,
        })

    return candidates


# Generate standalone syllables that begin with អ/អ៊, such as ey -> អី.
def generate_independent_vowel_candidates(tokens, rules):
    if len(tokens) != 1:
        return []

    token = tokens[0]
    candidates = []

    for khmer in rules.get("independent_vowels", {}).get(token, []):
        candidates.append({
            "khmer": khmer,
            "source": "rule_independent_vowel",
            "tokens": tokens,
            "rule_score": 0.69,
        })

    return candidates


# Generate independent vowel + final consonant, such as rirs -> ឬស.
def generate_independent_vowel_final_candidates(tokens, rules):
    if len(tokens) != 2:
        return []

    vowel_token, final_token = tokens

    if vowel_token not in rules.get("independent_vowels", {}):
        return []

    if not is_consonant_token(final_token, rules):
        return []

    candidates = []

    for independent_vowel in rules.get("independent_vowels", {}).get(vowel_token, []):
        for final_consonant in get_final_consonants_for_token(final_token, rules):
            candidates.append({
                "khmer": independent_vowel + final_consonant,
                "source": "rule_independent_vowel_final",
                "tokens": tokens,
                "rule_score": 0.76,
            })

    return candidates


def generate_vowel_carrier_candidates(tokens, rules):
    if len(tokens) != 1:
        return []

    token = tokens[0]
    candidates = []
    rule_scores = rules.get("rule_scores", {})
    vowel_carrier_score = rule_scores.get("vowel_carrier", 0.68)
    triisap_vowel_carrier_score = rule_scores.get("triisap_vowel_carrier", 0.66)

    for khmer in rules.get("vowel_carriers", {}).get(token, []):
        candidates.append({
            "khmer": khmer,
            "source": "rule_vowel_carrier",
            "tokens": tokens,
            "rule_score": vowel_carrier_score,
        })

    for khmer in rules.get("triisap_vowel_carriers", {}).get(token, []):
        candidates.append({
            "khmer": khmer,
            "source": "rule_triisap_vowel_carrier",
            "tokens": tokens,
            "rule_score": triisap_vowel_carrier_score,
        })

    return candidates


# Run every single-chunk pattern generator for one tokenization.
def generate_single_chunk_candidates(tokens, rules):
    candidates = []

    candidates.extend(generate_independent_vowel_candidates(tokens, rules))
    candidates.extend(generate_independent_vowel_final_candidates(tokens, rules))
    candidates.extend(generate_vowel_carrier_candidates(tokens, rules))
    candidates.extend(generate_or_carrier_final_candidates(tokens, rules))
    candidates.extend(generate_cv_candidates(tokens, rules))
    candidates.extend(generate_cvc_candidates(tokens, rules))
    candidates.extend(generate_cvc_bantoc_candidates(tokens, rules))
    candidates.extend(generate_cc_candidates(tokens, rules))
    candidates.extend(generate_ccv_candidates(tokens, rules))
    candidates.extend(generate_ccvc_candidates(tokens, rules))
    candidates.extend(generate_cccv_candidates(tokens, rules))
    candidates.extend(generate_cccvc_candidates(tokens, rules))
    candidates.extend(generate_cccc_candidates(tokens, rules))
    candidates.extend(generate_inherent_vowel_candidates(tokens, rules))

    return candidates

# Split longer tokenizations into reusable syllable-sized chunks for sequence generation.
def partition_token_chunks(tokens, max_results=MAX_SEQUENCE_PARTITIONS):
    partitions = []

    def backtrack(index, current_chunks):
        if len(partitions) >= max_results:
            return

        if index == len(tokens):
            if len(current_chunks) > 1:
                partitions.append([chunk.copy() for chunk in current_chunks])
            return

        for chunk_size in [5, 4, 3, 2, 1]:
            next_index = index + chunk_size

            if next_index > len(tokens):
                continue

            current_chunks.append(tokens[index:next_index])
            backtrack(next_index, current_chunks)
            current_chunks.pop()

    backtrack(0, [])
    return partitions

# Combine generated chunks into longer candidates such as CV+CV or CVC+CV.
def combine_chunk_candidates(chunks, rules, original_tokens):
    chunk_candidates = []

    for chunk in chunks:
        candidates = generate_single_chunk_candidates(chunk, rules)

        if not candidates:
            return []

        chunk_candidates.append(candidates)

    combined_candidates = []

    def backtrack(index, selected_candidates):
        if len(combined_candidates) >= MAX_SEQUENCE_COMBINATIONS:
            return

        if index == len(chunk_candidates):
            khmer = "".join(candidate["khmer"] for candidate in selected_candidates)
            score = sum(candidate["rule_score"] for candidate in selected_candidates)
            score = score / len(selected_candidates)
            score = max(score - (len(selected_candidates) - 1) * 0.03, 0)
            score = max(score - len(original_tokens) * 0.03, 0)

            if all(
                candidate["source"] in STRUCTURAL_SEQUENCE_SOURCES
                for candidate in selected_candidates
            ) and not any(
                is_vowel_carrier_like_chunk(candidate)
                for candidate in selected_candidates[1:]
            ):
                score += STRUCTURAL_SEQUENCE_BONUS

            for candidate in selected_candidates:
                if (
                    candidate["source"] == "rule_cvc"
                    and not is_vowel_carrier_like_chunk(candidate)
                ):
                    score += SEQUENCE_CVC_CHUNK_BONUS

            for previous_candidate, current_candidate in zip(
                selected_candidates,
                selected_candidates[1:],
            ):
                if (
                    previous_candidate["source"] in CLOSED_SYLLABLE_SOURCES
                    and current_candidate["source"] in VOWEL_CARRIER_SOURCES
                ):
                    score = max(score - VOWEL_CARRIER_AFTER_CLOSED_CHUNK_PENALTY, 0)

            combined_candidates.append({
                "khmer": khmer,
                "source": "rule_sequence",
                "tokens": original_tokens,
                "chunks": chunks,
                "chunk_sources": [
                    candidate["source"] for candidate in selected_candidates
                ],
                "rule_score": round(score, 4),
            })
            return

        for candidate in chunk_candidates[index]:
            if index > 0 and is_independent_vowel_chunk(candidate):
                continue

            selected_candidates.append(candidate)
            backtrack(index + 1, selected_candidates)
            selected_candidates.pop()

    backtrack(0, [])
    return combined_candidates

# Generate candidates for multi-chunk tokenizations.
def generate_sequence_candidates(tokens, rules):
    if len(tokens) <= 1:
        return []

    candidates = []

    for chunks in partition_token_chunks(tokens):
        candidates.extend(combine_chunk_candidates(chunks, rules, tokens))

    return candidates

# Run every pattern generator for one tokenization and combine their candidates.
def generate_candidates_from_tokens(tokens, rules):
    candidates = []

    candidates.extend(generate_single_chunk_candidates(tokens, rules))
    candidates.extend(generate_sequence_candidates(tokens, rules))

    return candidates

# Add final ranking fields so candidates from different tokenizations can be compared.
def score_candidate(candidate, normalized_text, rules):
    token_bonus = normalized_tokenization_score(candidate["tokens"], normalized_text)
    vowel_bonus = compound_vowel_bonus(candidate["tokens"], rules)
    split_penalty = split_known_token_penalty(candidate["tokens"], rules)
    final_score = candidate["rule_score"] + token_bonus * 0.10 + vowel_bonus - split_penalty

    ranked_candidate = candidate.copy()
    ranked_candidate["tokenization_score"] = token_bonus
    ranked_candidate["compound_vowel_bonus"] = vowel_bonus
    ranked_candidate["split_known_token_penalty"] = split_penalty
    ranked_candidate["final_score"] = round(final_score, 4)

    return ranked_candidate

# Keep only the best candidate for each Khmer output.
def dedupe_candidates(candidates):
    best_by_khmer = {}

    for candidate in candidates:
        khmer = candidate["khmer"]
        current = best_by_khmer.get(khmer)

        if current is None or candidate["final_score"] > current["final_score"]:
            best_by_khmer[khmer] = candidate

    return list(best_by_khmer.values())

# Generate ranked candidates from raw user input across all possible tokenizations.
def generate_ranked_candidates(user_input, rules, max_tokenizations=20, limit=20):
    normalized = normalize_input(user_input)
    patterns = get_all_patterns(rules)
    tokenizations = tokenize_all(normalized, patterns, max_results=max_tokenizations)
    candidates = []

    for tokens in tokenizations:
        for candidate in generate_candidates_from_tokens(tokens, rules):
            candidates.append(score_candidate(candidate, normalized, rules))

    ranked_candidates = dedupe_candidates(candidates)
    ranked_candidates.sort(
        key=lambda candidate: (
            candidate["final_score"],
            candidate["rule_score"],
            candidate["tokenization_score"],
            -len(candidate["tokens"]),
        ),
        reverse=True,
    )

    return ranked_candidates[:limit]


